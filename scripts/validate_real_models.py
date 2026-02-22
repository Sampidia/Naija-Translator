"""Staging smoke-check for real model mode.

Run with:
  USE_REAL_MODELS=true python scripts/validate_real_models.py
"""

from app.config import settings
from app.services.runtime import asr, english_tts, translator, yoruba_tts


def main() -> None:
    if not settings.use_real_models:
        raise SystemExit("Set USE_REAL_MODELS=true before running this validator")

    print("Running translation smoke test...")
    t = translator.translate("Hello from Naija", "en", "yo")
    print(f"en->yo model={t.model_id}, output={t.text[:120]}")

    print("Running Yoruba ASR smoke test with tiny placeholder wav bytes...")
    # Replace with real Yoruba speech bytes in staging for meaningful validation.
    try:
        transcript, model = asr.transcribe(b"RIFF....WAVEfmt ", "yo")
        print(f"asr model={model}, transcript={transcript[:120]}")
    except Exception as exc:
        print(f"ASR smoke test failed (expected if sample bytes are invalid): {exc}")

    print("Running TTS smoke tests...")
    wav_en, sr_en = english_tts.synthesize("Hello from Nigeria", "en")
    print(f"en tts bytes={len(wav_en)}, sr={sr_en}")

    wav_yo, sr_yo = yoruba_tts.synthesize("Bawo ni", "yo")
    print(f"yo tts bytes={len(wav_yo)}, sr={sr_yo}")

    print("Real-model smoke checks completed.")


if __name__ == "__main__":
    main()
