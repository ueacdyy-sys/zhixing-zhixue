param(
  [switch]$Reinstall
)

$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\env.ps1" -Quiet

$ApkPath = Join-Path $env:PHONE_CAPTURE_LAB 'downloads\apk\ScreenStream-4.4.1-FDroid-debug-built.apk'
if (!(Test-Path -LiteralPath $ApkPath)) {
  throw "ScreenStream APK not found: $ApkPath"
}

Write-Host "== ADB devices =="
& $env:PHONE_CAPTURE_ADB devices

$InstallArgs = @('install')
if ($Reinstall) { $InstallArgs += '-r' }
$InstallArgs += $ApkPath

Write-Host "`n== Installing ScreenStream APK =="
& $env:PHONE_CAPTURE_ADB @InstallArgs

Write-Host "`nAPK=$ApkPath"
Write-Host "After installation, open ScreenStream on the phone and grant screen capture permission."
