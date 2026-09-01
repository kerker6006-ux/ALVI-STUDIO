from __future__ import annotations

import hashlib
import json
import os
import subprocess
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .constants import APP_VERSION
from .storage import StorageLayout


@dataclass(frozen=True)
class UpdateInfo:
    version: str
    notes: str
    installer_url: str
    checksum_url: str


def _version(value: str) -> tuple[int, ...]:
    clean = value.strip().lower().lstrip("v")
    parts: list[int] = []
    for piece in clean.split("."):
        number = "".join(char for char in piece if char.isdigit())
        parts.append(int(number or "0"))
    return tuple(parts)


class GitHubUpdater:
    INSTALLER_NAME = "Alvi-Studio-Setup.exe"
    CHECKSUM_NAME = "Alvi-Studio-Setup.exe.sha256"

    def __init__(self, layout: StorageLayout, repository: str, expected_publisher: str = "") -> None:
        self.layout = layout
        self.repository = repository.strip().strip("/")
        self.expected_publisher = expected_publisher.strip()

    def check(self) -> UpdateInfo | None:
        if not self.repository or "/" not in self.repository:
            return None
        url = f"https://api.github.com/repos/{self.repository}/releases/latest"
        request = urllib.request.Request(
            url,
            headers={"Accept": "application/vnd.github+json", "User-Agent": "Alvi-Studio-Updater"},
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            release = json.load(response)
        remote = str(release.get("tag_name", "")).lstrip("v")
        if not remote or _version(remote) <= _version(APP_VERSION):
            return None
        assets = {asset["name"]: asset["browser_download_url"] for asset in release.get("assets", [])}
        if self.INSTALLER_NAME not in assets or self.CHECKSUM_NAME not in assets:
            raise RuntimeError("The latest GitHub release does not contain signed Alvi Studio update assets")
        return UpdateInfo(
            version=remote,
            notes=str(release.get("body", "")),
            installer_url=assets[self.INSTALLER_NAME],
            checksum_url=assets[self.CHECKSUM_NAME],
        )

    def download(self, update: UpdateInfo) -> Path:
        destination = self.layout.updates / f"Alvi-Studio-{update.version}-Setup.exe"
        checksum_file = self.layout.updates / f"Alvi-Studio-{update.version}.sha256"
        self._download(update.installer_url, destination)
        self._download(update.checksum_url, checksum_file)
        expected = checksum_file.read_text(encoding="utf-8").strip().split()[0].lower()
        digest = hashlib.sha256()
        with destination.open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
        if digest.hexdigest().lower() != expected:
            destination.unlink(missing_ok=True)
            raise RuntimeError("Update checksum verification failed")
        self._verify_authenticode(destination)
        return destination

    def install_on_exit(self, installer: Path) -> None:
        self.layout._assert_inside(installer.resolve())
        subprocess.Popen(
            [str(installer), "/S", f"/D={self.layout.root}"],
            cwd=str(self.layout.updates),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

    def _download(self, url: str, destination: Path) -> None:
        request = urllib.request.Request(url, headers={"User-Agent": "Alvi-Studio-Updater"})
        with urllib.request.urlopen(request, timeout=60) as response, destination.open("wb") as output:
            while True:
                block = response.read(1024 * 1024)
                if not block:
                    break
                output.write(block)

    def _verify_authenticode(self, installer: Path) -> None:
        if not self.expected_publisher:
            # GitHub HTTPS + SHA-256 is usable for development releases. Public
            # auto-installation is enabled only after a publisher is configured.
            raise RuntimeError(
                "Update downloaded safely, but automatic installation is disabled until a Windows code-signing publisher is configured"
            )
        command = (
            "$signature = Get-AuthenticodeSignature -LiteralPath $args[0]; "
            "if ($signature.Status -ne 'Valid') { exit 2 }; "
            "$signature.SignerCertificate.Subject"
        )
        process = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", command, str(installer)],
            capture_output=True,
            text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if process.returncode or self.expected_publisher.lower() not in process.stdout.lower():
            installer.unlink(missing_ok=True)
            raise RuntimeError("Update has an invalid or unexpected Windows code signature")


def load_update_config() -> dict[str, str]:
    candidates = [
        Path(os.environ.get("ALVI_STUDIO_HOME") or os.environ.get("DUBSTUDIO_HOME", "."))
        / "app"
        / "update-config.json",
        Path(__file__).resolve().parent / "assets" / "update-config.json",
    ]
    for candidate in candidates:
        if candidate.is_file():
            try:
                data = json.loads(candidate.read_text(encoding="utf-8"))
                return {str(key): str(value) for key, value in data.items()}
            except (OSError, ValueError):
                continue
    return {"repository": "", "expected_publisher": ""}
