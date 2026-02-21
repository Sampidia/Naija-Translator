from app.services.jobs import JobManager
from app.services.providers import (
    NigerianEnglishTTSProvider,
    SimpleTranslator,
    YorubaASRProvider,
    YorubaTTSProvider,
)
from app.services.store import build_audio_store

translator = SimpleTranslator()
asr = YorubaASRProvider()
english_tts = NigerianEnglishTTSProvider()
yoruba_tts = YorubaTTSProvider()
audio_store = build_audio_store()
jobs = JobManager()
