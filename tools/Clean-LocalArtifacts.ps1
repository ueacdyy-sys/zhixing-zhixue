[CmdletBinding(SupportsShouldProcess)]
param()

$ErrorActionPreference = 'Stop'
$OutputEncoding = [Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$projectRoot = (Split-Path -Parent $PSScriptRoot).TrimEnd('\', '/')
$prefix = $projectRoot + [IO.Path]::DirectorySeparatorChar

# 这些均为可再生依赖、下载包、构建缓存或已经确认未接入正式链路的调研克隆。
# 不包含 Android SDK/NDK、Python ASR 环境、真实采集证据和 ScreenStream 源码。
$relativeTargets = @(
    'node_modules',
    'apps/mobile-android',
    'android-cmdline-tools.zip',
    'cmdline-tools.zip',
    'mobile-edge/downloads',
    'mobile-edge/third_party/screen-memory',
    'mobile-edge/third_party/phone-screen',
    'mobile-edge/third_party/learning-assistant',
    'mobile-edge/third_party/glasses',
    'mobile-edge/third_party/realtime-vlm',
    'mobile-edge/third_party/screenstream_source/mjpeg',
    'mobile-edge/third_party/screenstream_source/webrtc',
    'mobile-edge/third_party/screenstream_source/app/src/FDroid',
    'mobile-edge/third_party/screenstream_source/app/src/PlayStore',
    'mobile-edge/third_party/screenstream_source/keys',
    'mobile-edge/third_party/screenstream_source/.gradle',
    'mobile-edge/third_party/screenstream_source/build',
    'mobile-edge/third_party/screenstream_source/.git',
    'mobile-edge/scripts/append_progress_docx_round2_20260708.py',
    'mobile-edge/scripts/append_progress_docx_round3_20260709.py',
    'mobile-edge/scripts/append_progress_docx_round4_20260709.py',
    'mobile-edge/scripts/append_progress_docx_round5_20260709.py',
    'mobile-edge/scripts/append_progress_docx_round6_20260709.py',
    'mobile-edge/scripts/build_progress_docx_20260708.py',
    'mobile-edge/scripts/build_progress_docx_original_style_20260708.py',
    'mobile-edge/scripts/screenstream_audio_rtsp_probe.py',
    'mobile-edge/scripts/run_screenstream_audio_rtsp_probe.ps1',
    'mobile-edge/tools/installed-base.apk',
    'mobile-edge/docs/progress_docx_render_20260708_word',
    'mobile-edge/docs/progress_docx_render_original_style_20260708',
    'mobile-edge/docs/progress_docx_render_original_style_20260708_final',
    'mobile-edge/docs/progress_docx_render_round2_20260708',
    'mobile-edge/docs/progress_docx_render_round2_word_20260708',
    'mobile-edge/docs/progress_docx_render_round3_word_20260709',
    'mobile-edge/docs/progress_docx_render_round4_20260709',
    'mobile-edge/docs/progress_docx_render_round4_word_20260709',
    'mobile-edge/docs/progress_docx_render_round4_word_20260709_v2',
    'mobile-edge/docs/progress_docx_render_round5_word_20260709',
    'mobile-edge/docs/progress_docx_render_round6_word_20260709',
    'mobile-edge/docs/华为杯项目推进情况_追加前备份_20260708_2.docx',
    'mobile-edge/docs/华为杯项目推进情况_追加前备份_20260709_133858.docx',
    'mobile-edge/docs/华为杯项目推进情况_追加前备份_round4_20260709_150513.docx',
    'mobile-edge/docs/华为杯项目推进情况_追加前备份_round4_20260709_150715.docx',
    'mobile-edge/docs/华为杯项目推进情况_追加前备份_round4_20260709_151156.docx',
    'mobile-edge/docs/华为杯项目推进情况_追加前备份_round5_20260709_152455.docx',
    'mobile-edge/docs/华为杯项目推进情况_追加前备份_round6_20260709_154459.docx',
    'mobile-edge/README_installation.md',
    'mobile-edge/docs/environment_inventory_20260707.md',
    'mobile-edge/docs/hardware_handoff_checklist_20260707.md',
    'mobile-edge/docs/hardware_probe_huawei_jny_al10_20260708.md',
    'mobile-edge/docs/ready_for_hardware_20260707.md',
    'mobile-edge/docs/realtime_frame_sampler_probe_20260708.md',
    'mobile-edge/docs/setup_report_20260707.md',
    'services/local-hub/_previous-attempts',
    'services/local-hub/.pytest_cache',
    'services/local-hub/.ruff_cache',
    'mobile-edge/_migration-source-empty',
    'mobile-edge/HuaweiCup_PhoneCaptureLab'
)

$removedBytes = [int64]0
foreach ($relativeTarget in $relativeTargets) {
    $target = [IO.Path]::GetFullPath((Join-Path $projectRoot $relativeTarget))
    if (-not $target.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "拒绝删除项目根目录外的路径：$target"
    }
    if (-not (Test-Path -LiteralPath $target)) { continue }

    $item = Get-Item -LiteralPath $target -Force
    $bytes = if ($item.PSIsContainer) {
        (Get-ChildItem -LiteralPath $target -Force -Recurse -File -ErrorAction SilentlyContinue |
            Measure-Object Length -Sum).Sum
    } else {
        $item.Length
    }
    $removedBytes += [int64]$bytes

    if ($PSCmdlet.ShouldProcess($target, '删除已确认的本地可再生制品')) {
        Remove-Item -LiteralPath $target -Recurse -Force
    }
}

Write-Output ("清理目标累计大小：{0:N2} GB" -f ($removedBytes / 1GB))
