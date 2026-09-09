param(
  [switch]$Quiet
)

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

# Android SDK：优先项目内 tools\android-sdk，回退用户级 %LOCALAPPDATA%\Android\Sdk
$UserSdk = [Environment]::GetEnvironmentVariable('ANDROID_SDK_ROOT', 'User')
if (!$UserSdk) { $UserSdk = "$env:LOCALAPPDATA\Android\Sdk" }
$LocalSdkRoot = Join-Path $ProjectRoot 'tools\android-sdk'
$AndroidSdkRoot = if (Test-Path -LiteralPath (Join-Path $LocalSdkRoot 'platform-tools\adb.exe')) { $LocalSdkRoot } else { $UserSdk }
$AndroidSdkPlatformToolsDir = Join-Path $AndroidSdkRoot 'platform-tools'
$AndroidSdkCmdlineToolsBin = Join-Path $AndroidSdkRoot 'cmdline-tools\latest\bin'
$AndroidBuildToolsDir = Join-Path $AndroidSdkRoot 'build-tools\37.0.0'

# platform-tools：优先项目内独立副本，回退 SDK 内副本
$LocalPlatformToolsDir = Join-Path $ProjectRoot 'tools\platform-tools\platform-tools'
$PlatformToolsDir = if (Test-Path -LiteralPath (Join-Path $LocalPlatformToolsDir 'adb.exe')) { $LocalPlatformToolsDir } else { $AndroidSdkPlatformToolsDir }

# JDK：优先已配置的 JAVA_HOME，其次本机 jdk-21 / jdk-17
$PreferredJdk = ''
foreach ($candidate in @([Environment]::GetEnvironmentVariable('JAVA_HOME', 'User'), 'C:\Program Files\Java\jdk-21', 'C:\Program Files\Microsoft\jdk-17.0.19.10-hotspot')) {
  if ($candidate -and (Test-Path -LiteralPath (Join-Path $candidate 'bin\java.exe'))) { $PreferredJdk = $candidate; break }
}

$AdbExe = Join-Path $PlatformToolsDir 'adb.exe'
$SdkAdbExe = Join-Path $AndroidSdkPlatformToolsDir 'adb.exe'
$SdkManagerExe = Join-Path $AndroidSdkCmdlineToolsBin 'sdkmanager.bat'

# scrcpy 为可选组件（仅 start_scrcpy_usb.ps1 需要）
$ScrcpyExe = Get-ChildItem -LiteralPath (Join-Path $ProjectRoot 'tools\scrcpy') -Recurse -Filter 'scrcpy.exe' -ErrorAction SilentlyContinue |
  Select-Object -First 1 -ExpandProperty FullName
$ScrcpyDir = if ($ScrcpyExe) { Split-Path -Parent $ScrcpyExe } else { '' }

# Python：优先项目内 env\py311，回退系统 python
$LocalPythonExe = Join-Path $ProjectRoot 'env\py311\Scripts\python.exe'
$PythonExe = if (Test-Path -LiteralPath $LocalPythonExe) { $LocalPythonExe } else { (Get-Command python -ErrorAction SilentlyContinue).Source }

if (!(Test-Path -LiteralPath $AdbExe)) {
  throw "adb.exe not found: $AdbExe（请先运行仓库根目录 install-android-sdk.ps1）"
}
if (!(Test-Path -LiteralPath $SdkManagerExe)) {
  throw "sdkmanager.bat not found: $SdkManagerExe（请先运行仓库根目录 install-android-sdk.ps1）"
}
if (!$PythonExe) {
  throw 'python.exe not found（未找到项目内 env\py311，系统 PATH 中也没有 python）'
}
if ($PreferredJdk) {
  $env:JAVA_HOME = $PreferredJdk
  $env:GRADLE_JAVA_HOME = $PreferredJdk
}

$env:ANDROID_HOME = $AndroidSdkRoot
$env:ANDROID_SDK_ROOT = $AndroidSdkRoot
$pathAdds = @($AndroidSdkPlatformToolsDir, $AndroidSdkCmdlineToolsBin, $AndroidBuildToolsDir)
if ($PreferredJdk) { $pathAdds = @("$PreferredJdk\bin") + $pathAdds }
if ($ScrcpyDir) { $pathAdds += $ScrcpyDir }
$env:PATH = ($pathAdds -join ';') + ";$env:PATH"
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
  if ($ScrcpyExe) { Write-Host "SCRCPY=$ScrcpyExe" } else { Write-Host 'SCRCPY=(未安装，可选)' }
  Write-Host "PYTHON=$PythonExe"
}
