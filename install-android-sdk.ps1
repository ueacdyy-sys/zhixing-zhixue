# 检查代理是否可用，不可用则等待
$proxy = "http://127.0.0.1:7897"
$maxWait = 60
$waited = 0
while ($waited -lt $maxWait) {
    try {
        $null = Invoke-WebRequest -Uri "https://www.baidu.com" -Proxy $proxy -TimeoutSec 5 -UseBasicParsing
        Write-Host "Proxy is available, starting download..."
        break
    } catch {
        Write-Host "Waiting for proxy ($($maxWait - $waited)s remaining)..."
        Start-Sleep 5
        $waited += 5
    }
}
if ($waited -ge $maxWait) {
    Write-Host "ERROR: Proxy not available after ${maxWait}s. Please start your proxy (Clash/V2Ray) and re-run."
    exit 1
}

# Download
$ProgressPreference = 'SilentlyContinue'
$zipUrl = "https://dl.google.com/android/repository/commandlinetools-win-11076708_latest.zip"
$zipPath = "$env:TEMP\cmdline-tools-final.zip"
$proxy = "http://127.0.0.1:7897"
Write-Host "Downloading Android SDK Command-line Tools..."
curl.exe -L -k -x $proxy -o $zipPath $zipUrl --connect-timeout 15 --max-time 600 --retry 3 -#

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Download failed"
    exit 1
}
$size = (Get-Item $zipPath).Length
Write-Host "Downloaded $size bytes"

# Extract
Write-Host "Extracting..."
$extractDir = "$env:TEMP\cmdline-tools-final-extract"
Remove-Item $extractDir -Recurse -Force -ErrorAction SilentlyContinue
Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::ExtractToDirectory($zipPath, $extractDir)

# Move to Android SDK dir
$cmdlineDir = "$env:LOCALAPPDATA\Android\Sdk\cmdline-tools\latest"
Remove-Item "$env:LOCALAPPDATA\Android\Sdk\cmdline-tools" -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $cmdlineDir | Out-Null
Copy-Item "$extractDir\cmdline-tools\*" $cmdlineDir -Recurse -Force
Write-Host "Command-line tools installed to: $cmdlineDir"

# Set environment variables for current session
$env:ANDROID_HOME = "$env:LOCALAPPDATA\Android\Sdk"
$env:ANDROID_SDK_ROOT = $env:ANDROID_HOME
$env:PATH = "$cmdlineDir\bin;$env:LOCALAPPDATA\Android\Sdk\platform-tools;$env:PATH"

Write-Host ""
Write-Host "Installing SDK packages (platform-tools, build-tools, platform 34)..."

# Accept licenses
Write-Host "y" | & "$cmdlineDir\bin\sdkmanager.bat" --proxy=http --proxy_host=127.0.0.1 --proxy_port=7897 "platform-tools" "build-tools;34.0.0" "platforms;android-34"

Write-Host ""
Write-Host "Setting permanent ANDROID_HOME..."
[System.Environment]::SetEnvironmentVariable("ANDROID_HOME", $env:ANDROID_HOME, "User")
[System.Environment]::SetEnvironmentVariable("ANDROID_SDK_ROOT", $env:ANDROID_HOME, "User")
$currentPath = [System.Environment]::GetEnvironmentVariable("PATH", "User")
if (-not $currentPath.Contains("Android\Sdk")) {
    [System.Environment]::SetEnvironmentVariable("PATH", "$cmdlineDir\bin;$env:LOCALAPPDATA\Android\Sdk\platform-tools;$currentPath", "User")
}
Write-Host ""
Write-Host "===== ALL DONE ====="
Write-Host "ANDROID_HOME = $env:ANDROID_HOME"
sdkmanager --version
