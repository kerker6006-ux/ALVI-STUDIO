from __future__ import annotations

import json
import re
import secrets
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from .storage import StorageLayout


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _safe_name(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-.")
    return value[:60] or "untitled"


@dataclass
class DubProject:
    project_id: str
    title: str
    source_media: str
    source_language: str
    target_language: str
    quality: str
    keep_music: bool
    keep_sfx: bool
    preserve_reactions: bool
    volumes: dict[str, float]
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    status: str = "created"
    current_stage: str = "Waiting"
    progress: float = 0.0
    error: str = ""

    @classmethod
    def new(cls, *, source_media: Path, **values: object) -> "DubProject":
        return cls(
            project_id=f"{datetime.now():%Y%m%d-%H%M%S}-{secrets.token_hex(3)}",
            title=source_media.stem,
            source_media=str(source_media.resolve()),
            **values,
        )


class ProjectStore:
    def __init__(self, layout: StorageLayout) -> None:
        self.layout = layout

    def directory(self, project: DubProject) -> Path:
        directory = self.layout.projects / f"{project.project_id}-{_safe_name(project.title)}"
        directory.mkdir(parents=True, exist_ok=True)
        for name in ("audio", "stems", "transcript", "translations", "takes", "mix", "logs"):
            (directory / name).mkdir(exist_ok=True)
        return directory

    def save(self, project: DubProject) -> Path:
        project.updated_at = _now()
        destination = self.directory(project) / "project.json"
        destination.write_text(json.dumps(asdict(project), indent=2), encoding="utf-8")
        return destination

    def load(self, project_file: Path) -> DubProject:
        return DubProject(**json.loads(project_file.read_text(encoding="utf-8")))

    def recent(self, limit: int = 10) -> list[DubProject]:
        files = sorted(self.layout.projects.glob("*/project.json"), reverse=True)
        projects: list[DubProject] = []
        for file in files[:limit]:
            try:
                projects.append(self.load(file))
            except (OSError, ValueError, TypeError):
                continue
        return projects

