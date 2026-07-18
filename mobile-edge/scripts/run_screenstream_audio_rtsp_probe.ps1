param(
  [string]$Serial = "MYQUT20213006206",
  [string]$PhoneIp = "10.26.122.39",
  [double]$Seconds = 15,
  [switch]$InstallDebugApk,
  [switch]$LaunchScreenStream,
  [switch]$RestartViaDebugBroadcast
)

$ErrorActionPreference = "Stop"
$OutputEncoding = [Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$Root = Split-Path -Parent $PSScriptRoot
$Python = "C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$Script = Join-Path $Root "scripts\screenstream_audio_rtsp_probe.py"

$argsList = @(
  $Script,
  "--serial", $Serial,
  "--phone-ip", $PhoneIp,
  "--seconds", "$Seconds"
)

if ($InstallDebugApk) {
  $argsList += "--install-debug-apk"
}
if ($LaunchScreenStream) {
  $argsList += "--launch-screenstream"
}
if ($RestartViaDebugBroadcast) {
  $argsList += "--restart-via-debug-broadcast"
}

& $Python @argsList
