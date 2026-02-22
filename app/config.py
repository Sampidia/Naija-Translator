import os


def get_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class Settings:
    audio_backend: str = os.getenv("AUDIO_BACKEND", "local")  # local|s3|supabase
    local_audio_root: str = os.getenv("LOCAL_AUDIO_ROOT", "app/storage/audio")

    use_real_models: bool = get_bool("USE_REAL_MODELS", False)
    en_yo_model_id: str = os.getenv("EN_YO_MODEL_ID", "google/madlad400-3b-mt")
    yo_en_model_id: str = os.getenv("YO_EN_MODEL_ID", "google/madlad400-3b-mt")
    yoruba_asr_model_id: str = os.getenv("YORUBA_ASR_MODEL_ID", "openai/whisper-large-v3")
    nigerian_english_tts_model_id: str = os.getenv(
        "NIGERIAN_ENGLISH_TTS_MODEL_ID", "facebook/mms-tts-eng"
    )
    yoruba_tts_model_id: str = os.getenv("YORUBA_TTS_MODEL_ID", "facebook/mms-tts-yor")

    require_api_key: bool = get_bool("REQUIRE_API_KEY", False)
    api_key: str = os.getenv("API_KEY", "")
    rate_limit_per_minute: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))

    use_redis_jobs: bool = get_bool("USE_REDIS_JOBS", False)
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    s3_bucket: str = os.getenv("S3_BUCKET", "")
    s3_region: str = os.getenv("S3_REGION", "us-east-1")
    s3_endpoint_url: str | None = os.getenv("S3_ENDPOINT_URL")
    s3_access_key_id: str | None = os.getenv("S3_ACCESS_KEY_ID")
    s3_secret_access_key: str | None = os.getenv("S3_SECRET_ACCESS_KEY")
    s3_use_ssl: bool = get_bool("S3_USE_SSL", False)
    s3_key_prefix: str = os.getenv("S3_KEY_PREFIX", "audio")

    supabase_url: str = os.getenv("SUPABASE_URL", "")
    supabase_service_role_key: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    supabase_bucket: str = os.getenv("SUPABASE_BUCKET", "audio")
    supabase_key_prefix: str = os.getenv("SUPABASE_KEY_PREFIX", "audio")
    google_application_credentials_json: str | None = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON")


settings = Settings()
