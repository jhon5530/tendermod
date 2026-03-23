import sqlite3
import logging

from django.conf import settings
from django.http import JsonResponse
from celery.result import AsyncResult

logger = logging.getLogger(__name__)


def task_status(request, task_id):
    """
    Generic Celery task status polling endpoint.
    Returns JSON: {status, result, error}
    status values: PENDING | STARTED | SUCCESS | FAILURE
    """
    result = AsyncResult(task_id)
    data = {
        'status': result.status,
        'result': None,
        'error': None,
    }

    if result.successful():
        data['result'] = result.result
    elif result.failed():
        data['error'] = str(result.result)

    return JsonResponse(data)


def db_status(request):
    """
    Returns record counts from the backend SQLite database.
    Used in the redneet dashboard to confirm data was loaded.
    """
    db_path = settings.TENDERMOD_DB_DIR / 'redneet_database.db'

    counts = {
        'indicadores': 0,
        'experiencia': 0,
        'db_exists': False,
        'error': None,
    }

    if not db_path.exists():
        counts['error'] = f'Base de datos no encontrada en {db_path}'
        return JsonResponse(counts)

    try:
        with sqlite3.connect(str(db_path)) as conn:
            cur = conn.cursor()

            # Table 'indicadores'
            try:
                cur.execute('SELECT COUNT(*) FROM indicadores')
                counts['indicadores'] = cur.fetchone()[0]
            except sqlite3.OperationalError:
                counts['indicadores'] = 0

            # Table 'experiencia'
            try:
                cur.execute('SELECT COUNT(*) FROM experiencia')
                counts['experiencia'] = cur.fetchone()[0]
            except sqlite3.OperationalError:
                counts['experiencia'] = 0

        counts['db_exists'] = True
    except Exception as exc:
        logger.error('Error consultando db_status: %s', exc)
        counts['error'] = str(exc)

    return JsonResponse(counts)
