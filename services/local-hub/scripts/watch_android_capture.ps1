param(
    [string]$Serial = 'NBLDU20C09022238',
    [int]$TimeoutSeconds = 180
)

$adb = 'C:\Users\Administrator\AppData\Local\Android\Sdk\platform-tools\adb.exe'
$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
$samples = @()
while ((Get-Date) -lt $deadline) {
    $files = & $adb -s $Serial shell ls -l /sdcard/Android/data/cn.zhixingzhixue.mobile/files/Movies 2>$null
    $sizes = @($files | ForEach-Object {
        if ($_ -match '^\S+\s+\S+\s+\S+\s+(\d+)\s+') { [int64]$Matches[1] }
    })
    $service = & $adb -s $Serial shell dumpsys activity services cn.zhixingzhixue.mobile 2>$null
    $samples += [pscustomobject]@{
        observed_at = (Get-Date).ToString('o')
        max_capture_bytes = if ($sizes) { ($sizes | Measure-Object -Maximum).Maximum } else { 0 }
        service_detected = [bool]($service -match 'ScreenCaptureService')
    }
    if ($sizes -and (($sizes | Measure-Object -Maximum).Maximum -gt 0)) { break }
    Start-Sleep -Seconds 2
}
$errors = & $adb -s $Serial logcat -d -v brief 2>$null | Select-String -Pattern 'ZhixingCapture|capture_start_failed'
$report = [pscustomobject]@{
    completed_at = (Get-Date).ToString('o')
    samples = $samples
    capture_started = [bool](($samples | Where-Object { $_.max_capture_bytes -gt 0 }))
    error_lines = @($errors | ForEach-Object { $_.Line })
}
$output = Join-Path $PSScriptRoot '..\evidence\live\android-capture-watch.json'
New-Item -ItemType Directory -Force -Path (Split-Path $output) | Out-Null
$report | ConvertTo-Json -Depth 4 | Set-Content -Encoding utf8 $output
