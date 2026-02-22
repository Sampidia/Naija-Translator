from app.services.readiness import evaluate_readiness


def test_readiness_ok_for_local_backend(monkeypatch):
    monkeypatch.setattr('app.services.readiness.settings.audio_backend', 'local')
    monkeypatch.setattr('app.services.readiness.settings.use_real_models', False)

    report = evaluate_readiness()
    assert report.ready is True
    assert report.checks['audio_backend'] == 'ok'
    assert report.checks['real_models'] == 'ok'


def test_readiness_fails_for_supabase_missing_credentials(monkeypatch):
    monkeypatch.setattr('app.services.readiness.settings.audio_backend', 'supabase')
    monkeypatch.setattr('app.services.readiness.settings.supabase_url', '')
    monkeypatch.setattr('app.services.readiness.settings.supabase_service_role_key', '')
    monkeypatch.setattr('app.services.readiness.settings.use_real_models', False)

    report = evaluate_readiness()
    assert report.ready is False
    assert report.checks['audio_backend'] == 'error'
