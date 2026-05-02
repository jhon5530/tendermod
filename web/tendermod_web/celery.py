import os
from celery import Celery
from celery.signals import worker_process_init, task_postrun
from django.db.backends.signals import connection_created

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tendermod_web.settings.local')

app = Celery('tendermod_web')

# Load task modules from all registered Django apps.
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()


@worker_process_init.connect
def close_db_connections_on_fork(**kwargs):
    """Cierra conexiones DB heredadas del proceso padre (aplica en ForkPool)."""
    from django.db import connections
    connections.close_all()


@task_postrun.connect
def close_db_after_task(**kwargs):
    """
    Cierra TODAS las conexiones Django al terminar cada task.
    Sin esto, el WAL de SQLite queda abierto entre tasks y la segunda
    escritura falla con 'disk I/O error' porque el checkpoint nunca se completa.
    """
    from django.db import connections
    connections.close_all()


@connection_created.connect
def configure_sqlite_connection(connection, **kwargs):
    """Configura busy_timeout para tolerar contención momentánea en SQLite."""
    if connection.vendor == 'sqlite':
        connection.cursor().execute('PRAGMA busy_timeout=10000;')


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
