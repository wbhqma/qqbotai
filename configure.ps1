param([switch]$Groups)
$ErrorActionPreference = 'Stop'
$taskVenv = if ($env:QQBOT_VENV) { $env:QQBOT_VENV } else { 'D:\IDE\python-envs\qqbotai' }
$taskPython = Join-Path $taskVenv 'Scripts\python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) {
    & (Join-Path $PSScriptRoot 'setup.ps1')
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
Push-Location -LiteralPath $PSScriptRoot
try {
    if ($Groups) {
        try { $Host.UI.RawUI.WindowTitle = 'qqbotai - Group setup' } catch { }
        & $taskPython -X utf8 (Join-Path $PSScriptRoot 'configure.py') --groups
    }
    else {
        & $taskPython -X utf8 (Join-Path $PSScriptRoot 'configure.py')
    }
    $taskExit = $LASTEXITCODE
}
finally { Pop-Location }
exit $taskExit
