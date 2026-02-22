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

try:
    from google.cloud import texttospeech
    from google.cloud import translate_v2 as translate
    from google.cloud import speech
    import json
    from google.oauth2 import service_account
except ImportError:
    texttospeech = None
    translate = None
    speech = None
    service_account = None
    json = None

from app.config import settings
from app.models.adapters import SpeechToText, TextToSpeech, TextTranslator, TranslationResult
from app.models.errors import InferenceError

HF_API_BASE = "https://router.huggingface.co/hf-inference/models"

# MADLAD400 uses <2xx> prefix for target language
MADLAD_LANG_MAP = {
    "en": "en",
    "yo": "yo",
    "ig": "ig",
    "ha": "ha",
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


class GoogleTranslationProvider(TextTranslator):
    def __init__(self) -> None:
        self.model_id = "google-cloud-translate-v2"
        self._client = None

    def _get_client(self):
        if self._client: return self._client
        if translate is None: return None
        creds_json = settings.google_application_credentials_json
        if not creds_json: return None
        try:
            info = json.loads(creds_json)
            creds = service_account.Credentials.from_service_account_info(info)
            self._client = translate.Client(credentials=creds)
            return self._client
        except Exception: return None

    def translate(self, text: str, source_lang: str, target_lang: str) -> TranslationResult:
        client = self._get_client()
        if not client:
            # Fallback to MADLAD if Google Translate is not configured
            return SimpleTranslator().translate(text, source_lang, target_lang)
        
        try:
            result = client.translate(text, target_language=target_lang, source_language=source_lang)
            return TranslationResult(text=result["translatedText"], model_id=self.model_id)
        except Exception as e:
            print(f"DEBUG: Google Translate failed: {e}")
            return SimpleTranslator().translate(text, source_lang, target_lang)


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


class GoogleSTTProvider(SpeechToText):
    def __init__(self) -> None:
        self.model_id = "google-cloud-speech-v1"
        self._client = None

    def _get_client(self):
        if self._client: return self._client
        if speech is None: return None
        creds_json = settings.google_application_credentials_json
        if not creds_json: return None
        try:
            info = json.loads(creds_json)
            creds = service_account.Credentials.from_service_account_info(info)
            self._client = speech.SpeechClient(credentials=creds)
            return self._client
        except Exception: return None

    def transcribe(self, audio_bytes: bytes, source_lang: str) -> tuple[str, str]:
        client = self._get_client()
        if not client:
            return YorubaASRProvider().transcribe(audio_bytes, source_lang)
        
        try:
            # Google STT needs audio config
            audio = speech.RecognitionAudio(content=audio_bytes)
            # Use yo-NG for Yoruba, en-NG for English
            lang_code = "yo-NG" if source_lang == "yo" else "en-NG"
            config = speech.RecognitionConfig(
                encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
                language_code=lang_code,
                enable_automatic_punctuation=True,
            )
            
            response = client.recognize(config=config, audio=audio)
            transcript = ""
            for result in response.results:
                transcript += result.alternatives[0].transcript
            
            if not transcript:
                print("DEBUG: Google STT returned empty transcript")
                return YorubaASRProvider().transcribe(audio_bytes, source_lang)
                
            return transcript, self.model_id
        except Exception as e:
            print(f"DEBUG: Google STT failed: {e}")
            return YorubaASRProvider().transcribe(audio_bytes, source_lang)


# ---------- TTS ---------- #

class GoogleTTSProvider(TextToSpeech):
    def __init__(self, voice_name: str, language_code: str, fallback_freq: float) -> None:
        self.voice_name = voice_name
        self.language_code = language_code
        self._fallback_freq = fallback_freq
        self._client = None

    def list_voices(self) -> list[dict]:
        client = self._get_client()
        if not client:
            print("DEBUG: list_voices called but client is None")
            return []
        
        codes_to_try = [self.language_code, self.language_code[:2]]
        for code in codes_to_try:
            try:
                print(f"DEBUG: Listing voices for {code}...")
                response = client.list_voices(language_code=code)
                if not response.voices:
                    print(f"DEBUG: No voices found for {code}")
                    continue
                
                voices = []
                for voice in response.voices:
                    voices.append({
                        "name": voice.name,
                        "ssml_gender": str(voice.ssml_gender),
                        "language_codes": list(voice.language_codes)
                    })
                print(f"DEBUG: Found {len(voices)} voices for {code}")
                return voices
            except Exception as e:
                print(f"DEBUG: Error listing voices for {code}: {e}")
        return []

    def _get_client(self):
        if self._client:
            return self._client
        if texttospeech is None:
            return None
        
        creds_json = settings.google_application_credentials_json
        if not creds_json:
            return None
            
        try:
            info = json.loads(creds_json)
            creds = service_account.Credentials.from_service_account_info(info)
            self._client = texttospeech.TextToSpeechClient(credentials=creds)
            return self._client
        except Exception as e:
            print(f"Error initializing Google TTS client: {e}")
            return None

    def synthesize(self, text: str, lang: str, voice: str = "default") -> tuple[bytes, int]:
        client = self._get_client()
        if client:
            # Order of preference: 
            # 1. Explicitly requested 'voice' (if not "default")
            # 2. Pre-configured 'self.voice_name'
            # 3. AUTO (None)
            
            voices_to_try = []
            if voice and voice != "default":
                voices_to_try.append(voice)
            voices_to_try.append(self.voice_name)
            voices_to_try.append(None) # AUTO fallback
            
            # Remove duplicates while preserving order
            unique_voices = []
            for v in voices_to_try:
                if v not in unique_voices:
                    unique_voices.append(v)
            
            for v_name in unique_voices:
                try:
                    print(f"DEBUG: Generating Google TTS for '{text[:20]}...' lang={self.language_code} voice={v_name or 'AUTO'}")
                    s_input = texttospeech.SynthesisInput(text=text)
                    v_params = texttospeech.VoiceSelectionParams(
                        language_code=self.language_code,
                        name=v_name
                    )
                    a_config = texttospeech.AudioConfig(
                        audio_encoding=texttospeech.AudioEncoding.LINEAR16
                    )
                    
                    response = client.synthesize_speech(
                        input=s_input, voice=v_params, audio_config=a_config
                    )
                    
                    sample_rate = 24000
                    wav_bytes = _audio_to_wav_bytes(response.audio_content, sample_rate)
                    
                    print(f"DEBUG: Successfully generated {len(wav_bytes)} bytes of audio (v={v_name or 'AUTO'})")
                    return wav_bytes, sample_rate
                except Exception as e:
                    print(f"DEBUG: Google TTS attempt failed (v={v_name or 'AUTO'}): {e}")
                    continue
        else:
            print("WARNING: Google TTS client not initialized (check credentials JSON)")
        
        return _tone_from_text(text, sample_rate=22050, freq=self._fallback_freq), 22050


class NigerianEnglishTTSProvider(GoogleTTSProvider):
    def __init__(self) -> None:
        super().__init__(
            voice_name="en-NG-Standard-A", 
            language_code="en-NG", 
            fallback_freq=440.0
        )


class YorubaTTSProvider(GoogleTTSProvider):
    def __init__(self) -> None:
        super().__init__(
            voice_name="yo-NG-Standard-A", 
            language_code="yo-NG", 
            fallback_freq=330.0
        )


class HausaTTSProvider(GoogleTTSProvider):
    def __init__(self) -> None:
        super().__init__(
            voice_name="ha-NG-Standard-A", 
            language_code="ha-NG", 
            fallback_freq=350.0
        )


class IgboTTSProvider(GoogleTTSProvider):
    def __init__(self) -> None:
        super().__init__(
            voice_name="ig-NG-Standard-A", 
            language_code="ig-NG", 
            fallback_freq=370.0
        )


# ---------- Audio helpers ---------- #

def _audio_to_wav_bytes(audio: bytes, sample_rate: int) -> bytes:
    """Wrap raw PCM bytes (from Google or HF) into a standard WAV container."""
    # audio might be a numpy array from HF or raw bytes from Google
    try:
        import numpy as np
        if isinstance(audio, (list, np.ndarray)):
            arr = np.asarray(audio, dtype=np.float32)
            if arr.ndim > 1:
                arr = arr[0]
            arr = np.clip(arr, -1.0, 1.0)
            pcm_bytes = (arr * 32767.0).astype(np.int16).tobytes()
        else:
            # Already bytes (e.g. from Google)
            pcm_bytes = audio
    except ImportError:
        # Fallback if numpy is missing but we have raw bytes
        if isinstance(audio, bytes):
            pcm_bytes = audio
        else:
            raise InferenceError("numpy is required to convert HF model output to audio")

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm_bytes)
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
