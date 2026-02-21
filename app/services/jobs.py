import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from threading import Lock
from typing import Callable, Literal
from uuid import uuid4

from app.config import settings
from app.models.errors import InferenceError
from app.services.store import AudioAsset

TaskHandler = Callable[[dict], AudioAsset]


@dataclass
class Job:
    status: Literal["queued", "running", "ready", "failed"]
    audio: AudioAsset | None = None
    error: str | None = None


class JobManager:
    def __init__(self) -> None:
        self.jobs: dict[str, Job] = {}
        self._lock = Lock()
        self._pool = ThreadPoolExecutor(max_workers=4)
        self._registry: dict[str, TaskHandler] = {}
        self._redis = None
        if settings.use_redis_jobs:
            try:
                import redis

                self._redis = redis.from_url(settings.redis_url, decode_responses=True)
            except Exception:
                self._redis = None

    def create(self) -> str:
        job_id = str(uuid4())
        with self._lock:
            self.jobs[job_id] = Job(status="queued")
        self._persist(job_id, "queued", None, None)
        return job_id

    def register_task(self, task_name: str, handler: TaskHandler) -> None:
        self._registry[task_name] = handler

    def mark_running(self, job_id: str) -> None:
        with self._lock:
            current = self.jobs.get(job_id, Job(status="queued"))
            self.jobs[job_id] = Job(status="running", audio=current.audio, error=current.error)
        self._persist(job_id, "running", None, None)

    def mark_ready(self, job_id: str, audio: AudioAsset) -> None:
        with self._lock:
            self.jobs[job_id] = Job(status="ready", audio=audio)
        self._persist(job_id, "ready", audio.audio_id, None, audio.sample_rate, audio.duration_sec)

    def mark_failed(self, job_id: str, error: str) -> None:
        with self._lock:
            self.jobs[job_id] = Job(status="failed", error=error)
        self._persist(job_id, "failed", None, error)

    def enqueue(self, job_id: str, fn: Callable[[], AudioAsset]) -> None:
        def run() -> None:
            self.mark_running(job_id)
            try:
                audio = fn()
                self.mark_ready(job_id, audio)
            except Exception as exc:
                message = str(exc)
                if isinstance(exc, InferenceError):
                    message = f"inference_error: {exc}"
                self.mark_failed(job_id, message)

        self._pool.submit(run)

    def enqueue_task(self, job_id: str, task_name: str, payload: dict) -> None:
        if self._redis is not None:
            item = json.dumps({"job_id": job_id, "task": task_name, "payload": payload})
            self._redis.lpush(self._queue_key(), item)
            return

        handler = self._registry.get(task_name)
        if handler is None:
            self.mark_failed(job_id, f"unknown task: {task_name}")
            return

        self.enqueue(job_id, lambda: handler(payload))

    def run_worker_once(self, timeout_s: int = 5) -> bool:
        if self._redis is None:
            return False

        item = self._redis.brpop(self._queue_key(), timeout=timeout_s)
        if not item:
            return False

        _, raw = item
        task = json.loads(raw)
        job_id = task["job_id"]
        name = task["task"]
        payload = task.get("payload", {})

        handler = self._registry.get(name)
        if handler is None:
            self.mark_failed(job_id, f"unknown task: {name}")
            return True

        self.mark_running(job_id)
        try:
            audio = handler(payload)
            self.mark_ready(job_id, audio)
        except Exception as exc:
            message = str(exc)
            if isinstance(exc, InferenceError):
                message = f"inference_error: {exc}"
            self.mark_failed(job_id, message)
        return True

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            if job_id in self.jobs:
                return self.jobs[job_id]

        if self._redis is not None:
            data = self._redis.hgetall(self._redis_key(job_id))
            if data:
                audio = None
                if data.get("audio_id"):
                    audio = AudioAsset(
                        audio_id=data["audio_id"],
                        sample_rate=int(data.get("sample_rate", 0) or 0),
                        duration_sec=float(data.get("duration_sec", 0.0) or 0.0),
                    )
                return Job(status=data.get("status", "failed"), audio=audio, error=data.get("error"))
        return None

    def _persist(
        self,
        job_id: str,
        status: str,
        audio_id: str | None,
        error: str | None,
        sample_rate: int = 0,
        duration_sec: float = 0.0,
    ) -> None:
        if self._redis is None:
            return
        payload = {
            "status": status,
            "audio_id": audio_id or "",
            "error": error or "",
            "sample_rate": str(sample_rate),
            "duration_sec": str(duration_sec),
        }
        self._redis.hset(self._redis_key(job_id), mapping=payload)
        self._redis.expire(self._redis_key(job_id), 60 * 60 * 24)

    def _redis_key(self, job_id: str) -> str:
        return f"naija:jobs:{job_id}"

    def _queue_key(self) -> str:
        return "naija:job_queue"
