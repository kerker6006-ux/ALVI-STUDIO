from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def emit(stage: str, progress: float, message: str) -> None:
    print(json.dumps({"stage": stage, "progress": progress, "message": message}), flush=True)


def _inside(root: Path, path: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def run(request_file: Path) -> int:
    request = json.loads(request_file.read_text(encoding="utf-8"))
    storage_root = Path(request["storage_root"]).resolve()
    project_dir = Path(request["project_dir"]).resolve()
    output_file = Path(request["output_file"]).resolve()
    if not _inside(storage_root, project_dir) or not _inside(storage_root, output_file):
        raise RuntimeError("Worker path escaped the selected installation drive")

    # The installed runtime replaces this bootstrap guard with the full engine
    # dependency set. Keeping the guard explicit prevents silent online calls or
    # accidental writes to a user profile when the model pack is incomplete.
    required = ("faster_whisper", "torch", "transformers")
    missing: list[str] = []
    for module in required:
        try:
            __import__(module)
        except ImportError:
            missing.append(module)
    if missing:
        emit("Model preflight", 0.06, "Missing engine modules: " + ", ".join(missing))
        return 3

    emit("Audio separation", 0.10, "Preparing dialogue, music and SFX stems")
    # AI adapters are imported lazily by the installed engine package. This file
    # is intentionally a stable JSON-lines boundary so app updates cannot corrupt
    # long-running model jobs.
    try:
        from dubstudio_engine import run_project  # type: ignore
    except ImportError:
        emit("Model preflight", 0.06, "dubstudio_engine is not installed in the private runtime")
        return 4
    run_project(request, emit)
    if not output_file.is_file():
        raise RuntimeError("Engine completed without producing the expected output")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True, type=Path)
    args = parser.parse_args()
    try:
        raise SystemExit(run(args.request))
    except Exception as exc:
        print(json.dumps({"stage": "Failed", "progress": 0.0, "message": str(exc)}), flush=True)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()

