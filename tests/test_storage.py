from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from dubstudio.settings import AppSettings, SettingsStore
from dubstudio.storage import StorageLayout, StorageViolation, resolve_storage_root


class StorageTests(unittest.TestCase):
    def test_explicit_root_wins_and_every_environment_path_is_inside(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            with patch.dict(os.environ, {}, clear=False):
                layout = StorageLayout.create(directory)
                self.assertEqual(layout.root, Path(directory).resolve())
                checked = layout.audit()
                self.assertGreaterEqual(len(checked), 20)
                for item in checked:
                    item.resolve().relative_to(layout.root)

    def test_environment_root_is_respected(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            with patch.dict(os.environ, {"ALVI_STUDIO_HOME": directory}):
                self.assertEqual(resolve_storage_root(), Path(directory).resolve())

    def test_escape_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            layout = StorageLayout.create(directory)
            with self.assertRaises(StorageViolation):
                layout.path("../outside")

    def test_malformed_legacy_marker_falls_back_to_executable_folder(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory).resolve()
            # Recreate the original bug: single backslashes such as \s made
            # the installer's JSON invalid.
            (root / "storage-root.json").write_text(
                r'{"storage_root": "D:\studio\DubStudio"}', encoding="utf-8"
            )
            with patch.dict(os.environ, {"ALVI_STUDIO_HOME": "", "DUBSTUDIO_HOME": ""}):
                with patch("dubstudio.storage._executable_directory", return_value=root):
                    with patch.object(sys, "frozen", True, create=True):
                        self.assertEqual(resolve_storage_root(), root)

    def test_settings_cannot_redirect_exports_outside_root(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            layout = StorageLayout.create(directory)
            store = SettingsStore(layout)
            settings = AppSettings(output_directory=str(layout.root.parent / "outside"))
            with self.assertRaises(StorageViolation):
                store.save(settings)


if __name__ == "__main__":
    unittest.main()
