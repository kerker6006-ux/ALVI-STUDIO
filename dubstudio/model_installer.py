from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable

from .components import MODEL_PACKS, ComponentManager
from .storage import StorageLayout


Reporter = Callable[[str, float], None]

PARLER_SOURCE = "https://github.com/huggingface/parler-tts/archive/refs/heads/main.zip"


class InstallError(RuntimeError):
    pass


def _download(url: str, destination: Path, reporter: Reporter, start: float, end: float) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "Alvi-Studio/0.1"})
    with urllib.request.urlopen(request, timeout=60) as response, destination.open("wb") as target:
        total = int(response.headers.get("Content-Length", "0"))
        received = 0
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            target.write(chunk)
            received += len(chunk)
            ratio = received / total if total else 0.5
            reporter(f"Downloading {destination.name}", start + (end - start) * ratio)


def _extract_single_root(archive: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.parent / f".{destination.name}-extracting"
    if temp.exists():
        shutil.rmtree(temp)
    temp.mkdir(parents=True)
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(temp)
    roots = [item for item in temp.iterdir() if item.is_dir()]
    source = roots[0] if len(roots) == 1 else temp
    if destination.exists():
        shutil.rmtree(destination)
    shutil.move(str(source), str(destination))
    if temp.exists():
        shutil.rmtree(temp)


def _run_pip(python: Path, arguments: list[str], layout: StorageLayout, reporter: Reporter) -> None:
    command = [str(python), "-m", "pip", "--disable-pip-version-check", *arguments]
    process = subprocess.Popen(
        command,
        cwd=str(layout.root),
        env=dict(os.environ),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    assert process.stdout is not None
    for line in process.stdout:
        line = line.strip()
        if line:
            reporter(line[-180:], 0.08)
    if process.wait():
        raise InstallError("Python engine dependency installation failed")


def install_pack(layout: StorageLayout, pack_id: str, token: str, reporter: Reporter) -> None:
    if pack_id not in MODEL_PACKS:
        raise InstallError(f"Unknown model pack: {pack_id}")
    pack = MODEL_PACKS[pack_id]
    free_gb = shutil.disk_usage(layout.root).free / (1024**3)
    required_gb = float(pack["approx_gb"]) + 8.0
    if free_gb < required_gb:
        raise InstallError(f"Not enough free space on selected drive. Need {required_gb:.0f} GB; found {free_gb:.1f} GB.")

    manager = ComponentManager(layout)
    python = manager.engine_python()
    if not python:
        raise InstallError("The private Python runtime was not bundled with this installation")

    reporter("Installing private engine dependencies", 0.02)
    requirements = layout.path("app/requirements-engine.txt")
    if not requirements.is_file():
        requirements = Path(__file__).resolve().parents[1] / "requirements-engine.txt"
    _run_pip(
        python,
        [
            "install",
            "--upgrade",
            "--cache-dir",
            str(layout.path("cache/pip")),
            "-r",
            str(requirements),
        ],
        layout,
        reporter,
    )

    temp = layout.path("temp/model-installer")
    temp.mkdir(parents=True, exist_ok=True)
    parler_zip = temp / "parler-tts.zip"
    if not parler_zip.is_file():
        _download(PARLER_SOURCE, parler_zip, reporter, 0.08, 0.10)
    parler_source = temp / "parler-tts"
    _extract_single_root(parler_zip, parler_source)
    _run_pip(
        python,
        ["install", "--cache-dir", str(layout.path("cache/pip")), str(parler_source)],
        layout,
        reporter,
    )

    from huggingface_hub import snapshot_download

    models = [item for item in pack["models"] if item != "kwatcharasupat/bandit-v2"]
    revisions: dict[str, str] = {}
    for index, repository in enumerate(models):
        destination = layout.path("models/hf") / Path(*repository.split("/"))
        destination.mkdir(parents=True, exist_ok=True)
        progress = 0.12 + 0.70 * (index / max(1, len(models)))
        reporter(f"Downloading {repository}", progress)
        snapshot_download(
            repo_id=repository,
            local_dir=str(destination),
            token=token or None,
            cache_dir=str(layout.path("cache/huggingface/hub")),
            local_dir_use_symlinks=False,
        )
        revisions[repository] = "downloaded"

    if pack_id in {"fast", "balanced", "studio"}:
        reporter("Downloading verified Bandit v2 cinematic separation weights", 0.88)
        # bandit-infer validates the official checkpoint with SHA-256 and honors
        # BANDIT_INFER_WEIGHTS, which StorageLayout locks beneath the chosen root.
        from bandit_infer import BanditSession

        session = BanditSession(
            "v2-multi",
            device="auto",
            weights_dir=layout.path("models/weights/bandit-infer"),
        )
        try:
            session.load()
        finally:
            session.close()
        revisions["kwatcharasupat/bandit-v2"] = "verified-by-bandit-infer"

    manager.mark_pack_ready(pack_id, revisions)
    reporter("Model pack is ready", 1.0)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--pack", required=True, choices=MODEL_PACKS)
    parser.add_argument("--token", default="")
    args = parser.parse_args()
    layout = StorageLayout.create(args.root)

    def report(message: str, progress: float) -> None:
        print(json.dumps({"message": message, "progress": progress}), flush=True)

    try:
        install_pack(layout, args.pack, args.token, report)
    except Exception as exc:
        print(json.dumps({"error": str(exc)}), flush=True)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
