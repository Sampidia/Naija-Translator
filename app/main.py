from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, Request, Response, UploadFile, status
from fastapi.responses import FileResponse, RedirectResponse

from app.models.errors import InferenceError, StorageError
from app.schemas import (
    JobResponse,
    SpeechTranslateResponse,
    TTSRequest,
    TTSStatusResponse,
    TranslateRequest,
    TranslateResponse,
)
from app.services.runtime import asr, audio_store, english_tts, jobs, translator, yoruba_tts
from app.services.readiness import evaluate_readiness
from app.services.security import enforce_rate_limit, require_api_key

app = FastAPI(title="Naija Translator API", version="0.2.0")


@app.get("/", response_class=FileResponse)
def index() -> FileResponse:
    return FileResponse(Path(__file__).parent / "static" / "index.html")


@app.get("/health/live")
def health_live() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready")
def health_ready(response: Response) -> dict[str, str | dict[str, str]]:
    report = evaluate_readiness()
    if not report.ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "not_ready", "checks": report.checks}
    return {"status": "ready", "checks": report.checks}


@app.post("/api/v1/translate", response_model=TranslateResponse)
def translate(
    payload: TranslateRequest,
    _api: None = Depends(require_api_key),
    _rate: None = Depends(enforce_rate_limit),
) -> TranslateResponse:
    try:
        result = translator.translate(payload.text, payload.source_lang, payload.target_lang)
    except InferenceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return TranslateResponse(translated_text=result.text, model=result.model_id)


@app.post("/api/v1/tts", response_model=JobResponse)
def tts(
    payload: TTSRequest,
    _api: None = Depends(require_api_key),
    _rate: None = Depends(enforce_rate_limit),
) -> JobResponse:
    job_id = jobs.create()
    jobs.enqueue_task(
        job_id,
        "tts",
        {"text": payload.text, "lang": payload.lang, "voice": payload.voice},
    )
    return JobResponse(job_id=job_id, status="queued")


@app.get("/api/v1/tts/{job_id}", response_model=TTSStatusResponse)
def tts_status(job_id: str) -> TTSStatusResponse:
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    if job.status == "failed":
        raise HTTPException(status_code=500, detail=job.error or "job failed")
    if job.status != "ready" or not job.audio:
        return TTSStatusResponse(status=job.status)
    return TTSStatusResponse(
        status="ready",
        audio_id=job.audio.audio_id,
        play_url=f"/api/v1/audio/{job.audio.audio_id}",
        download_url=f"/api/v1/audio/{job.audio.audio_id}/download",
        duration_sec=job.audio.duration_sec,
        sample_rate=job.audio.sample_rate,
    )


@app.post("/api/v1/speech/translate", response_model=SpeechTranslateResponse)
def speech_translate(
    request: Request,
    audio_file: UploadFile = File(...),
    source_lang: str = "yo",
    target_lang: str = "en",
    _api: None = Depends(require_api_key),
    _rate: None = Depends(enforce_rate_limit),
) -> SpeechTranslateResponse:
    try:
        transcript, asr_model = asr.transcribe(audio_file.file.read(), source_lang)
        translated = translator.translate(transcript, source_lang, target_lang)
    except InferenceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    job_id = jobs.create()
    jobs.enqueue_task(job_id, "english_tts", {"text": translated.text})

    return SpeechTranslateResponse(
        transcript_yo=transcript,
        translated_text_en=translated.text,
        asr_model=asr_model,
        translation_model=translated.model_id,
        tts_job_id=job_id,
        tts_status="queued",
    )


@app.get("/api/v1/audio/{audio_id}", response_model=None)
def audio_stream(audio_id: str) -> FileResponse | RedirectResponse:
    try:
        location = audio_store.get(audio_id)
    except (RuntimeError, StorageError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if location.startswith("http://") or location.startswith("https://"):
        return RedirectResponse(location)

    path = Path(location)
    if not path.exists():
        raise HTTPException(status_code=404, detail="audio not found")
    return FileResponse(path, media_type="audio/wav")


@app.get("/api/v1/audio/{audio_id}/download", response_model=None)
def audio_download(audio_id: str) -> FileResponse | RedirectResponse:
    try:
        location = audio_store.get(audio_id)
    except (RuntimeError, StorageError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if location.startswith("http://") or location.startswith("https://"):
        return RedirectResponse(location)

    path = Path(location)
    if not path.exists():
        raise HTTPException(status_code=404, detail="audio not found")
    return FileResponse(path, media_type="audio/wav", filename=f"{audio_id}.wav")
