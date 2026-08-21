package cn.zhixingzhixue.edge.android

/** The connection page's editable selection, reconstructed from durable capture state. */
public data class CaptureUiSelection(
    val modeIndex: Int,
    val selectedPackages: Set<String>,
)

/**
 * Keep the visible selection aligned with the policy the foreground service is
 * actually enforcing after an Activity/process recreation.
 */
public fun captureUiSelectionForPlan(plan: PcCapturePlan?): CaptureUiSelection {
    val policy = plan?.capturePolicy ?: PcCaptureModePolicy.fullContinuous()
    return if (policy.mode == PcCaptureMode.SELECTED_APPS) {
        CaptureUiSelection(modeIndex = 1, selectedPackages = policy.selectedPackages)
    } else {
        CaptureUiSelection(modeIndex = 0, selectedPackages = emptySet())
    }
}
