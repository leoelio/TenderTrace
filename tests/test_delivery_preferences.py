from pathlib import Path
import tempfile
import unittest

from tendertrace.config import Settings
from tendertrace.db import init_db
from tendertrace.delivery.preferences import (
    load_feishu_receiver,
    resolve_feishu_receiver,
    save_feishu_receiver,
)


class DeliveryPreferenceTests(unittest.TestCase):
    def test_feishu_receiver_is_persisted_and_safe_summary_hides_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings.load(Path(tmp))
            init_db(settings)
            saved = save_feishu_receiver(
                settings,
                receive_id="oc-private-chat",
                receive_id_type="chat_id",
                label="项目通知群",
            )
            loaded = load_feishu_receiver(settings)
            receive_id, receive_id_type = resolve_feishu_receiver(settings)

        self.assertEqual(loaded, saved)
        self.assertEqual((receive_id, receive_id_type), ("oc-private-chat", "chat_id"))
        self.assertEqual(saved.safe_dict()["label"], "项目通知群")
        self.assertNotIn("oc-private-chat", str(saved.safe_dict()))


if __name__ == "__main__":
    unittest.main()
