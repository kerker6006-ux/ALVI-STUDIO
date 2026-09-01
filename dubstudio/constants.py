from __future__ import annotations

APP_NAME = "Alvi Studio"
APP_VERSION = "0.1.6"

DIRECTORIES = (
    "app",
    "runtime",
    "tools",
    "models",
    "cache",
    "cache/huggingface",
    "cache/torch",
    "cache/transformers",
    "projects",
    "exports",
    "temp",
    "logs",
    "updates",
)

SOURCE_LANGUAGES = {
    "Auto detect": "auto",
    "Chinese (Mandarin)": "zh",
    "Chinese (Cantonese)": "yue",
    "English": "en",
    "Hindi": "hi",
    "Japanese": "ja",
    "Korean": "ko",
    "Other / auto": "auto",
}

TARGET_LANGUAGES = {
    "Hindi": "hi",
    "English (experimental)": "en",
}

QUALITY_PRESETS = {
    "Fast": {
        "takes": 1,
        "dual_asr": False,
        "translation_candidates": 1,
        "emotion_matching": False,
    },
    "Balanced": {
        "takes": 2,
        "dual_asr": True,
        "translation_candidates": 2,
        "emotion_matching": True,
    },
    "Studio": {
        "takes": 3,
        "dual_asr": True,
        "translation_candidates": 3,
        "emotion_matching": True,
    },
}
