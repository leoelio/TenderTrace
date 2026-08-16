from __future__ import annotations

import unittest

from tendertrace.adapters.canadabuys import CanadaBuysAdapter, parse_open_tenders


CSV_TEXT = '''title-titre-eng,title-titre-fra,referenceNumber-numeroReference,solicitationNumber-numeroSollicitation,publicationDate-datePublication,tenderClosingDate-appelOffresDateCloture,tenderStatus-appelOffresStatut-eng,noticeType-avisType-eng,procurementMethod-methodeApprovisionnement-eng,regionsOfOpportunity-regionAppelOffres-eng,regionsOfDelivery-regionsLivraison-eng,contractingEntityName-nomEntitContractante-eng,noticeURL-URLavis-eng,attachment-piecesJointes-eng,tenderDescription-descriptionAppelOffres-eng,unspscDescription-eng,contactInfoEmail-informationsContactCourriel,contactInfoPhone-contactInfoTelephone
Data centre server refresh,,PW-001,SOL-001,2026-08-14,2026-09-02T14:00:00,Open,Request for Proposal,Open Tendering,Ontario,Ontario,Shared Services Canada,https://canadabuys.canada.ca/en/tender-opportunities/tender-notice/pw-001,"https://canadabuys.canada.ca/docs/spec.pdf, https://canadabuys.canada.ca/docs/pricing.xlsx",Supply and support of rack servers,Computer servers,private@example.invalid,000-000-0000
Office furniture supply,,PW-002,SOL-002,2026-08-13,2026-09-03T14:00:00,Open,Request for Proposal,Open Tendering,Quebec,Quebec,Example Department,https://canadabuys.canada.ca/en/tender-opportunities/tender-notice/pw-002,,Supply of office furniture,Furniture,,
Historical server notice,,PW-003,SOL-003,2026-05-01,2026-05-20T14:00:00,Open,Request for Proposal,Open Tendering,Alberta,Alberta,Example Department,https://canadabuys.canada.ca/en/tender-opportunities/tender-notice/pw-003,,Legacy server supply,Computer servers,,
'''


class CanadaBuysAdapterTests(unittest.TestCase):
    def test_parser_filters_topic_and_window_and_preserves_public_evidence(self) -> None:
        notices = parse_open_tenders(
            CSV_TEXT,
            {
                "topic": {"source_terms": ["server"]},
                "time": {"resolved_window": {"from": "2026-08-01", "to": "2026-08-16"}},
            },
            max_results=5,
        )

        self.assertEqual(len(notices), 1)
        notice = notices[0]
        self.assertEqual(notice.source_site, "canadabuys")
        self.assertEqual(notice.publish_time, "2026-08-14")
        self.assertEqual(notice.region, "Ontario")
        self.assertEqual(notice.purchaser, "Shared Services Canada")
        self.assertEqual(notice.fields["deadline"], "2026-09-02")
        self.assertEqual(notice.fields["reference_number"], "PW-001")
        self.assertEqual(len(notice.attachments), 2)
        self.assertNotIn("contact", str(notice.fields).casefold())
        self.assertNotIn("example.invalid", str(notice.to_dict()))

    def test_parser_rejects_non_dataset_response(self) -> None:
        with self.assertRaisesRegex(ValueError, "schema"):
            parse_open_tenders("<html>Access denied</html>", {})

    def test_adapter_routes_only_canada_and_global_scope(self) -> None:
        adapter = CanadaBuysAdapter()

        self.assertTrue(adapter.supports({"region": {"scope": "canada"}}))
        self.assertTrue(adapter.supports({"region": {"scope": "global"}}))
        self.assertFalse(adapter.supports({"region": {"scope": "domestic"}}))


if __name__ == "__main__":
    unittest.main()
