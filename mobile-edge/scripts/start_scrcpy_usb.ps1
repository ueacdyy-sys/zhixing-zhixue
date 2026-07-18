param(
  [switch]$Record,
  [string]$Serial,
  [int]$MaxFps = 30,
  [string]$VideoBitRate = '8M'
)

$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\env.ps1" -Quiet

$captures = Join-Path $env:PHONE_CAPTURE_LAB 'captures'
New-Item -ItemType Directory -Path $captures -Force | Out-Null

& $env:PHONE_CAPTURE_ADB start-server | Out-Null
Write-Host "== Connected devices =="
& $env:PHONE_CAPTURE_ADB devices -l

$argsList = @(
  "--max-fps=$MaxFps",
  "--video-bit-rate=$VideoBitRate",
  "--stay-awake"
)

if ($Serial) {
  $argsList += @('--serial', $Serial)
}

if ($Record) {
  $stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
  $recordPath = Join-Path $captures "scrcpy_usb_$stamp.mp4"
  $argsList += @("--record=$recordPath")
  Write-Host "Recording to $recordPath"
}

& $env:PHONE_CAPTURE_SCRCPY @argsList
