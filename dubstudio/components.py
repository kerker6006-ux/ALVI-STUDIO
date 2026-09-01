from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from .storage import StorageLayout


@dataclass(frozen=True)
class ComponentStatus:
    component_id: str
    name: str
    ready: bool
    location: Path
    detail: str


MODEL_PACKS = {
    "fast": {
        "name": "Fast model pack",
        "approx_gb": 14,
        "models": [
            "Systran/faster-whisper-small",
            "google/madlad400-3b-mt",
            "ai4bharat/indic-parler-tts",
            "kwatcharasupat/bandit-v2",
        ],
    },
    "balanced": {
        "name": "Balanced model pack",
        "approx_gb": 19,
        "models": [
            "Systran/faster-whisper-large-v3",
            "google/madlad400-3b-mt",
            "ai4bharat/indic-parler-tts",
            "pyannote/speaker-diarization-community-1",
            "kwatcharasupat/bandit-v2",
        ],
    },
    "studio": {
        "name": "Studio model pack",
        "approx_gb": 22,
        "models": [
            "Systran/faster-whisper-large-v3",
            "FunAudioLLM/SenseVoiceSmall",
            "google/madlad400-3b-mt",
            "ai4bharat/indic-parler-tts",
            "pyannote/speaker-diarization-community-1",
            "kwatcharasupat/bandit-v2",
        ],
    },
}


class ComponentManager:
    def __init__(self, layout: StorageLayout) -> None:
        self.layout = layout

    def ffmpeg(self) -> Path | None:
        candidates = (
            self.layout.path("tools/ffmpeg/bin/ffmpeg.exe"),
            self.layout.path("tools/ffmpeg/ffmpeg.exe"),
        )
        for candidate in candidates:
            if candidate.is_file():
                return candidate
        system = shutil.which("ffmpeg")
        return Path(system).resolve() if system else None

    def ffprobe(self) -> Path | None:
        candidates = (
            self.layout.path("tools/ffmpeg/bin/ffprobe.exe"),
            self.layout.path("tools/ffmpeg/ffprobe.exe"),
        )
        for candidate in candidates:
            if candidate.is_file():
                return candidate
        system = shutil.which("ffprobe")
        return Path(system).resolve() if system else None

    def engine_python(self) -> Path | None:
        candidates = (
            self.layout.path("runtime/python/python.exe"),
            self.layout.path("runtime/python/python3.exe"),
        )
        for candidate in candidates:
            if candidate.is_file():
                return candidate
        return None

    def pack_marker(self, pack_id: str) -> Path:
        return self.layout.path(f"models/packs/{pack_id}.json")

    def pack_ready(self, pack_id: str) -> bool:
        marker = self.pack_marker(pack_id)
        if not marker.is_file():
            return False
        try:
            payload = json.loads(marker.read_text(encoding="utf-8"))
            return payload.get("status") == "ready" and payload.get("pack_id") == pack_id
        except (OSError, ValueError):
            return False

    def mark_pack_ready(self, pack_id: str, revisions: dict[str, str]) -> None:
        marker = self.pack_marker(pack_id)
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(
            json.dumps(
                {
                    "pack_id": pack_id,
                    "status": "ready",
                    "models": revisions,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    def status(self, quality: str) -> list[ComponentStatus]:
        pack_id = quality.lower()
        ffmpeg = self.ffmpeg()
        python = self.engine_python()
        pack = MODEL_PACKS.get(pack_id, MODEL_PACKS["studio"])
        return [
            ComponentStatus(
                "ffmpeg",
                "FFmpeg media tools",
                ffmpeg is not None,
                ffmpeg or self.layout.path("tools/ffmpeg"),
                "Ready" if ffmpeg else "Install into tools\\ffmpeg on the selected drive",
            ),
            ComponentStatus(
                "engine",
                "Private AI runtime",
                python is not None,
                python or self.layout.path("runtime/python"),
                "Ready" if python else "Runtime is not installed on the selected drive",
            ),
            ComponentStatus(
                f"pack-{pack_id}",
                pack["name"],
                self.pack_ready(pack_id),
                self.layout.path(f"models/packs/{pack_id}.json"),
                "Ready" if self.pack_ready(pack_id) else f"Requires about {pack['approx_gb']} GB",
            ),
        ]
