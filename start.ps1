param([switch]$Check)
$ErrorActionPreference = 'Stop'
try { $Host.UI.RawUI.WindowTitle = 'qqbotai - AI service' } catch { }
$taskVenv = if ($env:QQBOT_VENV) { $env:QQBOT_VENV } else { 'D:\IDE\python-envs\qqbotai' }
$taskPython = Join-Path $taskVenv 'Scripts\python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) {
    & (Join-Path $PSScriptRoot 'setup.ps1')
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
if (-not $Check) {
    & $taskPython -X utf8 (Join-Path $PSScriptRoot 'configure.py') --check
    $taskConfigExit = $LASTEXITCODE
    if ($taskConfigExit -eq 2) {
        & (Join-Path $PSScriptRoot 'configure.ps1')
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        & $taskPython -X utf8 (Join-Path $PSScriptRoot 'configure.py') --check
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
    elseif ($taskConfigExit -ne 0) { exit $taskConfigExit }
}
Push-Location -LiteralPath $PSScriptRoot
try {
    if ($Check) {
        & $taskPython -X utf8 (Join-Path $PSScriptRoot 'bot.py') --check
    }
    else {
        & $taskPython -X utf8 (Join-Path $PSScriptRoot 'bot.py')
    }
    $taskExit = $LASTEXITCODE
}
finally { Pop-Location }
exit $taskExit
