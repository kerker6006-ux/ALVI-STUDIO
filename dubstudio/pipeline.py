from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .components import ComponentManager
from .project import DubProject, ProjectStore
from .storage import StorageLayout


ProgressCallback = Callable[[str, float, str], None]


class PipelineError(RuntimeError):
    pass


class MissingComponentError(PipelineError):
    pass


@dataclass(frozen=True)
class PipelineResult:
    project_file: Path
    output_file: Path | None


class DubbingPipeline:
    """Orchestrates a resumable project while inference runs out-of-process."""

    def __init__(self, layout: StorageLayout) -> None:
        self.layout = layout
        self.components = ComponentManager(layout)
        self.projects = ProjectStore(layout)

    def preflight(self, project: DubProject) -> None:
        self.layout.audit()
        media = Path(project.source_media)
        if not media.is_file():
            raise PipelineError(f"Input file does not exist: {media}")
        outside = [item for item in self.components.status(project.quality) if not item.ready]
        if outside:
            missing = "\n".join(f"• {item.name}: {item.detail}" for item in outside)
            raise MissingComponentError(
                "This quality pack is not ready yet. Open Storage & Models and install:\n" + missing
            )

    def run(self, project: DubProject, progress: ProgressCallback) -> PipelineResult:
        project.status = "running"
        project.current_stage = "Preflight"
        project.progress = 0.01
        project_file = self.projects.save(project)
        progress("Preflight", 0.01, "Checking storage, runtime and models")
        try:
            self.preflight(project)
            project_dir = project_file.parent
            request_file = project_dir / "worker-request.json"
            output_file = self.layout.exports / f"{project.title}-dubbed-{project.target_language}.mp4"
            request = {
                "project_file": str(project_file),
                "project_dir": str(project_dir),
                "storage_root": str(self.layout.root),
                "output_file": str(output_file),
            }
            request_file.write_text(json.dumps(request, indent=2), encoding="utf-8")
            project.current_stage = "AI processing"
            project.progress = 0.05
            self.projects.save(project)
            progress("AI processing", 0.05, "Starting the private model worker")
            self._run_worker(request_file, project, progress)
            project.status = "complete"
            project.current_stage = "Complete"
            project.progress = 1.0
            self.projects.save(project)
            progress("Complete", 1.0, str(output_file))
            return PipelineResult(project_file, output_file)
        except Exception as exc:
            project.status = "failed"
            project.current_stage = "Failed"
            project.error = str(exc)
            self.projects.save(project)
            raise

    def _run_worker(
        self,
        request_file: Path,
        project: DubProject,
        progress: ProgressCallback,
    ) -> None:
        python = self.components.engine_python()
        if not python:
            raise MissingComponentError("Private AI runtime is not installed")
        command = [str(python), "-m", "dubstudio.worker", "--request", str(request_file)]
        environment = dict(__import__("os").environ)
        process = subprocess.Popen(
            command,
            cwd=str(request_file.parent),
            env=environment,
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
            if not line:
                continue
            try:
                event = json.loads(line)
            except ValueError:
                progress(project.current_stage, project.progress, line)
                continue
            stage = str(event.get("stage", project.current_stage))
            value = float(event.get("progress", project.progress))
            message = str(event.get("message", ""))
            project.current_stage = stage
            project.progress = max(0.0, min(1.0, value))
            self.projects.save(project)
            progress(stage, project.progress, message)
        return_code = process.wait()
        if return_code:
            raise PipelineError(f"AI worker stopped with exit code {return_code}")

