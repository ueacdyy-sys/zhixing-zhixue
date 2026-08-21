package cn.zhixingzhixue.edge.android

import android.content.Context
import cn.zhixingzhixue.learning.application.RecordStudentLearningResponse

/**
 * Process-scoped composition root for the student product.
 *
 * UI, notification receivers and LAN delivery must observe the same local
 * repositories.  Creating a repository at each Android boundary would create
 * distinct StateFlows and makes a delivered result invisible until a redraw.
 */
public object MobileAppServices {
    private var initialized: Boolean = false
    private lateinit var appContext: Context

    private lateinit var candidateStoreValue: AndroidCandidateCardRepository
    private lateinit var knowledgeVaultValue: AndroidKnowledgeGraphRepository
    private lateinit var knowledgeGraphEventStoreValue: AndroidKnowledgeGraphEventStore
    private lateinit var knowledgeGraphSyncClientValue: PcKnowledgeGraphSyncClient
    private lateinit var learningPathStoreValue: AndroidLearningPathStore
    private lateinit var learningContentStoreValue: AndroidPcLearningContentStore
    private lateinit var learningResponseStoreValue: AndroidLearningResponseStore
    private lateinit var learningResponseRecorderValue: RecordStudentLearningResponse
    private lateinit var agentWorkspaceStoreValue: AndroidAgentWorkspaceStore
    private lateinit var pcAgentGatewayClientValue: PcAgentGatewayClient
    private lateinit var pcLinkStoreValue: AndroidPcDeliveryLinkStore
    private lateinit var v2DeviceCredentialStoreValue: AndroidV2DeviceCredentialStore
    private lateinit var pcV2DeviceCredentialClientValue: PcV2DeviceCredentialClient
    private lateinit var pcV2MediaSecurityClientValue: PcV2MediaSecurityClient
    private lateinit var pcInboxValue: AndroidPcResultInbox
    private lateinit var pcCandidateInboxValue: PcCandidateCardInbox
    private lateinit var pcDeliveryClientValue: PcDeliveryClient
    private lateinit var pcCaptureSessionCoordinatorValue: PcCaptureSessionCoordinator
    private lateinit var pcSyncUserIntentStoreValue: PcSyncUserIntentStore
    private lateinit var pcCaptureConsentStoreValue: PcCaptureConsentStore

    public fun initialize(context: Context) {
        if (initialized) return
        synchronized(this) {
            if (initialized) return
            appContext = context.applicationContext
            candidateStoreValue = AndroidCandidateCardRepository(appContext)
            knowledgeVaultValue = AndroidKnowledgeGraphRepository(appContext)
            knowledgeGraphEventStoreValue = AndroidKnowledgeGraphEventStore(appContext)
            learningPathStoreValue = AndroidLearningPathStore(appContext)
            learningContentStoreValue = AndroidPcLearningContentStore(appContext)
            learningResponseStoreValue = AndroidLearningResponseStore(appContext)
            learningResponseRecorderValue = RecordStudentLearningResponse(
                AndroidLearningResponseEligibility(learningContentStoreValue, learningPathStoreValue),
                learningResponseStoreValue,
            )
            agentWorkspaceStoreValue = AndroidAgentWorkspaceStore(appContext)
            pcLinkStoreValue = AndroidPcDeliveryLinkStore(appContext)
            v2DeviceCredentialStoreValue = AndroidV2DeviceCredentialStore(appContext)
            pcV2DeviceCredentialClientValue = PcV2DeviceCredentialClient(v2DeviceCredentialStoreValue)
            pcV2MediaSecurityClientValue = PcV2MediaSecurityClient(
                v2DeviceCredentialStoreValue,
                pcV2DeviceCredentialClientValue,
            )
            pcAgentGatewayClientValue = PcAgentGatewayClient(pcLinkStoreValue)
            pcInboxValue = AndroidPcResultInbox(knowledgeVaultValue, learningContentStoreValue)
            pcCandidateInboxValue = PcCandidateCardInbox()
            knowledgeGraphSyncClientValue = PcKnowledgeGraphSyncClient(pcLinkStoreValue, knowledgeGraphEventStoreValue)
            pcDeliveryClientValue = PcDeliveryClient(pcLinkStoreValue, knowledgeGraphSyncClientValue)
            pcCaptureSessionCoordinatorValue = PcCaptureSessionCoordinator(appContext)
            pcSyncUserIntentStoreValue = PcSyncUserIntentStore(appContext)
            pcCaptureConsentStoreValue = PcCaptureConsentStore(appContext)
            initialized = true
        }
    }

    public fun candidateStore(context: Context): AndroidCandidateCardRepository {
        initialize(context)
        return candidateStoreValue
    }

    public fun knowledgeVault(context: Context): AndroidKnowledgeGraphRepository {
        initialize(context)
        return knowledgeVaultValue
    }

    public fun knowledgeGraphEventStore(context: Context): AndroidKnowledgeGraphEventStore {
        initialize(context)
        return knowledgeGraphEventStoreValue
    }

    public fun learningPathStore(context: Context): AndroidLearningPathStore {
        initialize(context)
        return learningPathStoreValue
    }

    public fun learningContentStore(context: Context): AndroidPcLearningContentStore {
        initialize(context)
        return learningContentStoreValue
    }

    public fun learningResponseStore(context: Context): AndroidLearningResponseStore {
        initialize(context)
        return learningResponseStoreValue
    }

    public fun learningResponseRecorder(context: Context): RecordStudentLearningResponse {
        initialize(context)
        return learningResponseRecorderValue
    }

    public fun agentWorkspaceStore(context: Context): AndroidAgentWorkspaceStore {
        initialize(context)
        return agentWorkspaceStoreValue
    }

    public fun pcAgentGatewayClient(context: Context): PcAgentGatewayClient {
        initialize(context)
        return pcAgentGatewayClientValue
    }

    public fun pcLinkStore(context: Context): AndroidPcDeliveryLinkStore {
        initialize(context)
        return pcLinkStoreValue
    }

    public fun pcV2DeviceCredentialClient(context: Context): PcV2DeviceCredentialClient {
        initialize(context)
        return pcV2DeviceCredentialClientValue
    }

    public fun pcV2MediaSecurityClient(context: Context): PcV2MediaSecurityClient {
        initialize(context)
        return pcV2MediaSecurityClientValue
    }

    public fun pcDeliveryClient(context: Context): PcDeliveryClient {
        initialize(context)
        return pcDeliveryClientValue
    }

    public fun pcCaptureSessionCoordinator(context: Context): PcCaptureSessionCoordinator {
        initialize(context)
        return pcCaptureSessionCoordinatorValue
    }

    public fun pcSyncUserIntentStore(context: Context): PcSyncUserIntentStore {
        initialize(context)
        return pcSyncUserIntentStoreValue
    }

    public fun pcCaptureConsentStore(context: Context): PcCaptureConsentStore {
        initialize(context)
        return pcCaptureConsentStoreValue
    }
}
