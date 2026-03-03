# ============================================================================
# Daily Bloomberg Pipeline v2.0 - Ledger-First Experiment Run
# ============================================================================
#
# A "run" only counts as SUCCESS if:
#   1. Run integrity passes BEFORE doing anything (exact engine commit)
#   2. Scrapers complete successfully
#   3. Forecasts are generated and written to experiment ledger
#   4. Ledger integrity verification passes
#   5. Required artifacts exist in correct experiment folder
#   6. Daily brief is generated (only after all checks pass)
#
# Exit codes:
#   0 - Full success
#   1 - Failed at some step (see FAILED AT STEP X)
#   2 - Run integrity failed (pre-flight abort)
#
# Schedule: Task Scheduler, daily at 6 AM
# ============================================================================

param(
    [string]$ExperimentId = "",
    [switch]$SkipScrapers,
    [switch]$Verbose
)

# Don't use "Stop" - it treats stderr (including INFO logs) as fatal errors
$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

# Paths
$ProjectRoot = "C:\Users\admin\briefAI"

# Auto-detect experiment from config if not provided
if (-not $ExperimentId) {
    $ExpConfig = Get-Content "$ProjectRoot\config\experiments.json" -Raw | ConvertFrom-Json
    $ExperimentId = $ExpConfig.active_experiment
}

$LogDir = "$ProjectRoot\logs"
$DateStr = Get-Date -Format "yyyy-MM-dd"
$LogFile = "$LogDir\daily_bloomberg_$DateStr.log"

# Ensure log directory exists
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}

# Logging function
function Log-Message {
    param([string]$Message, [string]$Level = "INFO")
    $Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $Line = "$Timestamp [$Level] $Message"
    Write-Host $Line
    Add-Content -Path $LogFile -Value $Line -Encoding UTF8
}

function Log-Error {
    param([string]$Message)
    Log-Message -Message $Message -Level "ERROR"
}

function Log-Success {
    param([string]$Message)
    Log-Message -Message $Message -Level "OK"
}

# Step failure handler
function Fail-Step {
    param(
        [int]$StepNum,
        [string]$StepName,
        [string]$ErrorMsg,
        [string]$NextAction
    )
    
    Log-Error "FAILED AT STEP $StepNum ($StepName)"
    Log-Error "Error: $ErrorMsg"
    
    Write-Host ""
    Write-Host "=" * 60 -ForegroundColor Red
    Write-Host "[FAIL] FAILED AT STEP $StepNum - $StepName" -ForegroundColor Red
    Write-Host "=" * 60 -ForegroundColor Red
    Write-Host ""
    Write-Host "Error: $ErrorMsg" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "NEXT ACTION:" -ForegroundColor Cyan
    Write-Host "  $NextAction" -ForegroundColor White
    Write-Host ""
    
    exit 1
}

# ============================================================================
# MAIN PIPELINE
# ============================================================================

Set-Location $ProjectRoot

Log-Message "=" * 60
Log-Message "DAILY BLOOMBERG PIPELINE - $DateStr"
Log-Message "Experiment: $ExperimentId"
Log-Message "=" * 60

$RunStartTime = Get-Date

# ============================================================================
# STEP 0: PRE-RUN INTEGRITY CHECK (MANDATORY)
# ============================================================================
Log-Message "STEP 0: Pre-run integrity check..."

$IntegrityResult = python -c "
import sys
sys.path.insert(0, '.')
from utils.run_lock import verify_run_integrity
report = verify_run_integrity(require_exact_commit=True)
report.print_report()
sys.exit(0 if report.valid else 1)
" 2>&1

if ($LASTEXITCODE -ne 0) {
    $ErrorOutput = $IntegrityResult | Out-String
    Fail-Step -StepNum 0 -StepName "Run Integrity" `
        -ErrorMsg "Pre-run integrity check failed. HEAD must be at engine tag." `
        -NextAction "git checkout ENGINE_v2.1 (or the correct engine tag for this experiment)"
}

Log-Success "Run integrity verified"

# ============================================================================
# STEP 1: RUN SCRAPERS (Data Collection)
# ============================================================================
if (-not $SkipScrapers) {
    Log-Message "STEP 1: Running scrapers..."
    
    # Helper function to run scrapers with resilience
    function Run-ScraperStep {
        param(
            [string]$Name,
            [string]$Command
        )
        Log-Message "  Running $Name..."
        $StepStart = Get-Date
        
        try {
            Invoke-Expression "$Command 2>&1" | Tee-Object -FilePath $LogFile -Append
            $StepExitCode = $LASTEXITCODE
            $Duration = ((Get-Date) - $StepStart).TotalSeconds
            
            if ($StepExitCode -eq 0) {
                Log-Message "  ✓ $Name completed successfully ($([math]::Round($Duration, 1))s)" -Level "OK"
            } else {
                Log-Message "  ⚠ $Name exited with code $StepExitCode, but continuing ($([math]::Round($Duration, 1))s)" -Level "WARN"
            }
        }
        catch {
            $Duration = ((Get-Date) - $StepStart).TotalSeconds
            Log-Message "  ✗ $Name failed: $($_.Exception.Message), but continuing ($([math]::Round($Duration, 1))s)" -Level "WARN"
        }
        
        # Reset error state for next step
        $Global:LASTEXITCODE = 0
    }
    
    # Run each scraper step independently - failures are non-fatal
    Run-ScraperStep "original scrapers" "python -u scrapers/run_all_scrapers.py"
    Run-ScraperStep "expanded scrapers" "python -u scrapers/run_expanded_scrapers.py"
    Run-ScraperStep "signal import" "python -u scripts/import_scraped_signals.py"
    Run-ScraperStep "high-value scrapers" "python -u scrapers/run_high_value_scrapers.py"
    Run-ScraperStep "insider trading" "python -u scrapers/insider_trading_scraper.py"
    Run-ScraperStep "market-news correlator" "python -u scrapers/market_news_correlator.py"
    Run-ScraperStep "finnhub market data" "python -u scrapers/finnhub_scraper.py"
    
    Log-Success "Scrapers phase complete (individual failures are non-fatal)"
}
else {
    Log-Message "STEP 1: Scrapers SKIPPED (--SkipScrapers flag)"
}

# ============================================================================
# STEP 2: REBUILD SIGNAL PROFILES
# ============================================================================
Log-Message "STEP 2: Rebuilding signal profiles..."

python scripts/rebuild_profiles_v2.py 2>&1 | Tee-Object -FilePath $LogFile -Append
if ($LASTEXITCODE -ne 0) {
    Log-Message "Profile rebuild had warnings (non-fatal), continuing..." -Level "WARN"
} else {
    Log-Success "Profiles rebuilt"
}

# ============================================================================
# STEP 3: ACCUMULATE AND VALIDATE
# ============================================================================
Log-Message "STEP 3: Accumulating predictions and validation..."

python scripts/accumulate_predictions.py 2>&1 | Tee-Object -FilePath $LogFile -Append
python scripts/realtime_validator.py --entities NVDA,META,MSFT,GOOGL,AMD 2>&1 | Tee-Object -FilePath $LogFile -Append
if ($LASTEXITCODE -ne 0) {
    Log-Message "Accumulation/validation had warnings (non-fatal), continuing..." -Level "WARN"
} else {
    Log-Success "Accumulation and validation complete"
}

# ============================================================================
# STEP 4: GENERATE FORECASTS (LEDGER WRITE)
# ============================================================================
Log-Message "STEP 4: Generating forecasts and writing to ledger..."

$ForecastResult = python scripts/run_forecast_phase.py --experiment $ExperimentId 2>&1
$ForecastExitCode = $LASTEXITCODE
$ForecastOutput = $ForecastResult | Out-String
Add-Content -Path $LogFile -Value $ForecastOutput -Encoding UTF8

if ($ForecastExitCode -ne 0) {
    Fail-Step -StepNum 4 -StepName "Forecast Generation" `
        -ErrorMsg "Forecast phase failed. Ledger may be incomplete." `
        -NextAction "Check forecast phase output and fix signal/hypothesis generation"
}

Log-Success "Forecasts generated and written to ledger"

# ============================================================================
# STEP 5: VERIFY LEDGER INTEGRITY
# ============================================================================
Log-Message "STEP 5: Verifying ledger integrity..."

$VerifyResult = python scripts/verify_ledger_integrity.py --experiment $ExperimentId 2>&1
$VerifyExitCode = $LASTEXITCODE
$VerifyOutput = $VerifyResult | Out-String
Add-Content -Path $LogFile -Value $VerifyOutput -Encoding UTF8

if ($VerifyExitCode -eq 2) {
    Fail-Step -StepNum 5 -StepName "Ledger Verification" `
        -ErrorMsg "Ledger file not found" `
        -NextAction "Check that forecast phase created forecast_history.jsonl in experiment folder"
}
elseif ($VerifyExitCode -ne 0) {
    Fail-Step -StepNum 5 -StepName "Ledger Verification" `
        -ErrorMsg "Ledger integrity check FAILED. Hash chain may be broken." `
        -NextAction "Run: python scripts/verify_ledger_integrity.py --experiment $ExperimentId --repair"
}

Log-Success "Ledger integrity verified"

# ============================================================================
# STEP 6: GENERATE DAILY BRIEF
# ============================================================================
Log-Message "STEP 6: Generating daily brief..."

$BriefResult = python scripts/generate_daily_brief.py 2>&1
$BriefExitCode = $LASTEXITCODE
$BriefOutput = $BriefResult | Out-String
Add-Content -Path $LogFile -Value $BriefOutput -Encoding UTF8

if ($BriefExitCode -ne 0) {
    Fail-Step -StepNum 6 -StepName "Daily Brief" `
        -ErrorMsg "Daily brief generation failed" `
        -NextAction "Check modules/daily_brief.py and LLM provider status"
}

Log-Success "Daily brief generated"

# ============================================================================
# STEP 7: VERIFY ARTIFACT CONTRACT (after all artifacts are generated)
# ============================================================================
Log-Message "STEP 7: Verifying artifact contract..."

$ArtifactResult = python -c "
import sys
sys.path.insert(0, '.')
from utils.run_artifact_contract import verify_run_artifacts
report = verify_run_artifacts(run_date='$DateStr', experiment_id='$ExperimentId')
report.print_report()
sys.exit(0 if report.all_passed else 1)
" 2>&1
$ArtifactOutput = $ArtifactResult | Out-String
Add-Content -Path $LogFile -Value $ArtifactOutput -Encoding UTF8

if ($LASTEXITCODE -ne 0) {
    Fail-Step -StepNum 7 -StepName "Artifact Contract" `
        -ErrorMsg "Required artifacts missing or invalid" `
        -NextAction "Check experiment folder: data/public/experiments/$ExperimentId/"
}

Log-Success "Artifact contract verified"

# ============================================================================
# STEP 8: DATABASE HEALTH CHECK
# ============================================================================
Log-Message "STEP 8: Database health check..."

python scripts/db_health_check.py 2>&1 | Tee-Object -FilePath $LogFile -Append
if ($LASTEXITCODE -ne 0) {
    Log-Message "Health check had warnings (non-fatal)" -Level "WARN"
} else {
    Log-Success "Health check complete"
}

# ============================================================================
# SUCCESS - PRINT SUMMARY AND NEXT STEPS
# ============================================================================

$RunEndTime = Get-Date
$Duration = ($RunEndTime - $RunStartTime).TotalMinutes

# Count run days
$ExperimentPath = "data\public\experiments\$ExperimentId"
$SnapshotCount = (Get-ChildItem "$ProjectRoot\$ExperimentPath\daily_snapshot_*.json" -ErrorAction SilentlyContinue | Measure-Object).Count

Log-Message "=" * 60
Log-Message "[OK] DAILY PIPELINE COMPLETE"
Log-Message "=" * 60
Log-Message "  Date:         $DateStr"
Log-Message "  Experiment:   $ExperimentId"
Log-Message "  Duration:     $([math]::Round($Duration, 1)) minutes"
Log-Message "  Run Day:      $SnapshotCount"

Write-Host ""
Write-Host "=" * 60 -ForegroundColor Green
Write-Host "[SUCCESS] DAILY PIPELINE COMPLETE" -ForegroundColor Green
Write-Host "=" * 60 -ForegroundColor Green
Write-Host ""
Write-Host "  Date:         $DateStr" -ForegroundColor White
Write-Host "  Experiment:   $ExperimentId" -ForegroundColor White
Write-Host "  Duration:     $([math]::Round($Duration, 1)) minutes" -ForegroundColor White
Write-Host "  Run Day:      $SnapshotCount" -ForegroundColor White
Write-Host ""
Write-Host "ARTIFACTS CREATED:" -ForegroundColor Cyan
Write-Host "  - $ExperimentPath\forecast_history.jsonl (appended)"
Write-Host "  - $ExperimentPath\daily_snapshot_$DateStr.json"
Write-Host "  - $ExperimentPath\run_metadata_$DateStr.json"
Write-Host "  - data\reports\daily_brief_$DateStr.md"
Write-Host ""
Write-Host "NEXT STEPS:" -ForegroundColor Yellow
Write-Host ""
Write-Host "  # Commit data changes only (no code changes allowed mid-experiment)" -ForegroundColor Gray
Write-Host "  git add data/public/experiments/$ExperimentId data/reports" -ForegroundColor White
Write-Host "  git commit -m `"data: forward-test Day $SnapshotCount ($DateStr)`"" -ForegroundColor White
Write-Host ""
Write-Host "  # Optional: Push to remote" -ForegroundColor Gray
Write-Host "  git push origin main" -ForegroundColor White
Write-Host ""
Write-Host "=" * 60 -ForegroundColor Green

exit 0
