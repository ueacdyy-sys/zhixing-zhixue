package cn.zhixingzhixue.edge.android

/**
 * Device-side interpretation of the selected-app capture policy.
 *
 * This gate controls only whether already-authorized MediaProjection output
 * may leave the phone.  It never stops, recreates or re-requests the system
 * capture authorization: a later return to a selected app can reopen output
 * in the same CaptureSession.
 */
public enum class ForegroundAppObservationSource {
    ACCESSIBILITY,
    USAGE_STATS,
    LOCAL_UI,
}

public enum class CaptureOutputGateTransition {
    ALLOWED_FULL_CONTINUOUS,
    ALLOWED_SELECTED_APP,
    BLOCKED_UNOBSERVED,
    BLOCKED_UNSELECTED_APP,
    BLOCKED_POLICY_UNCONFIRMED,
}

public data class CaptureOutputGateState(
    val isOutputAllowed: Boolean,
    val transition: CaptureOutputGateTransition,
    val foregroundPackage: String?,
    val observationSource: ForegroundAppObservationSource?,
    /** A blocked output is privacy filtering, never an implicit session stop. */
    val captureSessionRemainsAuthorized: Boolean = true,
)

/** Fail closed until the first device-side foreground-app observation arrives. */
public class ForegroundAppOutputGate(private val policy: PcCaptureModePolicy) {
    private var latest: CaptureOutputGateState = initialState(policy)

    public val current: CaptureOutputGateState
        get() = latest

    public val isOutputAllowed: Boolean
        get() = latest.isOutputAllowed

    public fun observe(
        foregroundPackage: String?,
        observationSource: ForegroundAppObservationSource,
    ): CaptureOutputGateState {
        latest = when {
            policy.mode == PcCaptureMode.FULL_CONTINUOUS -> CaptureOutputGateState(
                isOutputAllowed = true,
                transition = CaptureOutputGateTransition.ALLOWED_FULL_CONTINUOUS,
                foregroundPackage = foregroundPackage,
                observationSource = observationSource,
            )

            policy.allowsOutputFor(foregroundPackage) -> CaptureOutputGateState(
                isOutputAllowed = true,
                transition = CaptureOutputGateTransition.ALLOWED_SELECTED_APP,
                foregroundPackage = foregroundPackage,
                observationSource = observationSource,
            )

            else -> CaptureOutputGateState(
                isOutputAllowed = false,
                transition = CaptureOutputGateTransition.BLOCKED_UNSELECTED_APP,
                foregroundPackage = foregroundPackage,
                observationSource = observationSource,
            )
        }
        return latest
    }

    private companion object {
        private fun initialState(policy: PcCaptureModePolicy): CaptureOutputGateState =
            if (policy.mode == PcCaptureMode.FULL_CONTINUOUS) {
                CaptureOutputGateState(true, CaptureOutputGateTransition.ALLOWED_FULL_CONTINUOUS, null, null)
            } else {
                CaptureOutputGateState(false, CaptureOutputGateTransition.BLOCKED_UNOBSERVED, null, null)
            }
    }
}
