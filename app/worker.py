import time

from app.config import settings
from app.services.runtime import jobs


def main() -> None:
    if not settings.use_redis_jobs:
        raise SystemExit("USE_REDIS_JOBS must be true to run the external worker")

    print("Naija worker started (Redis queue mode)")
    while True:
        processed = jobs.run_worker_once(timeout_s=5)
        if not processed:
            time.sleep(0.2)


if __name__ == "__main__":
    main()
