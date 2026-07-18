$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\env.ps1" -Quiet

& $env:PHONE_CAPTURE_ADB start-server | Out-Null
& $env:PHONE_CAPTURE_ADB devices -l
