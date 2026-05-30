$ErrorActionPreference = 'SilentlyContinue'

$appDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$exe = Join-Path $appDir 'Antigravity.exe'
$injector = Join-Path $appDir 'antigravity_zh_inject.py'

$mainProcess = Get-CimInstance Win32_Process -Filter "name='Antigravity.exe'" |
  Where-Object { $_.CommandLine -notmatch '--type=' } |
  Select-Object -First 1

if (-not $mainProcess) {
  Start-Process -FilePath $exe -ArgumentList '--lang=zh-CN' -WorkingDirectory $appDir
} elseif ($mainProcess.CommandLine -notmatch '--lang=zh-CN') {
  Start-Process -FilePath $exe -ArgumentList '--lang=zh-CN' -WorkingDirectory $appDir
}

Start-Sleep -Seconds 2
python $injector | Out-Null
