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

HF_API_BASE = "https://api-inference.huggingface.co/models"


def _hf_headers() -> dict[str, str]:
    token = os.getenv("HF_TOKEN", "").strip()
    headers: dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


# ---------- Translation ---------- #

class SimpleTranslator(TextTranslator):
    def __init__(self) -> None:
        self.model_ids = {
            ("en", "yo"): settings.en_yo_model_id,
            ("yo", "en"): settings.yo_en_model_id,
        }

    def translate(self, text: str, source_lang: str, target_lang: str) -> TranslationResult:
        model_id = self.model_ids.get((source_lang, target_lang), "demo/unsupported")
        if source_lang == target_lang:
            return TranslationResult(text=text, model_id=model_id)

        if settings.use_real_models:
            try:
                url = f"{HF_API_BASE}/{model_id}"
                payload = {"inputs": text}
                resp = http_requests.post(url, json=payload, headers=_hf_headers(), timeout=30)
                resp.raise_for_status()
                data = resp.json()

                # HF translation returns [{"translation_text": "..."}]
                if isinstance(data, list) and data:
                    translated = data[0].get("translation_text", text)
                else:
                    translated = str(data)

                return TranslationResult(text=translated, model_id=model_id)
            except Exception as exc:
                raise InferenceError(f"translation failed ({model_id}): {exc}") from exc

        translated = f"[YO] {text}" if (source_lang, target_lang) == ("en", "yo") else f"[EN] {text}"
        return TranslationResult(text=translated, model_id=model_id)


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
        if settings.use_real_models:
            try:
                url = f"{HF_API_BASE}/{self.model_id}"
                payload = {"inputs": text}
                headers = _hf_headers()
                resp = http_requests.post(url, json=payload, headers=headers, timeout=60)
                resp.raise_for_status()

                content_type = resp.headers.get("Content-Type", "")

                # If the API returns audio bytes directly
                if "audio" in content_type or "octet-stream" in content_type:
                    return resp.content, 22050  # default sample rate

                # If the API returns JSON with audio data
                data = resp.json()
                if isinstance(data, dict) and "audio" in data:
                    import numpy as np
                    audio = data["audio"]
                    sample_rate = int(data.get("sampling_rate", 22050))
                    return _audio_to_wav_bytes(audio, sample_rate), sample_rate

                raise InferenceError(f"unexpected TTS response format from {self.model_id}")
            except InferenceError:
                raise
            except Exception as exc:
                raise InferenceError(f"tts failed ({self.model_id}): {exc}") from exc

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
