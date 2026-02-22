# Naija Translator App — Execution Plan (v4)

## 1) Scope and desired user experience
Build a web app where a user can:
1. Enter English text.
2. Generate **Nigerian-accented English audio** (play + download).
3. Translate English text to **Yoruba text**.
4. Generate **Yoruba audio** from the translated text (play + download).
5. Upload/record **Yoruba speech** and get **English text translation**.
6. Play and download the translated English text as **Nigerian-accented English audio**.

---

## 2) Model feasibility check (critical)
You requested these models:
- `NCAIR1/NigerianAccentedEnglish`
- `NCAIR1/Yoruba-ASR`

### What each model does
- `NCAIR1/NigerianAccentedEnglish` → text-to-speech style usage for Nigerian-accented English output.
- `NCAIR1/Yoruba-ASR` → **ASR only** (speech-to-text), not text-to-speech.

### Implication
To satisfy all requested flows:
- English text -> Yoruba text/audio requires a **Yoruba TTS** model.
- Yoruba speech -> English text requires a **2-step pipeline**:
  1) Yoruba ASR transcription (`Yoruba-ASR`), then
  2) Yoruba->English text translation model.

### Best-practice resolution
Use a pluggable model layer:
- Keep `Yoruba-ASR` for speech input transcription.
- Add dedicated translation adapters (`en->yo`, `yo->en`).
- Use `Workhelio/yoruba_tts` as the Yoruba TTS backend (benchmark and licensing verification still required before production).

---

## 3) Best language and framework choice
### Recommended stack
- **Backend language:** Python 3.11+
- **Backend API:** FastAPI
- **Inference runtime:** PyTorch + Hugging Face Transformers
- **Frontend:** Next.js (TypeScript) for production UX, or Jinja templates for MVP speed
- **Storage:** S3-compatible object storage for generated audio (MinIO/S3)
- **Background jobs:** Celery + Redis (or RQ) for long-running synthesis/transcription jobs

### Why this is best for your use case
- Python has strong Hugging Face support across ASR/TTS/translation.
- FastAPI gives clean async APIs + OpenAPI docs.
- Queue workers prevent timeout for heavier jobs.
- Object storage makes audio downloads reliable.

---

## 4) System architecture (clean separation)
```text
Frontend (Next.js)
   |
   v
FastAPI Gateway
   |--- Translation Service (EN->YO, YO->EN)
   |--- TTS Service (English TTS + Yoruba TTS)
   |--- ASR Service (Yoruba-ASR)
   |--- File Service (audio stream/download URLs)
   v
Redis Queue + Worker(s)
   v
Object Storage (audio files) + Postgres (metadata)
```

### Core design principles
- Adapters behind interfaces (`TextTranslator`, `TextToSpeech`, `SpeechToText`).
- Startup warm-loading for active models.
- Strict request validation and max input size.
- Idempotent jobs (same input + model can reuse cached output).

---

## 5) API contract (MVP)
### A) English text -> Yoruba text
`POST /api/v1/translate`
```json
{ "text": "How are you?", "source_lang": "en", "target_lang": "yo" }
```
Response
```json
{ "translated_text": "Bawo ni?", "model": "<en-yo-model-id>" }
```

### B) Yoruba speech -> English text
`POST /api/v1/speech/translate`
- Content-Type: `multipart/form-data`
- Fields: `audio_file`, `source_lang=yo`, `target_lang=en`

Response
```json
{
  "transcript_yo": "...",
  "translated_text_en": "...",
  "asr_model": "NCAIR1/Yoruba-ASR",
  "translation_model": "<yo-en-model-id>",
  "tts_job_id": "uuid",
  "tts_status": "queued"
}
```

### C) Text-to-speech generation
`POST /api/v1/tts`
```json
{ "text": "Bawo ni?", "lang": "yo", "voice": "default" }
```
Response
```json
{ "job_id": "uuid", "status": "queued" }
```

`GET /api/v1/tts/{job_id}`
```json
{
  "status": "ready",
  "audio_id": "uuid",
  "play_url": "/api/v1/audio/uuid",
  "download_url": "/api/v1/audio/uuid/download",
  "duration_sec": 2.41,
  "sample_rate": 22050
}
```

### D) Download/playback endpoints
- `GET /api/v1/audio/{audio_id}` -> stream for playback.
- `GET /api/v1/audio/{audio_id}/download` -> attachment download.

For Yoruba speech -> English flow, the backend should synthesize `translated_text_en` with `NCAIR1/NigerianAccentedEnglish`, then return standard audio play/download URLs.

---

## 6) Dependency plan
### Runtime dependencies
- `fastapi`
- `uvicorn[standard]`
- `pydantic-settings`
- `python-multipart`
- `torch`
- `transformers`
- `huggingface_hub`
- `torchaudio`
- `soundfile`
- `numpy`
- `celery`
- `redis`
- `sqlalchemy`
- `psycopg[binary]`
- `boto3`

### Dev quality dependencies
- `pytest`
- `pytest-asyncio`
- `httpx`
- `ruff`
- `black`
- `mypy`
- `pre-commit`

---

## 7) Data and storage design
### Postgres tables
- `translations` (id, source_text, translated_text, src_lang, dst_lang, model, created_at)
- `speech_translations` (id, source_audio_path, transcript_src, translated_text, asr_model, translation_model, created_at)
- `audio_assets` (id, text_hash, lang, model, path, duration, sample_rate, created_at, expires_at)
- `jobs` (id, type, status, payload_json, error, created_at, updated_at)

### Storage layout
- Audio: `audio/{lang}/{yyyy}/{mm}/{id}.wav`
- Return short-lived signed URLs in production.

---

## 8) Security and reliability best practices
- Input guardrails (max text length, max audio size, allowed MIME types).
- Per-IP/API-key rate limits.
- HF tokens in environment variables only.
- Structured logs + request IDs.
- Health endpoints: `/health/live` and `/health/ready`.
- Retry policy for transient model errors.
- Dead-letter queue for repeated failures.
- TTL cleanup for expired audio files.

---

## 9) Performance plan
- Warm model instances on startup.
- Queue TTS/ASR heavy jobs.
- Cache repeated requests by content hash and model/version.
- GPU preferred, CPU fallback.
- Track metrics: p50/p95 latency, queue time, success rate.

---

## 10) Testing strategy
### Unit tests
- Translator adapters (`en->yo`, `yo->en`).
- TTS adapter output validation (duration > 0, sample rate).
- ASR adapter parsing/error handling.
- Post-processing pipeline that converts `translated_text_en` into Nigerian-accented English audio.

### API tests
- Happy paths:
  - `translate` (en->yo)
  - `speech/translate` (yo speech->en text)
  - `tts` + audio download
  - translated English audio playback/download from speech input
- Validation failures (empty text, bad audio type, oversize payload).
- Job lifecycle transitions (`queued -> running -> ready/failed`).

### Integration checks
- Redis queue execution.
- Object storage upload/download links for audio.
- Model warm-load smoke test.

---

## 11) Delivery phases (practical)
### Phase 0 — Validation spike (1–2 days)
- Validate model I/O signatures and licenses.
- Benchmark ASR/TTS/translation latency and quality.
- Validate and finalize `Workhelio/yoruba_tts` + Yoruba->English translation model.

### Phase 1 — MVP backend (3–4 days)
- Scaffold FastAPI + workers + storage.
- Implement endpoints for translate, speech-translate, tts, downloads.

### Phase 2 — MVP frontend (2–3 days)
- Add text input flow and Yoruba speech upload/record flow.
- Add player + download buttons for generated audio (including speech-translated English output).

### Phase 3 — Production hardening (3–5 days)
- Monitoring/alerts, retries, caching, cleanup scheduler, CI/CD.

---

## 12) Minimum acceptance criteria
- English text -> Nigerian-accented English audio (playable + downloadable).
- English text -> Yoruba text.
- Yoruba text -> Yoruba audio (playable + downloadable).
- Yoruba speech -> English translation can be played and downloaded as Nigerian-accented English audio.
- API docs published and tests pass in CI.

---


## 13) Yoruba TTS model decision
### Selected Yoruba TTS model
- `Workhelio/yoruba_tts` (Hugging Face): https://huggingface.co/Workhelio/yoruba_tts

### Integration guidance
- Use `Workhelio/yoruba_tts` as the default `TextToSpeech` provider for `lang=yo`.
- Keep the TTS adapter interface pluggable so this model can be replaced without API changes.
- During Phase 0, validate:
  - pronunciation quality on Yoruba prompts,
  - latency on target hardware,
  - output sample rate/format compatibility,
  - license and deployment constraints.

### Minimal acceptance checks for this model
- Produces intelligible Yoruba audio for at least 30 representative prompts.
- Maintains stable synthesis for short and long text inputs.
- Meets target latency budgets in staging.
- Works with playback/download endpoint contract (`/api/v1/audio/{audio_id}` and `/download`).

---
## 14) First implementation commands (starter)
```bash
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install fastapi uvicorn[standard] pydantic-settings python-multipart \
            torch transformers huggingface_hub torchaudio soundfile numpy \
            celery redis sqlalchemy psycopg[binary] boto3
pip install -U pytest pytest-asyncio httpx ruff black mypy pre-commit
```

This foundation supports text/speech translation workflows with playable/downloadable audio outputs.
