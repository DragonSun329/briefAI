# Daily Bloomberg-grade maintenance for briefAI
# Schedule this in Task Scheduler to run daily at 6 AM

$ErrorActionPreference = "Continue"
$logFile = "C:\Users\admin\briefAI\logs\daily_bloomberg_$(Get-Date -Format 'yyyy-MM-dd').log"

function Log-Message {
    param([string]$message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$timestamp - $message" | Tee-Object -FilePath $logFile -Append
}

Set-Location "C:\Users\admin\briefAI"

Log-Message "=== Daily Bloomberg Maintenance Started ==="

# 1. Run scrapers to refresh data
Log-Message "Running original scrapers..."
python scrapers/run_all_scrapers.py 2>&1 | Tee-Object -FilePath $logFile -Append

# 1b. Run expanded scrapers (RSS, newsletters, Reddit)
Log-Message "Running expanded scrapers (tech news, newsletters, Reddit)..."
python scrapers/run_expanded_scrapers.py 2>&1 | Tee-Object -FilePath $logFile -Append

# 1c. Import scraped signals to briefAI
Log-Message "Importing scraped signals..."
python scripts/import_scraped_signals.py 2>&1 | Tee-Object -FilePath $logFile -Append

# 1d. Run high-value scrapers (jobs, earnings, patents, apps, papers, policy, verticals)
Log-Message "Running high-value scrapers..."
python scrapers/run_high_value_scrapers.py 2>&1 | Tee-Object -FilePath $logFile -Append

# 1e. Run insider trading scraper (SEC Form 4 data from OpenInsider)
Log-Message "Running insider trading scraper..."
python scrapers/insider_trading_scraper.py 2>&1 | Tee-Object -FilePath $logFile -Append

# 2. Rebuild signal profiles
Log-Message "Rebuilding signal profiles..."
python scripts/rebuild_profiles_v2.py 2>&1 | Tee-Object -FilePath $logFile -Append

# 3. Accumulate and resolve predictions
Log-Message "Accumulating predictions..."
python scripts/accumulate_predictions.py 2>&1 | Tee-Object -FilePath $logFile -Append

# 4. Run validation
Log-Message "Running validation..."
python scripts/realtime_validator.py --entities NVDA,META,MSFT,GOOGL,AMD 2>&1 | Tee-Object -FilePath $logFile -Append

# 5. Vertical snapshot for temporal tracking
Log-Message "Taking vertical snapshot..."
python scripts/snapshot_verticals.py 2>&1 | Tee-Object -FilePath $logFile -Append

# 6. Database health check
Log-Message "Health check..."
python scripts/db_health_check.py 2>&1 | Tee-Object -FilePath $logFile -Append

# 7. Run Meta-Signal Engine v2.6 (structural trends)
Log-Message "Running meta-signal synthesis..."
python scripts/run_meta_signals.py 2>&1 | Tee-Object -FilePath $logFile -Append

# 8. Generate Daily Brief v2 report
Log-Message "Generating Daily Brief v2 report..."
python -c "
import asyncio
from modules.daily_brief import DailyBriefGenerator

async def main():
    try:
        gen = DailyBriefGenerator()
        report_path = await gen.generate()
        print(f'Daily Brief v2 generated: {report_path}')
    except Exception as e:
        print(f'Daily Brief v2 generation failed: {e}')

asyncio.run(main())
" 2>&1 | Tee-Object -FilePath $logFile -Append

Log-Message "=== Daily Bloomberg Maintenance Complete ==="
