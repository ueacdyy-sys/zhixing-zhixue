from __future__ import annotations

import unittest
import json
import base64
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from candidate_notice_dispatcher import _l1_eligibility, _send, _wire_card_payload


class CandidateNoticeEligibilityTests(unittest.TestCase):
    def test_legacy_candidate_receiver_is_not_an_android_entry_point(self) -> None:
        manifest = (
            ROOT
            / "third_party"
            / "screenstream_source"
            / "edge-android"
            / "src"
            / "main"
            / "AndroidManifest.xml"
        )
        content = manifest.read_text(encoding="utf-8")

        self.assertNotIn("CandidateNoticeReceiver", content)
        self.assertNotIn("SHOW_CANDIDATE_NOTICE", content)

    def test_legacy_candidate_ingress_has_no_notification_side_effect(self) -> None:
        android_root = ROOT / "third_party" / "screenstream_source" / "edge-android" / "src" / "main" / "kotlin" / "cn" / "zhixingzhixue" / "edge" / "android"
        for name in ("CandidateNoticeReceiver.kt", "PcCandidateCardInbox.kt"):
            with self.subTest(name=name):
                content = (android_root / name).read_text(encoding="utf-8")
                self.assertNotIn("notifications.show(", content)
                self.assertNotIn("AndroidStudentNotice(appContext).show(", content)
        legacy_notice = (android_root / "AndroidStudentNotice.kt").read_text(encoding="utf-8")
        self.assertNotIn(".notify(", legacy_notice)
        self.assertIn("legacy_candidate_notification_disabled", legacy_notice)

    def test_v1_cannot_reach_old_learning_inboxes_or_deep_link_route(self) -> None:
        android_root = ROOT / "third_party" / "screenstream_source" / "edge-android" / "src" / "main" / "kotlin" / "cn" / "zhixingzhixue" / "edge" / "android"
        delivery = (android_root / "PcDeliveryClient.kt").read_text(encoding="utf-8")
        graph_sync = (android_root / "PcKnowledgeGraphSyncClient.kt").read_text(encoding="utf-8")
        legacy_repository = (android_root / "AndroidCandidateCardRepository.kt").read_text(encoding="utf-8")
        activity = (ROOT / "third_party" / "screenstream_source" / "app" / "src" / "main" / "java" / "info" / "dvkr" / "screenstream" / "SingleActivity.kt").read_text(encoding="utf-8")

        self.assertIn("legacy_v1_delivery_disabled", delivery)
        self.assertNotIn("inbox.accept(", delivery)
        self.assertNotIn("pcInbox.accept(", graph_sync)
        self.assertIn("legacy_candidate_repository_read_only", legacy_repository)
        self.assertNotIn("CandidateNoticeReceiver", activity)
        self.assertNotIn("initialOpenL1", activity)

    def test_candidate_card_shell_payload_is_url_safe_and_lossless(self) -> None:
        card = {"display_excerpt": "包括刚才我们看到的演员库", "facts": [{"text": "两万个角色"}]}
        payload = _wire_card_payload(card)

        self.assertNotRegex(payload, r"\s")
        self.assertEqual(card, json.loads(base64.urlsafe_b64decode(payload).decode("utf-8")))

    def test_legacy_candidate_chain_is_read_only_and_cannot_grant_l1(self) -> None:
        self.assertEqual(
            (False, "LEGACY_CHAIN_READ_ONLY"),
            _l1_eligibility(fusion_mode="TRIMODAL", is_current_visit=True, is_fresh=True),
        )
        self.assertEqual(
            (False, "LEGACY_CHAIN_READ_ONLY"),
            _l1_eligibility(fusion_mode="VISUAL_TEXT_NO_AUDIO", is_current_visit=True, is_fresh=True),
        )
        self.assertEqual(
            (False, "LEGACY_CHAIN_READ_ONLY"),
            _l1_eligibility(fusion_mode="TRIMODAL", is_current_visit=False, is_fresh=True),
        )
        self.assertEqual(
            (False, "LEGACY_CHAIN_READ_ONLY"),
            _l1_eligibility(fusion_mode="TRIMODAL", is_current_visit=True, is_fresh=False),
        )

    def test_legacy_sender_cannot_invoke_adb_even_if_called_directly(self) -> None:
        self.assertEqual(
            (False, "LEGACY_CHAIN_READ_ONLY"),
            _send("adb", "serial", {"window_id": "legacy", "display_excerpt": "ignored"}),
        )
