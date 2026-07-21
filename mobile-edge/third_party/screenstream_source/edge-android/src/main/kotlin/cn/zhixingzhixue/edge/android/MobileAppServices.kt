package cn.zhixingzhixue.edge.android

import android.content.Context

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
    private lateinit var learningPathStoreValue: AndroidLearningPathStore
    private lateinit var pcLinkStoreValue: AndroidPcDeliveryLinkStore
    private lateinit var pcInboxValue: AndroidPcResultInbox
    private lateinit var pcDeliveryClientValue: PcDeliveryClient

    public fun initialize(context: Context) {
        if (initialized) return
        synchronized(this) {
            if (initialized) return
            appContext = context.applicationContext
            candidateStoreValue = AndroidCandidateCardRepository(appContext)
            knowledgeVaultValue = AndroidKnowledgeGraphRepository(appContext)
            learningPathStoreValue = AndroidLearningPathStore(appContext)
            pcLinkStoreValue = AndroidPcDeliveryLinkStore(appContext)
            pcInboxValue = AndroidPcResultInbox(knowledgeVaultValue)
            pcDeliveryClientValue = PcDeliveryClient(pcLinkStoreValue, pcInboxValue)
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

    public fun learningPathStore(context: Context): AndroidLearningPathStore {
        initialize(context)
        return learningPathStoreValue
    }

    public fun pcLinkStore(context: Context): AndroidPcDeliveryLinkStore {
        initialize(context)
        return pcLinkStoreValue
    }

    public fun pcDeliveryClient(context: Context): PcDeliveryClient {
        initialize(context)
        return pcDeliveryClientValue
    }
}
