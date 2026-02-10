"""
Notification Channels

Multiple delivery channels for alert notifications:
- Discord webhook
- Email (SMTP)
- Slack webhook
- Windows desktop toast
- File log (always)
"""

import os
import json
import smtplib
import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from loguru import logger

import httpx

from utils.alert_engine import Alert, AlertSeverity, AlertCategory


@dataclass
class NotificationResult:
    """Result of a notification attempt."""
    channel: str
    success: bool
    message: str
    sent_at: datetime = field(default_factory=datetime.now)
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "channel": self.channel,
            "success": self.success,
            "message": self.message,
            "sent_at": self.sent_at.isoformat(),
            "error": self.error,
        }


class NotificationChannel(ABC):
    """Base class for notification channels."""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Channel identifier."""
        pass
    
    @abstractmethod
    async def send(self, alert: Alert) -> NotificationResult:
        """Send notification for an alert."""
        pass
    
    def format_alert(self, alert: Alert) -> Dict[str, Any]:
        """Format alert for display. Override in subclasses."""
        return {
            "title": alert.title,
            "message": alert.message,
            "severity": alert.severity.value,
            "category": alert.category.value,
            "entity": alert.entity_name,
            "created_at": alert.created_at.isoformat(),
        }


class FileLogChannel(NotificationChannel):
    """
    File-based logging channel.
    
    Always active, provides audit trail.
    """
    
    def __init__(self, log_dir: Path = None):
        self.log_dir = log_dir or Path("logs")
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.log_dir / "alerts.log"
    
    @property
    def name(self) -> str:
        return "file"
    
    async def send(self, alert: Alert) -> NotificationResult:
        """Append alert to log file."""
        try:
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "alert_id": alert.id,
                "type": alert.alert_type.value,
                "severity": alert.severity.value,
                "category": alert.category.value,
                "entity_id": alert.entity_id,
                "entity_name": alert.entity_name,
                "title": alert.title,
                "message": alert.message,
                "data": alert.data,
            }
            
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
            
            return NotificationResult(
                channel=self.name,
                success=True,
                message=f"Logged to {self.log_file}",
            )
        
        except Exception as e:
            logger.error(f"File log failed: {e}")
            return NotificationResult(
                channel=self.name,
                success=False,
                message="Failed to write to log",
                error=str(e),
            )


class DiscordWebhookChannel(NotificationChannel):
    """
    Discord webhook notification channel.
    
    Sends rich embeds with color-coded severity.
    """
    
    SEVERITY_COLORS = {
        AlertSeverity.LOW: 0x3498db,       # Blue
        AlertSeverity.MEDIUM: 0xf39c12,    # Orange
        AlertSeverity.HIGH: 0xe74c3c,      # Red
        AlertSeverity.CRITICAL: 0x9b59b6,  # Purple
    }
    
    SEVERITY_EMOJI = {
        AlertSeverity.LOW: "ℹ️",
        AlertSeverity.MEDIUM: "⚠️",
        AlertSeverity.HIGH: "🔴",
        AlertSeverity.CRITICAL: "🚨",
    }
    
    CATEGORY_EMOJI = {
        AlertCategory.OPPORTUNITY: "💡",
        AlertCategory.RISK: "⚠️",
        AlertCategory.WATCH: "👀",
        AlertCategory.INFORMATIONAL: "📋",
    }
    
    def __init__(self, webhook_url: Optional[str] = None):
        self.webhook_url = webhook_url or os.getenv("DISCORD_WEBHOOK_URL")
    
    @property
    def name(self) -> str:
        return "discord"
    
    async def send(self, alert: Alert) -> NotificationResult:
        """Send Discord webhook with embed."""
        if not self.webhook_url:
            return NotificationResult(
                channel=self.name,
                success=False,
                message="No webhook URL configured",
                error="DISCORD_WEBHOOK_URL not set",
            )
        
        try:
            embed = self._build_embed(alert)
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.webhook_url,
                    json={"embeds": [embed]},
                    timeout=10.0,
                )
                response.raise_for_status()
            
            return NotificationResult(
                channel=self.name,
                success=True,
                message="Discord notification sent",
            )
        
        except httpx.HTTPStatusError as e:
            logger.error(f"Discord HTTP error: {e.response.status_code}")
            return NotificationResult(
                channel=self.name,
                success=False,
                message=f"HTTP {e.response.status_code}",
                error=str(e),
            )
        except Exception as e:
            logger.error(f"Discord notification failed: {e}")
            return NotificationResult(
                channel=self.name,
                success=False,
                message="Failed to send notification",
                error=str(e),
            )
    
    def _build_embed(self, alert: Alert) -> Dict[str, Any]:
        """Build Discord embed structure."""
        severity_emoji = self.SEVERITY_EMOJI.get(alert.severity, "")
        category_emoji = self.CATEGORY_EMOJI.get(alert.category, "")
        
        embed = {
            "title": f"{severity_emoji} {alert.title}",
            "description": alert.message,
            "color": self.SEVERITY_COLORS.get(alert.severity, 0x95a5a6),
            "timestamp": alert.created_at.isoformat(),
            "fields": [
                {
                    "name": "Entity",
                    "value": alert.entity_name,
                    "inline": True,
                },
                {
                    "name": "Severity",
                    "value": alert.severity.value.title(),
                    "inline": True,
                },
                {
                    "name": "Category",
                    "value": f"{category_emoji} {alert.category.value.title()}",
                    "inline": True,
                },
            ],
            "footer": {
                "text": f"Alert ID: {alert.id} | Type: {alert.alert_type.value}",
            },
        }
        
        # Add signal data if present
        if alert.data.get("signals"):
            signals_text = "\n".join(
                f"• {k}: {v:.1f}" if isinstance(v, float) else f"• {k}: {v}"
                for k, v in alert.data["signals"].items()
            )
            embed["fields"].append({
                "name": "Signals",
                "value": signals_text[:1024],  # Discord limit
                "inline": False,
            })
        
        return embed


class SlackWebhookChannel(NotificationChannel):
    """
    Slack webhook notification channel.
    
    Sends message blocks with formatting.
    """
    
    SEVERITY_EMOJI = {
        AlertSeverity.LOW: ":information_source:",
        AlertSeverity.MEDIUM: ":warning:",
        AlertSeverity.HIGH: ":red_circle:",
        AlertSeverity.CRITICAL: ":rotating_light:",
    }
    
    def __init__(self, webhook_url: Optional[str] = None):
        self.webhook_url = webhook_url or os.getenv("SLACK_WEBHOOK_URL")
    
    @property
    def name(self) -> str:
        return "slack"
    
    async def send(self, alert: Alert) -> NotificationResult:
        """Send Slack webhook message."""
        if not self.webhook_url:
            return NotificationResult(
                channel=self.name,
                success=False,
                message="No webhook URL configured",
                error="SLACK_WEBHOOK_URL not set",
            )
        
        try:
            blocks = self._build_blocks(alert)
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.webhook_url,
                    json={
                        "text": f"{alert.severity.value.upper()}: {alert.title}",
                        "blocks": blocks,
                    },
                    timeout=10.0,
                )
                response.raise_for_status()
            
            return NotificationResult(
                channel=self.name,
                success=True,
                message="Slack notification sent",
            )
        
        except Exception as e:
            logger.error(f"Slack notification failed: {e}")
            return NotificationResult(
                channel=self.name,
                success=False,
                message="Failed to send notification",
                error=str(e),
            )
    
    def _build_blocks(self, alert: Alert) -> List[Dict[str, Any]]:
        """Build Slack block kit structure."""
        emoji = self.SEVERITY_EMOJI.get(alert.severity, ":bell:")
        
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{emoji} {alert.title}",
                    "emoji": True,
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": alert.message,
                },
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Entity:*\n{alert.entity_name}"},
                    {"type": "mrkdwn", "text": f"*Severity:*\n{alert.severity.value.title()}"},
                    {"type": "mrkdwn", "text": f"*Category:*\n{alert.category.value.title()}"},
                    {"type": "mrkdwn", "text": f"*Type:*\n{alert.alert_type.value}"},
                ],
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"Alert ID: {alert.id} | {alert.created_at.strftime('%Y-%m-%d %H:%M')}",
                    },
                ],
            },
        ]
        
        return blocks


class EmailChannel(NotificationChannel):
    """
    Email notification channel via SMTP.
    
    Sends HTML-formatted email with alert details.
    """
    
    def __init__(
        self,
        smtp_host: Optional[str] = None,
        smtp_port: int = 587,
        username: Optional[str] = None,
        password: Optional[str] = None,
        from_addr: Optional[str] = None,
        to_addrs: Optional[List[str]] = None,
    ):
        self.smtp_host = smtp_host or os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", smtp_port))
        self.username = username or os.getenv("SMTP_USERNAME")
        self.password = password or os.getenv("SMTP_PASSWORD")
        self.from_addr = from_addr or os.getenv("ALERT_FROM_EMAIL", self.username)
        self.to_addrs = to_addrs or os.getenv("ALERT_TO_EMAILS", "").split(",")
        self.to_addrs = [a.strip() for a in self.to_addrs if a.strip()]
    
    @property
    def name(self) -> str:
        return "email"
    
    async def send(self, alert: Alert) -> NotificationResult:
        """Send email notification."""
        if not all([self.smtp_host, self.username, self.password, self.to_addrs]):
            return NotificationResult(
                channel=self.name,
                success=False,
                message="Email not configured",
                error="Missing SMTP configuration",
            )
        
        try:
            msg = self._build_email(alert)
            
            # Run in thread pool since smtplib is synchronous
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._send_email, msg)
            
            return NotificationResult(
                channel=self.name,
                success=True,
                message=f"Email sent to {', '.join(self.to_addrs)}",
            )
        
        except Exception as e:
            logger.error(f"Email notification failed: {e}")
            return NotificationResult(
                channel=self.name,
                success=False,
                message="Failed to send email",
                error=str(e),
            )
    
    def _build_email(self, alert: Alert) -> MIMEMultipart:
        """Build email message."""
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"[{alert.severity.value.upper()}] {alert.title}"
        msg['From'] = self.from_addr
        msg['To'] = ", ".join(self.to_addrs)
        
        # Plain text version
        text = f"""
briefAI Alert

{alert.title}

{alert.message}

Entity: {alert.entity_name}
Severity: {alert.severity.value.title()}
Category: {alert.category.value.title()}
Type: {alert.alert_type.value}

Alert ID: {alert.id}
Created: {alert.created_at.strftime('%Y-%m-%d %H:%M:%S')}
"""
        
        # HTML version
        severity_colors = {
            AlertSeverity.LOW: "#3498db",
            AlertSeverity.MEDIUM: "#f39c12",
            AlertSeverity.HIGH: "#e74c3c",
            AlertSeverity.CRITICAL: "#9b59b6",
        }
        color = severity_colors.get(alert.severity, "#95a5a6")
        
        html = f"""
<html>
<body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
    <div style="background: {color}; color: white; padding: 20px; border-radius: 5px 5px 0 0;">
        <h2 style="margin: 0;">{alert.title}</h2>
    </div>
    <div style="border: 1px solid #ddd; border-top: none; padding: 20px; border-radius: 0 0 5px 5px;">
        <p style="font-size: 16px;">{alert.message}</p>
        
        <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
            <tr>
                <td style="padding: 10px; border: 1px solid #ddd;"><strong>Entity</strong></td>
                <td style="padding: 10px; border: 1px solid #ddd;">{alert.entity_name}</td>
            </tr>
            <tr>
                <td style="padding: 10px; border: 1px solid #ddd;"><strong>Severity</strong></td>
                <td style="padding: 10px; border: 1px solid #ddd;">{alert.severity.value.title()}</td>
            </tr>
            <tr>
                <td style="padding: 10px; border: 1px solid #ddd;"><strong>Category</strong></td>
                <td style="padding: 10px; border: 1px solid #ddd;">{alert.category.value.title()}</td>
            </tr>
            <tr>
                <td style="padding: 10px; border: 1px solid #ddd;"><strong>Type</strong></td>
                <td style="padding: 10px; border: 1px solid #ddd;">{alert.alert_type.value}</td>
            </tr>
        </table>
        
        <p style="color: #666; font-size: 12px;">
            Alert ID: {alert.id}<br>
            Created: {alert.created_at.strftime('%Y-%m-%d %H:%M:%S')}
        </p>
    </div>
</body>
</html>
"""
        
        msg.attach(MIMEText(text, 'plain'))
        msg.attach(MIMEText(html, 'html'))
        
        return msg
    
    def _send_email(self, msg: MIMEMultipart) -> None:
        """Send email via SMTP."""
        with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
            server.starttls()
            server.login(self.username, self.password)
            server.send_message(msg)


class DesktopNotificationChannel(NotificationChannel):
    """
    Windows desktop toast notification channel.
    
    Uses win10toast or plyer for cross-platform support.
    """
    
    def __init__(self):
        self._notifier = None
        self._init_notifier()
    
    def _init_notifier(self):
        """Initialize notification library."""
        try:
            # Try win10toast first (Windows-specific)
            from win10toast import ToastNotifier
            self._notifier = ToastNotifier()
            self._lib = "win10toast"
        except ImportError:
            try:
                # Fall back to plyer (cross-platform)
                from plyer import notification
                self._notifier = notification
                self._lib = "plyer"
            except ImportError:
                self._notifier = None
                self._lib = None
                logger.warning("No desktop notification library available")
    
    @property
    def name(self) -> str:
        return "desktop"
    
    async def send(self, alert: Alert) -> NotificationResult:
        """Show desktop notification."""
        if not self._notifier:
            return NotificationResult(
                channel=self.name,
                success=False,
                message="Desktop notifications not available",
                error="No notification library installed (win10toast or plyer)",
            )
        
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._show_notification, alert)
            
            return NotificationResult(
                channel=self.name,
                success=True,
                message="Desktop notification shown",
            )
        
        except Exception as e:
            logger.error(f"Desktop notification failed: {e}")
            return NotificationResult(
                channel=self.name,
                success=False,
                message="Failed to show notification",
                error=str(e),
            )
    
    def _show_notification(self, alert: Alert) -> None:
        """Show the notification (blocking call)."""
        severity_emoji = {
            AlertSeverity.LOW: "ℹ️",
            AlertSeverity.MEDIUM: "⚠️",
            AlertSeverity.HIGH: "🔴",
            AlertSeverity.CRITICAL: "🚨",
        }
        emoji = severity_emoji.get(alert.severity, "")
        
        title = f"{emoji} briefAI: {alert.entity_name}"
        message = f"{alert.title}\n{alert.message[:200]}"
        
        if self._lib == "win10toast":
            self._notifier.show_toast(
                title=title,
                msg=message,
                duration=10,
                threaded=True,
            )
        elif self._lib == "plyer":
            self._notifier.notify(
                title=title,
                message=message,
                timeout=10,
                app_name="briefAI",
            )


class NotificationManager:
    """
    Manages notification delivery across all channels.
    
    Handles:
    - Channel registration
    - Delivery to specified channels
    - Failure handling and retries
    - Delivery tracking
    """
    
    def __init__(self):
        self.channels: Dict[str, NotificationChannel] = {}
        self._register_default_channels()
    
    def _register_default_channels(self) -> None:
        """Register default notification channels."""
        # File log is always registered
        self.register_channel(FileLogChannel())
        
        # Register optional channels
        if os.getenv("DISCORD_WEBHOOK_URL"):
            self.register_channel(DiscordWebhookChannel())
        
        if os.getenv("SLACK_WEBHOOK_URL"):
            self.register_channel(SlackWebhookChannel())
        
        if os.getenv("SMTP_USERNAME"):
            self.register_channel(EmailChannel())
        
        # Desktop notifications (if library available)
        desktop = DesktopNotificationChannel()
        if desktop._notifier:
            self.register_channel(desktop)
    
    def register_channel(self, channel: NotificationChannel) -> None:
        """Register a notification channel."""
        self.channels[channel.name] = channel
        logger.debug(f"Registered notification channel: {channel.name}")
    
    def unregister_channel(self, name: str) -> None:
        """Unregister a notification channel."""
        if name in self.channels:
            del self.channels[name]
    
    async def notify(
        self, 
        alert: Alert, 
        channels: Optional[List[str]] = None,
    ) -> List[NotificationResult]:
        """
        Send notifications for an alert.
        
        Args:
            alert: Alert to notify about
            channels: Specific channels to use (None = all registered)
        
        Returns:
            List of NotificationResults
        """
        results = []
        
        # Determine which channels to use
        if channels is None:
            target_channels = list(self.channels.values())
        else:
            target_channels = [
                self.channels[name] 
                for name in channels 
                if name in self.channels
            ]
        
        # Always include file log
        if "file" not in [c.name for c in target_channels]:
            if "file" in self.channels:
                target_channels.append(self.channels["file"])
        
        # Send to each channel
        for channel in target_channels:
            try:
                result = await channel.send(alert)
                results.append(result)
                
                if result.success:
                    logger.debug(f"Notification sent via {channel.name}: {alert.title}")
                else:
                    logger.warning(f"Notification failed via {channel.name}: {result.error}")
            
            except Exception as e:
                logger.error(f"Channel {channel.name} threw exception: {e}")
                results.append(NotificationResult(
                    channel=channel.name,
                    success=False,
                    message="Exception during send",
                    error=str(e),
                ))
        
        return results
    
    async def notify_batch(
        self, 
        alerts: List[Alert],
        channels: Optional[List[str]] = None,
    ) -> Dict[str, List[NotificationResult]]:
        """
        Send notifications for multiple alerts.
        
        Args:
            alerts: List of alerts
            channels: Channels to use
        
        Returns:
            Dict mapping alert_id to results
        """
        results = {}
        
        for alert in alerts:
            alert_results = await self.notify(alert, channels)
            results[alert.id] = alert_results
        
        return results
    
    def get_available_channels(self) -> List[str]:
        """Get list of available channel names."""
        return list(self.channels.keys())
    
    def get_channel_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all channels."""
        status = {}
        
        for name, channel in self.channels.items():
            status[name] = {
                "available": True,
                "type": type(channel).__name__,
            }
        
        return status


# Convenience function for synchronous code
def send_notification(
    alert: Alert,
    channels: Optional[List[str]] = None,
) -> List[NotificationResult]:
    """
    Synchronous wrapper for sending notifications.
    
    Args:
        alert: Alert to notify about
        channels: Specific channels to use
    
    Returns:
        List of NotificationResults
    """
    manager = NotificationManager()
    
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    return loop.run_until_complete(manager.notify(alert, channels))


if __name__ == "__main__":
    # Test notifications
    from utils.alert_engine import AlertType
    
    test_alert = Alert(
        id="test-001",
        alert_type=AlertType.THRESHOLD,
        entity_id="openai",
        entity_name="OpenAI",
        severity=AlertSeverity.HIGH,
        title="OpenAI: TMS Above Threshold",
        message="Technical Momentum Signal is 92, significantly above the threshold of 80. Strong developer adoption detected.",
        data={"signals": {"tms": 92, "ccs": 45, "nas": 78}},
        created_at=datetime.now(),
        category=AlertCategory.OPPORTUNITY,
    )
    
    # Test file logging
    results = send_notification(test_alert, channels=["file"])
    
    print("Notification Results:")
    for result in results:
        status = "✓" if result.success else "✗"
        print(f"  {status} {result.channel}: {result.message}")
