"""
Alert Monitor Daemon

Background service that:
- Runs every 5 minutes (configurable)
- Checks all active rules against current signals
- Generates alerts when conditions are met
- Sends notifications via configured channels
- Can be run as Windows service or standalone

Usage:
    python scripts/alert_monitor.py          # Run once
    python scripts/alert_monitor.py --daemon # Run as daemon
    python scripts/alert_monitor.py --install-service  # Install as Windows service
"""

import argparse
import asyncio
import signal
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional
from loguru import logger

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.alert_engine import (
    AlertEngine, Alert, AlertType, AlertSeverity, AlertCategory,
    generate_threshold_alert, generate_divergence_alert,
    generate_momentum_alert, generate_event_alert, generate_anomaly_alert
)
from utils.alert_rules import AlertRulesEngine, AlertRule
from utils.notifications import NotificationManager, send_notification
from utils.signal_store import SignalStore
from utils.divergence_detector import DivergenceDetector, PriceFundamentalDivergenceDetector
from utils.event_store import BusinessEventStore as EventStore


class AlertMonitor:
    """
    Background alert monitoring service.
    
    Periodically checks signal data against rules and generates alerts.
    """
    
    DEFAULT_INTERVAL_SECONDS = 300  # 5 minutes
    
    def __init__(
        self,
        interval_seconds: int = DEFAULT_INTERVAL_SECONDS,
        db_path: Optional[Path] = None,
    ):
        """
        Initialize alert monitor.
        
        Args:
            interval_seconds: Check interval
            db_path: Path to alerts database
        """
        self.interval = interval_seconds
        self.running = False
        self.last_run: Optional[datetime] = None
        self.run_count = 0
        
        # Initialize components
        self.alert_engine = AlertEngine(db_path=db_path)
        self.rules_engine = AlertRulesEngine(alert_engine=self.alert_engine)
        self.notification_manager = NotificationManager()
        self.signal_store = SignalStore()
        self.divergence_detector = DivergenceDetector()
        self.pf_divergence_detector = PriceFundamentalDivergenceDetector()
        
        # Try to initialize event store
        try:
            self.event_store = EventStore()
        except Exception:
            self.event_store = None
            logger.warning("Event store not available")
        
        logger.info(f"AlertMonitor initialized (interval: {interval_seconds}s)")
    
    async def run_once(self) -> Dict[str, Any]:
        """
        Run a single monitoring cycle.
        
        Returns:
            Dict with run statistics
        """
        start_time = datetime.now()
        stats = {
            "run_at": start_time.isoformat(),
            "entities_checked": 0,
            "rules_evaluated": 0,
            "alerts_generated": 0,
            "notifications_sent": 0,
            "errors": [],
        }
        
        try:
            # Get all entities with recent profiles
            profiles = self._get_recent_profiles()
            stats["entities_checked"] = len(profiles)
            
            logger.info(f"Checking {len(profiles)} entities against {len(self.rules_engine.rules)} rules")
            
            all_alerts = []
            
            # Check rules for each entity
            for profile in profiles:
                try:
                    alerts = await self._check_entity(profile)
                    all_alerts.extend(alerts)
                except Exception as e:
                    logger.error(f"Error checking entity {profile.get('entity_id')}: {e}")
                    stats["errors"].append(str(e))
            
            # Check for divergences
            divergence_alerts = await self._check_divergences(profiles)
            all_alerts.extend(divergence_alerts)
            
            # Check for new events
            event_alerts = await self._check_events()
            all_alerts.extend(event_alerts)
            
            stats["alerts_generated"] = len(all_alerts)
            stats["rules_evaluated"] = stats["entities_checked"] * len(self.rules_engine.rules)
            
            # Send notifications
            for alert in all_alerts:
                try:
                    # Get channels from rule
                    rule = self.rules_engine.get_rule(alert.rule_id) if alert.rule_id else None
                    channels = rule.channels if rule else ["file"]
                    
                    results = await self.notification_manager.notify(alert, channels)
                    
                    # Track notifications
                    for result in results:
                        if result.success:
                            stats["notifications_sent"] += 1
                            self.alert_engine.mark_notification_sent(alert.id, result.channel)
                
                except Exception as e:
                    logger.error(f"Error sending notification for alert {alert.id}: {e}")
                    stats["errors"].append(str(e))
            
            # Cleanup expired alerts
            expired = self.alert_engine.expire_old_alerts()
            stats["alerts_expired"] = expired
            
            self.last_run = start_time
            self.run_count += 1
            
            elapsed = (datetime.now() - start_time).total_seconds()
            stats["elapsed_seconds"] = elapsed
            
            logger.info(
                f"Monitor cycle complete: {stats['alerts_generated']} alerts, "
                f"{stats['notifications_sent']} notifications, {elapsed:.1f}s"
            )
        
        except Exception as e:
            logger.error(f"Monitor cycle failed: {e}")
            stats["errors"].append(str(e))
        
        return stats
    
    def _get_recent_profiles(self) -> List[Dict[str, Any]]:
        """Get recent signal profiles for all entities."""
        profiles = []
        
        try:
            # Get top profiles by composite score
            top_profiles = self.signal_store.get_top_profiles(limit=100)
            
            for profile in top_profiles:
                # Build signals dict
                signals = {
                    "tms": profile.technical_score or 0,
                    "ccs": profile.financial_score or 0,
                    "nas": profile.media_score or 0,
                    "eis": profile.company_score or 0,
                    "pms": profile.product_score or 0,
                    "composite_score": profile.composite_score,
                    "momentum_7d": profile.momentum_7d or 0,
                    "momentum_30d": profile.momentum_30d or 0,
                }
                
                # Calculate divergence score
                scores = [s for s in [
                    profile.technical_score,
                    profile.financial_score,
                    profile.media_score,
                    profile.company_score,
                    profile.product_score,
                ] if s is not None]
                
                if len(scores) >= 2:
                    max_s = max(scores)
                    min_s = min(scores)
                    signals["divergence_score"] = (max_s - min_s) / 100.0
                else:
                    signals["divergence_score"] = 0
                
                profiles.append({
                    "entity_id": profile.entity_id,
                    "entity_name": profile.entity_name,
                    "entity_type": profile.entity_type.value,
                    **signals,
                    "_profile": profile,  # Keep reference for divergence detection
                })
        
        except Exception as e:
            logger.error(f"Failed to get profiles: {e}")
        
        return profiles
    
    async def _check_entity(self, profile: Dict[str, Any]) -> List[Alert]:
        """Check all rules against an entity's signals."""
        entity_id = profile["entity_id"]
        entity_name = profile["entity_name"]
        
        # Extract signals (exclude metadata)
        signals = {
            k: v for k, v in profile.items()
            if k not in ("entity_id", "entity_name", "entity_type", "_profile")
            and isinstance(v, (int, float))
        }
        
        # Evaluate rules
        alerts = self.rules_engine.evaluate_entity(entity_id, entity_name, signals)
        
        return alerts
    
    async def _check_divergences(self, profiles: List[Dict[str, Any]]) -> List[Alert]:
        """Check for signal divergences across profiles."""
        alerts = []
        
        for profile in profiles:
            if "_profile" not in profile:
                continue
            
            signal_profile = profile["_profile"]
            
            # Detect divergences
            divergences = self.divergence_detector.detect_divergences(signal_profile)
            
            for div in divergences:
                # Create alert for significant divergences
                if div.divergence_magnitude >= 30:
                    alert = generate_divergence_alert(
                        engine=self.alert_engine,
                        entity_id=div.entity_id,
                        entity_name=div.entity_name,
                        high_signal=div.high_signal_category.value,
                        high_value=div.high_signal_score,
                        low_signal=div.low_signal_category.value,
                        low_value=div.low_signal_score,
                        interpretation=div.interpretation_rationale,
                    )
                    if alert:
                        alerts.append(alert)
        
        return alerts
    
    async def _check_events(self) -> List[Alert]:
        """Check for new business events."""
        alerts = []
        
        if not self.event_store:
            return alerts
        
        try:
            # Get events from last check interval
            hours_back = 24
            if self.last_run:
                hours_back = max(1, int((datetime.now() - self.last_run).total_seconds() / 3600))
            
            recent_events = self.event_store.get_recent_events(days=max(1, hours_back // 24), limit=50)
            
            for event in recent_events:
                alert = generate_event_alert(
                    engine=self.alert_engine,
                    entity_id=event.entity_id,
                    entity_name=event.entity_name,
                    event_type=event.event_type.value,
                    event_title=event.headline,
                    event_details=event.details if hasattr(event, 'details') else {},
                )
                if alert:
                    alerts.append(alert)
        
        except Exception as e:
            logger.error(f"Failed to check events: {e}")
        
        return alerts
    
    async def run_daemon(self):
        """Run as continuous daemon."""
        self.running = True
        logger.info(f"Starting alert monitor daemon (interval: {self.interval}s)")
        
        # Setup signal handlers
        def handle_shutdown(signum, frame):
            logger.info("Shutdown signal received")
            self.running = False
        
        signal.signal(signal.SIGINT, handle_shutdown)
        signal.signal(signal.SIGTERM, handle_shutdown)
        
        while self.running:
            try:
                await self.run_once()
            except Exception as e:
                logger.error(f"Daemon cycle error: {e}")
            
            # Wait for next interval
            if self.running:
                await asyncio.sleep(self.interval)
        
        logger.info("Alert monitor daemon stopped")
    
    def get_status(self) -> Dict[str, Any]:
        """Get monitor status."""
        return {
            "running": self.running,
            "interval_seconds": self.interval,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "run_count": self.run_count,
            "rules_count": len(self.rules_engine.rules),
            "channels": self.notification_manager.get_available_channels(),
        }


def run_windows_service():
    """Install and run as Windows service."""
    try:
        import win32serviceutil
        import win32service
        import win32event
        import servicemanager
        
        class AlertMonitorService(win32serviceutil.ServiceFramework):
            _svc_name_ = "briefAI_AlertMonitor"
            _svc_display_name_ = "briefAI Alert Monitor"
            _svc_description_ = "Monitors signals and sends alerts for briefAI"
            
            def __init__(self, args):
                win32serviceutil.ServiceFramework.__init__(self, args)
                self.stop_event = win32event.CreateEvent(None, 0, 0, None)
                self.monitor = AlertMonitor()
            
            def SvcStop(self):
                self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
                self.monitor.running = False
                win32event.SetEvent(self.stop_event)
            
            def SvcDoRun(self):
                servicemanager.LogMsg(
                    servicemanager.EVENTLOG_INFORMATION_TYPE,
                    servicemanager.PYS_SERVICE_STARTED,
                    (self._svc_name_, '')
                )
                asyncio.run(self.monitor.run_daemon())
        
        return AlertMonitorService
    
    except ImportError:
        logger.error("pywin32 not installed. Cannot run as Windows service.")
        return None


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="briefAI Alert Monitor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python alert_monitor.py                  # Run single check
    python alert_monitor.py --daemon         # Run as daemon
    python alert_monitor.py --interval 60    # Custom interval (seconds)
    python alert_monitor.py --install        # Install Windows service
    python alert_monitor.py --uninstall      # Remove Windows service
        """
    )
    
    parser.add_argument(
        "--daemon", "-d",
        action="store_true",
        help="Run as continuous daemon"
    )
    
    parser.add_argument(
        "--interval", "-i",
        type=int,
        default=300,
        help="Check interval in seconds (default: 300)"
    )
    
    parser.add_argument(
        "--install",
        action="store_true",
        help="Install as Windows service"
    )
    
    parser.add_argument(
        "--uninstall",
        action="store_true",
        help="Uninstall Windows service"
    )
    
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose logging"
    )
    
    args = parser.parse_args()
    
    # Configure logging
    if args.verbose:
        logger.remove()
        logger.add(sys.stderr, level="DEBUG")
    
    # Handle Windows service commands
    if args.install or args.uninstall:
        try:
            import win32serviceutil
            ServiceClass = run_windows_service()
            
            if ServiceClass:
                if args.install:
                    win32serviceutil.HandleCommandLine(ServiceClass, argv=['', 'install'])
                    logger.info("Windows service installed")
                elif args.uninstall:
                    win32serviceutil.HandleCommandLine(ServiceClass, argv=['', 'remove'])
                    logger.info("Windows service removed")
        except ImportError:
            logger.error("pywin32 required for Windows service. Install with: pip install pywin32")
        return
    
    # Create monitor
    monitor = AlertMonitor(interval_seconds=args.interval)
    
    if args.daemon:
        # Run as daemon
        asyncio.run(monitor.run_daemon())
    else:
        # Single run
        stats = asyncio.run(monitor.run_once())
        
        print("\n" + "=" * 50)
        print("Alert Monitor - Run Complete")
        print("=" * 50)
        print(f"Time: {stats['run_at']}")
        print(f"Entities checked: {stats['entities_checked']}")
        print(f"Rules evaluated: {stats['rules_evaluated']}")
        print(f"Alerts generated: {stats['alerts_generated']}")
        print(f"Notifications sent: {stats['notifications_sent']}")
        print(f"Elapsed: {stats.get('elapsed_seconds', 0):.1f}s")
        
        if stats.get('errors'):
            print(f"Errors: {len(stats['errors'])}")
            for err in stats['errors'][:5]:
                print(f"  - {err}")
        
        print("=" * 50)


if __name__ == "__main__":
    main()
