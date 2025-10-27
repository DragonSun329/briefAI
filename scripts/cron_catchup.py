#!/usr/bin/env python3
"""
Cron Catch-up Script - Automatically runs missed cron jobs

Triggered by LaunchAgent when:
- Computer wakes from sleep
- Computer restarts
- User logs in

Checks which scheduled jobs were missed and executes them in order.
"""

import json
import subprocess
import os
from pathlib import Path
from datetime import datetime, timedelta
from loguru import logger

# Setup logging
log_dir = Path("/Users/dragonsun/briefAI/data/logs")
log_dir.mkdir(parents=True, exist_ok=True)
logger.remove()
logger.add(
    log_dir / "cron_catchup.log",
    rotation="10 MB",
    level="INFO",
    format="<level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>"
)

# Project directory
PROJECT_DIR = Path("/Users/dragonsun/briefAI")
CATCHUP_STATE_FILE = log_dir / ".catchup_state.json"


def load_catchup_state():
    """Load last successful execution times"""
    if CATCHUP_STATE_FILE.exists():
        with open(CATCHUP_STATE_FILE) as f:
            return json.load(f)
    return {
        "last_collection": None,  # Friday 6 PM collection
        "last_weekly_report": None,  # Friday 11 PM report
        "last_check": None
    }


def save_catchup_state(state):
    """Save execution state"""
    with open(CATCHUP_STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)


def get_scheduled_times():
    """Get Beijing time scheduled execution times for Friday only"""
    now = datetime.now()

    # Calculate Friday of this week (0=Monday, 4=Friday)
    days_until_friday = (4 - now.weekday()) % 7
    if days_until_friday == 0 and now.hour >= 11:
        # If today is Friday and we're past 11 AM, use next Friday
        days_until_friday = 7

    friday = now + timedelta(days=days_until_friday)

    return {
        "collection": friday.replace(hour=10, minute=0, second=0, microsecond=0),  # Friday 10 AM
        "weekly_report": friday.replace(hour=11, minute=0, second=0, microsecond=0)  # Friday 11 AM
    }


def should_run_collection(state, scheduled_times):
    """Check if Friday weekly collection job was missed"""
    # Only on Fridays
    if datetime.now().weekday() != 4:
        return False

    last_collection = state.get("last_collection")
    scheduled_time = scheduled_times["collection"]

    if last_collection is None:
        # First time, check if we're past collection time
        return datetime.now() > scheduled_time

    last_run = datetime.fromisoformat(last_collection)
    # Run if more than 7 days since last collection and we're past collection time
    return (
        (datetime.now() - last_run).total_seconds() > 604800 and  # 7 days
        datetime.now() > scheduled_time
    )


def should_run_weekly_report(state, scheduled_times):
    """Check if Friday weekly report job was missed"""
    # Only on Fridays
    if datetime.now().weekday() != 4:
        return False

    last_weekly = state.get("last_weekly_report")
    scheduled_time = scheduled_times["weekly_report"]

    if last_weekly is None:
        return datetime.now() > scheduled_time

    last_run = datetime.fromisoformat(last_weekly)
    # Run if more than 7 days since last weekly report and we're past report time
    return (
        (datetime.now() - last_run).total_seconds() > 604800 and  # 7 days
        datetime.now() > scheduled_time
    )


def run_command(cmd, name):
    """Execute a cron command and return success status"""
    logger.info(f"[CATCHUP] Running: {name}")
    logger.info(f"[CATCHUP] Command: {cmd}")

    try:
        result = subprocess.run(
            cmd,
            shell=True,
            cwd=PROJECT_DIR,
            capture_output=True,
            text=True,
            timeout=1800  # 30 minute timeout
        )

        if result.returncode == 0:
            logger.info(f"[CATCHUP] ✅ {name} completed successfully")
            return True
        else:
            logger.error(f"[CATCHUP] ❌ {name} failed with code {result.returncode}")
            logger.error(f"[CATCHUP] stderr: {result.stderr}")
            return False

    except subprocess.TimeoutExpired:
        logger.error(f"[CATCHUP] ❌ {name} timed out (30 minutes)")
        return False
    except Exception as e:
        logger.error(f"[CATCHUP] ❌ {name} error: {e}")
        return False


def main():
    """Main catch-up logic"""
    logger.info("="*80)
    logger.info("[CATCHUP] Cron Catch-up Check Started")
    logger.info(f"[CATCHUP] Current time: {datetime.now().isoformat()}")

    state = load_catchup_state()
    scheduled_times = get_scheduled_times()

    # Check and run collection if missed (Friday only)
    if should_run_collection(state, scheduled_times):
        logger.info("[CATCHUP] Weekly collection job was missed - running now")
        cmd = "python3 main.py --defaults --collect >> data/logs/cron.log 2>&1"
        if run_command(cmd, "Weekly Collection (Catch-up)"):
            state["last_collection"] = datetime.now().isoformat()

    # Check and run weekly report if missed (Friday only)
    if should_run_weekly_report(state, scheduled_times):
        logger.info("[CATCHUP] Weekly report job was missed - running now")
        cmd = "python3 main.py --defaults --finalize --weekly >> data/logs/cron.log 2>&1"
        if run_command(cmd, "Weekly Report (Catch-up)"):
            state["last_weekly_report"] = datetime.now().isoformat()

    # Update last check time
    state["last_check"] = datetime.now().isoformat()
    save_catchup_state(state)

    logger.info("[CATCHUP] Cron Catch-up Check Completed")
    logger.info("="*80)


if __name__ == "__main__":
    main()
