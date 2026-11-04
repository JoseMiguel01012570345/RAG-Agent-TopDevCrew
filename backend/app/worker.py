import app.tasks as tasks
from app.celery_app import celery

__all__ = ["celery", "tasks"]
