import shutil
import logging

from django.conf import settings
from django.contrib import messages
from django.shortcuts import render, redirect
from django.views.decorators.http import require_POST

from apps.core.models import SystemConfig
from .forms import IndicadoresUploadForm, ExperienciaUploadForm
from .tasks import load_indicadores_task, load_experiencia_task

logger = logging.getLogger(__name__)


def dashboard(request):
    """
    Vista 1: Dashboard de datos de la empresa (Redneet).
    Muestra formularios de carga de Excels y el estado actual de las tablas SQLite.
    """
    context = {
        'form_indicadores': IndicadoresUploadForm(),
        'form_experiencia': ExperienciaUploadForm(),
        'task_id_indicadores': request.session.get('task_id_indicadores'),
        'task_id_experiencia': request.session.get('task_id_experiencia'),
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
