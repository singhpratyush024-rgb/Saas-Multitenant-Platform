# app/worker/celery_app.py

from celery import Celery
from celery.schedules import crontab
import os
from dotenv import load_dotenv

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
BROKER_URL = REDIS_URL + "/1"
BACKEND_URL = REDIS_URL + "/2"

celery_app = Celery(
    "saas_worker",
    broker=BROKER_URL,
    backend=BACKEND_URL,
    include=["app.worker.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    result_expires=86400,
    task_track_started=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,

    beat_schedule={
        "clean-expired-invitations": {
            "task": "app.worker.tasks.clean_expired_invitations",
            "schedule": crontab(minute=0),
        },
        "daily-digest": {
            "task": "app.worker.tasks.send_daily_digest",
            "schedule": crontab(hour=8, minute=0),
        },
        "usage-stats": {
            "task": "app.worker.tasks.collect_usage_stats",
            "schedule": crontab(hour=0, minute=0),
        },
        "auto-downgrade-trials": {
            "task": "app.worker.tasks.auto_downgrade_expired_trials",
            "schedule": crontab(minute=0),   # every hour
        },
        "auto-downgrade-grace-periods": {
            "task": "app.worker.tasks.auto_downgrade_expired_grace_periods",
            "schedule": crontab(minute=30),  # every hour at :30
        },
    },
)