import time

from fastapi.testclient import TestClient

from app.main import app


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
