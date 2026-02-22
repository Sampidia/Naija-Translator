import time
from collections import defaultdict, deque

from fastapi.testclient import TestClient

from app.main import app
from app.services import security as security_module


client = TestClient(app)

def _wait_for_ready(job_id: str, timeout_s: float = 2.0) -> dict:
    start = time.time()
    while time.time() - start < timeout_s:
        status = client.get(f'/api/v1/tts/{job_id}')
        if status.status_code == 200 and status.json()['status'] == 'ready':
            return status.json()
        time.sleep(0.02)
    raise AssertionError('job did not become ready in time')


def test_health_live() -> None:
    response = client.get('/health/live')
    assert response.status_code == 200
    assert response.json()['status'] == 'ok'


def test_health_ready() -> None:
    response = client.get('/health/ready')
    assert response.status_code == 200
    assert response.json()['status'] == 'ready'


def test_translate() -> None:
    response = client.post(
        '/api/v1/translate',
        json={'text': 'Hello world', 'source_lang': 'en', 'target_lang': 'yo'},
    )
    assert response.status_code == 200
    body = response.json()
    assert body['translated_text'].startswith('[YO]')


def test_tts_job_and_audio_download() -> None:
    create = client.post('/api/v1/tts', json={'text': 'Bawo ni', 'lang': 'yo', 'voice': 'default'})
    assert create.status_code == 200
    job_id = create.json()['job_id']

    payload = _wait_for_ready(job_id)
    assert payload['audio_id']

    audio = client.get(payload['play_url'])
    assert audio.status_code == 200
    assert audio.headers['content-type'] in ('audio/wav', 'audio/x-wav')


def test_speech_translate() -> None:
    files = {'audio_file': ('sample.wav', b'RIFF....WAVEfmt ', 'audio/wav')}
    response = client.post('/api/v1/speech/translate', files=files)
    assert response.status_code == 200
    body = response.json()
    assert body['asr_model'] == 'NCAIR1/Yoruba-ASR'
    assert body['translated_text_en'].startswith('[EN]')

    payload = _wait_for_ready(body['tts_job_id'])
    assert payload['status'] == 'ready'


def test_index_serves_frontend() -> None:
    response = client.get('/')
    assert response.status_code == 200
    assert 'text/html' in response.headers['content-type']
    assert 'Naija Translator UI (MVP)' in response.text


def test_translate_requires_api_key_when_enabled() -> None:
    original_require = security_module.settings.require_api_key
    original_key = security_module.settings.api_key
    try:
        security_module.settings.require_api_key = True
        security_module.settings.api_key = 'secret-key'

        missing = client.post('/api/v1/translate', json={'text': 'hello', 'source_lang': 'en', 'target_lang': 'yo'})
        assert missing.status_code == 401

        wrong = client.post('/api/v1/translate', headers={'x-api-key': 'wrong'}, json={'text': 'hello', 'source_lang': 'en', 'target_lang': 'yo'})
        assert wrong.status_code == 401

        ok = client.post('/api/v1/translate', headers={'x-api-key': 'secret-key'}, json={'text': 'hello', 'source_lang': 'en', 'target_lang': 'yo'})
        assert ok.status_code == 200
    finally:
        security_module.settings.require_api_key = original_require
        security_module.settings.api_key = original_key


def test_rate_limit_blocks_excess_requests() -> None:
    original_limit = security_module.rate_limiter.limit
    original_hits = security_module.rate_limiter.hits
    try:
        security_module.rate_limiter.limit = 1
        security_module.rate_limiter.hits = defaultdict(deque)

        first = client.post('/api/v1/translate', json={'text': 'a', 'source_lang': 'en', 'target_lang': 'yo'})
        assert first.status_code == 200

        second = client.post('/api/v1/translate', json={'text': 'b', 'source_lang': 'en', 'target_lang': 'yo'})
        assert second.status_code == 429
    finally:
        security_module.rate_limiter.limit = original_limit
        security_module.rate_limiter.hits = original_hits
