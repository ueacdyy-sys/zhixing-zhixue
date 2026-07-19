param(
  [string]$UsbSerial,
  [int]$Port = 5555,
  [int]$WaitSeconds = 10
)

$ErrorActionPreference = 'Stop'
$OutputEncoding = [Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = $OutputEncoding
. "$PSScriptRoot\env.ps1" -Quiet

function Get-AuthorizedUsbSerial {
  param([string]$RequestedSerial)

  $devices = & $env:PHONE_CAPTURE_ADB devices
  $authorized = @(
    $devices |
      Select-String '^(?<serial>[^\s:]+)\s+device$' |
      ForEach-Object { $_.Matches[0].Groups['serial'].Value }
  )
  if ($RequestedSerial) {
    if ($authorized -notcontains $RequestedSerial) {
      throw "指定 USB 设备未处于授权状态：$RequestedSerial"
    }
    return $RequestedSerial
  }
  if ($authorized.Count -eq 0) {
    throw '未检测到已授权的 USB ADB 设备。请连接 nova 8，解锁并确认“允许 USB 调试”后重试。'
  }
  if ($authorized.Count -gt 1) {
    throw "检测到多个 USB ADB 设备：$($authorized -join ', ')。请使用 -UsbSerial 指定 nova 8。"
  }
  return $authorized[0]
}

function Get-PhoneWlanIp {
  param([string]$Serial)

  $addresses = & $env:PHONE_CAPTURE_ADB -s $Serial shell 'ip -4 -o addr show wlan0' 2>$null
  $match = [regex]::Match(($addresses -join "`n"), 'inet\s+(?<ip>\d{1,3}(?:\.\d{1,3}){3})/')
  if (-not $match.Success) {
    throw '无法从 wlan0 读取 IPv4 地址；请确认 nova 8 已连接 WLAN，而非仅使用移动数据。'
  }
  return $match.Groups['ip'].Value
}

$usb = Get-AuthorizedUsbSerial -RequestedSerial $UsbSerial
$phoneIp = Get-PhoneWlanIp -Serial $usb

Write-Host "USB device: $usb"
Write-Host "Phone WLAN IP: $phoneIp"
Write-Host "Enabling legacy ADB TCP/IP on port $Port ..."
& $env:PHONE_CAPTURE_ADB -s $usb tcpip $Port
if ($LASTEXITCODE -ne 0) { throw 'adb tcpip 未成功执行。' }

Start-Sleep -Seconds $WaitSeconds
$endpoint = "$phoneIp`:$Port"
Write-Host "Connecting: $endpoint"
& $env:PHONE_CAPTURE_ADB connect $endpoint
if ($LASTEXITCODE -ne 0) { throw "adb connect 失败：$endpoint" }

$state = (& $env:PHONE_CAPTURE_ADB -s $endpoint get-state).Trim()
if ($state -ne 'device') { throw "无线 ADB 未进入 device 状态：$state" }

Write-Host 'Wireless ADB connected:'
& $env:PHONE_CAPTURE_ADB devices -l
