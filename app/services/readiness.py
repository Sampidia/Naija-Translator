import os
from dataclasses import dataclass

from app.config import settings


@dataclass
class ReadinessReport:
    ready: bool
    checks: dict[str, str]


def evaluate_readiness() -> ReadinessReport:
    checks: dict[str, str] = {}

    checks["audio_backend"] = _check_audio_backend()
    checks["real_models_enabled"] = "true" if settings.use_real_models else "false"
    checks["hf_token_set"] = "true" if os.getenv("HF_TOKEN") else "false"
    checks["real_models_deps"] = _check_real_model_dependencies()

    ready = all(status == "ok" for status in checks.values())
    return ReadinessReport(ready=ready, checks=checks)


def _check_audio_backend() -> str:
    backend = settings.audio_backend
    if backend == "s3" and not settings.s3_bucket:
        return "error"
    if backend == "supabase":
        if not settings.supabase_url or not settings.supabase_service_role_key:
            return "error"
    if backend not in {"local", "s3", "supabase"}:
        return "error"
    return "ok"


def _check_real_model_dependencies() -> str:
    if not settings.use_real_models:
        return "ok"
    # We now use HF Inference API (HTTP), only need requests
    try:
        import requests  # noqa: F401
    except Exception:
        return "error"
    token = os.getenv("HF_TOKEN", "").strip()
    if not token:
        return "warning:no_hf_token"
    return "ok"
