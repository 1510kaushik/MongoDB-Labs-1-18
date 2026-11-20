$ErrorActionPreference = "Stop"

$LabRoot = Join-Path $env:USERPROFILE "Downloads\MongoDB-Lab14\Lab14.2_Backup_Recovery"
$BackupRoot = Join-Path $LabRoot "backups"
$ResultsRoot = Join-Path $LabRoot "results"
$LogFile = Join-Path $ResultsRoot "hourly_backup.log"

$MongoDump = "C:\Program Files\MongoDB\Tools\100\bin\mongodump.exe"
$MongoUri = "mongodb://127.0.0.1:27019/?directConnection=true"
$Database = "lab14_backup_test"
$RetentionDays = 7

function Write-Log {
    param([string]$Message)

    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  $Message"
    Write-Host $line
    Add-Content -Path $LogFile -Value $line -Encoding UTF8 -ErrorAction Stop
}

New-Item -ItemType Directory -Force -Path $BackupRoot, $ResultsRoot | Out-Null

if (!(Test-Path $MongoDump)) {
    throw "mongodump.exe not found: $MongoDump"
}

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backupDir = Join-Path $BackupRoot "hourly_$timestamp"
$timer = [System.Diagnostics.Stopwatch]::StartNew()

Write-Log "Starting backup of $Database"

try {
    # Native MongoDB progress messages may be written to stderr.
    # Temporarily allow them through; check the actual exit code below.
    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"

        $dumpOutput = & $MongoDump `
            "--uri=$MongoUri" `
            "--db=$Database" `
            "--excludeCollectionsWithPrefix=benchmark_" `
            "--out=$backupDir" 2>&1

        $dumpExitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousPreference
    }

    foreach ($line in $dumpOutput) {
        $lineText = [string]$line
        Write-Host $lineText
        Add-Content -Path $LogFile -Value $lineText -Encoding UTF8 -ErrorAction Stop
    }

    if ($dumpExitCode -ne 0) {
        throw "mongodump failed with exit code $dumpExitCode"
    }

    $databaseBackupPath = Join-Path $backupDir $Database

    $bsonFiles = @(
        Get-ChildItem -Path $databaseBackupPath -Filter "*.bson" -File
    )

    if ($bsonFiles.Count -eq 0) {
        throw "Backup validation failed: no BSON files found"
    }

    $backupSize = ($bsonFiles | Measure-Object Length -Sum).Sum

    if ($backupSize -le 0) {
        throw "Backup validation failed: backup size is zero"
    }

    $timer.Stop()

    Write-Log "SUCCESS: Backup completed"
    Write-Log "Backup location: $backupDir"
    Write-Log "BSON files: $($bsonFiles.Count)"
    Write-Log "Backup size: $backupSize bytes"
    Write-Log "Elapsed time: $($timer.Elapsed.TotalSeconds) seconds"
}
catch {
    if ($timer.IsRunning) {
        $timer.Stop()
    }

    if (Test-Path $backupDir) {
        Remove-Item -Path $backupDir -Recurse -Force
    }

    Write-Log "FAILED: $($_.Exception.Message)"
    throw
}

# Retain only automated hourly backups from the last seven days.
# Manual and benchmark backups are not affected.
$cutoff = (Get-Date).AddDays(-$RetentionDays)

$expiredBackups = @(
    Get-ChildItem -Path $BackupRoot -Directory -Filter "hourly_*" |
        Where-Object { $_.CreationTime -lt $cutoff }
)

foreach ($oldBackup in $expiredBackups) {
    Remove-Item -Path $oldBackup.FullName -Recurse -Force
    Write-Log "Retention: deleted expired backup $($oldBackup.Name)"
}

Write-Log "Retention completed. Expired backups removed: $($expiredBackups.Count)"
Write-Log "Backup job finished."
