$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
$hub = Join-Path $projectRoot 'services\local-hub'
$sdk = [Environment]::GetEnvironmentVariable('ANDROID_SDK_ROOT', 'User')
$javaHome = [Environment]::GetEnvironmentVariable('JAVA_HOME', 'User')
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
Invoke-Check 'Android SDK variables' { if (!$sdk -or !$javaHome) { throw 'ANDROID_SDK_ROOT or JAVA_HOME is missing' }; if (!(Test-Path "$sdk\platform-tools\adb.exe")) { throw 'adb.exe missing' }; if (!(Test-Path "$sdk\cmdline-tools\latest\bin\sdkmanager.bat")) { throw 'sdkmanager.bat missing' }; if (!(Test-Path "$sdk\platforms\android-35\android.jar")) { throw 'Android 35 platform missing' }; if (!(Test-Path "$sdk\build-tools\35.0.0\aapt.exe")) { throw 'Build-Tools 35.0.0 missing' } }
Invoke-Check 'Android commands' { & "$sdk\platform-tools\adb.exe" version; & "$sdk\cmdline-tools\latest\bin\sdkmanager.bat" --version; & "$sdk\build-tools\35.0.0\aapt.exe" version; if ($LASTEXITCODE) { throw 'Android command failed' } }
Invoke-Check 'JDK and Gradle' { javac -version; gradle --version | Out-Null; if ($LASTEXITCODE) { throw 'Gradle failed' } }
Invoke-Check 'Spec Kit artifacts' { if (!(Test-Path "$projectRoot\.specify\memory\constitution.md")) { throw 'constitution missing' }; if (!(Test-Path "$projectRoot\specs\001-multi-entry-learning-evidence\tasks.md")) { throw 'tasks missing' }; $specify = 'C:\Users\Administrator\.local\bin\specify.exe'; if (!(Test-Path $specify)) { $specify = (Get-Command specify -ErrorAction Stop).Source }; & $specify --version; if ($LASTEXITCODE) { throw 'Specify CLI failed' } }

$checks | Format-Table -AutoSize
if ($checks.Result -match '^FAIL') { exit 1 }
