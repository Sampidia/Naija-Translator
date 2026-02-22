from pydantic import BaseModel, Field


class TranslateRequest(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    source_lang: str = Field(pattern="^(en|yo|ig|ha)$")
    target_lang: str = Field(pattern="^(en|yo|ig|ha)$")


class TranslateResponse(BaseModel):
    translated_text: str
    model: str


class TTSRequest(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    lang: str = Field(pattern="^(en|yo|ig|ha)$")
    voice: str = "default"


class JobResponse(BaseModel):
    job_id: str
    status: str


class TTSStatusResponse(BaseModel):
    status: str
    audio_id: str | None = None
    play_url: str | None = None
    download_url: str | None = None
    duration_sec: float | None = None
    sample_rate: int | None = None


class SpeechTranslateResponse(BaseModel):
    transcript_yo: str
    translated_text_en: str
    asr_model: str
    translation_model: str
    tts_job_id: str
    tts_status: str
