from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


BANDIT_V2_SHA256 = "abcfccf65446752a057f4a302c941479a54b7560ebf8d7bca039d2ea98e64cfc"


@dataclass
class Word:
    start: float
    end: float
    text: str
    confidence: float


@dataclass
class Segment:
    segment_id: int
    start: float
    end: float
    source_text: str
    source_language: str
    words: list[Word] = field(default_factory=list)
    speaker: str = "SPEAKER_00"
    emotion: str = "neutral"
    emotion_confidence: float = 0.0
    target_text: str = ""
    voice: str = "Rohit"
    gender: str = "unknown"


def local_model(root: Path, repository: str) -> Path:
    return root / "models" / "hf" / Path(*repository.split("/"))


class BanditSeparator:
    def __init__(self, root: Path) -> None:
        self.root = root

    def separate(self, audio: Path, output: Path) -> dict[str, Path]:
        import soundfile as sf
        from bandit_infer import BanditSession

        output.mkdir(parents=True, exist_ok=True)
        samples, sample_rate = sf.read(str(audio), dtype="float32", always_2d=True)
        if sample_rate != 48000:
            raise RuntimeError(f"Bandit v2 requires 48 kHz audio; received {sample_rate} Hz")
        checkpoint = self.root / "models" / "weights" / "bandit-infer" / "checkpoint-multi.ckpt"
        if not checkpoint.is_file():
            raise RuntimeError(f"Bandit v2 model is missing: {checkpoint}")
        with BanditSession(
            "v2-multi",
            device="auto",
            weights_dir=checkpoint.parent,
            checkpoint_path=checkpoint,
            checkpoint_sha256=BANDIT_V2_SHA256,
        ) as session:
            stems = session.infer(samples.T, sample_rate=sample_rate)
        mapping = {"dialogue": "speech", "music": "music", "sfx": "effects"}
        result: dict[str, Path] = {}
        for destination_name, source_name in mapping.items():
            if source_name not in stems:
                continue
            destination = output / f"{destination_name}.wav"
            values = stems[source_name]
            if getattr(values, "ndim", 1) == 2:
                values = values.T
            sf.write(str(destination), values, sample_rate, subtype="PCM_24")
            result[destination_name] = destination
        if "dialogue" not in result:
            raise RuntimeError("Bandit v2 did not produce a speech stem")
        return result


class WhisperTranscriber:
    def __init__(self, root: Path, quality: str) -> None:
        from faster_whisper import WhisperModel

        model_name = "faster-whisper-small" if quality == "Fast" else "faster-whisper-large-v3"
        model_path = local_model(root, f"Systran/{model_name}")
        if not model_path.is_dir():
            raise RuntimeError(f"Whisper model is missing: {model_path}")
        try:
            import torch

            device = "cuda" if torch.cuda.is_available() else "cpu"
        except ImportError:
            device = "cpu"
        compute_type = "float16" if device == "cuda" else "int8"
        self.model = WhisperModel(str(model_path), device=device, compute_type=compute_type)

    def transcribe(self, audio: Path, language: str) -> list[Segment]:
        selected = None if language == "auto" else language
        segments, info = self.model.transcribe(
            str(audio),
            language=selected,
            vad_filter=True,
            word_timestamps=True,
            beam_size=5,
            condition_on_previous_text=False,
        )
        result: list[Segment] = []
        for item in segments:
            words = [
                Word(float(word.start), float(word.end), word.word.strip(), float(word.probability))
                for word in (item.words or [])
                if word.start is not None and word.end is not None
            ]
            result.append(
                Segment(
                    segment_id=len(result),
                    start=float(item.start),
                    end=float(item.end),
                    source_text=item.text.strip(),
                    source_language=str(info.language),
                    words=words,
                )
            )
        return result


class SpeakerDiarizer:
    def __init__(self, root: Path) -> None:
        from pyannote.audio import Pipeline

        model_path = local_model(root, "pyannote/speaker-diarization-community-1")
        if not model_path.is_dir():
            raise RuntimeError(f"Diarization model is missing: {model_path}")
        self.pipeline = Pipeline.from_pretrained(str(model_path))
        try:
            import torch

            if torch.cuda.is_available():
                self.pipeline.to(torch.device("cuda"))
        except ImportError:
            pass

    def assign(self, audio: Path, segments: list[Segment]) -> None:
        output = self.pipeline(str(audio))
        annotation = getattr(output, "exclusive_speaker_diarization", None)
        if annotation is None:
            annotation = getattr(output, "speaker_diarization", output)
        turns: list[tuple[float, float, str]] = []
        for turn, _, speaker in annotation.itertracks(yield_label=True):
            turns.append((float(turn.start), float(turn.end), str(speaker)))
        for segment in segments:
            midpoint = (segment.start + segment.end) / 2
            containing = [turn for turn in turns if turn[0] <= midpoint <= turn[1]]
            if containing:
                segment.speaker = containing[0][2]
            elif turns:
                segment.speaker = min(turns, key=lambda item: abs(((item[0] + item[1]) / 2) - midpoint))[2]


class EmotionAnalyzer:
    LABELS = ("happy", "sad", "angry", "disgust", "fear", "surprise", "neutral")

    def __init__(self, root: Path) -> None:
        from funasr import AutoModel

        model_path = local_model(root, "FunAudioLLM/SenseVoiceSmall")
        if not model_path.is_dir():
            raise RuntimeError(f"SenseVoice model is missing: {model_path}")
        self.model = AutoModel(model=str(model_path), disable_update=True)

    def analyze(self, clip: Path) -> tuple[str, float]:
        result = self.model.generate(input=str(clip), cache={}, language="auto", use_itn=True)
        serialized = json.dumps(result, ensure_ascii=False).lower()
        for label in self.LABELS:
            if label in serialized:
                return label, 0.8
        return "neutral", 0.25


class VoiceGenderAnalyzer:
    """Estimate vocal range from several clean clips for stable voice-family selection.

    This deliberately predicts only the acoustic voice family needed to select a
    fixed TTS voice. It does not infer a person's identity or demographic data.
    """

    def analyze(self, clips: list[Path]) -> tuple[str, float]:
        import librosa
        import numpy as np

        voiced: list[float] = []
        for clip in clips:
            signal, sample_rate = librosa.load(str(clip), sr=16000, mono=True)
            if signal.size < sample_rate // 2:
                continue
            f0, voiced_flag, _ = librosa.pyin(
                signal,
                fmin=65.0,
                fmax=350.0,
                sr=sample_rate,
                frame_length=2048,
            )
            if f0 is not None and voiced_flag is not None:
                values = f0[voiced_flag & np.isfinite(f0)]
                voiced.extend(float(value) for value in values)
        if len(voiced) < 12:
            return "unknown", 0.0
        median = float(np.median(np.asarray(voiced)))
        if median <= 145.0:
            return "male", min(0.98, 0.58 + (145.0 - median) / 100.0)
        if median >= 170.0:
            return "female", min(0.98, 0.58 + (median - 170.0) / 140.0)
        return "unknown", 0.35


class Translator:
    LANGUAGE_CODES = {
        "zh": "zho_Hans",
        "yue": "yue_Hant",
        "en": "eng_Latn",
        "hi": "hin_Deva",
        "ja": "jpn_Jpan",
        "ko": "kor_Hang",
    }

    def __init__(self, root: Path) -> None:
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

        model_path = local_model(root, "facebook/nllb-200-distilled-600M")
        if not model_path.is_dir():
            raise RuntimeError(f"NLLB translation model is missing: {model_path}")
        self.tokenizer = AutoTokenizer.from_pretrained(str(model_path), local_files_only=True)
        self.model = AutoModelForSeq2SeqLM.from_pretrained(
            str(model_path), low_cpu_mem_usage=True, local_files_only=True
        )

    def translate(self, segments: list[Segment], target: str) -> None:
        target_code = self.LANGUAGE_CODES.get(target, "hin_Deva")
        forced_bos = self.tokenizer.convert_tokens_to_ids(target_code)
        batch_size = 8
        for offset in range(0, len(segments), batch_size):
            batch = segments[offset : offset + batch_size]
            source_code = self.LANGUAGE_CODES.get(batch[0].source_language, "eng_Latn")
            self.tokenizer.src_lang = source_code
            texts = [item.source_text for item in batch]
            inputs = self.tokenizer(
                texts, return_tensors="pt", padding=True, truncation=True
            ).to(self.model.device)
            outputs = self.model.generate(
                **inputs,
                forced_bos_token_id=forced_bos,
                max_new_tokens=256,
                num_beams=4,
            )
            translations = self.tokenizer.batch_decode(outputs, skip_special_tokens=True)
            for item, translation in zip(batch, translations, strict=True):
                item.target_text = translation.strip()


class IndicParlerSynthesizer:
    VOICES = ("Rohit", "Divya", "Aman", "Rani")
    EMOTION_STYLE = {
        "happy": "warm, lively and happy",
        "sad": "soft, restrained and sad",
        "angry": "intense and angry without distortion",
        "disgust": "controlled and disgusted",
        "fear": "tense and fearful",
        "surprise": "animated and surprised",
        "neutral": "natural and conversational",
    }

    def __init__(self, root: Path) -> None:
        import torch
        from parler_tts import ParlerTTSForConditionalGeneration
        from transformers import AutoTokenizer

        model_path = local_model(root, "ai4bharat/indic-parler-tts")
        if not model_path.is_dir():
            raise RuntimeError(f"Indic Parler model is missing: {model_path}")
        self.torch = torch
        self.device = "cuda:0" if torch.cuda.is_available() else "cpu"
        self.model = ParlerTTSForConditionalGeneration.from_pretrained(
            str(model_path), local_files_only=True
        ).to(self.device)
        self.tokenizer = AutoTokenizer.from_pretrained(str(model_path), local_files_only=True)
        description_path = local_model(root, "google/flan-t5-large")
        if not description_path.is_dir():
            raise RuntimeError(f"Parler description tokenizer is missing: {description_path}")
        self.description_tokenizer = AutoTokenizer.from_pretrained(
            str(description_path), local_files_only=True
        )

    def synthesize(self, segment: Segment, destination: Path, variation: int = 0) -> None:
        import soundfile as sf

        style = self.EMOTION_STYLE.get(segment.emotion, self.EMOTION_STYLE["neutral"])
        intensity = ("controlled", "expressive", "cinematic")[variation % 3]
        description = (
            f"{segment.voice}'s Hindi voice sounds {style}, with clear studio-quality speech, "
            f"natural emphasis, a {intensity} performance, a close recording, and no background noise."
        )
        prompt_ids = self.tokenizer(segment.target_text, return_tensors="pt").to(self.device)
        description_ids = self.description_tokenizer(description, return_tensors="pt").to(self.device)
        with self.torch.inference_mode():
            self.torch.manual_seed(1200 + segment.segment_id * 17 + variation)
            generation = self.model.generate(
                input_ids=description_ids.input_ids,
                attention_mask=description_ids.attention_mask,
                prompt_input_ids=prompt_ids.input_ids,
                prompt_attention_mask=prompt_ids.attention_mask,
            )
        audio = generation.cpu().numpy().squeeze()
        destination.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(destination), audio, self.model.config.sampling_rate)


def save_segments(segments: list[Segment], destination: Path) -> None:
    destination.write_text(
        json.dumps([asdict(segment) for segment in segments], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
