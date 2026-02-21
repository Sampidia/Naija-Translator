from app.services.jobs import JobManager
from app.services.providers import (
    NigerianEnglishTTSProvider,
    SimpleTranslator,
    YorubaASRProvider,
    YorubaTTSProvider,
)
from app.services.store import AudioAsset, build_audio_store

translator = SimpleTranslator()
asr = YorubaASRProvider()
english_tts = NigerianEnglishTTSProvider()
yoruba_tts = YorubaTTSProvider()
audio_store = build_audio_store()
jobs = JobManager()


def _task_tts(payload: dict) -> AudioAsset:
    text = str(payload.get("text", ""))
    lang = str(payload.get("lang", "en"))
    voice = str(payload.get("voice", "default"))
    provider = yoruba_tts if lang == "yo" else english_tts
    wav, rate = provider.synthesize(text, lang, voice)
    return audio_store.save_wav(wav, rate)


def _task_english_tts(payload: dict) -> AudioAsset:
    text = str(payload.get("text", ""))
    wav, rate = english_tts.synthesize(text, lang="en")
    return audio_store.save_wav(wav, rate)


jobs.register_task("tts", _task_tts)
jobs.register_task("english_tts", _task_english_tts)
