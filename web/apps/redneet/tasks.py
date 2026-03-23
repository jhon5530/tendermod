import logging
from celery import shared_task
from django.db import connection

logger = logging.getLogger(__name__)


@shared_task(bind=True, name='redneet.load_indicadores_task')
def load_indicadores_task(self):
    """
    Carga el archivo rib.xlsx desde TENDERMOD_DB_DIR a la tabla 'indicadores' en SQLite.
    El archivo debe haber sido copiado a TENDERMOD_DB_DIR/rib.xlsx antes de invocar esta tarea.
    """
    connection.close()
    try:
        from tendermod.data_sources.redneet_db.xls_loader import load_db
        load_db('indicadores', 'rib.xlsx')
        logger.info('Tabla indicadores cargada exitosamente')
        return {'status': 'ok', 'message': 'Indicadores cargados correctamente'}
    except Exception as exc:
        logger.error('Error cargando indicadores: %s', exc)
        raise self.retry(exc=exc, countdown=5, max_retries=1)


@shared_task(bind=True, name='redneet.load_experiencia_task')
def load_experiencia_task(self):
    """
    Carga experiencia_rup.xlsx a SQLite y luego ingesta en ChromaDB de experiencia.
    El archivo debe haber sido copiado a TENDERMOD_DB_DIR/experiencia_rup.xlsx.
    """
    connection.close()
    try:
        from tendermod.data_sources.redneet_db.xls_loader import load_db
        from tendermod.ingestion.ingestion_experience_flow import ingest_experience_data

        logger.info('Cargando experiencia_rup.xlsx a SQLite...')
        load_db('experiencia', 'experiencia_rup.xlsx')
        logger.info('Tabla experiencia cargada. Ingresando a ChromaDB...')
        ingest_experience_data()
        logger.info('Experiencia cargada en ChromaDB exitosamente')
        return {'status': 'ok', 'message': 'Experiencia cargada y vectorizada correctamente'}
    except Exception as exc:
        logger.error('Error cargando experiencia: %s', exc)
        raise self.retry(exc=exc, countdown=5, max_retries=1)
