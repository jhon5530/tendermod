import sqlite3
import logging
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.http import FileResponse, Http404
from django.shortcuts import render, redirect
from django.views.decorators.http import require_POST

from apps.core.models import SystemConfig
from .forms import IndicadoresUploadForm, ExperienciaUploadForm, EquipoUploadForm
from .tasks import load_indicadores_task, load_experiencia_task, load_team_task

logger = logging.getLogger(__name__)


def dashboard(request):
    """
    Vista 1: Dashboard de datos de la empresa (Redneet).
    Muestra formularios de carga de Excels y el estado actual de las tablas SQLite.
    """
    context = {
        'form_indicadores': IndicadoresUploadForm(),
        'form_experiencia': ExperienciaUploadForm(),
        'form_equipo': EquipoUploadForm(),
        'task_id_indicadores': request.session.get('task_id_indicadores'),
        'task_id_experiencia': request.session.get('task_id_experiencia'),
        'task_id_equipo': request.session.get('task_id_equipo'),
    }
    return render(request, 'redneet/dashboard.html', context)


@require_POST
def upload_indicadores(request):
    """
    Recibe rib.xlsx, lo copia a TENDERMOD_DB_DIR y lanza la tarea Celery.
    """
    form = IndicadoresUploadForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, 'Archivo invalido: ' + str(form.errors))
        return redirect('redneet:dashboard')

    archivo = form.cleaned_data['archivo']
    dest = settings.TENDERMOD_DB_DIR / 'rib.xlsx'

    try:
        settings.TENDERMOD_DB_DIR.mkdir(parents=True, exist_ok=True)
        with open(dest, 'wb') as f:
            for chunk in archivo.chunks():
                f.write(chunk)
        logger.info('rib.xlsx copiado a %s', dest)
    except Exception as exc:
        logger.error('Error copiando rib.xlsx: %s', exc)
        messages.error(request, f'Error al guardar el archivo: {exc}')
        return redirect('redneet:dashboard')

    task = load_indicadores_task.delay()
    request.session['task_id_indicadores'] = task.id
    logger.info('Tarea load_indicadores_task lanzada: %s', task.id)

    messages.success(request, 'Archivo recibido. Procesando indicadores en segundo plano...')
    return redirect('redneet:dashboard')


@require_POST
def upload_experiencia(request):
    """
    Recibe experiencia_rup.xlsx, lo copia a TENDERMOD_DB_DIR y lanza la tarea Celery.
    """
    form = ExperienciaUploadForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, 'Archivo invalido: ' + str(form.errors))
        return redirect('redneet:dashboard')

    archivo = form.cleaned_data['archivo']
    dest = settings.TENDERMOD_DB_DIR / 'experiencia_rup.xlsx'

    try:
        settings.TENDERMOD_DB_DIR.mkdir(parents=True, exist_ok=True)
        with open(dest, 'wb') as f:
            for chunk in archivo.chunks():
                f.write(chunk)
        logger.info('experiencia_rup.xlsx copiado a %s', dest)
    except Exception as exc:
        logger.error('Error copiando experiencia_rup.xlsx: %s', exc)
        messages.error(request, f'Error al guardar el archivo: {exc}')
        return redirect('redneet:dashboard')

    task = load_experiencia_task.delay()
    request.session['task_id_experiencia'] = task.id
    logger.info('Tarea load_experiencia_task lanzada: %s', task.id)

    messages.success(request, 'Archivo recibido. Cargando experiencia y vectorizando en ChromaDB...')
    return redirect('redneet:dashboard')


@require_POST
def upload_equipo(request):
    """
    Recibe el Excel de equipo, lo copia a TENDERMOD_DB_DIR y lanza la tarea Celery.
    """
    form = EquipoUploadForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, 'Archivo invalido: ' + str(form.errors))
        return redirect('redneet:dashboard')

    archivo = form.cleaned_data['archivo']
    dest = settings.TENDERMOD_DB_DIR / 'certificaciones_personal.xlsx'

    try:
        settings.TENDERMOD_DB_DIR.mkdir(parents=True, exist_ok=True)
        with open(dest, 'wb') as f:
            for chunk in archivo.chunks():
                f.write(chunk)
        logger.info('certificaciones_personal.xlsx copiado a %s', dest)
    except Exception as exc:
        logger.error('Error copiando certificaciones_personal.xlsx: %s', exc)
        messages.error(request, f'Error al guardar el archivo: {exc}')
        return redirect('redneet:dashboard')

    task = load_team_task.delay()
    request.session['task_id_equipo'] = task.id
    logger.info('Tarea load_team_task lanzada: %s', task.id)

    messages.success(request, 'Archivo recibido. Cargando datos del equipo en segundo plano...')
    return redirect('redneet:dashboard')


def _get_db_path() -> Path:
    return settings.TENDERMOD_DB_DIR / "redneet_database.db"


@require_POST
def clear_indicadores(request):
    """Borra la tabla 'indicadores' de SQLite y el archivo rib.xlsx."""
    db_path = _get_db_path()
    try:
        if db_path.exists():
            with sqlite3.connect(str(db_path)) as conn:
                conn.execute("DELETE FROM indicadores")
                conn.commit()
        xlsx = settings.TENDERMOD_DB_DIR / "rib.xlsx"
        if xlsx.exists():
            xlsx.unlink()
        messages.success(request, "Indicadores financieros eliminados correctamente.")
        logger.info("[clear_indicadores] Tabla indicadores vaciada")
    except Exception as exc:
        logger.error("[clear_indicadores] Error: %s", exc)
        messages.error(request, f"Error al borrar indicadores: {exc}")
    return redirect("redneet:dashboard")


@require_POST
def clear_experiencia(request):
    """Borra la tabla 'experiencia' de SQLite, el ChromaDB de experiencia y el xlsx."""
    db_path = _get_db_path()
    try:
        if db_path.exists():
            with sqlite3.connect(str(db_path)) as conn:
                conn.execute("DELETE FROM experiencia")
                conn.commit()
        # Borrar ChromaDB de experiencia
        from tendermod.config.settings import CHROMA_EXPERIENCE_PERSIST_DIR
        from tendermod.retrieval.vectorstore import delete_current_vectorStore
        from chromadb.api.shared_system_client import SharedSystemClient
        delete_current_vectorStore(CHROMA_EXPERIENCE_PERSIST_DIR)
        SharedSystemClient.clear_system_cache()

        xlsx = settings.TENDERMOD_DB_DIR / "experiencia_rup.xlsx"
        if xlsx.exists():
            xlsx.unlink()
        messages.success(request, "Experiencia RUP eliminada correctamente (SQLite + ChromaDB).")
        logger.info("[clear_experiencia] Tabla experiencia y ChromaDB vaciados")
    except Exception as exc:
        logger.error("[clear_experiencia] Error: %s", exc)
        messages.error(request, f"Error al borrar experiencia: {exc}")
    return redirect("redneet:dashboard")


@require_POST
def clear_equipo(request):
    """Borra las tablas 'personas' y 'certificaciones' de SQLite y el xlsx."""
    db_path = _get_db_path()
    try:
        if db_path.exists():
            with sqlite3.connect(str(db_path)) as conn:
                conn.execute("DELETE FROM personas")
                conn.execute("DELETE FROM certificaciones")
                conn.commit()
        xlsx = settings.TENDERMOD_DB_DIR / "certificaciones_personal.xlsx"
        if xlsx.exists():
            xlsx.unlink()
        messages.success(request, "Datos del equipo eliminados correctamente.")
        logger.info("[clear_equipo] Tablas personas y certificaciones vaciadas")
    except Exception as exc:
        logger.error("[clear_equipo] Error: %s", exc)
        messages.error(request, f"Error al borrar datos del equipo: {exc}")
    return redirect("redneet:dashboard")


def download_excel(request, file_type):
    FILE_MAP = {
        'indicadores': ('rib.xlsx', 'rib.xlsx'),
        'experiencia': ('experiencia_rup.xlsx', 'experiencia_rup.xlsx'),
        'equipo': ('certificaciones_personal.xlsx', 'CERTIFICACIONES_PERSONAL.xlsx'),
    }
    if file_type not in FILE_MAP:
        raise Http404
    stored_name, download_name = FILE_MAP[file_type]
    file_path = settings.TENDERMOD_DB_DIR / stored_name
    if not file_path.exists():
        raise Http404
    return FileResponse(
        open(file_path, 'rb'),
        as_attachment=True,
        filename=download_name,
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )


def system_settings(request):
    """
    Vista de configuracion del sistema.
    Permite ajustar el umbral de similitud semantica por defecto para la validacion de objeto.
    """
    config = SystemConfig.get_solo()
    if request.method == 'POST':
        try:
            threshold = float(request.POST.get('threshold_objeto', 0.75))
        except (ValueError, TypeError):
            threshold = 0.75
        config.threshold_objeto = max(0.0, min(1.0, threshold))
        config.save()
        messages.success(request, 'Configuracion guardada.')
        return redirect('redneet:settings')
    return render(request, 'redneet/settings.html', {'config': config})
