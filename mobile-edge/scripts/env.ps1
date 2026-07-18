param(
  [switch]$Quiet
)

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$PlatformToolsDir = Join-Path $ProjectRoot 'tools\platform-tools\platform-tools'
$AndroidSdkRoot = Join-Path $ProjectRoot 'tools\android-sdk'
$AndroidSdkPlatformToolsDir = Join-Path $AndroidSdkRoot 'platform-tools'
$AndroidSdkCmdlineToolsBin = Join-Path $AndroidSdkRoot 'cmdline-tools\latest\bin'
$AndroidBuildToolsDir = Join-Path $AndroidSdkRoot 'build-tools\37.0.0'
$PreferredJdk17 = 'C:\Program Files\Microsoft\jdk-17.0.19.10-hotspot'
$AdbExe = Join-Path $PlatformToolsDir 'adb.exe'
$SdkAdbExe = Join-Path $AndroidSdkPlatformToolsDir 'adb.exe'
$SdkManagerExe = Join-Path $AndroidSdkCmdlineToolsBin 'sdkmanager.bat'
$ScrcpyExe = Get-ChildItem -LiteralPath (Join-Path $ProjectRoot 'tools\scrcpy') -Recurse -Filter 'scrcpy.exe' |
  Select-Object -First 1 -ExpandProperty FullName
$ScrcpyDir = Split-Path -Parent $ScrcpyExe
$PythonExe = Join-Path $ProjectRoot 'env\py311\Scripts\python.exe'

if (!(Test-Path -LiteralPath $AdbExe)) {
  throw "adb.exe not found: $AdbExe"
}
if (!(Test-Path -LiteralPath $ScrcpyExe)) {
  throw "scrcpy.exe not found under tools\scrcpy"
}
if (!(Test-Path -LiteralPath $PythonExe)) {
  throw "python.exe not found: $PythonExe"
}
if (!(Test-Path -LiteralPath $SdkManagerExe)) {
  throw "sdkmanager.bat not found: $SdkManagerExe"
}
if (Test-Path -LiteralPath (Join-Path $PreferredJdk17 'bin\java.exe')) {
  $env:JAVA_HOME = $PreferredJdk17
  $env:GRADLE_JAVA_HOME = $PreferredJdk17
}

$env:ANDROID_HOME = $AndroidSdkRoot
$env:ANDROID_SDK_ROOT = $AndroidSdkRoot
$env:PATH = "$PreferredJdk17\bin;$PlatformToolsDir;$AndroidSdkPlatformToolsDir;$AndroidSdkCmdlineToolsBin;$AndroidBuildToolsDir;$ScrcpyDir;$env:PATH"
$env:PHONE_CAPTURE_LAB = $ProjectRoot
$env:PHONE_CAPTURE_ADB = $AdbExe
$env:PHONE_CAPTURE_SDK_ADB = $SdkAdbExe
$env:PHONE_CAPTURE_SDKMANAGER = $SdkManagerExe
$env:PHONE_CAPTURE_SCRCPY = $ScrcpyExe
$env:PHONE_CAPTURE_PYTHON = $PythonExe

if (!$Quiet) {
  Write-Host "PHONE_CAPTURE_LAB=$ProjectRoot"
  Write-Host "ADB=$AdbExe"
  Write-Host "ANDROID_HOME=$AndroidSdkRoot"
  if ($env:JAVA_HOME) { Write-Host "JAVA_HOME=$env:JAVA_HOME" }
  Write-Host "SDKMANAGER=$SdkManagerExe"
  Write-Host "SCRCPY=$ScrcpyExe"
  Write-Host "PYTHON=$PythonExe"
}
