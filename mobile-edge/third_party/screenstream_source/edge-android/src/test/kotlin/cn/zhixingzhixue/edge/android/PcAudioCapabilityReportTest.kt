package cn.zhixingzhixue.edge.android

import info.dvkr.screenstream.rtsp.RtspAudioCapabilitySnapshot
import info.dvkr.screenstream.rtsp.RtspAudioCapabilityStatus
import info.dvkr.screenstream.rtsp.RtspAudioCaptureMode
import info.dvkr.screenstream.rtsp.RtspTransportSnapshot
import info.dvkr.screenstream.rtsp.RtspTransportStatus
import info.dvkr.screenstream.rtsp.RtspTransportTimingSnapshot
import java.security.KeyPairGenerator
import java.security.spec.ECGenParameterSpec
import java.util.Base64
import kotlin.test.Test
import kotlin.test.assertContentEquals
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertNotNull
import kotlin.test.assertNull

public class PcAudioCapabilityReportTest {
    @Test
    public fun `active playback is reported as unverified telemetry with raw timing only`() {
        val report = PcAudioCapabilityReport.fromTransport(
            sessionId = "capture-1",
            captureGeneration = 7,
            applicationPackageId = "tv.danmaku.bili",
            transport = transport(
                audio = RtspAudioCapabilitySnapshot(
                    RtspAudioCaptureMode.PLAYBACK,
                    RtspAudioCapabilityStatus.CAPTURE_ACTIVE_UNVERIFIED,
                    null,
                ),
            ),
        )

        assertNotNull(report)
        assertEquals("PLAYBACK", report.capturePath)
        assertEquals("CAPTURE_ACTIVE_UNVERIFIED", report.status)
        assertEquals("NONE", report.restriction)
        assertEquals(1000L, report.videoPtsStartUs)
        assertEquals(1010L, report.audioPtsStartUs)
        // Current RTSP timing exposes raw endpoints only.  It must not
        // masquerade as a validated audiovisual sync measurement.
        assertNull(report.syncErrorUs)
        assertEquals("L0_ONLY_NO_V2_CONSENT", report.admission)
    }

    @Test
    public fun `audio telemetry is not emitted until a live video timing anchor exists`() {
        val report = PcAudioCapabilityReport.fromTransport(
            sessionId = "capture-1",
            captureGeneration = 7,
            applicationPackageId = null,
            transport = RtspTransportSnapshot(
                status = RtspTransportStatus.STREAMING,
                activeConsumerCount = 1,
                endpoint = "rtsp://127.0.0.1:8554/live",
                deviceAudioAvailable = false,
                failureCode = null,
                audioCapability = RtspAudioCapabilitySnapshot(
                    RtspAudioCaptureMode.NONE,
                    RtspAudioCapabilityStatus.NOT_REQUESTED,
                    null,
                ),
                timing = null,
            ),
        )

        assertNull(report)
    }

    @Test
    public fun `v2 refresh proof binds the Android key to one exact endpoint`() {
        val payload = V2DeviceCredentialProof.payload(
            method = "POST",
            path = "/api/v2/device-credentials/refresh",
            deviceId = "phone-v2",
            timestampMs = 1234L,
            nonce = "nonce-000000000001",
            bodySha256 = null,
        )

        assertEquals(
            "ZHIXING_DEVICE_PROOF.v2\nPOST\n/api/v2/device-credentials/refresh\n" +
                "phone-v2\n1234\nnonce-000000000001\n" +
                "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855\n",
            payload.toString(Charsets.UTF_8),
        )
    }

    @Test
    public fun `v2 media session open proof is byte identical to the PC canonical contract`() {
        val payload = V2MediaSecurityProtocol.openPayload(
            V2MediaSecurityOpenRequest(
                deviceId = "phone-v2",
                learnerId = "learner-1",
                captureSessionId = "capture-1",
                captureConsentId = "consent-1",
                consentGeneration = 3L,
                routeLeaseId = "route-1",
                routeEpoch = 5L,
                clientEphemeralSpkiBase64 = "Y2xpZW50LWVwaGVtZXJhbC1rZXk=",
            ),
        )

        assertEquals(
            "ZHIXING_MEDIA_SECURITY_OPEN.v1\n" +
                "{\"capture_consent_id\":\"consent-1\",\"capture_epoch\":1,\"capture_session_id\":\"capture-1\"," +
                "\"client_ephemeral_spki_b64\":\"Y2xpZW50LWVwaGVtZXJhbC1rZXk=\",\"consent_generation\":3," +
                "\"device_id\":\"phone-v2\",\"learner_id\":\"learner-1\",\"route_epoch\":5," +
                "\"route_lease_id\":\"route-1\"}\n",
            payload.toString(Charsets.UTF_8),
        )
    }

    @Test
    public fun `v2 media fragment encryption binds the scope header and payload hash`() {
        val key = ByteArray(32) { index -> index.toByte() }
        val header = V2MediaFragmentHeader(
            mediaSecuritySessionId = "session-1",
            learnerId = "learner-1",
            captureSessionId = "capture-1",
            captureConsentId = "consent-1",
            consentGeneration = 3L,
            routeLeaseId = "route-1",
            routeEpoch = 5L,
            sequence = 0L,
            ptsStartUs = 10_000L,
            ptsEndUs = 12_000L,
            mediaSha256 = "",
        )
        val encrypted = V2MediaSecurityProtocol.encryptFragment(key, header, "encoded-media".toByteArray())

        assertEquals("02acb815e590b075502b17505e3c7cfe5d6b2d9ff63c9df9221be6e7cefa7056", encrypted.header.mediaSha256)
        assertContentEquals("encoded-media".toByteArray(), V2MediaSecurityProtocol.decryptFragment(key, encrypted))
        assertFailsWith<IllegalArgumentException> {
            V2MediaSecurityProtocol.decryptFragment(
                key,
                encrypted.copy(header = encrypted.header.copy(learnerId = "learner-other")),
            )
        }
    }

    @Test
    public fun `v2 media key derivation info is byte identical to the PC binding`() {
        val info = V2MediaSecurityProtocol.keyDerivationInfo(
            V2MediaSecurityOpenResponse(
                mediaSecuritySessionId = "session-1",
                deviceId = "phone-v2",
                learnerId = "learner-1",
                captureSessionId = "capture-1",
                captureConsentId = "consent-1",
                consentGeneration = 3L,
                routeLeaseId = "route-1",
                routeEpoch = 5L,
                serverEphemeralSpkiBase64 = "c2VydmVyLWtleQ==",
                keyDerivationSaltBase64 = "c2FsdA==",
                expiresAtMs = 1_234_567L,
            ),
        )

        assertEquals(
            "ZHIXING_MEDIA_FRAGMENT_KEY.v1\n" +
                "{\"capture_consent_id\":\"consent-1\",\"capture_epoch\":1,\"capture_session_id\":\"capture-1\"," +
                "\"consent_generation\":3,\"device_id\":\"phone-v2\",\"learner_id\":\"learner-1\"," +
                "\"media_security_session_id\":\"session-1\",\"route_epoch\":5,\"route_lease_id\":\"route-1\"}\n",
            info.toString(Charsets.UTF_8),
        )
    }

    @Test
    public fun `v2 media ECDH derives one in-memory fragment key for both peers`() {
        val generator = KeyPairGenerator.getInstance("EC").apply {
            initialize(ECGenParameterSpec("secp256r1"))
        }
        val client = generator.generateKeyPair()
        val server = generator.generateKeyPair()
        val response = V2MediaSecurityOpenResponse(
            mediaSecuritySessionId = "session-1",
            deviceId = "phone-v2",
            learnerId = "learner-1",
            captureSessionId = "capture-1",
            captureConsentId = "consent-1",
            consentGeneration = 3L,
            routeLeaseId = "route-1",
            routeEpoch = 5L,
            serverEphemeralSpkiBase64 = Base64.getEncoder().encodeToString(server.public.encoded),
            keyDerivationSaltBase64 = Base64.getEncoder().encodeToString(ByteArray(32) { 7 }),
            expiresAtMs = 1_234_567L,
        )

        val clientKey = V2MediaSecurityProtocol.deriveFragmentKey(client.private, response.serverEphemeralSpkiBase64, response)
        val serverKey = V2MediaSecurityProtocol.deriveFragmentKey(
            server.private,
            Base64.getEncoder().encodeToString(client.public.encoded),
            response,
        )

        assertContentEquals(clientKey, serverKey)
        assertEquals(32, clientKey.size)
    }

    private fun transport(audio: RtspAudioCapabilitySnapshot): RtspTransportSnapshot = RtspTransportSnapshot(
        status = RtspTransportStatus.STREAMING,
        activeConsumerCount = 1,
        endpoint = "rtsp://127.0.0.1:8554/live",
        deviceAudioAvailable = true,
        failureCode = null,
        audioCapability = audio,
        timing = RtspTransportTimingSnapshot(
            sessionEpochId = 11,
            anchorElapsedRealtimeNs = 100_000,
            anchorWallClockMs = null,
            latestVideoPtsUs = 1_000,
            latestAudioPtsUs = 1_010,
            lastMediaEmitElapsedRealtimeNs = 101_000,
        ),
    )
}
