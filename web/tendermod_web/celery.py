import os
from celery import Celery
from celery.signals import worker_process_init

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tendermod_web.settings.local')

app = Celery('tendermod_web')

# Load task modules from all registered Django apps.
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()


@worker_process_init.connect
def close_db_connections_on_fork(**kwargs):
    """
    Cierra todas las conexiones DB heredadas del proceso padre por fork.
    Sin esto, Celery ForkPoolWorker hereda file descriptors abiertos al SQLite
    del proceso principal, causando 'disk I/O error' al intentar escribir.
    """
    from django.db import connections
    connections.close_all()


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
