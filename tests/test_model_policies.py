from dubstudio.components import MODEL_PACKS
from dubstudio.model_installer import BANDIT_V2_SHA256
from dubstudio_engine.models import Translator


def test_all_model_packs_use_low_memory_nllb() -> None:
    for pack in MODEL_PACKS.values():
        assert "facebook/nllb-200-distilled-600M" in pack["models"]
        assert "google/madlad400-3b-mt" not in pack["models"]


def test_hindi_and_main_source_languages_have_nllb_codes() -> None:
    assert Translator.LANGUAGE_CODES["hi"] == "hin_Deva"
    assert Translator.LANGUAGE_CODES["en"] == "eng_Latn"
    assert Translator.LANGUAGE_CODES["zh"] == "zho_Hans"


def test_bandit_checkpoint_checksum_is_pinned() -> None:
    assert BANDIT_V2_SHA256 == "abcfccf65446752a057f4a302c941479a54b7560ebf8d7bca039d2ea98e64cfc"
