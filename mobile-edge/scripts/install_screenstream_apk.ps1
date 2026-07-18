param(
  [switch]$Reinstall
)

$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\env.ps1" -Quiet

$ApkPath = Join-Path $env:PHONE_CAPTURE_LAB 'third_party\screenstream_source\app\build\outputs\apk\debug\app-debug.apk'
if (!(Test-Path -LiteralPath $ApkPath)) {
  throw "知行智学 Debug APK 不存在；请先从 C:\ZhixingZhixue\mobile-edge\third_party\screenstream_source 运行 .\gradlew.bat :app:assembleDebug。"
}

Write-Host "== ADB devices =="
& $env:PHONE_CAPTURE_ADB devices

$InstallArgs = @('install')
if ($Reinstall) { $InstallArgs += '-r' }
$InstallArgs += $ApkPath

Write-Host "`n== Installing 知行智学 Debug APK =="
& $env:PHONE_CAPTURE_ADB @InstallArgs

Write-Host "`nAPK=$ApkPath"
Write-Host "安装后打开知行智学，并由学生主动确认系统屏幕共享授权。"
