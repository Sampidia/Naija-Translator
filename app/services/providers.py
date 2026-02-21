import io
import math
import struct
import wave

from app.config import settings
from app.models.adapters import SpeechToText, TextToSpeech, TextTranslator, TranslationResult
from app.models.errors import InferenceError


class SimpleTranslator(TextTranslator):
    def __init__(self) -> None:
        self.model_ids = {
            ("en", "yo"): settings.en_yo_model_id,
            ("yo", "en"): settings.yo_en_model_id,
        }
        self._pipelines: dict[tuple[str, str], object] = {}

    def translate(self, text: str, source_lang: str, target_lang: str) -> TranslationResult:
        model_id = self.model_ids.get((source_lang, target_lang), "demo/unsupported")
        if source_lang == target_lang:
            return TranslationResult(text=text, model_id=model_id)

        if settings.use_real_models:
            try:
                pipe = self._get_pipeline(source_lang, target_lang, model_id)
                output = pipe(text)
                translated = output[0]["translation_text"]
                return TranslationResult(text=translated, model_id=model_id)
            except Exception as exc:
                raise InferenceError(f"translation failed: {exc}") from exc

        translated = f"[YO] {text}" if (source_lang, target_lang) == ("en", "yo") else f"[EN] {text}"
        return TranslationResult(text=translated, model_id=model_id)

    def _get_pipeline(self, source_lang: str, target_lang: str, model_id: str):
        key = (source_lang, target_lang)
        if key in self._pipelines:
            return self._pipelines[key]
        from transformers import pipeline

        self._pipelines[key] = pipeline("translation", model=model_id)
        return self._pipelines[key]


class YorubaASRProvider(SpeechToText):
    model_id = settings.yoruba_asr_model_id

    def __init__(self) -> None:
        self._pipe = None

    def transcribe(self, audio_bytes: bytes, source_lang: str) -> tuple[str, str]:
        if settings.use_real_models:
            try:
                if self._pipe is None:
                    from transformers import pipeline

                    self._pipe = pipeline("automatic-speech-recognition", model=self.model_id)
                result = self._pipe(audio_bytes)
                text = result["text"] if isinstance(result, dict) else str(result)
                return text, self.model_id
            except Exception as exc:
                raise InferenceError(f"asr failed: {exc}") from exc

        return "eyi je apeere transcription", self.model_id


class _HFTextToAudioProvider(TextToSpeech):
    def __init__(self, model_id: str, fallback_freq: float) -> None:
        self.model_id = model_id
        self._pipe = None
        self._fallback_freq = fallback_freq

    def synthesize(self, text: str, lang: str, voice: str = "default") -> tuple[bytes, int]:
        if settings.use_real_models:
            try:
                audio, sample_rate = self._infer(text)
                return _audio_to_wav_bytes(audio, sample_rate), sample_rate
            except Exception as exc:
                raise InferenceError(f"tts failed ({self.model_id}): {exc}") from exc
        return _tone_from_text(text, sample_rate=22050, freq=self._fallback_freq), 22050

    def _infer(self, text: str) -> tuple[object, int]:
        if self._pipe is None:
            from transformers import pipeline

            self._pipe = pipeline("text-to-audio", model=self.model_id)

        result = self._pipe(text)
        if isinstance(result, dict) and "audio" in result and "sampling_rate" in result:
            return result["audio"], int(result["sampling_rate"])
        raise InferenceError("unexpected TTS pipeline output")


class NigerianEnglishTTSProvider(_HFTextToAudioProvider):
    def __init__(self) -> None:
        super().__init__(model_id=settings.nigerian_english_tts_model_id, fallback_freq=440.0)


class YorubaTTSProvider(_HFTextToAudioProvider):
    def __init__(self) -> None:
        super().__init__(model_id=settings.yoruba_tts_model_id, fallback_freq=330.0)


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
