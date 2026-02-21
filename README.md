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

## Frontend readiness
- This repository currently contains a **backend scaffold only** (FastAPI routes, async jobs, storage adapters, tests).
- A production frontend UI is **not built yet** in this codebase.
- Recommended next UI milestone: implement a Next.js app with:
  - text translation inputs (`en <-> yo`),
  - Yoruba speech upload/record,
  - audio playback and download controls,
  - job status polling for async TTS/speech jobs.

> Note: inference providers are placeholders currently; this scaffold focuses on production-ready API and storage wiring.
