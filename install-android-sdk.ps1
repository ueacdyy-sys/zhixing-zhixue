# install-android-sdk.ps1
# 知行智学 Android SDK 安装脚本（国内镜像版）
# 镜像源：腾讯云 mirrors.cloud.tencent.com/AndroidSDK（无需代理，国内直连）
# 安装内容：cmdline-tools + platform-tools + build-tools 37.0.0 + platforms android-37.0
# 说明：项目 mobile-edge/third_party/screenstream_source 要求 compileSdk 37 / buildToolsVersion 37.0.0
$ErrorActionPreference = 'Stop'

$Mirror = 'https://mirrors.cloud.tencent.com/AndroidSDK'
$SdkRoot = "$env:LOCALAPPDATA\Android\Sdk"
$TempDir = Join-Path $env:TEMP 'zhixing-android-sdk'
New-Item -ItemType Directory -Force -Path $TempDir | Out-Null

function Fetch-And-Unzip([string]$File, [string]$DestDir, [string]$RenameTo = '') {
    $zip = Join-Path $TempDir $File
    if (!(Test-Path $zip)) {
        Write-Host "下载 $File ..."
        curl.exe -L -sS -o $zip "$Mirror/$File" --connect-timeout 15 --max-time 900 --retry 3
        if ($LASTEXITCODE -ne 0) { throw "下载失败: $File" }
    } else {
        Write-Host "复用缓存 $File"
    }
    Write-Host "解压 $File -> $DestDir"
    Expand-Archive -Path $zip -DestinationPath $DestDir -Force
    if ($RenameTo) {
        $sub = Get-ChildItem -LiteralPath $DestDir -Directory | Select-Object -First 1
        $target = Join-Path (Split-Path -Parent $DestDir) $RenameTo
        if ((Test-Path $target) -and ($sub.FullName -ne $target)) { Remove-Item $target -Recurse -Force }
        if ($sub.FullName -ne $target) { Move-Item $sub.FullName $target }
    }
}

# 1) cmdline-tools（latest）
$cmdlineLatest = "$SdkRoot\cmdline-tools\latest"
if (!(Test-Path "$cmdlineLatest\bin\sdkmanager.bat")) {
    $zip = Join-Path $TempDir 'commandlinetools-win-latest.zip'
    Write-Host '下载 cmdline-tools ...'
    curl.exe -L -sS -o $zip "$Mirror/commandlinetools-win-11076708_latest.zip" --connect-timeout 15 --max-time 900 --retry 3
    if ($LASTEXITCODE -ne 0) { throw '下载失败: cmdline-tools' }
    $stage = Join-Path $TempDir 'cmdline-extract'
    Remove-Item $stage -Recurse -Force -ErrorAction SilentlyContinue
    Expand-Archive -Path $zip -DestinationPath $stage -Force
    Remove-Item "$SdkRoot\cmdline-tools" -Recurse -Force -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Force -Path $cmdlineLatest | Out-Null
    Copy-Item "$stage\cmdline-tools\*" $cmdlineLatest -Recurse -Force
}
Write-Host "cmdline-tools OK: $cmdlineLatest"

# 2) platform-tools
Fetch-And-Unzip 'platform-tools-latest-windows.zip' $SdkRoot
# 3) build-tools 37.0.0（zip 内目录名为 android-37.0，需改名为 37.0.0）
Fetch-And-Unzip 'build-tools_r37_windows.zip' "$SdkRoot\build-tools" '37.0.0'
# 4) platforms android-37.0
Fetch-And-Unzip 'platform-37.0_r02.zip' "$SdkRoot\platforms"

# 5) 写入用户级环境变量
[Environment]::SetEnvironmentVariable('ANDROID_HOME', $SdkRoot, 'User')
[Environment]::SetEnvironmentVariable('ANDROID_SDK_ROOT', $SdkRoot, 'User')
$userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
$adds = @("$SdkRoot\platform-tools", "$SdkRoot\cmdline-tools\latest\bin") | Where-Object { $userPath -notlike "*$_*" }
if ($adds) { [Environment]::SetEnvironmentVariable('Path', ($adds -join ';') + ';' + $userPath, 'User') }
# JAVA_HOME（若缺失则写入本机 JDK 21）
if (![Environment]::GetEnvironmentVariable('JAVA_HOME', 'User')) {
    $jdk = Get-ChildItem 'C:\Program Files\Java' -Directory -ErrorAction SilentlyContinue |
      Where-Object { $_.Name -like 'jdk-*' } | Sort-Object Name -Descending | Select-Object -First 1
    if ($jdk) { [Environment]::SetEnvironmentVariable('JAVA_HOME', $jdk.FullName, 'User') }
}

# 6) 验证
& "$SdkRoot\platform-tools\adb.exe" version
Write-Host ''
Write-Host '===== ALL DONE ====='
Write-Host "ANDROID_HOME = $SdkRoot"
Write-Host '组件: cmdline-tools / platform-tools / build-tools 37.0.0 / platforms android-37.0'
