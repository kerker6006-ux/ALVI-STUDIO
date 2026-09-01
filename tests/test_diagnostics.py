from __future__ import annotations

import tempfile
import unittest
import logging
from pathlib import Path

from dubstudio.diagnostics import configure_logging, get_logger
from dubstudio.storage import StorageLayout


class DiagnosticsTests(unittest.TestCase):
    def test_application_log_is_created_under_selected_root(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            layout = StorageLayout.create(directory)
            log_path = configure_logging(layout)
            get_logger("test").error("diagnostic-test-marker")
            self.assertEqual(log_path, layout.logs / "alvi-studio.log")
            self.assertIn("diagnostic-test-marker", log_path.read_text(encoding="utf-8"))
            log_path.resolve().relative_to(layout.root)
            logger = logging.getLogger("alvi_studio")
            for handler in list(logger.handlers):
                handler.close()
                logger.removeHandler(handler)


if __name__ == "__main__":
    unittest.main()
