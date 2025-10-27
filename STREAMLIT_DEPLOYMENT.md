# Streamlit Cloud Deployment Guide

This guide walks you through deploying briefAI to Streamlit Cloud for easy access by your CEO.

## Overview

The deployment consists of:
1. **GitHub Repository** - Stores code and reports (Streamlit Cloud pulls from here)
2. **Streamlit Cloud** - Hosts the web application (free tier available)
3. **Local Mac** - Generates reports weekly and pushes to GitHub

**Architecture:**
```
Local Mac (weekly scripts)
    ↓ (generates reports)
GitHub Repository (stores reports & code)
    ↓ (pulls latest)
Streamlit Cloud (serves web app to CEO)
    ↓ (user accesses)
CEO Browser (reads reports & searches)
```

## Step 1: Create GitHub Repository

### 1a. Create GitHub Account (if needed)
- Go to https://github.com/signup
- Create a free account
- Verify email

### 1b. Create New Repository on GitHub

1. Go to https://github.com/new
2. Fill in:
   - **Repository name**: `briefAI`
   - **Description**: "AI Industry Weekly Briefing for CEO"
   - **Visibility**: Choose **Private** (only you and invited team can see)
   - **Initialize with**: Leave unchecked (we'll push existing code)
3. Click "Create repository"

After creation, GitHub will show you commands like:
```bash
git remote add origin https://github.com/YOUR_USERNAME/briefAI.git
git branch -M main
git push -u origin main
```

### 1c. Configure Local Repository

On your Mac, go to the briefAI directory:

```bash
cd /Users/dragonsun/briefAI

# Add the GitHub repository as remote
# Replace YOUR_USERNAME with your GitHub username
git remote add origin https://github.com/YOUR_USERNAME/briefAI.git

# Rename branch to main (if needed)
git branch -M main

# Push all commits to GitHub
git push -u origin main
```

**⚠️ Important**: If you get authentication errors:

Option A: **Use GitHub Token (Recommended)**
1. Go to https://github.com/settings/tokens/new
2. Create new token with:
   - Expiration: 90 days (can be renewed)
   - Scopes: Check `repo` (full control of private repositories)
3. Copy the token
4. When pushing, use the token as password:
   ```bash
   git push -u origin main
   # Username: your_username
   # Password: paste_the_token_here
   ```

Option B: **Set up SSH Keys (Better for automation)**
1. Generate SSH key:
   ```bash
   ssh-keygen -t ed25519 -C "your_email@example.com"
   # Press Enter for all prompts to use defaults
   ```
2. Add to GitHub:
   - Go to https://github.com/settings/keys
   - Click "New SSH key"
   - Copy contents of `~/.ssh/id_ed25519.pub`
   - Paste and save
3. Update local repository to use SSH:
   ```bash
   git remote set-url origin git@github.com:YOUR_USERNAME/briefAI.git
   git push -u origin main
   ```

### 1d. Verify Push

Check that your code is on GitHub:
```bash
git log --oneline
# Should show commits like:
# 96d9f3d Add Streamlit Cloud deployment setup: app.py, config, and GitHub auto-push
# 0a1b2c3 Initial commit with all briefAI code
```

Visit https://github.com/YOUR_USERNAME/briefAI to verify files are there.

## Step 2: Deploy to Streamlit Cloud

### 2a. Connect GitHub to Streamlit Cloud

1. Go to https://streamlit.io/cloud
2. Click "Sign up" or "Sign in"
3. Sign in with your GitHub account
4. Authorize Streamlit to access your GitHub repositories

### 2b. Create New App

1. Click "New app"
2. Fill in:
   - **Repository**: YOUR_USERNAME/briefAI
   - **Branch**: main
   - **Main file path**: app.py
3. Click "Deploy"

Streamlit will:
- Pull your code from GitHub
- Install dependencies from `requirements.txt`
- Run `app.py`
- Assign you a URL like: https://YOUR_USERNAME-briefai-xyz123.streamlit.app

### 2c. Add Secrets

**IMPORTANT**: Your API key must NEVER be committed to GitHub. Instead, store it in Streamlit Cloud Secrets:

1. In Streamlit Cloud app dashboard, click "Settings" (gear icon, top right)
2. Go to "Secrets"
3. Paste your API key:
   ```
   ANTHROPIC_API_KEY = "sk-ant-xxxxxxxxxxxxx"
   ```
4. Click "Save"

The app will restart and read the secret from Streamlit Cloud's secure storage (not from GitHub).

### 2d. Verify App Works

1. Wait for deployment to complete (usually 30-60 seconds)
2. Visit the generated URL
3. You should see:
   - "📊 AI Industry Weekly Briefing" header
   - Latest report in tabs
   - Search sidebar on left
   - Article cards with entities

If you see errors, check the "Logs" tab in Streamlit Cloud dashboard.

## Step 3: Configure Weekly Generation

Now set up automatic weekly report generation on your Mac:

### 3a. Update Cron Schedules

Edit your cron jobs to match when you want reports generated:

```bash
# Edit your crontab
crontab -e

# Example: Collection on Friday at 10 AM, finalization at 11 AM
0 10 * * 5 cd /Users/dragonsun/briefAI && python main.py --defaults --collect >> data/logs/cron.log 2>&1
0 11 * * 5 cd /Users/dragonsun/briefAI && python main.py --defaults --finalize --weekly >> data/logs/cron.log 2>&1
```

### 3b. Verify Git SSH Authentication

For the auto-push to work reliably, use SSH keys instead of password:

```bash
# Test SSH connection
ssh -T git@github.com
# Should say: "Hi YOUR_USERNAME! You've successfully authenticated..."

# Update remote if using HTTPS
git remote set-url origin git@github.com:YOUR_USERNAME/briefAI.git

# Test push manually
git push origin main
# Should succeed without prompting for password
```

## Step 4: Share with CEO

Once deployed, share the Streamlit URL with your CEO:

**Example message:**
```
Hi [CEO name],

Your weekly AI briefing is ready! Access it here:
https://YOUR_USERNAME-briefai-xyz123.streamlit.app

Features:
- 📰 View latest AI news briefing
- 🔍 Search by company/model/topic
- 📥 Download report as markdown

Reports update every Friday at 11 AM.
```

### Optional: Add as Bookmark

- Bookmark the URL in browser for quick access
- Add to phone home screen (iOS: Share → Add to Home Screen)

## Troubleshooting

### "App failed to initialize"
- Check Streamlit Cloud logs: Click "Logs" tab
- Verify `requirements.txt` is correct
- Check that `.streamlit/secrets.toml` is in `.gitignore` (never committed)

### "API Key not found"
- Verify you added `ANTHROPIC_API_KEY` in Streamlit Cloud Secrets
- Secrets are environment variables, not read from .env file
- Secrets format must be exact: `ANTHROPIC_API_KEY = "sk-ant-..."`

### "No reports available yet"
- Verify weekly script ran on your Mac
- Check Mac logs: `tail -f /Users/dragonsun/briefAI/data/logs/cron.log`
- Verify reports exist: `ls -la /Users/dragonsun/briefAI/data/reports/`
- Push to GitHub: `git push origin main`
- Refresh Streamlit app (hit R or reload browser)

### Reports not updating in Streamlit
- Streamlit caches data with 1-hour TTL
- Manually refresh: Press R or reload browser
- Or change file modification time to force reload

### Too many users (upgrade needed)
- Streamlit free tier: ~5 simultaneous users
- If team grows: Go to Streamlit Cloud dashboard → "Settings" → "Upgrade plan"
- Pro plan: $15/month for more resources

## Maintenance

### Weekly Checklist
- [ ] Check CEO received briefing notification
- [ ] Verify Streamlit app loaded successfully
- [ ] Check logs for any errors: `tail data/logs/cron.log`

### Monthly Tasks
- [ ] Renew GitHub token if using (30-90 day expiration)
- [ ] Check Streamlit resource usage in dashboard
- [ ] Update `requirements.txt` if dependencies need upgrade

### Updating Code
When you improve the system:

```bash
cd /Users/dragonsun/briefAI

# Make your changes...
# Test locally...

# Commit and push
git add .
git commit -m "Description of changes"
git push origin main

# Streamlit Cloud will auto-redeploy from GitHub
# (takes 30-60 seconds)
```

## Architecture Summary

```
┌─────────────────────────────────────────────────────┐
│  Local Mac (dragonsun's computer)                   │
│  ├─ main.py (weekly cron scripts)                   │
│  ├─ data/reports/ (generated markdown)              │
│  ├─ data/cache/ (cached articles)                   │
│  └─ Git repository (local)                          │
└────────────────┬────────────────────────────────────┘
                 │ git push
                 ↓
┌─────────────────────────────────────────────────────┐
│  GitHub Repository (private)                        │
│  ├─ Source code                                     │
│  ├─ data/reports/ (latest reports)                  │
│  ├─ data/cache/ (cached data)                       │
│  └─ .streamlit/config.toml                          │
└────────────────┬────────────────────────────────────┘
                 │ git pull (auto)
                 ↓
┌─────────────────────────────────────────────────────┐
│  Streamlit Cloud (web server)                       │
│  ├─ app.py (web interface)                          │
│  ├─ Pulled from GitHub                              │
│  ├─ Secrets: ANTHROPIC_API_KEY (secure)             │
│  └─ URL: https://...streamlit.app                   │
└────────────────┬────────────────────────────────────┘
                 │ HTTP/HTTPS
                 ↓
┌─────────────────────────────────────────────────────┐
│  CEO's Browser                                      │
│  └─ Views briefing, searches articles               │
└─────────────────────────────────────────────────────┘
```

## Next Steps

1. ✅ Code is ready (app.py, main.py with auto-push)
2. Create GitHub account and repository
3. Push local code to GitHub
4. Deploy to Streamlit Cloud
5. Add API key in Streamlit Cloud Secrets
6. Share URL with CEO
7. Test weekly workflow

Good luck! 🚀
