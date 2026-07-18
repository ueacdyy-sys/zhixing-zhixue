package info.dvkr.screenstream

import info.dvkr.screenstream.common.analytics.StreamingAnalytics
import info.dvkr.screenstream.common.analytics.StreamingAnalyticsEvent

/** 保持传输内核生命周期完整，但不收集、不持久化或上传任何统计事件。 */
public data object NoOpStreamingAnalytics : StreamingAnalytics {
    override fun logEvent(event: StreamingAnalyticsEvent): Unit = Unit
}
