from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from .constants import APP_NAME, DIRECTORIES


class StorageViolation(RuntimeError):
    """Raised when an application-managed path escapes the selected root."""


def _executable_directory() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def resolve_storage_root(explicit: str | Path | None = None) -> Path:
    """Resolve the one root used by every large or user-controlled artifact.

    Precedence is explicit argument, ALVI_STUDIO_HOME (plus the legacy alias),
    an installer marker beside the executable, and finally a development-only
    folder in the source tree.
    No AppData or user-profile fallback is used.
    """

    if explicit:
        return Path(explicit).expanduser().resolve()

    configured = os.environ.get("ALVI_STUDIO_HOME") or os.environ.get("DUBSTUDIO_HOME")
    if configured:
        return Path(configured).expanduser().resolve()

    exe_dir = _executable_directory()
    marker = exe_dir / "storage-root.json"
    if marker.is_file():
        try:
            payload = json.loads(marker.read_text(encoding="utf-8"))
            selected = payload.get("storage_root")
            if selected:
                return Path(selected).expanduser().resolve()
        except (OSError, ValueError, TypeError):
            # Version 0.1 installers wrote unescaped Windows backslashes. A
            # malformed marker must never prevent the desktop UI from opening.
            pass

    if getattr(sys, "frozen", False):
        return exe_dir.resolve()
    return (exe_dir / "Alvi-Studio-data").resolve()


@dataclass(frozen=True)
class StorageLayout:
    root: Path

    @classmethod
    def create(cls, explicit: str | Path | None = None) -> "StorageLayout":
        layout = cls(resolve_storage_root(explicit))
        layout.ensure()
        layout.apply_environment()
        layout.audit()
        return layout

    def path(self, relative: str) -> Path:
        candidate = (self.root / relative).resolve()
        self._assert_inside(candidate)
        return candidate

    @property
    def models(self) -> Path:
        return self.path("models")

    @property
    def projects(self) -> Path:
        return self.path("projects")

    @property
    def exports(self) -> Path:
        return self.path("exports")

    @property
    def temp(self) -> Path:
        return self.path("temp")

    @property
    def logs(self) -> Path:
        return self.path("logs")

    @property
    def updates(self) -> Path:
        return self.path("updates")

    def ensure(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        for directory in DIRECTORIES:
            self.path(directory).mkdir(parents=True, exist_ok=True)
        marker = self.root / "storage-root.json"
        marker.write_text(
            json.dumps(
                {
                    "application": APP_NAME,
                    "storage_root": str(self.root),
                    "policy": "all-application-managed-data-here",
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    def apply_environment(self) -> None:
        values = {
            "ALVI_STUDIO_HOME": self.root,
            "DUBSTUDIO_HOME": self.root,
            "HF_HOME": self.path("cache/huggingface"),
            "HUGGINGFACE_HUB_CACHE": self.path("cache/huggingface/hub"),
            "TRANSFORMERS_CACHE": self.path("cache/transformers"),
            "TORCH_HOME": self.path("cache/torch"),
            "BANDIT_INFER_WEIGHTS": self.path("models/weights/bandit-infer"),
            "XDG_CACHE_HOME": self.path("cache"),
            "TMP": self.temp,
            "TEMP": self.temp,
            "TMPDIR": self.temp,
        }
        for name, value in values.items():
            Path(value).mkdir(parents=True, exist_ok=True)
            os.environ[name] = str(value)

    def audit(self) -> list[Path]:
        checked = [self.root]
        for directory in DIRECTORIES:
            checked.append(self.path(directory))
        for variable in (
            "ALVI_STUDIO_HOME",
            "DUBSTUDIO_HOME",
            "HF_HOME",
            "HUGGINGFACE_HUB_CACHE",
            "TRANSFORMERS_CACHE",
            "TORCH_HOME",
            "BANDIT_INFER_WEIGHTS",
            "XDG_CACHE_HOME",
            "TMP",
            "TEMP",
            "TMPDIR",
        ):
            value = os.environ.get(variable)
            if value:
                candidate = Path(value).resolve()
                self._assert_inside(candidate)
                checked.append(candidate)
        return checked

    def _assert_inside(self, candidate: Path) -> None:
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise StorageViolation(
                f"Application path escaped the selected storage root: {candidate}"
            ) from exc


def write_installer_marker(install_dir: Path) -> None:
    """Write the marker consumed by packaged builds after installation."""

    install_dir = install_dir.resolve()
    install_dir.mkdir(parents=True, exist_ok=True)
    (install_dir / "storage-root.json").write_text(
        json.dumps({"application": APP_NAME, "storage_root": str(install_dir)}, indent=2),
        encoding="utf-8",
    )
