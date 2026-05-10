from celery import Celery
from app.config import get_settings
from app.evaluator import run_full_eval, run_targeted_failed_eval
from app.orchestrator import run_job

settings = get_settings()
celery_app = Celery("delivery_readiness_worker", broker=settings.redis_url, backend=settings.redis_url)


@celery_app.task(name="run_query_job")
def run_query_job(job_id: str, query: str) -> None:
    run_job(job_id, query)


@celery_app.task(name="run_full_eval_job")
def run_full_eval_job() -> int:
    return run_full_eval()


@celery_app.task(name="run_targeted_failed_eval_job")
def run_targeted_failed_eval_job() -> int | None:
    return run_targeted_failed_eval()
