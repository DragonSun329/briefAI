#!/bin/bash
#
# Cron Job Setup Script for AI Industry Weekly Briefing Agent
#
# This script sets up automated cron jobs for:
# 1. Daily article collection at 23:59 (11:59 PM)
# 2. Daily report generation at 06:00 (6:00 AM)
# 3. Weekly final report at 08:00 (8:00 AM) on Friday
# 4. Archive daily reports at 09:00 (9:00 AM) on Friday
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get the script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

echo -e "${YELLOW}========================================${NC}"
echo -e "${YELLOW}AI Briefing Agent - Cron Setup${NC}"
echo -e "${YELLOW}========================================${NC}"
echo ""

# Check if running on macOS or Linux
if [[ "$OSTYPE" == "darwin"* ]]; then
    CRON_COMMAND="crontab"
    echo -e "${GREEN}Detected macOS${NC}"
else
    CRON_COMMAND="crontab"
    echo -e "${GREEN}Detected Linux${NC}"
fi

# Check if crontab is available
if ! command -v $CRON_COMMAND &> /dev/null; then
    echo -e "${RED}Error: crontab not found. Please install cron/crond first.${NC}"
    exit 1
fi

echo -e "${GREEN}✓ crontab found${NC}"
echo ""

# Create required directories
echo "Creating required directories..."
mkdir -p "$SCRIPT_DIR/data/reports/archive"
mkdir -p "$SCRIPT_DIR/data/logs"
mkdir -p "$SCRIPT_DIR/data/cache"
echo -e "${GREEN}✓ Directories created${NC}"
echo ""

# Determine Python interpreter
PYTHON_CMD="python3"
if ! command -v $PYTHON_CMD &> /dev/null; then
    PYTHON_CMD="python"
fi

if ! command -v $PYTHON_CMD &> /dev/null; then
    echo -e "${RED}Error: Python 3 not found. Please install Python 3.8 or later.${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Python found: $($PYTHON_CMD --version)${NC}"
echo ""

# Get current crontab
CURRENT_CRONTAB=$(crontab -l 2>/dev/null || echo "")

# Check if jobs already exist
if echo "$CURRENT_CRONTAB" | grep -q "briefAI.*--collect"; then
    echo -e "${YELLOW}⚠ Collection job already exists${NC}"
fi
if echo "$CURRENT_CRONTAB" | grep -q "briefAI.*--finalize"; then
    echo -e "${YELLOW}⚠ Finalization job already exists${NC}"
fi

echo "Setting up cron jobs..."
echo ""

# Create temporary file for new crontab
TEMP_CRONTAB=$(mktemp)
trap "rm -f $TEMP_CRONTAB" EXIT

# Add current crontab to temp file (if exists)
if [ ! -z "$CURRENT_CRONTAB" ]; then
    echo "$CURRENT_CRONTAB" > "$TEMP_CRONTAB"
    # Remove any existing briefAI jobs to avoid duplicates
    grep -v "briefAI" "$TEMP_CRONTAB" > "$TEMP_CRONTAB.tmp" || true
    mv "$TEMP_CRONTAB.tmp" "$TEMP_CRONTAB"
else
    touch "$TEMP_CRONTAB"
fi

# Add new cron jobs
echo "" >> "$TEMP_CRONTAB"
echo "# AI Industry Weekly Briefing Agent" >> "$TEMP_CRONTAB"
echo "# Last updated: $(date)" >> "$TEMP_CRONTAB"
echo "" >> "$TEMP_CRONTAB"

# Job 1: Daily collection at 23:59
echo "# Daily article collection at 23:59 (every day)" >> "$TEMP_CRONTAB"
echo "59 23 * * * cd $SCRIPT_DIR && $PYTHON_CMD main.py --defaults --collect >> data/logs/cron.log 2>&1" >> "$TEMP_CRONTAB"

# Job 2: Daily report generation at 06:00
echo "# Daily report generation at 06:00 (every day)" >> "$TEMP_CRONTAB"
echo "0 6 * * * cd $SCRIPT_DIR && $PYTHON_CMD main.py --defaults --finalize >> data/logs/cron.log 2>&1" >> "$TEMP_CRONTAB"

# Job 3: Weekly final report at 08:00 on Friday
echo "# Weekly finalization at 08:00 on Friday" >> "$TEMP_CRONTAB"
echo "0 8 * * 5 cd $SCRIPT_DIR && $PYTHON_CMD main.py --defaults --finalize --weekly >> data/logs/cron.log 2>&1" >> "$TEMP_CRONTAB"

# Job 4: Archive daily reports at 09:00 on Friday
echo "# Archive daily reports at 09:00 on Friday" >> "$TEMP_CRONTAB"
echo "0 9 * * 5 cd $SCRIPT_DIR && $PYTHON_CMD utils/report_archiver.py archive >> data/logs/cron.log 2>&1" >> "$TEMP_CRONTAB"

# Install the new crontab
$CRON_COMMAND "$TEMP_CRONTAB"

echo -e "${GREEN}✓ Cron jobs installed successfully${NC}"
echo ""
echo "Installed cron jobs:"
echo "---"
echo "59 23 * * * - Daily collection at 23:59"
echo "0  6 * * * - Daily report at 06:00"
echo "0  8 * * 5 - Weekly report at 08:00 (Friday)"
echo "0  9 * * 5 - Archive reports at 09:00 (Friday)"
echo "---"
echo ""

# Display installed crontab
echo "Current crontab:"
echo "---"
crontab -l | tail -10
echo "---"
echo ""

# Instructions for verification
echo -e "${YELLOW}Verification Steps:${NC}"
echo "1. View your crontab:"
echo "   crontab -l"
echo ""
echo "2. Monitor logs:"
echo "   tail -f $SCRIPT_DIR/data/logs/cron.log"
echo ""
echo "3. Test collection manually:"
echo "   cd $SCRIPT_DIR && $PYTHON_CMD main.py --defaults --collect"
echo ""
echo "4. Test report generation manually:"
echo "   cd $SCRIPT_DIR && $PYTHON_CMD main.py --defaults --finalize"
echo ""

# Instructions for removal
echo -e "${YELLOW}To remove cron jobs:${NC}"
echo "1. Run: crontab -e"
echo "2. Delete the lines containing 'briefAI'"
echo "3. Save and exit"
echo ""

# Final status
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Cron setup complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Log file location: $SCRIPT_DIR/data/logs/cron.log"
echo "Archive directory: $SCRIPT_DIR/data/reports/archive"
echo ""
echo -e "${YELLOW}Next Steps:${NC}"
echo "1. Verify the cron jobs are installed: crontab -l"
echo "2. Monitor the logs for errors: tail -f data/logs/cron.log"
echo "3. Test the system manually before relying on automation"
echo ""
