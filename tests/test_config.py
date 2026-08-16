from pathlib import Path
import tempfile
import unittest

from tendertrace.config import ConfigError, ModelMode, OpenAIAPIStyle, Settings


class SettingsTests(unittest.TestCase):
    def test_default_settings_are_local_and_safe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings.load(Path(tmp))
        self.assertEqual(settings.model_mode, ModelMode.LOCAL)
        self.assertFalse(settings.model_enhancement_enabled)
        self.assertEqual(settings.model_request_timeout, 8)
        self.assertEqual(settings.ollama_model, "qwen3:8b")
        self.assertFalse(settings.openai_api_key_present)
        self.assertEqual(settings.openai_model, "gpt-5.5")
        self.assertEqual(settings.openai_api_style, OpenAIAPIStyle.RESPONSES)
        self.assertEqual(settings.attachment_max_per_notice, 3)
        self.assertEqual(settings.attachment_max_bytes, 8388608)
        self.assertFalse(settings.vector_enabled)
        self.assertFalse(settings.feishu_lead_import_enabled)
        self.assertEqual(settings.feishu_lead_import_cron, "*/15 * * * *")
        self.assertEqual(settings.vector_model, "BAAI/bge-small-zh-v1.5")
        self.assertEqual(settings.qualification_min_opportunity_score, 65)
        self.assertEqual(settings.qualification_min_credibility, 60)
        self.assertEqual(settings.qualification_min_team_coverage, 60)
        self.assertEqual(settings.qualification_min_stakeholder_coverage, 50)
        self.assertEqual(settings.decision_sla_hours, 24)
        self.assertEqual(settings.change_review_sla_hours, 8)
        self.assertFalse(settings.opportunity_escalation_enabled)
        self.assertEqual(settings.opportunity_escalation_cron, "0 9,14 * * 1-5")
        self.assertFalse(settings.opportunity_briefing_enabled)
        self.assertEqual(settings.opportunity_briefing_cron, "45 8 * * 1-5")
        self.assertFalse(settings.feishu_task_sync_enabled)
        self.assertEqual(settings.feishu_task_sync_cron, "*/10 * * * *")
        self.assertFalse(settings.opportunity_change_alert_enabled)
        self.assertEqual(settings.opportunity_change_alert_cron, "*/15 * * * *")
        self.assertFalse(settings.source_alert_enabled)
        self.assertEqual(settings.source_alert_cron, "15 */2 * * *")
        self.assertEqual(settings.source_alert_min_reliability, 0.75)
        self.assertEqual(settings.source_alert_stale_hours, 24)
        self.assertEqual(settings.source_incident_sla_hours, 4)
        self.assertFalse(settings.api_token_present)
        self.assertIn("openai_key_configured", settings.safe_summary())
        self.assertIn("openai_api_style", settings.safe_summary())
        self.assertIn("attachment_max_bytes", settings.safe_summary())
        self.assertIn("vector_enabled", settings.safe_summary())
        self.assertNotIn("smtp_password", settings.safe_summary())
        self.assertFalse(settings.safe_summary()["smtp_password_configured"])
        self.assertFalse(settings.safe_summary()["api_token_configured"])
        self.assertFalse(settings.safe_summary()["feishu_lead_import_enabled"])
        self.assertEqual(
            settings.safe_summary()["qualification_policy"]["decision_sla_hours"],
            24,
        )
        self.assertEqual(
            settings.safe_summary()["qualification_policy"]["change_review_sla_hours"],
            8,
        )
        self.assertFalse(
            settings.safe_summary()["qualification_policy"]["briefing_enabled"]
        )
        self.assertFalse(settings.safe_summary()["source_alert_enabled"])
        self.assertFalse(settings.safe_summary()["opportunity_change_alert_enabled"])

    def test_source_health_alert_requires_feishu_and_valid_ratio(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".env.local").write_text(
                "TENDERTRACE_SOURCE_ALERT_ENABLED=true\n",
                encoding="utf-8",
            )
            with self.assertRaises(ConfigError):
                Settings.load(root)

            (root / ".env.local").write_text(
                "TENDERTRACE_SOURCE_INCIDENT_SLA_HOURS=0\n",
                encoding="utf-8",
            )
            with self.assertRaises(ConfigError):
                Settings.load(root)

            (root / ".env.local").write_text(
                "TENDERTRACE_CHANGE_REVIEW_SLA_HOURS=0\n",
                encoding="utf-8",
            )
            with self.assertRaises(ConfigError):
                Settings.load(root)

            (root / ".env.local").write_text(
                "TENDERTRACE_SOURCE_ALERT_MIN_RELIABILITY=1.2\n",
                encoding="utf-8",
            )
            with self.assertRaises(ConfigError):
                Settings.load(root)

    def test_opportunity_briefing_schedule_is_configurable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".env.local").write_text(
                "TENDERTRACE_OPPORTUNITY_BRIEFING_ENABLED=true\n"
                "TENDERTRACE_OPPORTUNITY_BRIEFING_CRON=15 8 * * 1-5\n",
                encoding="utf-8",
            )
            settings = Settings.load(root)

        self.assertTrue(settings.opportunity_briefing_enabled)
        self.assertEqual(settings.opportunity_briefing_cron, "15 8 * * 1-5")

    def test_feishu_task_sync_requires_enabled_message_app(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".env.local").write_text(
                "TENDERTRACE_FEISHU_TASK_SYNC_ENABLED=true\n",
                encoding="utf-8",
            )
            with self.assertRaises(ConfigError):
                Settings.load(root)

            (root / ".env.local").write_text(
                "TENDERTRACE_OPPORTUNITY_CHANGE_ALERT_ENABLED=true\n",
                encoding="utf-8",
            )
            with self.assertRaises(ConfigError):
                Settings.load(root)

            (root / ".env.local").write_text(
                "FEISHU_ENABLED=true\n"
                "FEISHU_APP_ID=cli_test\n"
                "FEISHU_APP_SECRET=secret\n"
                "TENDERTRACE_FEISHU_TASK_SYNC_ENABLED=true\n"
                "TENDERTRACE_FEISHU_TASK_SYNC_CRON=*/5 * * * *\n"
                "TENDERTRACE_OPPORTUNITY_CHANGE_ALERT_ENABLED=true\n"
                "TENDERTRACE_OPPORTUNITY_CHANGE_ALERT_CRON=*/7 * * * *\n",
                encoding="utf-8",
            )
            settings = Settings.load(root)

        self.assertTrue(settings.feishu_task_sync_enabled)
        self.assertEqual(settings.feishu_task_sync_cron, "*/5 * * * *")
        self.assertTrue(settings.opportunity_change_alert_enabled)
        self.assertEqual(settings.opportunity_change_alert_cron, "*/7 * * * *")

    def test_qualification_policy_is_configurable_and_validated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".env.local").write_text(
                "TENDERTRACE_QUALIFICATION_MIN_OPPORTUNITY_SCORE=75\n"
                "TENDERTRACE_QUALIFICATION_MIN_CREDIBILITY=70\n"
                "TENDERTRACE_QUALIFICATION_MIN_COMPLETENESS=65\n"
                "TENDERTRACE_QUALIFICATION_MIN_REQUIREMENT_COVERAGE=50\n"
                "TENDERTRACE_QUALIFICATION_MIN_TEAM_COVERAGE=75\n"
                "TENDERTRACE_QUALIFICATION_MIN_STAKEHOLDER_COVERAGE=80\n"
                "TENDERTRACE_DECISION_SLA_HOURS=12\n"
                "TENDERTRACE_CHANGE_REVIEW_SLA_HOURS=6\n",
                encoding="utf-8",
            )
            settings = Settings.load(root)

        self.assertEqual(settings.qualification_min_opportunity_score, 75)
        self.assertEqual(settings.qualification_min_credibility, 70)
        self.assertEqual(settings.qualification_min_completeness, 65)
        self.assertEqual(settings.qualification_min_requirement_coverage, 50)
        self.assertEqual(settings.qualification_min_team_coverage, 75)
        self.assertEqual(settings.qualification_min_stakeholder_coverage, 80)
        self.assertEqual(settings.decision_sla_hours, 12)
        self.assertEqual(settings.change_review_sla_hours, 6)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".env.local").write_text(
                "TENDERTRACE_QUALIFICATION_MIN_CREDIBILITY=101\n",
                encoding="utf-8",
            )
            with self.assertRaises(ConfigError):
                Settings.load(root)

    def test_feishu_lead_import_requires_complete_bitable_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".env.local").write_text(
                "TENDERTRACE_FEISHU_LEAD_IMPORT_ENABLED=true\n",
                encoding="utf-8",
            )

            with self.assertRaises(ConfigError):
                Settings.load(root)

    def test_feishu_lead_import_schedule_is_configurable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".env.local").write_text(
                "TENDERTRACE_FEISHU_APP_ID=cli_test\n"
                "TENDERTRACE_FEISHU_APP_SECRET=secret\n"
                "TENDERTRACE_FEISHU_BITABLE_APP_TOKEN=base_test\n"
                "TENDERTRACE_FEISHU_BITABLE_TABLE_ID=tbl_test\n"
                "TENDERTRACE_FEISHU_LEAD_IMPORT_ENABLED=true\n"
                "TENDERTRACE_FEISHU_LEAD_IMPORT_CRON=*/5 * * * *\n",
                encoding="utf-8",
            )

            settings = Settings.load(root)

        self.assertTrue(settings.feishu_lead_import_enabled)
        self.assertEqual(settings.feishu_lead_import_cron, "*/5 * * * *")

    def test_cloud_mode_requires_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".env.local").write_text("TENDERTRACE_MODEL_MODE=cloud\n", encoding="utf-8")
            with self.assertRaises(ConfigError):
                Settings.load(root)

    def test_env_local_can_select_cloud_without_exposing_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".env.local").write_text(
                "TENDERTRACE_MODEL_MODE=cloud\nOPENAI_API_KEY=secret-value\nOPENAI_MODEL=test-model\n",
                encoding="utf-8",
            )
            settings = Settings.load(root)
        summary = settings.safe_summary()
        self.assertTrue(summary["openai_key_configured"])
        self.assertNotIn("secret-value", str(summary))

    def test_env_local_can_enable_vector_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".env.local").write_text(
                "TENDERTRACE_VECTOR_ENABLED=true\n"
                "TENDERTRACE_VECTOR_MODEL=test-vector\n"
                "TENDERTRACE_VECTOR_TOP_K=12\n",
                encoding="utf-8",
            )
            settings = Settings.load(root)
        self.assertTrue(settings.vector_enabled)
        self.assertEqual(settings.vector_model, "test-vector")
        self.assertEqual(settings.vector_top_k, 12)

    def test_env_local_can_configure_smtp_without_exposing_password(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".env.local").write_text(
                "TENDERTRACE_DELIVERY_CHANNELS=web,outbox,email\n"
                "TENDERTRACE_SMTP_HOST=smtp.example.com\n"
                "TENDERTRACE_SMTP_PORT=2525\n"
                "TENDERTRACE_SMTP_USERNAME=sender\n"
                "TENDERTRACE_SMTP_PASSWORD=secret-mail-password\n"
                "TENDERTRACE_SMTP_FROM=sender@example.com\n"
                "TENDERTRACE_SMTP_TO=a@example.com,b@example.com\n"
                "TENDERTRACE_SMTP_USE_TLS=false\n",
                encoding="utf-8",
            )
            settings = Settings.load(root)
        summary = settings.safe_summary()
        self.assertIn("email", settings.delivery_channels)
        self.assertEqual(settings.smtp_host, "smtp.example.com")
        self.assertEqual(settings.smtp_port, 2525)
        self.assertEqual(settings.smtp_to, ("a@example.com", "b@example.com"))
        self.assertFalse(settings.smtp_use_tls)
        self.assertTrue(summary["smtp_password_configured"])
        self.assertNotIn("secret-mail-password", str(summary))

    def test_env_local_can_configure_feishu_without_exposing_secret(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".env.local").write_text(
                "TENDERTRACE_DELIVERY_CHANNELS=web,outbox,feishu_bitable\n"
                "TENDERTRACE_FEISHU_APP_ID=cli_test\n"
                "TENDERTRACE_FEISHU_APP_SECRET=secret-feishu-value\n"
                "TENDERTRACE_FEISHU_BITABLE_APP_TOKEN=base_token\n"
                "TENDERTRACE_FEISHU_BITABLE_TABLE_ID=tbl_test\n"
                "TENDERTRACE_FEISHU_BITABLE_BASE_URL=https://tenant.feishu.cn/base/base_token\n"
                "TENDERTRACE_FEISHU_TIMEOUT=9\n"
                "TENDERTRACE_PUBLIC_BASE_URL=https://tt.example.com\n",
                encoding="utf-8",
            )
            settings = Settings.load(root)
        summary = settings.safe_summary()
        self.assertIn("feishu_bitable", settings.delivery_channels)
        self.assertEqual(settings.feishu_app_id, "cli_test")
        self.assertEqual(settings.feishu_bitable_app_token, "base_token")
        self.assertEqual(settings.feishu_bitable_table_id, "tbl_test")
        self.assertEqual(
            settings.feishu_bitable_base_url,
            "https://tenant.feishu.cn/base/base_token",
        )
        self.assertEqual(settings.feishu_timeout, 9)
        self.assertEqual(settings.public_base_url, "https://tt.example.com")
        self.assertTrue(summary["feishu_app_secret_configured"])
        self.assertEqual(
            summary["feishu_bitable_base_url"],
            "https://tenant.feishu.cn/base/base_token",
        )
        self.assertNotIn("secret-feishu-value", str(summary))

    def test_bitable_reuses_message_app_credentials_when_not_overridden(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".env.local").write_text(
                "FEISHU_ENABLED=true\n"
                "FEISHU_APP_ID=cli_shared\n"
                "FEISHU_APP_SECRET=shared-secret\n",
                encoding="utf-8",
            )
            settings = Settings.load(root)
            secret = settings.feishu_app_secret()
        summary = settings.safe_summary()
        self.assertEqual(settings.feishu_app_id, "cli_shared")
        self.assertEqual(secret, "shared-secret")
        self.assertTrue(summary["feishu_app_secret_configured"])
        self.assertNotIn("shared-secret", str(summary))

    def test_env_local_can_configure_api_token_without_exposing_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".env.local").write_text(
                "TENDERTRACE_API_TOKEN=local-api-token\n",
                encoding="utf-8",
            )
            settings = Settings.load(root)
            token = settings.api_token()
        summary = settings.safe_summary()
        self.assertTrue(settings.api_token_present)
        self.assertEqual(token, "local-api-token")
        self.assertTrue(summary["api_token_configured"])
        self.assertNotIn("local-api-token", str(summary))

    def test_prod_mode_requires_api_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".env.local").write_text("TENDERTRACE_APP_ENV=prod\n", encoding="utf-8")

            with self.assertRaises(ConfigError):
                Settings.load(root)

    def test_prod_mode_can_load_with_api_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".env.local").write_text(
                "TENDERTRACE_APP_ENV=prod\nTENDERTRACE_API_TOKEN=local-api-token\n",
                encoding="utf-8",
            )
            settings = Settings.load(root)

        self.assertEqual(settings.app_env, "prod")
        self.assertTrue(settings.api_token_present)


if __name__ == "__main__":
    unittest.main()
