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
        self.assertEqual(settings.vector_model, "BAAI/bge-small-zh-v1.5")
        self.assertIn("openai_key_configured", settings.safe_summary())
        self.assertIn("openai_api_style", settings.safe_summary())
        self.assertIn("attachment_max_bytes", settings.safe_summary())
        self.assertIn("vector_enabled", settings.safe_summary())
        self.assertNotIn("smtp_password", settings.safe_summary())
        self.assertFalse(settings.safe_summary()["smtp_password_configured"])

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
        self.assertEqual(settings.feishu_timeout, 9)
        self.assertEqual(settings.public_base_url, "https://tt.example.com")
        self.assertTrue(summary["feishu_app_secret_configured"])
        self.assertNotIn("secret-feishu-value", str(summary))


if __name__ == "__main__":
    unittest.main()
