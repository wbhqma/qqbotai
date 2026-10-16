param([switch]$Groups, [switch]$Pexels, [switch]$Tavily, [switch]$Check)
$ErrorActionPreference = 'Stop'
$taskModes = [int]$Groups.IsPresent + [int]$Pexels.IsPresent + [int]$Tavily.IsPresent + [int]$Check.IsPresent
if ($taskModes -gt 1) {
    Write-Output 'Choose only one of -Groups, -Pexels, -Tavily or -Check.'
    exit 2
}
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
    elseif ($Pexels) {
        try { $Host.UI.RawUI.WindowTitle = 'qqbotai - Pexels setup' } catch { }
        & $taskPython -X utf8 (Join-Path $PSScriptRoot 'configure.py') --pexels
    }
    elseif ($Tavily) {
        try { $Host.UI.RawUI.WindowTitle = 'qqbotai - Tavily setup' } catch { }
        & $taskPython -X utf8 (Join-Path $PSScriptRoot 'configure.py') --tavily
    }
    elseif ($Check) {
        & $taskPython -X utf8 (Join-Path $PSScriptRoot 'configure.py') --check
    }
    else {
        & $taskPython -X utf8 (Join-Path $PSScriptRoot 'configure.py')
    }
    $taskExit = $LASTEXITCODE
}
finally { Pop-Location }
exit $taskExit
