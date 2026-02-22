from pathlib import Path

from app.services.store import LocalAudioStore


def test_local_audio_store_roundtrip(tmp_path: Path) -> None:
    store = LocalAudioStore(root=str(tmp_path / "audio"))
    wav_bytes = b"RIFF" + b"0" * 100

    asset = store.save_wav(wav_bytes=wav_bytes, sample_rate=22050)
    location = store.get(asset.audio_id)

    assert location.endswith(f"{asset.audio_id}.wav")
    assert Path(location).exists()
    assert asset.duration_sec > 0
