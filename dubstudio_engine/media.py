from __future__ import annotations

import json
import subprocess
from pathlib import Path


class MediaError(RuntimeError):
    pass


class MediaTools:
    def __init__(self, storage_root: Path) -> None:
        self.root = storage_root.resolve()
        self.ffmpeg = self._find("ffmpeg.exe")
        self.ffprobe = self._find("ffprobe.exe")

    def _find(self, executable: str) -> Path:
        candidates = (
            self.root / "tools" / "ffmpeg" / "bin" / executable,
            self.root / "tools" / "ffmpeg" / executable,
        )
        for candidate in candidates:
            if candidate.is_file():
                return candidate
        raise MediaError(f"{executable} is missing from {self.root / 'tools' / 'ffmpeg'}")

    def run(self, arguments: list[str], *, cwd: Path | None = None) -> None:
        process = subprocess.run(
            [str(self.ffmpeg), "-hide_banner", "-loglevel", "error", "-y", *arguments],
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if process.returncode:
            raise MediaError(process.stderr.strip() or "FFmpeg failed")

    def probe(self, path: Path) -> dict[str, object]:
        process = subprocess.run(
            [
                str(self.ffprobe),
                "-v",
                "error",
                "-show_entries",
                "format=duration:stream=index,codec_type,codec_name,channels,sample_rate",
                "-of",
                "json",
                str(path),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if process.returncode:
            raise MediaError(process.stderr.strip() or "FFprobe failed")
        return json.loads(process.stdout)

    def duration(self, path: Path) -> float:
        return float(self.probe(path).get("format", {}).get("duration", 0.0))  # type: ignore[union-attr]

    def extract_audio(self, source: Path, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        self.run(["-i", str(source), "-vn", "-ac", "2", "-ar", "48000", "-c:a", "pcm_s24le", str(destination)])

    def extract_clip(self, source: Path, start: float, end: float, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        self.run(
            [
                "-ss",
                f"{max(0.0, start):.3f}",
                "-to",
                f"{max(start, end):.3f}",
                "-i",
                str(source),
                "-ac",
                "1",
                "-ar",
                "16000",
                "-c:a",
                "pcm_s16le",
                str(destination),
            ]
        )

    def fit_duration(self, source: Path, destination: Path, target_seconds: float) -> None:
        actual = max(0.01, self.duration(source))
        target = max(0.05, target_seconds)
        tempo = actual / target
        filters: list[str] = []
        remaining = tempo
        while remaining > 2.0:
            filters.append("atempo=2.0")
            remaining /= 2.0
        while remaining < 0.5:
            filters.append("atempo=0.5")
            remaining /= 0.5
        filters.extend([f"atempo={remaining:.6f}", f"apad=pad_dur={target:.6f}", f"atrim=duration={target:.6f}"])
        self.run(["-i", str(source), "-af", ",".join(filters), "-ar", "48000", "-ac", "1", str(destination)])

    def make_silence(self, destination: Path, duration: float) -> None:
        self.run(
            [
                "-f",
                "lavfi",
                "-i",
                "anullsrc=r=48000:cl=mono",
                "-t",
                f"{max(0.001, duration):.6f}",
                "-c:a",
                "pcm_s16le",
                str(destination),
            ]
        )

    def concat(self, files: list[Path], destination: Path, list_file: Path) -> None:
        def quote(path: Path) -> str:
            return str(path.resolve()).replace("'", "'\\''")

        list_file.write_text("".join(f"file '{quote(path)}'\n" for path in files), encoding="utf-8")
        self.run(["-f", "concat", "-safe", "0", "-i", str(list_file), "-c:a", "pcm_s16le", str(destination)])

    def preserve_reactions(
        self,
        source: Path,
        spoken_ranges: list[tuple[float, float]],
        destination: Path,
    ) -> None:
        """Mute recognized words while retaining breaths, laughs and reactions."""

        filters = [
            f"volume=0:enable='between(t,{max(0.0, start - 0.04):.3f},{end + 0.04:.3f})'"
            for start, end in spoken_ranges
            if end > start
        ]
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not filters:
            self.run(["-i", str(source), "-c:a", "pcm_s24le", str(destination)])
            return
        self.run(["-i", str(source), "-af", ",".join(filters), "-c:a", "pcm_s24le", str(destination)])

    def final_mix(
        self,
        *,
        source_media: Path,
        dub: Path,
        original_dialogue: Path | None,
        reactions: Path | None,
        music: Path | None,
        sfx: Path | None,
        destination: Path,
        volumes: dict[str, float],
    ) -> None:
        inputs = ["-i", str(source_media), "-i", str(dub)]
        filters = [f"[1:a]volume={volumes.get('voice', 1.0):.4f}[voice]"]
        mix_labels = ["[voice]"]
        index = 2
        original_level = volumes.get("original_dialogue", 0.0)
        if original_dialogue and original_level > 0.0001:
            inputs.extend(["-i", str(original_dialogue)])
            filters.append(f"[{index}:a]volume={original_level:.4f}[original]")
            mix_labels.append("[original]")
            index += 1
        if reactions and original_level <= 0.0001:
            inputs.extend(["-i", str(reactions)])
            filters.append(f"[{index}:a]volume={volumes.get('sfx', 0.88):.4f}[reactions]")
            mix_labels.append("[reactions]")
            index += 1
        if music:
            inputs.extend(["-i", str(music)])
            filters.append(f"[{index}:a]volume={volumes.get('music', 0.72):.4f}[music]")
            mix_labels.append("[music]")
            index += 1
        if sfx:
            inputs.extend(["-i", str(sfx)])
            filters.append(f"[{index}:a]volume={volumes.get('sfx', 0.88):.4f}[sfx]")
            mix_labels.append("[sfx]")
        master = volumes.get("master", 1.0)
        filters.append(
            "".join(mix_labels)
            + f"amix=inputs={len(mix_labels)}:duration=longest:normalize=0,volume={master:.4f},"
            + "alimiter=limit=0.891251[outa]"
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        self.run(
            [
                *inputs,
                "-filter_complex",
                ";".join(filters),
                "-map",
                "0:v?",
                "-map",
                "[outa]",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-b:a",
                "256k",
                "-shortest",
                str(destination),
            ]
        )
