$ErrorActionPreference = 'Stop'
try { $Host.UI.RawUI.WindowTitle = 'qqbotai - QQ login' } catch { }
$taskRuntime = 'D:\IDE\NapCat\runtime-v4.18.38'
$taskNode = Join-Path $taskRuntime 'node.exe'
$taskEntry = Join-Path $taskRuntime 'index.js'
$taskVenv = if ($env:QQBOT_VENV) { $env:QQBOT_VENV } else { 'D:\IDE\python-envs\qqbotai' }
$taskPython = Join-Path $taskVenv 'Scripts\python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) {
    & (Join-Path $PSScriptRoot 'setup.ps1')
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
if (-not (Test-Path -LiteralPath $taskNode) -or -not (Test-Path -LiteralPath $taskEntry)) {
    Write-Output 'NapCat portable runtime is missing. See README for the official download and runtime location.'
    exit 2
}
$taskRunning = @(Get-Process -Name node -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $taskNode })
if ($taskRunning.Count -gt 0) {
    Write-Output 'This NapCat runtime is already running. Stop its window before synchronizing or restarting.'
    exit 2
}
$taskPreviousWorkdir = $env:NAPCAT_WORKDIR
$env:NAPCAT_WORKDIR = 'D:\IDE\NapCat\qqbotai-data'
try {
    & $taskPython -B -X utf8 (Join-Path $PSScriptRoot 'prepare_napcat.py') --workdir $env:NAPCAT_WORKDIR
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Write-Output 'Log in to your own QQ locally. Never send the password, QR code or panel token to the chat.'
    Push-Location -LiteralPath $taskRuntime
    try {
        & $taskNode $taskEntry
        $taskExit = $LASTEXITCODE
    }
    finally { Pop-Location }
}
finally { $env:NAPCAT_WORKDIR = $taskPreviousWorkdir }
exit $taskExit
