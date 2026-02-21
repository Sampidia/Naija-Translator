# Naija Translator (Implementation Scaffold)

FastAPI scaffold implementing the planned API flows:
- English <-> Yoruba text translation (placeholder translator)
- Yoruba speech -> English text translation (placeholder ASR + translator)
- TTS generation with model-oriented providers:
  - `NCAIR1/NigerianAccentedEnglish` (English audio path)
  - `Workhelio/yoruba_tts` (Yoruba audio path)
- Audio playback and download endpoints

## Run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Test

```bash
pip install -r requirements.txt
PYTHONPATH=. pytest -q
```

## CI

GitHub Actions runs compile checks and the full test suite on every push and pull request:
- Workflow: `.github/workflows/ci.yml`
- Steps: install dependencies, `python -m compileall app tests`, `PYTHONPATH=. pytest -q`

## Health endpoints
- `GET /health/live`
- `GET /health/ready` (returns 503 with failing `checks` when backend/model prerequisites are missing)

## Security controls
- Optional API key auth via `REQUIRE_API_KEY=true` and `API_KEY`.
- In-memory per-client rate limiting via `RATE_LIMIT_PER_MINUTE` (default 60).

## Do you need a FastAPI API key?
- **For local development/testing:** No. Keep `REQUIRE_API_KEY=false`.
- **For staging/production (recommended):** Yes. Set `REQUIRE_API_KEY=true` and a strong `API_KEY`, then send it as `x-api-key` on protected endpoints.
- Health endpoints (`/health/live`, `/health/ready`) remain unauthenticated for platform probes.

## Job backend
- Default in-process async workers.
- Optional Redis-backed job status persistence with `USE_REDIS_JOBS=true` and `REDIS_URL`.

## Real model mode
Set `USE_REAL_MODELS=true` to enable Hugging Face runtime model calls.
Model IDs can be overridden with:
- `EN_YO_MODEL_ID`
- `YO_EN_MODEL_ID`
- `YORUBA_ASR_MODEL_ID`
- `NIGERIAN_ENGLISH_TTS_MODEL_ID`
- `YORUBA_TTS_MODEL_ID`

If disabled, providers use safe local fallbacks for development.
When enabled, translation/ASR call Hugging Face pipelines and TTS uses `text-to-audio` pipeline output converted to WAV.

Copy `.env.example` to `.env` and set values for your backend.

## Audio storage backends
Default backend is local disk.

### Local (default)
- `AUDIO_BACKEND=local`
- Files are saved to `LOCAL_AUDIO_ROOT` (default `app/storage/audio`).

### S3 / MinIO
- `AUDIO_BACKEND=s3`
- Required: `S3_BUCKET`
- Optional/typical:
  - `S3_ENDPOINT_URL` (set this for MinIO, e.g. `http://localhost:9000`)
  - `S3_ACCESS_KEY_ID`
  - `S3_SECRET_ACCESS_KEY`
  - `S3_REGION` (default `us-east-1`)
  - `S3_USE_SSL` (`true`/`false`)
  - `S3_KEY_PREFIX` (default `audio`)

### Supabase Storage
- `AUDIO_BACKEND=supabase`
- Required:
  - `SUPABASE_URL` (e.g. `https://<project-ref>.supabase.co`)
  - `SUPABASE_SERVICE_ROLE_KEY`
- Optional:
  - `SUPABASE_BUCKET` (default `audio`)
  - `SUPABASE_KEY_PREFIX` (default `audio`)

Supabase backend uploads audio to Storage and uses signed URLs for retrieval.

When using S3/MinIO/Supabase, `/api/v1/audio/{audio_id}` and `/download` return redirects to signed URLs.

## Free / low-cost storage alternatives
Yes—you can avoid AWS S3 initially.

- **MinIO self-hosted**: free software, good S3-compatible choice for development and small deployments.
- **Cloudflare R2**: S3-compatible API with low/zero egress to Cloudflare ecosystem; often cheaper than S3.
- **Backblaze B2**: low-cost object storage; can be used via S3-compatible endpoint.
- **Supabase Storage**: managed storage with free tier (good for MVPs).

### About Vercel
- Vercel is excellent for frontend/serverless hosting, but it is **not** a persistent object store for generated media.
- Vercel functions have ephemeral filesystem; generated audio should still be stored in object storage (S3/MinIO/R2/B2/Supabase), then served via signed URLs.

### Practical MVP recommendation
- Host API + worker on a VM/container.
- Use **MinIO (self-hosted)** or **Supabase Storage free tier** first.
- Keep `AUDIO_BACKEND=s3` and point `S3_ENDPOINT_URL` to your chosen S3-compatible provider.
- If using Supabase directly, set `AUDIO_BACKEND=supabase` and provide Supabase credentials.

## Deployment target (recommended for this project)
- **Frontend**: deploy to **Vercel** (best fit for Next.js/React UI hosting).
- **Backend API + background workers**: deploy FastAPI and job workers to a container host (Render, Railway, Fly.io, or VPS/Docker).
- **Audio artifacts**: keep using **Supabase Storage** for generated audio and signed download/play URLs.

This split keeps Vercel for frontend delivery while running ASR/TTS inference and queue processing on compute better suited for Python/ML workloads.

## Implementation process (all steps)
1. **Backend API foundation** (done): translation, TTS jobs, speech->English, playback/download endpoints.
2. **Storage + environment hardening** (done): local/S3/Supabase backends, readiness checks, CI test workflow.
3. **Frontend MVP** (done in-repo): browser UI at `/` for translate, TTS generation, speech upload, playback/download.
4. **Security baseline** (done): optional API key + rate limiting.
5. **Production model rollout** (next): run with `USE_REAL_MODELS=true`, validate quality/latency, tune model IDs.
6. **Durable worker rollout** (next): move from in-process executor to dedicated queue workers for restart-safe processing.

## Frontend readiness
- A lightweight in-repo frontend MVP is now available at `/` (`app/static/index.html`).
- It supports text translation, TTS generation with polling, Yoruba speech upload, playback, and download links.
- Next UI milestone: move this MVP into a dedicated Next.js frontend for Vercel deployment and stronger UX/accessibility.

> Note: inference providers are placeholders currently; this scaffold focuses on production-ready API and storage wiring.

## What’s next (execution order)
1. **Run real models in staging** (`USE_REAL_MODELS=true`) and verify quality/latency for:
   - `NCAIR1/Yoruba-ASR`
   - `NCAIR1/NigerianAccentedEnglish`
   - `Workhelio/yoruba_tts`
2. **Harden job execution** by replacing in-process `ThreadPoolExecutor` with a durable queue worker (Celery/RQ + Redis) so jobs survive restarts.
3. **Split deployment for production**:
   - Vercel for frontend
   - container host for FastAPI API + workers
   - Supabase Storage for generated audio
4. **Production security**:
   - set `REQUIRE_API_KEY=true`
   - set strong `API_KEY`
   - tune `RATE_LIMIT_PER_MINUTE`
5. **Release gate**:
   - require CI green (`compileall` + `pytest`)
   - run staged E2E checks for translate -> TTS -> stream/download.

