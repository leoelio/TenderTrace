from __future__ import annotations

import unittest

from tendertrace.source_trust import assess_notice_trust


class SourceTrustTests(unittest.TestCase):
    def test_official_corroborated_notice_with_attachment_is_high_trust(self) -> None:
        assessment = assess_notice_trust(
            {
                "source_site": "official",
                "source_sites": ["official", "second_official"],
                "attachment_snapshots": [
                    {
                        "status": "extracted",
                        "sha256": "b" * 64,
                        "text_length": 500,
                    }
                ],
            },
            {
                "status": "passed",
                "quality_score": 0.95,
                "snapshot_sha256": "a" * 64,
            },
            profiles={"official": _profile("official_primary", runs=20, reliability=0.95)},
        )

        self.assertGreaterEqual(assessment["score"], 90)
        self.assertEqual(assessment["level"], "high")
        self.assertEqual(assessment["verification_status"], "corroborated")
        self.assertEqual(assessment["source_count"], 2)
        self.assertEqual(assessment["attachment_evidence"]["status"], "verified")

    def test_zero_sample_source_is_explicitly_unobserved(self) -> None:
        assessment = assess_notice_trust(
            {"source_site": "official"},
            {
                "status": "passed",
                "quality_score": 1,
                "snapshot_sha256": "a" * 64,
            },
            profiles={"official": _profile("official_primary", runs=0, reliability=None)},
        )

        observed = assessment["observed_reliability"]
        self.assertEqual(observed["status"], "unobserved")
        self.assertIsNone(observed["score"])
        self.assertIn("未计为已验证可靠", assessment["basis"][1])
        self.assertLess(assessment["score"], 80)

    def test_single_aggregator_is_lower_than_corroborated_official_source(self) -> None:
        aggregator = assess_notice_trust(
            {"source_site": "aggregator"},
            {
                "status": "passed",
                "quality_score": 0.9,
                "snapshot_sha256": "a" * 64,
            },
            profiles={
                "aggregator": _profile(
                    "authenticated_aggregator",
                    runs=20,
                    reliability=1,
                )
            },
        )
        official = assess_notice_trust(
            {
                "source_site": "official",
                "source_sites": ["official", "second_official"],
                "attachment_snapshots": [
                    {"status": "downloaded", "sha256": "b" * 64}
                ],
            },
            {
                "status": "passed",
                "quality_score": 0.9,
                "snapshot_sha256": "a" * 64,
            },
            profiles={"official": _profile("official_primary", runs=20, reliability=1)},
        )

        self.assertLess(aggregator["score"], official["score"])
        self.assertEqual(aggregator["source_count"], 1)
        self.assertEqual(aggregator["verification_status"], "evidence_only")

    def test_observed_failures_reduce_trust_and_are_explained(self) -> None:
        assessment = assess_notice_trust(
            {"source_site": "official"},
            {
                "status": "passed",
                "quality_score": 1,
                "snapshot_sha256": "a" * 64,
            },
            profiles={"official": _profile("official_primary", runs=10, reliability=0.2)},
        )

        reliability = next(
            item for item in assessment["components"] if item["key"] == "reliability"
        )
        self.assertEqual(reliability["score"], 4)
        self.assertIn("20%", reliability["evidence"])
        self.assertEqual(assessment["level"], "low")


def _profile(source_class: str, *, runs: int, reliability: float | None) -> dict[str, object]:
    return {
        "authority": "测试权威来源",
        "source_class": source_class,
        "observed_runs": runs,
        "reliability_score": reliability,
        "health_status": "healthy" if reliability and reliability >= 0.85 else "unhealthy",
    }


if __name__ == "__main__":
    unittest.main()
