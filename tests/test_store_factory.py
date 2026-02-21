import importlib
import os

import pytest

from app.models.errors import StorageError


def _reload_store_module() -> object:
    import app.config as config
    import app.services.store as store

    importlib.reload(config)
    importlib.reload(store)
    return store


def test_build_audio_store_defaults_local(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AUDIO_BACKEND", raising=False)
    store = _reload_store_module()
    backend = store.build_audio_store()
    assert backend.__class__.__name__ == "LocalAudioStore"


def test_build_audio_store_supabase_requires_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUDIO_BACKEND", "supabase")
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)

    store = _reload_store_module()
    with pytest.raises(StorageError):
        store.build_audio_store()

    os.environ.pop("AUDIO_BACKEND", None)
