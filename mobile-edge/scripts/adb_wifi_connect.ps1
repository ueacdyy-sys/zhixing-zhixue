param(
  [Parameter(Mandatory = $true)]
  [string]$PhoneIp,

  [int]$Port = 5555
)

$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\env.ps1" -Quiet

Write-Host "== Current ADB devices =="
& $env:PHONE_CAPTURE_ADB devices

Write-Host "`n== Enable TCP/IP mode over existing USB authorization =="
& $env:PHONE_CAPTURE_ADB tcpip $Port

Write-Host "`n== Connect over Wi-Fi =="
& $env:PHONE_CAPTURE_ADB connect "$PhoneIp`:$Port"

Write-Host "`n== ADB devices after Wi-Fi connect =="
& $env:PHONE_CAPTURE_ADB devices

Write-Host "`nNote: this only works after the phone has already authorized USB debugging once."
