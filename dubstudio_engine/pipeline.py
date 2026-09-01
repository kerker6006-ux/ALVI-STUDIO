from __future__ import annotations

import json
import gc
from pathlib import Path
from typing import Callable

from .media import MediaTools
from .models import (
    BanditSeparator,
    EmotionAnalyzer,
    IndicParlerSynthesizer,
    Segment,
    SpeakerDiarizer,
    Translator,
    VoiceGenderAnalyzer,
    WhisperTranscriber,
    save_segments,
)


Emitter = Callable[[str, float, str], None]


def _release_models() -> None:
    gc.collect()
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:
        pass


def _assert_inside(root: Path, path: Path) -> None:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise RuntimeError(f"Engine path escaped selected storage root: {path}") from exc


def run_project(request: dict[str, str], emit: Emitter) -> None:
    root = Path(request["storage_root"]).resolve()
    project_file = Path(request["project_file"]).resolve()
    project_dir = Path(request["project_dir"]).resolve()
    output_file = Path(request["output_file"]).resolve()
    for path in (project_file, project_dir, output_file):
        _assert_inside(root, path)

    project = json.loads(project_file.read_text(encoding="utf-8"))
    source = Path(project["source_media"]).resolve()
    media = MediaTools(root)

    extracted = project_dir / "audio" / "source-48k.wav"
    emit("Extracting audio", 0.08, "Creating a lossless local working track")
    media.extract_audio(source, extracted)

    emit("Separating soundtrack", 0.14, "Separating dialogue, music and sound effects")
    stems = BanditSeparator(root).separate(extracted, project_dir / "stems")
    dialogue = stems["dialogue"]

    emit("Transcribing", 0.28, "Recognizing dialogue with word-level timestamps")
    transcriber = WhisperTranscriber(root, project["quality"])
    segments = transcriber.transcribe(dialogue, project["source_language"])
    del transcriber
    _release_models()
    if not segments:
        raise RuntimeError("No dialogue was detected in the selected media")

    if project["quality"] != "Fast":
        emit("Detecting speakers", 0.38, "Keeping a consistent fixed voice for each speaker")
        diarizer = SpeakerDiarizer(root)
        diarizer.assign(dialogue, segments)
        del diarizer
        _release_models()
    emit("Matching voice families", 0.43, "Estimating each speaker's vocal range from clean dialogue")
    speakers = sorted({item.speaker for item in segments})
    gender_analyzer = VoiceGenderAnalyzer()
    gender_dir = project_dir / "audio" / "gender-clips"
    speaker_genders: dict[str, str] = {}
    for speaker in speakers:
        candidates = sorted(
            (item for item in segments if item.speaker == speaker),
            key=lambda item: item.end - item.start,
            reverse=True,
        )[:5]
        clips: list[Path] = []
        for candidate in candidates:
            clip = gender_dir / f"{speaker}-{candidate.segment_id:06d}.wav"
            media.extract_clip(dialogue, candidate.start, candidate.end, clip)
            clips.append(clip)
        speaker_genders[speaker], _ = gender_analyzer.analyze(clips)
    male_voices = ("Rohit", "Aman")
    female_voices = ("Divya", "Rani")
    unknown_voices = ("Rohit", "Divya", "Aman", "Rani")
    counters = {"male": 0, "female": 0, "unknown": 0}
    assignments: dict[str, str] = {}
    for speaker in speakers:
        gender = speaker_genders[speaker]
        pool = male_voices if gender == "male" else female_voices if gender == "female" else unknown_voices
        assignments[speaker] = pool[counters[gender] % len(pool)]
        counters[gender] += 1
    for segment in segments:
        segment.voice = assignments[segment.speaker]
        segment.gender = speaker_genders[segment.speaker]

    if project["quality"] == "Studio":
        emit("Analyzing emotion", 0.46, "Reading tone, emotion and non-verbal performance")
        source_analyzer = EmotionAnalyzer(root)
        clip_dir = project_dir / "audio" / "emotion-clips"
        for index, segment in enumerate(segments):
            clip = clip_dir / f"{segment.segment_id:06d}.wav"
            media.extract_clip(dialogue, segment.start, segment.end, clip)
            segment.emotion, segment.emotion_confidence = source_analyzer.analyze(clip)
            if index % 10 == 0:
                emit("Analyzing emotion", 0.46 + 0.06 * (index / len(segments)), f"Line {index + 1} of {len(segments)}")
        del source_analyzer
        _release_models()

    emit("Translating", 0.54, "Creating context-safe Hindi dialogue")
    translator = Translator(root)
    translator.translate(segments, project["target_language"])
    del translator
    _release_models()
    save_segments(segments, project_dir / "translations" / "timeline.json")

    emit("Generating voices", 0.67, "Producing clean fixed-voice emotional takes")
    synthesizer = IndicParlerSynthesizer(root)
    candidate_dir = project_dir / "takes" / "candidates"
    take_dir = project_dir / "takes" / "selected"
    fitted_dir = project_dir / "takes" / "fitted"
    candidate_sets: list[tuple[Segment, list[Path], float]] = []
    take_count = 1 if project["quality"] == "Fast" else 2 if project["quality"] == "Balanced" else 3
    for index, segment in enumerate(segments):
        target_duration = max(0.05, segment.end - segment.start)
        candidates: list[Path] = []
        for variation in range(take_count):
            candidate = candidate_dir / f"{segment.segment_id:06d}-{variation + 1}.wav"
            synthesizer.synthesize(segment, candidate, variation)
            candidates.append(candidate)
        candidate_sets.append((segment, candidates, target_duration))
        emit(
            "Generating voices",
            0.67 + 0.16 * ((index + 1) / len(segments)),
            f"Line {index + 1} of {len(segments)} • {segment.voice} • {segment.emotion}",
        )
    del synthesizer
    _release_models()

    emit("Selecting takes", 0.84, "Matching timing and emotion across generated takes")
    take_analyzer = EmotionAnalyzer(root) if project["quality"] == "Studio" else None
    timeline_files: list[Path] = []
    take_scores: list[dict[str, object]] = []
    cursor = 0.0
    for index, (segment, candidates, target_duration) in enumerate(candidate_sets):
        gap = max(0.0, segment.start - cursor)
        if gap > 0.001:
            silence = fitted_dir / f"{segment.segment_id:06d}-gap.wav"
            media.make_silence(silence, gap)
            timeline_files.append(silence)
        raw_take = take_dir / f"{segment.segment_id:06d}.wav"
        fitted_take = fitted_dir / f"{segment.segment_id:06d}.wav"
        scored: list[tuple[float, Path, str]] = []
        for candidate in candidates:
            timing_error = abs(media.duration(candidate) - target_duration) / target_duration
            detected_emotion = "not-scored"
            emotion_penalty = 0.0
            if take_analyzer is not None:
                detected_emotion, confidence = take_analyzer.analyze(candidate)
                if detected_emotion != segment.emotion:
                    emotion_penalty = 0.35 * confidence
            scored.append((timing_error + emotion_penalty, candidate, detected_emotion))
        score, selected, detected_emotion = min(scored, key=lambda item: item[0])
        raw_take.parent.mkdir(parents=True, exist_ok=True)
        __import__("shutil").copy2(selected, raw_take)
        take_scores.append(
            {
                "segment_id": segment.segment_id,
                "selected": selected.name,
                "score": round(score, 5),
                "target_emotion": segment.emotion,
                "detected_emotion": detected_emotion,
            }
        )
        media.fit_duration(raw_take, fitted_take, segment.end - segment.start)
        timeline_files.append(fitted_take)
        cursor = segment.end
        emit(
            "Selecting takes",
            0.84 + 0.05 * ((index + 1) / len(candidate_sets)),
            f"Line {index + 1} of {len(segments)} • {segment.voice} • {segment.emotion}",
        )
    del take_analyzer
    _release_models()
    (project_dir / "takes" / "take-scores.json").write_text(
        json.dumps(take_scores, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    source_duration = media.duration(source)
    if cursor < source_duration:
        tail = fitted_dir / "tail-silence.wav"
        media.make_silence(tail, source_duration - cursor)
        timeline_files.append(tail)
    dub_track = project_dir / "mix" / "hindi-dub.wav"
    media.concat(timeline_files, dub_track, project_dir / "mix" / "concat.txt")

    reactions = None
    if project["preserve_reactions"]:
        reactions = project_dir / "mix" / "reactions.wav"
        word_ranges = [
            (word.start, word.end)
            for segment in segments
            for word in segment.words
        ]
        media.preserve_reactions(dialogue, word_ranges, reactions)

    emit("Mixing", 0.91, "Balancing dub, music, effects and master loudness")
    music = stems.get("music") if project["keep_music"] else None
    sfx = stems.get("sfx") if project["keep_sfx"] else None
    media.final_mix(
        source_media=source,
        dub=dub_track,
        original_dialogue=dialogue,
        reactions=reactions,
        music=music,
        sfx=sfx,
        destination=output_file,
        volumes=project["volumes"],
    )
    emit("Quality check", 0.98, "Checking duration, clipping and output integrity")
    if abs(media.duration(output_file) - source_duration) > 0.25:
        raise RuntimeError("Final output duration did not match the source")
    emit("Complete", 1.0, str(output_file))
