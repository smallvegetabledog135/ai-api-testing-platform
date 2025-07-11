# celery_config.py
from celery import Celery

celery_app = Celery(
    'test_platform',
    broker='pyamqp://guest:guest@localhost:5672//',
    backend='redis://localhost:6379/0'
)

celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='Asia/Shanghai',
    task_track_started=True,
    task_time_limit=3600,  # 1小时超时
    worker_prefetch_multiplier=1  # 控制预取消息数量
)