"""ML providers using the Hugging Face Inference API (HTTP).

This avoids loading multi-GB models into RAM, making it compatible
with Render's free tier (512 MB).  When USE_REAL_MODELS is False the
providers still return safe local fallbacks for development.
"""

import io
import math
import os
import struct
import wave

import requests as http_requests

from app.config import settings
from app.models.adapters import SpeechToText, TextToSpeech, TextTranslator, TranslationResult
from app.models.errors import InferenceError

HF_API_BASE = "https://router.huggingface.co/hf-inference/models"

# MADLAD400 uses <2xx> prefix for target language
MADLAD_LANG_MAP = {
    "en": "en",
    "yo": "yo",
}


def _hf_headers() -> dict[str, str]:
    token = os.getenv("HF_TOKEN", "").strip()
    headers: dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


# ---------- Translation ---------- #

class SimpleTranslator(TextTranslator):
    def __init__(self) -> None:
        # google/madlad400-3b-mt supports 400+ languages including Yoruba
        self.model_id = settings.en_yo_model_id

    def translate(self, text: str, source_lang: str, target_lang: str) -> TranslationResult:
        if source_lang == target_lang:
            return TranslationResult(text=text, model_id=self.model_id)

        if settings.use_real_models:
            try:
                model_id = self.model_id
                tgt_code = MADLAD_LANG_MAP.get(target_lang, target_lang)

                # MADLAD400 format: prefix input with <2xx> target language tag
                formatted_input = f"<2{tgt_code}> {text}"

                url = f"{HF_API_BASE}/{model_id}"
                payload = {"inputs": formatted_input}
                headers = _hf_headers()
                # Tell HF to wait for model to load (cold start can take 2+ min)
                headers["x-wait-for-model"] = "true"

                # Retry up to 2 times for cold starts
                last_exc = None
                for attempt in range(2):
                    try:
                        resp = http_requests.post(
                            url, json=payload, headers=headers, timeout=180
                        )
                        resp.raise_for_status()
                        break
                    except Exception as e:
                        last_exc = e
                        if attempt == 0:
                            import time
                            time.sleep(5)  # brief pause before retry
                else:
                    raise last_exc  # type: ignore[misc]

                data = resp.json()

                # HF translation returns [{"translation_text": "..."}]
                if isinstance(data, list) and data:
                    translated = data[0].get("translation_text", text)
                elif isinstance(data, dict) and "translation_text" in data:
                    translated = data["translation_text"]
                else:
                    translated = str(data)

                return TranslationResult(text=translated, model_id=model_id)
            except Exception as exc:
                raise InferenceError(f"translation failed ({model_id}): {exc}") from exc

        translated = f"[YO] {text}" if (source_lang, target_lang) == ("en", "yo") else f"[EN] {text}"
        return TranslationResult(text=translated, model_id=self.model_id)


# ---------- ASR ---------- #

class YorubaASRProvider(SpeechToText):
    model_id = settings.yoruba_asr_model_id

    def transcribe(self, audio_bytes: bytes, source_lang: str) -> tuple[str, str]:
        if settings.use_real_models:
            try:
                url = f"{HF_API_BASE}/{self.model_id}"
                headers = _hf_headers()
                headers["Content-Type"] = "audio/wav"
                resp = http_requests.post(url, data=audio_bytes, headers=headers, timeout=60)
                resp.raise_for_status()
                data = resp.json()
                text = data.get("text", str(data)) if isinstance(data, dict) else str(data)
                return text, self.model_id
            except Exception as exc:
                raise InferenceError(f"asr failed: {exc}") from exc

        return "eyi je apeere transcription", self.model_id


# ---------- TTS ---------- #

class _HFTextToAudioProvider(TextToSpeech):
    def __init__(self, model_id: str, fallback_freq: float) -> None:
        self.model_id = model_id
        self._fallback_freq = fallback_freq

    def synthesize(self, text: str, lang: str, voice: str = "default") -> tuple[bytes, int]:
        # NOTE: HF free Inference API does not support text-to-speech tasks.
        # We always use the local tone generator fallback for now.
        # To enable real TTS, use a paid TTS API (Google Cloud TTS, ElevenLabs, etc.)
        return _tone_from_text(text, sample_rate=22050, freq=self._fallback_freq), 22050


class NigerianEnglishTTSProvider(_HFTextToAudioProvider):
    def __init__(self) -> None:
        super().__init__(model_id=settings.nigerian_english_tts_model_id, fallback_freq=440.0)


class YorubaTTSProvider(_HFTextToAudioProvider):
    def __init__(self) -> None:
        super().__init__(model_id=settings.yoruba_tts_model_id, fallback_freq=330.0)


# ---------- Audio helpers ---------- #

def _audio_to_wav_bytes(audio: object, sample_rate: int) -> bytes:
    """Convert HF pipeline audio output to PCM16 WAV bytes."""
    try:
        import numpy as np
    except Exception as exc:  # pragma: no cover
        raise InferenceError(f"numpy is required for real TTS conversion: {exc}") from exc

    arr = np.asarray(audio, dtype=np.float32)
    if arr.ndim > 1:
        arr = arr[0]
    arr = np.clip(arr, -1.0, 1.0)

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        pcm = (arr * 32767.0).astype(np.int16)
        wav.writeframes(pcm.tobytes())
    return buf.getvalue()


def _tone_from_text(text: str, sample_rate: int = 22050, freq: float = 440.0) -> bytes:
    duration = max(0.8, min(4.0, len(text) / 50.0))
    frames = int(sample_rate * duration)

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        for i in range(frames):
            amp = int(32767 * 0.2 * math.sin(2 * math.pi * freq * i / sample_rate))
            wav.writeframes(struct.pack("<h", amp))
    return buf.getvalue()
