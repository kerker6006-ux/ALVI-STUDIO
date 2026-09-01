from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from dubstudio.project import DubProject, ProjectStore
from dubstudio.storage import StorageLayout


class ProjectTests(unittest.TestCase):
    def test_project_is_persisted_under_selected_root(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            layout = StorageLayout.create(directory)
            media = layout.path("temp/source.mp4")
            media.write_bytes(b"fixture")
            project = DubProject.new(
                source_media=media,
                source_language="zh",
                target_language="hi",
                quality="Studio",
                keep_music=True,
                keep_sfx=True,
                preserve_reactions=True,
                volumes={"voice": 1.0, "music": 0.7, "sfx": 0.9, "master": 1.0},
            )
            store = ProjectStore(layout)
            project_file = store.save(project)
            project_file.relative_to(layout.root)
            loaded = store.load(project_file)
            self.assertEqual(loaded.project_id, project.project_id)
            self.assertEqual(loaded.source_language, "zh")


if __name__ == "__main__":
    unittest.main()

