from dataclasses import dataclass


@dataclass
class TranslationResult:
    text: str
    model_id: str


class TextTranslator:
    def translate(self, text: str, source_lang: str, target_lang: str) -> TranslationResult:
        raise NotImplementedError


class SpeechToText:
    def transcribe(self, audio_bytes: bytes, source_lang: str) -> tuple[str, str]:
        raise NotImplementedError


class TextToSpeech:
    def synthesize(self, text: str, lang: str, voice: str = "default") -> tuple[bytes, int]:
        raise NotImplementedError

    def list_voices(self) -> list[dict]:
        return []
