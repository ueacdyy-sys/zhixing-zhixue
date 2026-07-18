param(
    [string]$Serial = "10.26.122.39:5555",
    [string]$PhoneIp = "10.26.122.39",
    [int]$RtspPort = 8554,
    [int]$WaitSeconds = 180,
    [int]$CaptureSeconds = 10,
    [double]$SampleIntervalSeconds = 0.75,
    [int]$DedupHammingThreshold = 4
)

$ErrorActionPreference = "Stop"
$OutputEncoding = [Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root "env\py311\Scripts\python.exe"
$Runner = Join-Path $Root "scripts\live_rtsp_sampler_probe.py"

& $Python $Runner `
    --serial $Serial `
    --phone-ip $PhoneIp `
    --rtsp-port $RtspPort `
    --wait-seconds $WaitSeconds `
    --capture-seconds $CaptureSeconds `
    --target-interval-s $SampleIntervalSeconds `
    --dedup-hamming-threshold $DedupHammingThreshold
