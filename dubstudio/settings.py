from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from .storage import StorageLayout


@dataclass
class AppSettings:
    source_language: str = "auto"
    target_language: str = "hi"
    quality: str = "Studio"
    keep_music: bool = True
    keep_sfx: bool = True
    preserve_reactions: bool = True
    voice_volume: float = 1.0
    music_volume: float = 0.72
    sfx_volume: float = 0.88
    original_dialogue_volume: float = 0.0
    master_volume: float = 1.0
    output_directory: str = ""
    github_repository: str = ""
    update_channel: str = "stable"


class SettingsStore:
    def __init__(self, layout: StorageLayout) -> None:
        self.layout = layout
        self.file = layout.path("settings.json")

    def load(self) -> AppSettings:
        if not self.file.is_file():
            settings = AppSettings(output_directory=str(self.layout.exports))
            self.save(settings)
            return settings
        try:
            payload = json.loads(self.file.read_text(encoding="utf-8"))
            allowed = AppSettings.__dataclass_fields__.keys()
            clean = {key: value for key, value in payload.items() if key in allowed}
            settings = AppSettings(**clean)
            if not settings.output_directory:
                settings.output_directory = str(self.layout.exports)
            return settings
        except (OSError, ValueError, TypeError):
            return AppSettings(output_directory=str(self.layout.exports))

    def save(self, settings: AppSettings) -> None:
        output = Path(settings.output_directory or self.layout.exports).resolve()
        self.layout._assert_inside(output)
        output.mkdir(parents=True, exist_ok=True)
        self.file.write_text(json.dumps(asdict(settings), indent=2), encoding="utf-8")

