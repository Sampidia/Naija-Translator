from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from app.config import settings
from app.models.errors import StorageError


@dataclass
class AudioAsset:
    audio_id: str
    sample_rate: int
    duration_sec: float


class AudioStore:
    def save_wav(self, wav_bytes: bytes, sample_rate: int) -> AudioAsset:
        raise NotImplementedError

    def get(self, audio_id: str) -> str:
        raise NotImplementedError


class LocalAudioStore(AudioStore):
    def __init__(self, root: str | None = None) -> None:
        self.root = Path(root or settings.local_audio_root)
        self.root.mkdir(parents=True, exist_ok=True)

    def save_wav(self, wav_bytes: bytes, sample_rate: int) -> AudioAsset:
        audio_id = str(uuid4())
        path = self.root / f"{audio_id}.wav"
        path.write_bytes(wav_bytes)
        duration = max(0.1, (len(wav_bytes) - 44) / (sample_rate * 2))
        return AudioAsset(audio_id=audio_id, sample_rate=sample_rate, duration_sec=duration)

    def get(self, audio_id: str) -> str:
        return str(self.root / f"{audio_id}.wav")


class S3AudioStore(AudioStore):
    def __init__(self) -> None:
        try:
            import boto3
        except Exception as exc:  # pragma: no cover
            raise StorageError("boto3 is required for AUDIO_BACKEND=s3") from exc

        if not settings.s3_bucket:
            raise StorageError("S3_BUCKET must be set for AUDIO_BACKEND=s3")

        self.bucket = settings.s3_bucket
        self.key_prefix = settings.s3_key_prefix.strip("/")
        self.client = boto3.client(
            "s3",
            region_name=settings.s3_region,
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key_id,
            aws_secret_access_key=settings.s3_secret_access_key,
            use_ssl=settings.s3_use_ssl,
        )

    def save_wav(self, wav_bytes: bytes, sample_rate: int) -> AudioAsset:
        audio_id = str(uuid4())
        key = self._key(audio_id)
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=wav_bytes,
            ContentType="audio/wav",
        )
        duration = max(0.1, (len(wav_bytes) - 44) / (sample_rate * 2))
        return AudioAsset(audio_id=audio_id, sample_rate=sample_rate, duration_sec=duration)

    def get(self, audio_id: str) -> str:
        key = self._key(audio_id)
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=3600,
        )

    def _key(self, audio_id: str) -> str:
        return f"{self.key_prefix}/{audio_id}.wav" if self.key_prefix else f"{audio_id}.wav"


class SupabaseAudioStore(AudioStore):
    def __init__(self) -> None:
        try:
            import requests
        except Exception as exc:  # pragma: no cover
            raise StorageError("requests is required for AUDIO_BACKEND=supabase") from exc

        if not settings.supabase_url or not settings.supabase_service_role_key:
            raise StorageError(
                "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set for AUDIO_BACKEND=supabase"
            )

        self.requests = requests
        self.base_url = settings.supabase_url.rstrip("/")
        self.bucket = settings.supabase_bucket
        self.key_prefix = settings.supabase_key_prefix.strip("/")
        self.api_key = settings.supabase_service_role_key

    def save_wav(self, wav_bytes: bytes, sample_rate: int) -> AudioAsset:
        audio_id = str(uuid4())
        key = self._key(audio_id)
        upload_url = f"{self.base_url}/storage/v1/object/{self.bucket}/{key}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "apikey": self.api_key,
            "Content-Type": "audio/wav",
            "x-upsert": "true",
        }
        response = self.requests.post(upload_url, headers=headers, data=wav_bytes, timeout=30)
        response.raise_for_status()

        duration = max(0.1, (len(wav_bytes) - 44) / (sample_rate * 2))
        return AudioAsset(audio_id=audio_id, sample_rate=sample_rate, duration_sec=duration)

    def get(self, audio_id: str) -> str:
        key = self._key(audio_id)
        sign_url = f"{self.base_url}/storage/v1/object/sign/{self.bucket}/{key}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "apikey": self.api_key,
            "Content-Type": "application/json",
        }
        response = self.requests.post(sign_url, headers=headers, json={"expiresIn": 3600}, timeout=15)
        response.raise_for_status()
        payload = response.json()
        signed_path = payload.get("signedURL") or payload.get("signedUrl")
        if not signed_path:
            raise StorageError("Supabase did not return a signed URL")
        if signed_path.startswith("http://") or signed_path.startswith("https://"):
            return signed_path
        return f"{self.base_url}/storage/v1{signed_path}"

    def _key(self, audio_id: str) -> str:
        return f"{self.key_prefix}/{audio_id}.wav" if self.key_prefix else f"{audio_id}.wav"


def build_audio_store() -> AudioStore:
    if settings.audio_backend == "s3":
        return S3AudioStore()
    if settings.audio_backend == "supabase":
        return SupabaseAudioStore()
    return LocalAudioStore()
