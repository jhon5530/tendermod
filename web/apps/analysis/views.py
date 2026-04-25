import glob
import json
import logging
import os
import shutil

from django.conf import settings
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST, require_GET

from apps.core.models import AnalysisSession, AnalysisResult, SystemConfig
from .forms import PDFUploadForm, ExperienceEditForm, IndicatorsEditForm
from .tasks import (
    ingest_pdf_task,
    extract_experience_task,
    extract_indicators_task,
    extract_general_info_task,
    evaluate_experience_task,
    evaluate_indicators_task,
    quick_evaluate_experience_task,
    quick_evaluate_indicators_task,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Vista: lista de sesiones
# ---------------------------------------------------------------------------

def analysis_list(request):
    sessions = AnalysisSession.objects.select_related('result').all()
    return render(request, 'analysis/list.html', {'sessions': sessions})


# ---------------------------------------------------------------------------
# Vista: nueva sesion (subida de PDF)
# ---------------------------------------------------------------------------

def analysis_new(request):
    if request.method == 'POST':
        form = PDFUploadForm(request.POST, request.FILES)
        if form.is_valid():
            pdf_file = form.cleaned_data['pdf_file']
            pdf_filename = pdf_file.name

            # Limpiar PDFs anteriores en data/
            data_dir = settings.TENDERMOD_DATA_DIR
            data_dir.mkdir(parents=True, exist_ok=True)
            for old_pdf in glob.glob(str(data_dir / '*.pdf')):
                os.remove(old_pdf)
                logger.info('PDF anterior eliminado: %s', old_pdf)

            # Copiar el nuevo PDF a data/
            dest = data_dir / pdf_filename
            try:
                with open(dest, 'wb') as f:
                    for chunk in pdf_file.chunks():
                        f.write(chunk)
                logger.info('PDF copiado a %s', dest)
            except Exception as exc:
                logger.error('Error copiando PDF: %s', exc)
                messages.error(request, f'Error al guardar el PDF: {exc}')
                return render(request, 'analysis/new.html', {'form': form})

            # Crear sesion y lanzar tarea de ingesta
            session = AnalysisSession.objects.create(
                pdf_filename=pdf_filename,
                status='created',
            )
            task = ingest_pdf_task.delay(session.pk)
            session.celery_task_id = task.id
            session.save(update_fields=['celery_task_id', 'updated_at'])

            logger.info('Sesion %s creada, tarea de ingesta %s lanzada', session.pk, task.id)
            return redirect('analysis:step1', pk=session.pk)
        else:
            messages.error(request, 'Formulario invalido: ' + str(form.errors))
    else:
        form = PDFUploadForm()

    return render(request, 'analysis/new.html', {'form': form})


# ---------------------------------------------------------------------------
# Vista: Paso 1 — Extraccion de requisitos
# ---------------------------------------------------------------------------

def analysis_step1(request, pk):
    session = get_object_or_404(AnalysisSession, pk=pk)
    context = {
        'session': session,
        'has_experience': bool(session.experience_requirements_json),
        'has_indicators': bool(session.indicators_requirements_json),
        'has_general_info': bool(session.general_info_text),
    }
    return render(request, 'analysis/step1.html', context)


@require_POST
def analysis_extract(request, pk):
    """
    AJAX endpoint para lanzar tareas de extraccion desde el Paso 1.
    Body JSON: {action: "experience" | "indicators" | "general_info"}
    Responde con {task_id: "..."}
    """
    session = get_object_or_404(AnalysisSession, pk=pk)

    try:
        body = json.loads(request.body)
        action = body.get('action')
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'error': 'Body JSON invalido'}, status=400)

    if action == 'experience':
        task = extract_experience_task.delay(session.pk)
    elif action == 'indicators':
        task = extract_indicators_task.delay(session.pk)
    elif action == 'general_info':
        task = extract_general_info_task.delay(session.pk)
    else:
        return JsonResponse({'error': f'Accion desconocida: {action}'}, status=400)

    session.celery_task_id = task.id
    session.save(update_fields=['celery_task_id', 'updated_at'])

    logger.info('Tarea %s lanzada para sesion %s (action=%s)', task.id, pk, action)
    return JsonResponse({'task_id': task.id})


# ---------------------------------------------------------------------------
# Vista: Paso 2 — Validacion humana y evaluacion
# ---------------------------------------------------------------------------

def analysis_step2(request, pk):
    session = get_object_or_404(AnalysisSession, pk=pk)

    # Pre-poblar formularios desde JSON guardado en la sesion
    exp_initial = {}
    if session.experience_requirements_json:
        try:
            from tendermod.evaluation.schemas import ExperienceResponse
            exp = ExperienceResponse.model_validate_json(session.experience_requirements_json)
            exp_initial = {
                'listado_codigos': ', '.join(exp.listado_codigos),
                'cantidad_codigos': exp.cantidad_codigos,
                'objeto': exp.objeto,
                'cantidad_contratos': exp.cantidad_contratos,
                'valor': exp.valor,
                'pagina': exp.pagina,
                'seccion': exp.seccion,
                'regla_codigos': exp.regla_codigos,
                'objeto_exige_relevancia': exp.objeto_exige_relevancia,
            }
        except Exception as exc:
            logger.error('Error parseando experience_requirements_json: %s', exc)
            messages.warning(request, 'No se pudo cargar la extraccion de experiencia. Revise los datos.')

    ind_initial = {}
    indicators_list = []
    if session.indicators_requirements_json:
        try:
            from tendermod.evaluation.schemas import MultipleIndicatorResponse
            ind = MultipleIndicatorResponse.model_validate_json(session.indicators_requirements_json)
            indicators_list = [{'indicador': i.indicador, 'valor': str(i.valor)} for i in ind.answer]
            ind_initial = {'indicators_json': json.dumps(indicators_list)}
        except Exception as exc:
            logger.error('Error parseando indicators_requirements_json: %s', exc)
            messages.warning(request, 'No se pudo cargar la extraccion de indicadores.')

    if request.method == 'POST':
        # Handle normal form submission (non-AJAX evaluation triggers)
        # AJAX evaluations are handled by analysis_evaluate endpoint
        pass

    exp_form = ExperienceEditForm(initial=exp_initial)
    ind_form = IndicatorsEditForm(initial=ind_initial)

    # Parsear objeto completo ExperienceResponse para acceso en la plantilla
    exp_data = None
    if session.experience_requirements_json:
        try:
            from tendermod.evaluation.schemas import ExperienceResponse
            exp_data = ExperienceResponse.model_validate_json(session.experience_requirements_json)
        except Exception as exc:
            logger.error('Error parseando ExperienceResponse para step2: %s', exc)

    context = {
        'session': session,
        'exp_form': exp_form,
        'ind_form': ind_form,
        'indicators_list': indicators_list,
        'exp_initial_json': json.dumps(exp_initial),
        'system_threshold': SystemConfig.get_solo().threshold_objeto,
        'exp_data': exp_data,
    }
    return render(request, 'analysis/step2.html', context)


@require_POST
def analysis_evaluate(request, pk):
    """
    AJAX endpoint para lanzar evaluaciones desde el Paso 2.
    Body JSON:
      {action: "experience", experience_data: {...}}  — evalua experiencia
      {action: "indicators", indicators_list: [...]}  — evalua indicadores
    """
    session = get_object_or_404(AnalysisSession, pk=pk)

    try:
        body = json.loads(request.body)
        action = body.get('action')
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'error': 'Body JSON invalido'}, status=400)

    if action == 'experience':
        exp_data = body.get('experience_data', {})
        # Normalizar el campo listado_codigos desde string a lista
        if isinstance(exp_data.get('listado_codigos'), str):
            raw = exp_data['listado_codigos']
            exp_data['listado_codigos'] = [c.strip() for c in raw.split(',') if c.strip()]
        # Extraer umbral de experience_data (enviado por buildExperienceData) o del cuerpo
        # y removerlo del dict antes de construir ExperienceResponse
        try:
            umbral = float(exp_data.pop('umbral', body.get('umbral', SystemConfig.get_solo().threshold_objeto)))
        except (TypeError, ValueError):
            umbral = float(SystemConfig.get_solo().threshold_objeto)
        task = evaluate_experience_task.delay(session.pk, exp_data, umbral)

    elif action == 'indicators':
        ind_list = body.get('indicators_list', [])
        task = evaluate_indicators_task.delay(session.pk, ind_list)

    else:
        return JsonResponse({'error': f'Accion desconocida: {action}'}, status=400)

    session.celery_task_id = task.id
    session.save(update_fields=['celery_task_id', 'updated_at'])

    logger.info('Tarea de evaluacion %s lanzada para sesion %s (action=%s)', task.id, pk, action)
    return JsonResponse({'task_id': task.id})


# ---------------------------------------------------------------------------
# Vista: Resultados
# ---------------------------------------------------------------------------

def analysis_results(request, pk):
    session = get_object_or_404(AnalysisSession, pk=pk)

    result = None
    exp_result = None
    ind_result = None

    try:
        result = session.result
    except AnalysisResult.DoesNotExist:
        pass

    if result:
        if result.experience_result_json:
            try:
                from tendermod.evaluation.schemas import ExperienceComplianceResult
                exp_result = ExperienceComplianceResult.model_validate_json(result.experience_result_json)
            except Exception as exc:
                logger.error('Error parseando experience_result_json: %s', exc)

        if result.indicators_result_json:
            try:
                from tendermod.evaluation.schemas import IndicatorComplianceResult
                ind_result = IndicatorComplianceResult.model_validate_json(result.indicators_result_json)
            except Exception as exc:
                logger.error('Error parseando indicators_result_json: %s', exc)

    context = {
        'session': session,
        'result': result,
        'exp_result': exp_result,
        'ind_result': ind_result,
    }
    return render(request, 'analysis/results.html', context)


# ---------------------------------------------------------------------------
# Exportacion
# ---------------------------------------------------------------------------

def export_excel(request, pk):
    """
    Exporta los resultados de la sesion como archivo Excel (.xlsx).
    Hoja 1: Indicadores | Hoja 2: Experiencia RUP
    """
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment
    from io import BytesIO

    session = get_object_or_404(AnalysisSession, pk=pk)

    try:
        result = session.result
    except AnalysisResult.DoesNotExist:
        messages.error(request, 'No hay resultados para exportar.')
        return redirect('analysis:results', pk=pk)

    wb = openpyxl.Workbook()

    # ---- Hoja 1: Indicadores ----
    ws_ind = wb.active
    ws_ind.title = 'Indicadores'

    header_font = Font(bold=True, color='FFFFFF')
    header_fill = PatternFill('solid', fgColor='1F4E79')

    ind_headers = ['Indicador', 'Valor Empresa', 'Condicion', 'Umbral', 'Cumple', 'Detalle']
    for col_num, header in enumerate(ind_headers, 1):
        cell = ws_ind.cell(row=1, column=col_num, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal='center')

    if result.indicators_result_json:
        try:
            from tendermod.evaluation.schemas import IndicatorComplianceResult
            ind_result = IndicatorComplianceResult.model_validate_json(result.indicators_result_json)
            cumple_str = 'CUMPLE' if ind_result.cumple else ('NO CUMPLE' if ind_result.cumple is False else 'INDETERMINADO')
            ws_ind.append(['Resultado general', '', '', '', cumple_str, ind_result.detalle])
            for nombre in ind_result.indicadores_evaluados:
                ws_ind.append([nombre, '', '', '', '', ''])
        except Exception:
            ws_ind.append(['Error al parsear resultado de indicadores', '', '', '', '', ''])

    # Auto-width columns
    for col in ws_ind.columns:
        max_len = max((len(str(cell.value or '')) for cell in col), default=10)
        ws_ind.column_dimensions[col[0].column_letter].width = min(max_len + 4, 60)

    # ---- Hoja 2: Experiencia RUP ----
    ws_exp = wb.create_sheet('Experiencia RUP')

    exp_headers = ['NUMERO RUP', 'Cliente', 'Valor COP', 'Cumple Codigos',
                   'Cumple Valor', 'Cumple Objeto', 'Score Objeto',
                   'Contrato Elegido', 'Cumple Total']
    for col_num, header in enumerate(exp_headers, 1):
        cell = ws_exp.cell(row=1, column=col_num, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal='center')

    def fmt_cop(v):
        try:
            return f'${int(round(float(v))):,}'.replace(',', '.')
        except Exception:
            return v

    if result.experience_result_json:
        try:
            from tendermod.evaluation.schemas import ExperienceComplianceResult
            exp_result = ExperienceComplianceResult.model_validate_json(result.experience_result_json)

            # Summary row
            ws_exp.cell(row=2, column=1, value='RESUMEN')
            ws_exp.cell(row=2, column=2, value=f'Codigos requeridos: {", ".join(exp_result.codigos_requeridos)}')
            ws_exp.cell(row=2, column=3, value=fmt_cop(exp_result.valor_requerido_cop) if exp_result.valor_requerido_cop else '')
            ws_exp.cell(row=2, column=9, value='CUMPLE' if exp_result.cumple else 'NO CUMPLE')

            for i, rup in enumerate(exp_result.rups_evaluados, start=3):
                ws_exp.append([
                    rup.numero_rup,
                    rup.cliente or '',
                    fmt_cop(rup.valor_cop) if rup.valor_cop else '',
                    'SI' if rup.cumple_codigos else 'NO',
                    'SI' if rup.cumple_valor else ('NO' if rup.cumple_valor is False else 'N/A'),
                    'SI' if rup.cumple_objeto else ('NO' if rup.cumple_objeto is False else 'N/A'),
                    f'{rup.score_objeto:.3f}' if rup.score_objeto is not None else 'N/A',
                    (rup.objeto_contrato or '')[:200],
                    'CUMPLE' if rup.cumple_total else 'NO CUMPLE',
                ])
        except Exception as exc:
            ws_exp.append([f'Error al parsear resultado de experiencia: {exc}'])

    for col in ws_exp.columns:
        max_len = max((len(str(cell.value or '')) for cell in col), default=10)
        ws_exp.column_dimensions[col[0].column_letter].width = min(max_len + 4, 40)

    # ---- Hoja 3: Sub-Requisitos (solo si hay datos MULTI_CONDICION) ----
    if result.experience_result_json:
        try:
            from tendermod.evaluation.schemas import ExperienceComplianceResult as ECR
            exp_check = ECR.model_validate_json(result.experience_result_json)
            if exp_check.sub_requisitos_resultado:
                ws_sub = wb.create_sheet('Sub-Requisitos')
                sub_headers = ['NUMERO RUP', 'Sub-Requisito', 'Cumple', 'Score', 'Contrato que Cumple']
                for col_num, header in enumerate(sub_headers, 1):
                    cell = ws_sub.cell(row=1, column=col_num, value=header)
                    cell.font = header_font
                    cell.fill = header_fill
                    cell.alignment = Alignment(horizontal='center')

                for sr in exp_check.sub_requisitos_resultado:
                    ws_sub.append([
                        sr.rup_elegido if sr.rup_elegido is not None else '',
                        sr.descripcion,
                        'CUMPLE' if sr.cumple else 'NO CUMPLE',
                        f'{sr.score_objeto:.3f}' if sr.score_objeto is not None else 'N/A',
                        (sr.objeto_contrato or '')[:200],
                    ])

                for col in ws_sub.columns:
                    max_len = max((len(str(cell.value or '')) for cell in col), default=10)
                    ws_sub.column_dimensions[col[0].column_letter].width = min(max_len + 4, 60)
        except Exception as exc:
            logger.warning('No se pudo generar hoja Sub-Requisitos: %s', exc)

    # ---- Generar respuesta ----
    output = BytesIO()
    wb.save(output)
    output.seek(0)

    filename = f'tendermod_resultados_{pk}.xlsx'
    response = HttpResponse(
        output.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


def export_text(request, pk):
    """
    Exporta los resultados como texto plano con resumen ejecutivo.
    """
    session = get_object_or_404(AnalysisSession, pk=pk)

    try:
        result = session.result
    except AnalysisResult.DoesNotExist:
        messages.error(request, 'No hay resultados para exportar.')
        return redirect('analysis:results', pk=pk)

    lines = []
    lines.append('=' * 70)
    lines.append('TENDERMOD — RESUMEN DE EVALUACION DE CUMPLIMIENTO')
    lines.append('=' * 70)
    lines.append(f'Sesion ID   : {session.pk}')
    lines.append(f'PDF         : {session.pdf_filename}')
    lines.append(f'Fecha       : {session.created_at.strftime("%Y-%m-%d %H:%M")}')
    lines.append(f'Estado      : {session.get_status_display()}')
    lines.append('')

    # Resultado general
    if result.cumple_final is not None:
        veredicto = 'CUMPLE' if result.cumple_final else 'NO CUMPLE'
        lines.append(f'VEREDICTO FINAL: {veredicto}')
    lines.append('')

    # Indicadores
    lines.append('-' * 70)
    lines.append('INDICADORES FINANCIEROS')
    lines.append('-' * 70)
    if result.indicators_result_json:
        try:
            from tendermod.evaluation.schemas import IndicatorComplianceResult
            ind = IndicatorComplianceResult.model_validate_json(result.indicators_result_json)
            cumple_str = 'CUMPLE' if ind.cumple else ('NO CUMPLE' if ind.cumple is False else 'INDETERMINADO')
            lines.append(f'Resultado: {cumple_str}')
            lines.append('')
            lines.append('Indicadores evaluados:')
            for nombre in ind.indicadores_evaluados:
                lines.append(f'  - {nombre}')
            lines.append('')
            lines.append('Argumentacion del LLM:')
            lines.append(ind.detalle)
        except Exception as exc:
            lines.append(f'Error al parsear: {exc}')
    else:
        lines.append('Sin datos de indicadores.')
    lines.append('')

    # Experiencia
    lines.append('-' * 70)
    lines.append('EXPERIENCIA RUP')
    lines.append('-' * 70)
    if result.experience_result_json:
        try:
            from tendermod.evaluation.schemas import ExperienceComplianceResult
            exp = ExperienceComplianceResult.model_validate_json(result.experience_result_json)
            cumple_str = 'CUMPLE' if exp.cumple else 'NO CUMPLE'
            lines.append(f'Resultado: {cumple_str}')
            lines.append(f'Codigos requeridos  : {", ".join(exp.codigos_requeridos)}')
            if exp.objeto_requerido:
                lines.append(f'Objeto requerido    : {exp.objeto_requerido}')
            if exp.objeto_exige_relevancia:
                lines.append(f'Exige relevancia    : {exp.objeto_exige_relevancia}')
            if exp.cantidad_contratos_requerida is not None:
                lines.append(f'Contratos (top-N)   : {exp.cantidad_contratos_requerida}')
            if exp.valor_requerido_cop:
                lines.append(f'Valor requerido     : ${int(round(exp.valor_requerido_cop)):,} COP'.replace(',', '.'))
            if exp.total_valor_cop:
                lines.append(f'Valor total acreditado: ${int(round(exp.total_valor_cop)):,} COP'.replace(',', '.'))
            lines.append(f'RUPs candidatos     : {len(exp.rups_candidatos_codigos)} contratos')
            lines.append(f'RUPs que cumplen    : {exp.rups_cumplen}')
            if exp.rups_excluidos_por_objeto:
                lines.append(f'RUPs excluidos por objeto: {exp.rups_excluidos_por_objeto}')
            lines.append('')
            lines.append('Detalle por RUP:')
            for rup in exp.rups_evaluados:
                cumple_rup = 'CUMPLE' if rup.cumple_total else 'NO CUMPLE'
                valor_str = f'${int(round(rup.valor_cop)):,} COP'.replace(',', '.') if rup.valor_cop else 'N/A'
                # FIX BUG-2: reemplazar \n en cliente
                cliente_str = (rup.cliente or 'N/A').replace('\n', ' ').replace('\r', '').strip()

                lines.append(f'  ┌─ RUP {rup.numero_rup} — {cliente_str} — {valor_str} — [{cumple_rup}]')
                lines.append(f'  │  Codigos UNSPSC  : {"CUMPLE" if rup.cumple_codigos else "NO CUMPLE"}')
                if rup.cumple_valor is not None:
                    lines.append(f'  │  Valor           : {"CUMPLE" if rup.cumple_valor else "NO CUMPLE"}')
                else:
                    lines.append(f'  │  Valor           : N/A')

                # FIX BUG-3: mostrar score aunque cumple_objeto sea None
                if rup.score_objeto is not None:
                    umbral_val = exp.similarity_threshold_usado
                    umbral_str = f'SUPERA umbral {umbral_val}' if rup.score_objeto >= umbral_val else f'BAJO umbral {umbral_val}'
                    if rup.cumple_objeto is False:
                        estado_obj = f'EXCLUIDO — Score {rup.score_objeto:.3f} ({umbral_str})'
                    elif rup.cumple_objeto is True:
                        estado_obj = f'CUMPLE — Score {rup.score_objeto:.3f} ({umbral_str})'
                    else:
                        estado_obj = f'Score {rup.score_objeto:.3f} ({umbral_str}) — filtro inactivo'
                    lines.append(f'  │  Objeto          : {estado_obj}')
                else:
                    obj_razon = 'sin datos en ChromaDB' if rup.cumple_objeto is False else 'N/A'
                    lines.append(f'  │  Objeto          : {obj_razon}')

                # FIX BUG-4: mostrar objeto_contrato
                if rup.objeto_contrato:
                    contrato_short = rup.objeto_contrato[:120].replace('\n', ' ')
                    if len(rup.objeto_contrato) > 120:
                        contrato_short += '...'
                    lines.append(f'  │  Contrato elegido: {contrato_short}')

                lines.append(f'  └─ Resultado      : {cumple_rup}')
                lines.append('')

            # Sub-requisitos MULTI_CONDICION (nivel global, no por RUP)
            if exp.sub_requisitos_resultado:
                lines.append('Sub-requisitos (MULTI_CONDICION):')
                for sr in exp.sub_requisitos_resultado:
                    estado = 'CUMPLE' if sr.cumple else 'NO CUMPLE'
                    score_str = f'Score={sr.score_objeto:.3f}' if sr.score_objeto is not None else 'Score=N/A'
                    rup_str = f'RUP={sr.rup_elegido}' if sr.rup_elegido is not None else 'RUP=Ninguno'
                    lines.append(f'  [{estado}] {sr.descripcion} ({score_str}, {rup_str})')
                lines.append('')
        except Exception as exc:
            lines.append(f'Error al parsear: {exc}')
    else:
        lines.append('Sin datos de experiencia.')

    lines.append('')
    lines.append('=' * 70)
    lines.append('Generado por tendermod')
    lines.append('=' * 70)

    content = '\n'.join(lines)
    filename = f'tendermod_resultados_{pk}.txt'
    response = HttpResponse(content, content_type='text/plain; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


def export_context(request, pk):
    """
    Descarga el contexto RAW del retriever usado para la evaluacion (indicadores + experiencia).
    """
    session = get_object_or_404(AnalysisSession, pk=pk)

    try:
        result = session.result
    except AnalysisResult.DoesNotExist:
        messages.error(request, 'No hay resultados para exportar.')
        return redirect('analysis:results', pk=pk)

    lines = []
    lines.append('=' * 70)
    lines.append('TENDERMOD — CONTEXTO DEL RETRIEVER (RAG)')
    lines.append('=' * 70)
    lines.append(f'Sesion ID   : {session.pk}')
    lines.append(f'PDF         : {session.pdf_filename}')
    lines.append(f'Fecha       : {session.created_at.strftime("%Y-%m-%d %H:%M")}')
    lines.append('')
    lines.append('-' * 70)
    lines.append('CONTEXTO — INDICADORES FINANCIEROS')
    lines.append('-' * 70)
    lines.append(result.indicators_context_text or '(sin contexto disponible — use el flujo PDF completo)')
    lines.append('')
    lines.append('-' * 70)
    lines.append('CONTEXTO — EXPERIENCIA')
    lines.append('-' * 70)
    lines.append(result.experience_context_text or '(sin contexto disponible — use el flujo PDF completo)')
    lines.append('')
    lines.append('=' * 70)

    content = '\n'.join(lines)
    filename = f'tendermod_contexto_rag_{pk}.txt'
    response = HttpResponse(content, content_type='text/plain; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


# ---------------------------------------------------------------------------
# Vista: Evaluacion Rapida
# ---------------------------------------------------------------------------

def analysis_quick(request):
    """
    GET: Renderiza la pagina de Evaluacion Rapida.
    Pasa session_id desde la sesion de Django si existe una sesion rapida previa.
    """
    quick_session_id = request.session.get('quick_session_id')
    context = {
        'quick_session_id': quick_session_id,
        'system_threshold': SystemConfig.get_solo().threshold_objeto,
    }
    return render(request, 'analysis/quick.html', context)


@require_POST
def analysis_quick_evaluate(request):
    """
    POST (JSON): Lanza evaluaciones rapidas de experiencia o indicadores desde texto libre.

    Body JSON:
      {action: "experience", text: "..."}  — extrae ExperienceResponse y evalua
      {action: "indicators", text: "..."}  — extrae MultipleIndicatorResponse y evalua
      {action: "reset"}                    — elimina la sesion rapida activa

    Responde con {task_id, session_id} o {status: "ok"} para reset.
    """
    try:
        body = json.loads(request.body)
        action = body.get('action')
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'error': 'Body JSON invalido'}, status=400)

    if action == 'reset':
        request.session.pop('quick_session_id', None)
        return JsonResponse({'status': 'ok'})

    if action not in ('experience', 'indicators'):
        return JsonResponse({'error': f'Accion desconocida: {action}'}, status=400)

    plain_text = body.get('text', '').strip()
    if not plain_text:
        return JsonResponse({'error': 'El campo text no puede estar vacio'}, status=400)

    # Obtener o crear la sesion de evaluacion rapida
    quick_session_id = request.session.get('quick_session_id')
    if quick_session_id:
        try:
            session = AnalysisSession.objects.get(pk=quick_session_id)
        except AnalysisSession.DoesNotExist:
            quick_session_id = None

    if not quick_session_id:
        session = AnalysisSession.objects.create(
            pdf_filename='[Evaluacion Rapida]',
            status='pdf_ready',
        )
        request.session['quick_session_id'] = session.pk
        logger.info('Sesion rapida %s creada', session.pk)

    if action == 'experience':
        try:
            umbral = float(body.get('umbral', SystemConfig.get_solo().threshold_objeto))
        except (TypeError, ValueError):
            umbral = float(SystemConfig.get_solo().threshold_objeto)
        task = quick_evaluate_experience_task.delay(session.pk, plain_text, umbral)
    else:
        task = quick_evaluate_indicators_task.delay(session.pk, plain_text)

    session.celery_task_id = task.id
    session.save(update_fields=['celery_task_id', 'updated_at'])

    logger.info('Tarea rapida %s lanzada para sesion %s (action=%s)', task.id, session.pk, action)
    return JsonResponse({'task_id': task.id, 'session_id': session.pk})
