import time

from app.services.jobs import JobManager
from app.services.store import AudioAsset


def test_job_manager_async_ready() -> None:
    manager = JobManager()
    job_id = manager.create()

    def work() -> AudioAsset:
        return AudioAsset(audio_id='a1', sample_rate=22050, duration_sec=1.0)

    manager.enqueue(job_id, work)

    start = time.time()
    while time.time() - start < 1.0:
        job = manager.get(job_id)
        if job and job.status == 'ready':
            assert job.audio is not None
            assert job.audio.audio_id == 'a1'
            return
        time.sleep(0.01)

    raise AssertionError('job did not reach ready state')
