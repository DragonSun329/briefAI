# Cron Automation Setup - BriefAI

## 📅 Schedule (Beijing Time UTC+8)

| Time | Frequency | Task | Status |
|------|-----------|------|--------|
| **6:00 PM** | Every day (Mon-Sun) | Daily article collection | ✅ |
| **10:30 AM** | Monday-Friday | Daily report generation | ✅ |
| **11:00 AM** | Friday only | Final weekly report + archive | ✅ |

## 🔄 Auto Catch-up System

**Automatic catch-up runs when:**
- Computer wakes from sleep
- Computer restarts  
- User logs in
- Every 5 minutes (as backup)

**What it catches up:**
- ✅ Missed 6 PM collections
- ✅ Missed 10:30 AM daily reports
- ✅ Missed 11 AM Friday weekly reports

## 📝 Configuration Files

### 1. Crontab (`crontab -l`)
```
0 18 * * * python3 main.py --defaults --collect >> data/logs/cron.log 2>&1
30 10 * * 1-5 python3 main.py --defaults --finalize >> data/logs/cron.log 2>&1
0 11 * * 5 cd /Users/dragonsun/briefAI && python3 main.py --defaults --finalize --weekly >> data/logs/cron.log 2>&1
```

### 2. LaunchAgent
- **Location:** `~/Library/LaunchAgents/com.dragonsun.briefai.catchup.plist`
- **Status:** Loaded and active
- **Logs:** `data/logs/launchagent.log` and `data/logs/launchagent_error.log`

### 3. Catch-up Script
- **Location:** `scripts/cron_catchup.py`
- **Logs:** `data/logs/cron_catchup.log`
- **State file:** `data/logs/.catchup_state.json`

## 🎯 How It Works

### Normal Operation
1. **6 PM** → Cron executes collection job
2. **10:30 AM next day** → Cron executes daily report (Mon-Fri)
3. **11 AM Friday** → Cron executes weekly report

### If Computer Was Off
1. Computer powers on (any time)
2. LaunchAgent triggers catch-up script
3. Script checks what was missed
4. Script executes missed jobs in order
5. All logged to `cron_catchup.log`

## 📊 Monitoring

### View Logs
```bash
# Main cron log
tail -f data/logs/cron.log

# Catch-up log
tail -f data/logs/cron_catchup.log

# LaunchAgent log
tail -f data/logs/launchagent.log
```

### Check Cron Jobs
```bash
# List active cron jobs
crontab -l

# Check LaunchAgent status
launchctl list | grep briefai

# View last execution times
cat data/logs/.catchup_state.json
```

## ⚙️ Manual Control

### Enable cron (already enabled)
```bash
crontab -r  # Clear
crontab -   # Install new schedule
```

### Enable LaunchAgent (already enabled)
```bash
launchctl load ~/Library/LaunchAgents/com.dragonsun.briefai.catchup.plist
```

### Disable catch-up temporarily
```bash
launchctl unload ~/Library/LaunchAgents/com.dragonsun.briefai.catchup.plist
```

### Re-enable catch-up
```bash
launchctl load ~/Library/LaunchAgents/com.dragonsun.briefai.catchup.plist
```

## ✅ Verification Checklist

- ✅ Crontab entries installed (3 jobs)
- ✅ LaunchAgent loaded and active
- ✅ Catch-up script executable
- ✅ Log directories created
- ✅ All permissions correct

## 🚀 You're All Set!

Your BriefAI automation is now fully configured with automatic catch-up.

**What you need to do:** Simply keep your computer on during scheduled times (or it will auto-catch-up when you turn it on).

**No manual intervention needed!**
