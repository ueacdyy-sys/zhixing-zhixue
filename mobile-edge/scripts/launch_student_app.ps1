param(
  [Parameter(Mandatory = $true)]
  [string]$Serial
)

$ErrorActionPreference = 'Stop'
$OutputEncoding = [Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = $OutputEncoding
. "$PSScriptRoot\env.ps1" -Quiet

$Package = 'cn.zhixingzhixue.mobile'
$Activity = "$Package/info.dvkr.screenstream.SingleActivity"
$ConfiguredDebugPackage = (& $env:PHONE_CAPTURE_ADB -s $Serial shell settings get global debug_app).Trim()

if ($ConfiguredDebugPackage -eq $Package) {
  Write-Host 'Clearing stale debugger-wait state for 知行智学.'
  & $env:PHONE_CAPTURE_ADB -s $Serial shell am clear-debug-app
}

& $env:PHONE_CAPTURE_ADB -s $Serial shell am force-stop $Package
$Launch = & $env:PHONE_CAPTURE_ADB -s $Serial shell am start -W -n $Activity
$Launch
$LaunchText = $Launch -join "`n"
if ($LaunchText -notmatch 'Status: ok' -or $LaunchText -notmatch 'LaunchState: (COLD|HOT|WARM)') {
  throw '知行智学未通过受检冷启动；请检查 Activity 状态与 logcat。'
}

$State = (& $env:PHONE_CAPTURE_ADB -s $Serial get-state).Trim()
$ProcessId = (& $env:PHONE_CAPTURE_ADB -s $Serial shell pidof $Package).Trim()
if ($State -ne 'device' -or -not $ProcessId) {
  throw '知行智学启动后未保持进程存活。'
}
Write-Host "启动验收通过：serial=$Serial pid=$ProcessId"
