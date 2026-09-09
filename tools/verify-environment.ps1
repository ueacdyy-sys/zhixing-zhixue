$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
$hub = Join-Path $projectRoot 'services\local-hub'
$sdk = [Environment]::GetEnvironmentVariable('ANDROID_SDK_ROOT', 'User')
if (!$sdk) { $sdk = "$env:LOCALAPPDATA\Android\Sdk" }
$javaHome = [Environment]::GetEnvironmentVariable('JAVA_HOME', 'User')
$androidProject = Join-Path $projectRoot 'mobile-edge\third_party\screenstream_source'
# Windows 构建必须从 ASCII Junction 启动（中文路径会导致 Gradle/Kotlin Worker 解码错误）
$junctionProject = 'C:\ZhixingZhixue\mobile-edge\third_party\screenstream_source'
$checks = @()

function Invoke-Check([string]$Name, [scriptblock]$Action) {
    try {
        & $Action
        $script:checks += [pscustomobject]@{ Check = $Name; Result = 'PASS' }
    }
    catch {
        $script:checks += [pscustomobject]@{ Check = $Name; Result = "FAIL: $($_.Exception.Message)" }
    }
}

Invoke-Check 'Python local hub lint' { Push-Location $hub; try { uv run ruff check src tests; if ($LASTEXITCODE) { throw 'ruff failed' } } finally { Pop-Location } }
Invoke-Check 'Python local hub tests' { Push-Location $hub; try { uv run pytest; if ($LASTEXITCODE) { throw 'pytest failed' } } finally { Pop-Location } }
Invoke-Check 'PC workbench toolchain' { Push-Location $projectRoot; try { pnpm --filter @zhixingzhixue/pc-workbench exec vite --version; pnpm --filter @zhixingzhixue/pc-workbench exec vitest --version; pnpm --filter @zhixingzhixue/pc-workbench exec tsc --version; if ($LASTEXITCODE) { throw 'PC toolchain command failed' } } finally { Pop-Location } }
Invoke-Check 'Android SDK variables' { if (!$sdk) { throw 'ANDROID_SDK_ROOT is missing' }; if (!(Test-Path "$sdk\platform-tools\adb.exe")) { throw 'adb.exe missing' }; if (!(Test-Path "$sdk\cmdline-tools\latest\bin\sdkmanager.bat")) { throw 'sdkmanager.bat missing' }; if (!(Test-Path "$sdk\platforms\android-37.0\android.jar")) { throw 'Android 37.0 platform missing' }; if (!(Test-Path "$sdk\build-tools\37.0.0\aapt.exe")) { throw 'Build-Tools 37.0.0 missing' } }
Invoke-Check 'Android commands' { & "$sdk\platform-tools\adb.exe" version | Out-Null; & "$sdk\build-tools\37.0.0\aapt.exe" version | Out-Null; if ($LASTEXITCODE) { throw 'Android command failed' } }
Invoke-Check 'JDK' { if (!$javaHome -and !(Get-Command javac -ErrorAction SilentlyContinue)) { throw 'JAVA_HOME missing and javac not on PATH' }; javac -version }
Invoke-Check 'Gradle wrapper (Junction path)' { if (!(Test-Path $junctionProject)) { throw 'Junction C:\ZhixingZhixue missing' }; Push-Location $junctionProject; try { .\gradlew.bat --version | Out-Null; if ($LASTEXITCODE) { throw 'Gradle wrapper failed' } } finally { Pop-Location } }
Invoke-Check 'Frozen spec artifacts' { if (!(Test-Path "$projectRoot\.specify\memory\constitution.md")) { throw 'constitution missing' }; if (!(Test-Path "$projectRoot\specs\004-realtime-learning-core\spec.md")) { throw 'frozen spec 004 missing' } }
Invoke-Check 'Specify CLI (optional)' { $specify = Get-Command specify -ErrorAction SilentlyContinue; if (!$specify) { $script:checks[-1].Result = 'WARN: specify CLI not installed (optional, uv tool install specify-cli)'; return }; & specify --version | Out-Null }

$checks | Format-Table -AutoSize
if ($checks.Result -match '^FAIL') { exit 1 }
