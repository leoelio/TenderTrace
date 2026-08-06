from pathlib import Path
import tempfile
import unittest

from tendertrace.config import Settings
from tendertrace.db import init_db
from tendertrace.vector import build_notice_embeddings, vector_coverage


class VectorTests(unittest.TestCase):
    def test_vector_embedding_is_disabled_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings.load(Path(tmp))
            init_db(settings)
            result = build_notice_embeddings(settings)
            coverage = vector_coverage(settings)

        self.assertEqual(result.status, "disabled")
        self.assertFalse(coverage["enabled"])
        self.assertEqual(coverage["embedded_notices"], 0)


if __name__ == "__main__":
    unittest.main()
