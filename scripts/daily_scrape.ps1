# Daily BriefAI Scraper Script
# Run via Task Scheduler at 6:00 AM daily

$ErrorActionPreference = "Continue"
$timestamp = Get-Date -Format "yyyy-MM-dd_HH-mm"
$logFile = "C:\Users\admin\briefAI\logs\scrape_$timestamp.log"

# Ensure logs directory exists
New-Item -ItemType Directory -Force -Path "C:\Users\admin\briefAI\logs" | Out-Null

# Change to briefAI directory
Set-Location "C:\Users\admin\briefAI"

# Run scrapers
Write-Output "Starting daily scrape at $(Get-Date)" | Tee-Object -FilePath $logFile

python scrapers/run_all_scrapers.py 2>&1 | Tee-Object -FilePath $logFile -Append

Write-Output "Scrape completed at $(Get-Date)" | Tee-Object -FilePath $logFile -Append
