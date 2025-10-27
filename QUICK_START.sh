#!/bin/bash
# Quick Start Guide for Streamlit Cloud Deployment
# Copy and paste these commands into your Terminal

# ============================================
# STEP 1: Verify Local Repository
# ============================================
echo "Step 1: Checking local repository..."
cd /Users/dragonsun/briefAI
git log --oneline | head -5
git status

# Should show:
# - Several commits with Phase 3 files
# - "working tree clean" (no uncommitted changes)

# ============================================
# STEP 2: Push to GitHub
# ============================================
echo ""
echo "Step 2: Setting up GitHub remote..."
echo "IMPORTANT: Replace YOUR_USERNAME with your actual GitHub username"
read -p "Enter your GitHub username: " github_username

# Add remote
git remote add origin https://github.com/${github_username}/briefAI.git

# Verify remote
echo "Remote configured:"
git remote -v

# Push to GitHub
echo ""
echo "Pushing code to GitHub..."
echo "(You may be prompted for username and Personal Access Token)"
git push -u origin main

# ============================================
# STEP 3: Verify Push
# ============================================
echo ""
echo "Verifying push succeeded..."
git log --oneline | head -3
echo ""
echo "Visit this URL to verify files on GitHub:"
echo "https://github.com/${github_username}/briefAI"
echo ""

# ============================================
# STEP 4: Next Manual Steps
# ============================================
echo "✅ Code pushed to GitHub!"
echo ""
echo "Next steps (manual via web browser):"
echo "1. Go to https://streamlit.io/cloud"
echo "2. Sign in with GitHub"
echo "3. Click 'New app'"
echo "4. Select: Repository = ${github_username}/briefAI"
echo "5. Select: Branch = main"
echo "6. Select: Main file = app.py"
echo "7. Click Deploy"
echo "8. Wait 30-60 seconds for deployment"
echo "9. Go to Streamlit Cloud Settings → Secrets"
echo "10. Add: ANTHROPIC_API_KEY = \"sk-ant-xxxxxxxxxxxxx\""
echo "11. Save and test!"
echo ""
echo "For detailed instructions, see: NEXT_STEPS.md"
