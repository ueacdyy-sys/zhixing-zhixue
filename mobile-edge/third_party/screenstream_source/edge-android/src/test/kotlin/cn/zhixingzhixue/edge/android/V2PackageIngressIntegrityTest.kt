package cn.zhixingzhixue.edge.android

import kotlin.test.Test
import kotlin.test.assertFailsWith

public class V2PackageIngressIntegrityTest {
    @Test
    public fun `rejects revision that belongs to another moment`() {
        val ingress = validIngress().copy(
            momentRevisionEntity = validIngress().momentRevisionEntity.copy(momentId = "moment-other"),
        )

        assertFailsWith<IllegalArgumentException> {
            V2PackageIngressIntegrity.validate(ingress)
        }
    }

    @Test
    public fun `rejects package that crosses a session or consent generation`() {
        val sessionMismatch = validIngress().copy(
            packageEntity = validIngress().packageEntity.copy(sessionId = "session-other"),
        )
        val consentMismatch = validIngress().copy(
            packageEntity = validIngress().packageEntity.copy(consentGeneration = 2L),
        )

        assertFailsWith<IllegalArgumentException> {
            V2PackageIngressIntegrity.validate(sessionMismatch)
        }
        assertFailsWith<IllegalArgumentException> {
            V2PackageIngressIntegrity.validate(consentMismatch)
        }
    }

    @Test
    public fun `requires a stable brief identity for the same learning moment`() {
        val first = validIngress()
        val revision = first.copy(
            packageEntity = first.packageEntity.copy(packageRevisionId = "package-rev-2"),
            momentEntity = first.momentEntity.copy(currentRevisionId = "moment-rev-2"),
            momentRevisionEntity = first.momentRevisionEntity.copy(
                momentRevisionId = "moment-rev-2",
                revisionNumber = 2L,
                replacesRevisionId = "moment-rev-1",
            ),
            briefEntity = first.briefEntity.copy(briefId = "brief-other"),
            discoverEntryEntity = first.discoverEntryEntity.copy(
                packageRevisionId = "package-rev-2",
                briefId = "brief-other",
            ),
        )

        assertFailsWith<IllegalArgumentException> {
            V2PackageIngressIntegrity.requireSameMomentBrief(first.briefEntity, revision.briefEntity)
        }
    }

    @Test
    public fun `rejects a package when the local route lease or L0 continuity differs`() {
        val ingress = validIngress()
        val validAdmission = V2PackageAdmission(
            learnerId = "learner-1",
            sessionId = "session-1",
            captureConsentId = "consent-1",
            consentGeneration = 1L,
            processingEligibilityGrantId = "grant-1",
            policyBundleHash = "policy-hash",
            protocolProfileId = "profile-1",
            routeLeaseId = "route-1",
            routeEpoch = 1L,
            routeState = V2LocalRouteState.PC_LOCAL_ACTIVE,
            audioSnapshotId = "audio-1",
            audioResolution = "PLAYBACK_AUDIO_VERIFIED",
            semanticAudioDecisionId = null,
            scopeId = "scope-1",
            scopeHash = "scope-hash",
            scopeStable = true,
            l0ContinuityVerified = true,
            runtimeRiskClear = true,
        )

        V2PackageAdmissionGate.validate(ingress, validAdmission)
        assertFailsWith<IllegalArgumentException> {
            V2PackageAdmissionGate.validate(ingress, validAdmission.copy(routeEpoch = 2L))
        }
        assertFailsWith<IllegalArgumentException> {
            V2PackageAdmissionGate.validate(ingress, validAdmission.copy(l0ContinuityVerified = false))
        }
        assertFailsWith<IllegalArgumentException> {
            V2PackageAdmissionGate.validate(ingress, validAdmission.copy(processingEligibilityGrantId = "grant-other"))
        }
        assertFailsWith<IllegalArgumentException> {
            V2PackageAdmissionGate.validate(
                ingress.copy(packageEntity = ingress.packageEntity.copy(processingEligibilityGrantId = "")),
                validAdmission.copy(processingEligibilityGrantId = ""),
            )
        }
        assertFailsWith<IllegalArgumentException> {
            V2PackageIngressIntegrity.validate(ingress.copy(deliveryLeaseId = ""))
        }
    }

    private fun validIngress(): V2PackageIngress {
        val packageEntity = V2ContentPackageEntity(
            learnerId = "learner-1",
            packageId = "package-1",
            packageRevisionId = "package-rev-1",
            messageId = "message-1",
            sessionId = "session-1",
            captureConsentId = "consent-1",
            consentGeneration = 1L,
            processingEligibilityGrantId = "grant-1",
            policyBundleHash = "policy-hash",
            protocolProfileId = "profile-1",
            analysisRouteLeaseId = "route-1",
            routeEpoch = 1L,
            audioSnapshotId = "audio-1",
            audioResolution = "PLAYBACK_AUDIO_VERIFIED",
            semanticAudioDecisionId = null,
            episodeId = "episode-1",
            momentId = "moment-1",
            momentRevisionId = "moment-rev-1",
            scopeId = "scope-1",
            scopeHash = "scope-hash",
            payloadHash = "payload-hash",
            payloadJson = "{}",
            receivedElapsedNs = 1L,
        )
        val moment = V2LearningMomentEntity(
            learnerId = "learner-1",
            momentId = "moment-1",
            sessionId = "session-1",
            episodeId = "episode-1",
            captureConsentId = "consent-1",
            consentGeneration = 1L,
            semanticLineageId = "lineage-1",
            learningAnchorId = "anchor-1",
            interventionKey = "l1:learner-1:moment-1:NORMAL",
            currentRevisionId = "moment-rev-1",
            state = "ACTIVE_DISCOVER",
            createdElapsedNs = 1L,
        )
        val revision = V2LearningMomentRevisionEntity(
            learnerId = "learner-1",
            momentRevisionId = "moment-rev-1",
            momentId = "moment-1",
            revisionNumber = 1L,
            replacesRevisionId = null,
            scopeId = "scope-1",
            scopeHash = "scope-hash",
            scopeSemanticRevision = 1L,
            interestAssessmentId = "interest-1",
            learningOfferAssessmentId = "offer-1",
            evidenceHash = "evidence-hash",
            revisionReason = "INITIAL",
            createdElapsedNs = 1L,
        )
        val brief = V2L1BriefEntity(
            learnerId = "learner-1",
            briefId = "brief-1",
            momentId = "moment-1",
            scopeId = "scope-1",
            interventionKey = "l1:learner-1:moment-1:NORMAL",
            title = "title",
            summary = "summary",
            evidenceHash = "evidence-hash",
            accessState = "ACTIVE",
        )
        return V2PackageIngress(
            packageEntity = packageEntity,
            deliveryLeaseId = "delivery-lease-1",
            momentEntity = moment,
            momentRevisionEntity = revision,
            briefEntity = brief,
            discoverEntryEntity = V2DiscoverEntryEntity(
                learnerId = "learner-1",
                momentId = "moment-1",
                packageId = "package-1",
                packageRevisionId = "package-rev-1",
                briefId = "brief-1",
                recordedElapsedNs = 1L,
            ),
        )
    }
}
