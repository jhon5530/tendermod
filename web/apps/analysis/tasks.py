import json
import logging
import time

from celery import shared_task
from django.db import connection

logger = logging.getLogger(__name__)


def _record_timing(session_id: int, paso: str, tarea: str, duracion_s: float, estado: str) -> None:
    """Agrega una entrada de timing a session.timing_json de forma segura."""
    try:
        from apps.core.models import AnalysisSession
        session = AnalysisSession.objects.get(pk=session_id)
        entries = json.loads(session.timing_json or '[]')
        entries.append({
            'paso': paso,
            'tarea': tarea,
            'duracion_s': round(duracion_s, 1),
            'estado': estado,
        })
        session.timing_json = json.dumps(entries)
        session.save(update_fields=['timing_json'])
    except Exception as exc:
        logger.warning('_record_timing: no se pudo guardar timing para sesion %s: %s', session_id, exc)


@shared_task(bind=True, name='analysis.ingest_pdf_task')
def ingest_pdf_task(self, session_id):
    """
    Ingesta el PDF copiado a data/ en ChromaDB para licitacion.
    Actualiza el estado de la sesion a 'pdf_ready' al completar.
    """
    connection.close()
    from apps.core.models import AnalysisSession
    _t0 = time.time()
    _estado = 'ok'
    try:
        from tendermod.ingestion.ingestion_flow import ingest_documents

        session = AnalysisSession.objects.get(pk=session_id)
        session.status = 'ingesting_pdf'
        session.celery_task_id = self.request.id
        session.save(update_fields=['status', 'celery_task_id', 'updated_at'])

        logger.info('Ingiriendo PDF para sesion %s', session_id)
        result = ingest_documents()
        connection.close()  # ChromaDB usa SQLite propio; cerrar antes del siguiente save

        session.status = 'pdf_ready'
        session.ocr_document_path = result.get('ocr_docx_path') or ''
        session.save(update_fields=['status', 'ocr_document_path', 'updated_at'])

        if result.get('ocr_applied'):
            logger.info('OCR aplicado para sesion %s — docx: %s', session_id, session.ocr_document_path)
        logger.info('PDF ingerido exitosamente para sesion %s', session_id)
        return {'status': 'ok', 'session_id': session_id, 'ocr_applied': result.get('ocr_applied', False)}

    except Exception as exc:
        _estado = 'error'
        logger.error('Error ingiriendo PDF para sesion %s: %s', session_id, exc)
        try:
            session = AnalysisSession.objects.get(pk=session_id)
            session.status = 'error'
            session.save(update_fields=['status', 'updated_at'])
        except Exception:
            pass
        raise
    finally:
        _record_timing(session_id, 'Ingesta del PDF', 'ingest_pdf_task', time.time() - _t0, _estado)


@shared_task(bind=True, name='analysis.extract_general_requirements_task')
def extract_general_requirements_task(self, session_id):
    """
    Extrae requisitos habilitantes generales del pliego usando RAG.
    Guarda GeneralRequirementList en session.general_requirements_json.
    """
    connection.close()
    from apps.core.models import AnalysisSession
    _t0 = time.time()
    _estado = 'ok'
    try:
        from tendermod.evaluation.general_requirements_inference import get_general_requirements

        session = AnalysisSession.objects.get(pk=session_id)
        session.celery_task_id = self.request.id
        session.save(update_fields=['celery_task_id', 'updated_at'])

        logger.info('Extrayendo requisitos generales para sesion %s', session_id)
        req_list = get_general_requirements(k=15)
        connection.close()

        session.general_requirements_json = req_list.model_dump_json()
        session.save(update_fields=['general_requirements_json', 'updated_at'])
        logger.info('Requisitos generales extraidos para sesion %s (%d items)', session_id, len(req_list.requisitos))
        return {'status': 'ok', 'session_id': session_id, 'count': len(req_list.requisitos)}

    except Exception as exc:
        _estado = 'error'
        logger.error('Error extrayendo requisitos generales para sesion %s: %s', session_id, exc)
        raise
    finally:
        _record_timing(session_id, 'Extraccion de requisitos habilitantes', 'extract_general_requirements_task', time.time() - _t0, _estado)


@shared_task(bind=True, name='analysis.extract_experience_task')
def extract_experience_task(self, session_id):
    """
    Extrae requisitos de experiencia del pliego usando RAG.
    Guarda ExperienceResponse en session.experience_requirements_json.
    """
    connection.close()
    from apps.core.models import AnalysisSession
    _t0 = time.time()
    _estado = 'ok'
    try:
        from tendermod.evaluation.compare_experience import experience_comparation

        session = AnalysisSession.objects.get(pk=session_id)
        session.celery_task_id = self.request.id
        session.save(update_fields=['celery_task_id', 'updated_at'])

        logger.info('Extrayendo requisitos de experiencia para sesion %s', session_id)
        exp_response, experience_context = experience_comparation()
        connection.close()

        if exp_response is None:
            raise ValueError('experience_comparation() retorno None — revise el PDF ingerido')

        if not exp_response.listado_codigos:
            logger.warning(
                'extract_experience_task sesion %s: ExperienceResponse sin codigos UNSPSC — '
                'puede ser pliego sin requisito de codigos o falla de extraccion. '
                'Revise logs [get_experience] para el contexto enviado al LLM.',
                session_id,
            )

        session.experience_requirements_json = exp_response.model_dump_json()
        session.save(update_fields=['experience_requirements_json', 'updated_at'])

        from apps.core.models import AnalysisResult
        result, _ = AnalysisResult.objects.get_or_create(session=session)
        result.experience_context_text = experience_context or ''
        result.save(update_fields=['experience_context_text'])

        logger.info('Requisitos de experiencia extraidos para sesion %s', session_id)
        return {'status': 'ok', 'session_id': session_id}

    except Exception as exc:
        _estado = 'error'
        logger.error('Error extrayendo experiencia para sesion %s: %s', session_id, exc)
        raise
    finally:
        _record_timing(session_id, 'Extraccion de experiencia RUP', 'extract_experience_task', time.time() - _t0, _estado)


@shared_task(bind=True, name='analysis.extract_indicators_task')
def extract_indicators_task(self, session_id):
    """
    Extrae indicadores financieros del pliego usando RAG.
    Guarda MultipleIndicatorResponse en session.indicators_requirements_json.
    """
    connection.close()
    from apps.core.models import AnalysisSession
    _t0 = time.time()
    _estado = 'ok'
    try:
        from tendermod.evaluation.indicators_inference import get_indicators

        session = AnalysisSession.objects.get(pk=session_id)
        session.celery_task_id = self.request.id
        session.save(update_fields=['celery_task_id', 'updated_at'])

        query = (
            'Extrae TODOS los indicadores financieros y organizacionales requeridos como '
            'habilitantes en el pliego. Incluye sin omitir: liquidez, endeudamiento, '
            'razon de cobertura de intereses, capital de trabajo, rentabilidad del '
            'patrimonio, rentabilidad del activo, y cualquier otro indicador con umbral '
            'numerico que aparezca en el documento.'
        )
        logger.info('Extrayendo indicadores para sesion %s', session_id)
        ind_response, indicators_context = get_indicators(user_input=query, k=12)
        connection.close()

        if ind_response is None:
            raise ValueError('get_indicators() retorno None — revise el PDF ingerido')

        session.indicators_requirements_json = ind_response.model_dump_json()
        session.save(update_fields=['indicators_requirements_json', 'updated_at'])

        from apps.core.models import AnalysisResult
        result, _ = AnalysisResult.objects.get_or_create(session=session)
        result.indicators_context_text = indicators_context or ''
        result.save(update_fields=['indicators_context_text'])

        logger.info('Indicadores extraidos para sesion %s', session_id)
        return {'status': 'ok', 'session_id': session_id}

    except Exception as exc:
        _estado = 'error'
        logger.error('Error extrayendo indicadores para sesion %s: %s', session_id, exc)
        raise
    finally:
        _record_timing(session_id, 'Extraccion de indicadores financieros', 'extract_indicators_task', time.time() - _t0, _estado)


@shared_task(bind=True, name='analysis.extract_general_info_task')
def extract_general_info_task(self, session_id):
    """
    Extrae informacion general del proceso (presupuesto, objeto, etc).
    Guarda texto libre en session.general_info_text.
    """
    connection.close()
    from apps.core.models import AnalysisSession
    _t0 = time.time()
    _estado = 'ok'
    try:
        from tendermod.evaluation.indicators_inference import get_general_info

        session = AnalysisSession.objects.get(pk=session_id)
        session.celery_task_id = self.request.id
        session.save(update_fields=['celery_task_id', 'updated_at'])

        query = 'Cual es el presupuesto oficial, objeto y numero del proceso?'
        logger.info('Extrayendo informacion general para sesion %s', session_id)
        info_text = get_general_info(user_input=query, k=2)
        connection.close()

        session.general_info_text = info_text or ''
        session.save(update_fields=['general_info_text', 'updated_at'])
        logger.info('Informacion general extraida para sesion %s', session_id)
        return {'status': 'ok', 'session_id': session_id, 'info': info_text}

    except Exception as exc:
        _estado = 'error'
        logger.error('Error extrayendo info general para sesion %s: %s', session_id, exc)
        raise
    finally:
        _record_timing(session_id, 'Extraccion de informacion general', 'extract_general_info_task', time.time() - _t0, _estado)


@shared_task(bind=True, name='analysis.evaluate_experience_task')
def evaluate_experience_task(self, session_id, exp_dict=None, similarity_threshold=None, set_completed=True):
    """
    Evalua cumplimiento de experiencia a partir del dict editado por el usuario.
    Crea o actualiza AnalysisResult con el resultado.

    En el flujo automatico (chain) se invoca como .si(session_id): exp_dict y
    similarity_threshold quedan en None y se leen de la sesion / config.
    set_completed=False evita marcar 'completed' a mitad del chain (lo hace finalize_auto_flow_task).
    """
    connection.close()
    from apps.core.models import AnalysisSession, AnalysisResult, SystemConfig
    _t0 = time.time()
    _estado = 'ok'
    try:
        from tendermod.evaluation.schemas import ExperienceResponse
        from tendermod.evaluation.compare_experience import check_compliance_experience

        session = AnalysisSession.objects.get(pk=session_id)
        session.status = 'evaluating'
        session.celery_task_id = self.request.id
        session.save(update_fields=['status', 'celery_task_id', 'updated_at'])

        # Modo automatico: leer datos de la sesion si no se pasaron explicitamente
        if exp_dict is None:
            exp_dict = json.loads(session.experience_requirements_json or '{}')
        if similarity_threshold is None:
            similarity_threshold = float(SystemConfig.get_solo().threshold_objeto)

        # Reconstruir ExperienceResponse desde el dict editado por el usuario
        exp_response = ExperienceResponse(**exp_dict)

        # Fallback: si objeto es None/vacío o meta-texto genérico, y el pliego exige relevancia,
        # usar el objeto real del proceso extraído de general_info_text.
        # Esto ocurre porque el RAG de experiencia no incluye el capítulo de Generalidades
        # donde está el objeto real; general_info_task lo extrae por separado y siempre corre
        # antes de evaluate_experience_task en el chain automático.
        from tendermod.evaluation.compare_experience import _is_generic_objeto, _extract_objeto_from_general_info
        _objeto_nulo = not exp_response.objeto or exp_response.objeto.strip() in ("None", "")
        if (_objeto_nulo or _is_generic_objeto(exp_response.objeto)) \
                and exp_response.objeto_exige_relevancia == "SI" \
                and session.general_info_text:
            objeto_real = _extract_objeto_from_general_info(session.general_info_text)
            if objeto_real:
                logger.info(
                    '[evaluate_experience] Objeto %s en sesion %s con relevancia=SI — '
                    'usando objeto del proceso desde general_info: "%s"',
                    "nulo" if _objeto_nulo else "genérico",
                    session_id, objeto_real,
                )
                exp_response = exp_response.model_copy(update={"objeto": objeto_real})

        logger.info('Evaluando experiencia para sesion %s (umbral=%.2f)', session_id, similarity_threshold)
        compliance = check_compliance_experience(exp_response, similarity_threshold=similarity_threshold)
        connection.close()  # el backend abre sqlite directo; re-cerrar para obtener handle limpio

        result, _ = AnalysisResult.objects.get_or_create(session=session)
        result.experience_result_json = compliance.model_dump_json()
        result.cumple_experiencia = compliance.cumple

        # Determinar cumple_final si ya hay resultado de indicadores
        if result.indicators_result_json:
            from tendermod.evaluation.schemas import IndicatorComplianceResult
            ind_result = IndicatorComplianceResult.model_validate_json(result.indicators_result_json)
            result.cumple_indicadores = ind_result.cumple
            if result.cumple_experiencia is not None and result.cumple_indicadores is not None:
                result.cumple_final = result.cumple_experiencia and result.cumple_indicadores
            elif result.cumple_experiencia is not None:
                result.cumple_final = result.cumple_experiencia
        result.save()

        if set_completed:
            session.status = 'completed'
            session.save(update_fields=['status', 'updated_at'])
        logger.info('Evaluacion de experiencia completada para sesion %s — cumple=%s', session_id, compliance.cumple)
        return {'status': 'ok', 'session_id': session_id, 'cumple': compliance.cumple}

    except Exception as exc:
        _estado = 'error'
        logger.error('Error evaluando experiencia para sesion %s: %s', session_id, exc)
        try:
            session = AnalysisSession.objects.get(pk=session_id)
            session.status = 'error'
            session.save(update_fields=['status', 'updated_at'])
        except Exception:
            pass
        raise
    finally:
        _record_timing(session_id, 'Evaluacion de cumplimiento de experiencia', 'evaluate_experience_task', time.time() - _t0, _estado)


@shared_task(bind=True, name='analysis.evaluate_indicators_task')
def evaluate_indicators_task(self, session_id, ind_list=None, set_completed=True):
    """
    Evalua indicadores usando merge_indicators() + run_llm_indicators_comparation().
    ind_list: lista de dicts {indicador, valor} (editados por el usuario).

    En el flujo automatico (chain) se invoca como .si(session_id): ind_list queda
    en None y se lee de la sesion. set_completed=False evita marcar 'completed'
    a mitad del chain (lo hace finalize_auto_flow_task).
    """
    connection.close()
    from apps.core.models import AnalysisSession, AnalysisResult
    _t0 = time.time()
    _estado = 'ok'
    try:
        from tendermod.evaluation.compare_indicators import (
            merge_indicators, extract_compliance_bool,
        )
        from tendermod.evaluation.llm_client import run_llm_indicators_comparation
        from tendermod.evaluation.indicators_inference import get_general_info
        from tendermod.evaluation.schemas import IndicatorComplianceResult
        from tendermod.ingestion.db_loader import get_specific_gold_indicator

        session = AnalysisSession.objects.get(pk=session_id)
        session.status = 'evaluating'
        session.celery_task_id = self.request.id
        session.save(update_fields=['status', 'celery_task_id', 'updated_at'])

        # Modo automatico: leer indicadores de la sesion si no se pasaron explicitamente
        if ind_list is None:
            raw = json.loads(session.indicators_requirements_json or '{"answer": []}')
            ind_list = [
                {'indicador': i['indicador'], 'valor': str(i['valor'])}
                for i in raw.get('answer', [])
            ]

        logger.info('Evaluando indicadores para sesion %s', session_id)

        # Construir tender_indicators_json en el formato que espera merge_indicators()
        tender_indicators_json = {
            'result': [{'nombre': item['indicador'], 'valor': item['valor']} for item in ind_list]
        }

        # Obtener nombres de indicadores para construir la query al SQL agent
        indicator_names = '\n'.join(item['indicador'] for item in ind_list)
        query_gold = (
            'Devuelve un objeto JSON valido con los siguientes indicadores financieros. '
            'Busca en la tabla el indicador mas semanticamente cercano aunque el nombre sea diferente '
            '(ej: "Utilidad operacional sobre activos" equivale a "RENTABILIDAD DEL ACTIVO", '
            '"Rentabilidad sobre el patrimonio" equivale a "RENTABILIDAD DEL PATRIMONIO", '
            '"Rentabilidad sobre activos" equivale a "RENTABILIDAD DEL ACTIVO", '
            '"Nivel de Endeudamiento" equivale a "INDICE DE ENDEUDAMIENTO", '
            '"Liquidez" equivale a "INDICE DE LIQUIDEZ", '
            '"Razon de Cobertura de Intereses" equivale a "RAZON DE COBRERTURA DE INTERES").\n\n'
            f'Indicadores solicitados:\n{indicator_names}\n\n'
            'REGLAS:\n'
            '1) Responde EXCLUSIVAMENTE con JSON valido (un unico objeto).\n'
            '2) Prohibido: explicaciones, markdown, texto adicional, encabezados, bloques ```json.\n'
            '3) El campo "nombre" DEBE ser EXACTAMENTE el nombre solicitado arriba, no el nombre de la columna en la DB.\n'
            '4) Si no hay ningun indicador similar en la DB, incluyelo en "faltantes" con valor null — NUNCA uses 0 para un indicador no encontrado.\n'
            '5) valor debe ser el numero real de la BD. Si el indicador no existe su valor es null, no cero.\n\n'
            'FORMATO (exacto):\n'
            '{"indicadores":[{"nombre":"Indice de Liquidez","valor":3.04},{"nombre":"Capital de Trabajo","valor":5744148157.0}],"faltantes":[]}'
        )

        gold_indicators = get_specific_gold_indicator(query_gold)

        # Obtener presupuesto para resolver umbrales relativos ("15% del POE")
        general_info = get_general_info('Cual es el presupuesto del proceso?', k=2)
        from tendermod.evaluation.compare_indicators import _compute_cumple, _parse_budget_from_text
        presupuesto = _parse_budget_from_text(general_info)

        indicadores_emparejados = merge_indicators(tender_indicators_json, gold_indicators['output'],
                                                   presupuesto=presupuesto)

        from tendermod.evaluation.schemas import IndicatorDetail

        def _safe_float(v):
            try:
                return float(v)
            except (TypeError, ValueError):
                return None

        indicadores_detalle = [
            IndicatorDetail(
                indicador=item['indicador'],
                valor_empresa=_safe_float(item.get('valor_empresa')),
                condicion=item.get('condicion') if item.get('condicion') != item.get('umbral') else None,
                umbral=_safe_float(item.get('umbral')),
                cumple=_compute_cumple(item.get('valor_empresa'), item.get('condicion', ''), item.get('umbral')),
            )
            for item in indicadores_emparejados
        ]

        comparation_response = run_llm_indicators_comparation(
            str(indicadores_emparejados), general_info
        )
        connection.close()  # el backend abre sqlite directo; re-cerrar para obtener handle limpio

        cumple = extract_compliance_bool(comparation_response)
        ind_compliance = IndicatorComplianceResult(
            cumple=cumple,
            detalle=comparation_response,
            indicadores_evaluados=[item['indicador'] for item in ind_list],
            indicadores_faltantes=[],
            indicadores_detalle=indicadores_detalle,
        )

        result, _ = AnalysisResult.objects.get_or_create(session=session)
        result.indicators_result_json = ind_compliance.model_dump_json()
        result.cumple_indicadores = cumple

        # Determinar cumple_final si ya hay resultado de experiencia
        if result.experience_result_json:
            from tendermod.evaluation.schemas import ExperienceComplianceResult
            exp_result = ExperienceComplianceResult.model_validate_json(result.experience_result_json)
            result.cumple_experiencia = exp_result.cumple
            if result.cumple_experiencia is not None and result.cumple_indicadores is not None:
                result.cumple_final = result.cumple_experiencia and result.cumple_indicadores
            elif result.cumple_indicadores is not None:
                result.cumple_final = result.cumple_indicadores
        result.save()

        if set_completed:
            session.status = 'completed'
            session.save(update_fields=['status', 'updated_at'])
        logger.info('Evaluacion de indicadores completada para sesion %s — cumple=%s', session_id, cumple)
        return {'status': 'ok', 'session_id': session_id, 'cumple': cumple}

    except Exception as exc:
        _estado = 'error'
        logger.error('Error evaluando indicadores para sesion %s: %s', session_id, exc)
        try:
            session = AnalysisSession.objects.get(pk=session_id)
            session.status = 'error'
            session.save(update_fields=['status', 'updated_at'])
        except Exception:
            pass
        raise
    finally:
        _record_timing(session_id, 'Evaluacion de indicadores financieros', 'evaluate_indicators_task', time.time() - _t0, _estado)


@shared_task(bind=True, name='analysis.quick_evaluate_experience_task')
def quick_evaluate_experience_task(self, session_id, plain_text, similarity_threshold=0.75):
    """
    Evaluacion rapida de experiencia a partir de texto libre.
    El LLM extrae ExperienceResponse del texto y luego llama check_compliance_experience().
    """
    connection.close()
    from apps.core.models import AnalysisSession, AnalysisResult
    try:
        from tendermod.evaluation.llm_client import run_llm_quick_experience
        from tendermod.evaluation.compare_experience import check_compliance_experience
        from tendermod.evaluation.schemas import IndicatorComplianceResult

        session = AnalysisSession.objects.get(pk=session_id)
        session.status = 'evaluating'
        session.celery_task_id = self.request.id
        session.save(update_fields=['status', 'celery_task_id', 'updated_at'])
        connection.close()  # liberar conexión antes de llamadas LLM/SQLite largas

        logger.info('Evaluacion rapida de experiencia para sesion %s (umbral=%.2f)', session_id, similarity_threshold)
        exp_response = run_llm_quick_experience(plain_text)

        session.experience_requirements_json = exp_response.model_dump_json()
        session.save(update_fields=['experience_requirements_json', 'updated_at'])

        compliance = check_compliance_experience(exp_response, similarity_threshold=similarity_threshold)
        connection.close()

        result, _ = AnalysisResult.objects.get_or_create(session=session)
        result.experience_result_json = compliance.model_dump_json()
        result.cumple_experiencia = compliance.cumple

        if result.indicators_result_json:
            ind_result = IndicatorComplianceResult.model_validate_json(result.indicators_result_json)
            result.cumple_indicadores = ind_result.cumple
            if result.cumple_experiencia is not None and result.cumple_indicadores is not None:
                result.cumple_final = result.cumple_experiencia and result.cumple_indicadores
            elif result.cumple_experiencia is not None:
                result.cumple_final = result.cumple_experiencia
        result.save()

        session.status = 'completed'
        session.save(update_fields=['status', 'updated_at'])
        logger.info('Evaluacion rapida de experiencia completada para sesion %s — cumple=%s', session_id, compliance.cumple)
        return {'status': 'ok', 'session_id': session_id, 'cumple': compliance.cumple}

    except Exception as exc:
        logger.error('Error en evaluacion rapida de experiencia para sesion %s: %s', session_id, exc)
        try:
            session = AnalysisSession.objects.get(pk=session_id)
            session.status = 'error'
            session.save(update_fields=['status', 'updated_at'])
        except Exception:
            pass
        raise


@shared_task(bind=True, name='analysis.quick_evaluate_indicators_task')
def quick_evaluate_indicators_task(self, session_id, plain_text):
    """
    Evaluacion rapida de indicadores a partir de texto libre.
    El LLM extrae MultipleIndicatorResponse del texto y luego compara con SQLite.
    """
    connection.close()
    from apps.core.models import AnalysisSession, AnalysisResult
    try:
        from tendermod.evaluation.llm_client import run_llm_quick_indicators, run_llm_indicators_comparation
        from tendermod.evaluation.compare_indicators import (
            merge_indicators, extract_compliance_bool,
        )
        from tendermod.evaluation.indicators_inference import get_general_info
        from tendermod.evaluation.schemas import IndicatorComplianceResult
        from tendermod.ingestion.db_loader import get_specific_gold_indicator

        session = AnalysisSession.objects.get(pk=session_id)
        session.status = 'evaluating'
        session.celery_task_id = self.request.id
        session.save(update_fields=['status', 'celery_task_id', 'updated_at'])
        connection.close()  # liberar conexión antes de llamadas LLM/SQLite largas

        logger.info('Evaluacion rapida de indicadores para sesion %s', session_id)
        ind_response = run_llm_quick_indicators(plain_text)

        session.indicators_requirements_json = ind_response.model_dump_json()
        session.save(update_fields=['indicators_requirements_json', 'updated_at'])

        ind_list = [{'indicador': i.indicador, 'valor': str(i.valor)} for i in ind_response.answer]

        tender_indicators_json = {
            'result': [{'nombre': item['indicador'], 'valor': item['valor']} for item in ind_list]
        }

        indicator_names = '\n'.join(item['indicador'] for item in ind_list)
        query_gold = (
            'Devuelve un objeto JSON valido con los siguientes indicadores financieros. '
            'Busca en la tabla el indicador mas semanticamente cercano aunque el nombre sea diferente '
            '(ej: "Utilidad operacional sobre activos" equivale a "RENTABILIDAD DEL ACTIVO", '
            '"Rentabilidad sobre el patrimonio" equivale a "RENTABILIDAD DEL PATRIMONIO", '
            '"Rentabilidad sobre activos" equivale a "RENTABILIDAD DEL ACTIVO", '
            '"Nivel de Endeudamiento" equivale a "INDICE DE ENDEUDAMIENTO", '
            '"Liquidez" equivale a "INDICE DE LIQUIDEZ", '
            '"Razon de Cobertura de Intereses" equivale a "RAZON DE COBRERTURA DE INTERES").\n\n'
            f'Indicadores solicitados:\n{indicator_names}\n\n'
            'REGLAS:\n'
            '1) Responde EXCLUSIVAMENTE con JSON valido (un unico objeto).\n'
            '2) Prohibido: explicaciones, markdown, texto adicional, encabezados, bloques ```json.\n'
            '3) El campo "nombre" DEBE ser EXACTAMENTE el nombre solicitado arriba, no el nombre de la columna en la DB.\n'
            '4) Si no hay ningun indicador similar en la DB, incluyelo en "faltantes" con valor null — NUNCA uses 0 para un indicador no encontrado.\n'
            '5) valor debe ser el numero real de la BD. Si el indicador no existe su valor es null, no cero.\n\n'
            'FORMATO (exacto):\n'
            '{"indicadores":[{"nombre":"Indice de Liquidez","valor":3.04},{"nombre":"Capital de Trabajo","valor":5744148157.0}],"faltantes":[]}'
        )

        gold_indicators = get_specific_gold_indicator(query_gold)

        # Obtener presupuesto para resolver umbrales relativos ("15% del POE")
        general_info = get_general_info('Cual es el presupuesto del proceso?', k=2)
        from tendermod.evaluation.compare_indicators import _compute_cumple, _parse_budget_from_text
        presupuesto = _parse_budget_from_text(general_info)

        indicadores_emparejados = merge_indicators(tender_indicators_json, gold_indicators['output'],
                                                   presupuesto=presupuesto)

        from tendermod.evaluation.schemas import IndicatorDetail

        def _safe_float(v):
            try:
                return float(v)
            except (TypeError, ValueError):
                return None

        indicadores_detalle = [
            IndicatorDetail(
                indicador=item['indicador'],
                valor_empresa=_safe_float(item.get('valor_empresa')),
                condicion=item.get('condicion') if item.get('condicion') != item.get('umbral') else None,
                umbral=_safe_float(item.get('umbral')),
                cumple=_compute_cumple(item.get('valor_empresa'), item.get('condicion', ''), item.get('umbral')),
            )
            for item in indicadores_emparejados
        ]

        comparation_response = run_llm_indicators_comparation(
            str(indicadores_emparejados), general_info
        )
        connection.close()

        cumple = extract_compliance_bool(comparation_response)
        ind_compliance = IndicatorComplianceResult(
            cumple=cumple,
            detalle=comparation_response,
            indicadores_evaluados=[item['indicador'] for item in ind_list],
            indicadores_faltantes=[],
            indicadores_detalle=indicadores_detalle,
        )

        result, _ = AnalysisResult.objects.get_or_create(session=session)
        result.indicators_result_json = ind_compliance.model_dump_json()
        result.cumple_indicadores = cumple

        if result.experience_result_json:
            from tendermod.evaluation.schemas import ExperienceComplianceResult
            exp_result = ExperienceComplianceResult.model_validate_json(result.experience_result_json)
            result.cumple_experiencia = exp_result.cumple
            if result.cumple_experiencia is not None and result.cumple_indicadores is not None:
                result.cumple_final = result.cumple_experiencia and result.cumple_indicadores
            elif result.cumple_indicadores is not None:
                result.cumple_final = result.cumple_indicadores
        result.save()

        session.status = 'completed'
        session.save(update_fields=['status', 'updated_at'])
        logger.info('Evaluacion rapida de indicadores completada para sesion %s — cumple=%s', session_id, cumple)
        return {'status': 'ok', 'session_id': session_id, 'cumple': cumple}

    except Exception as exc:
        logger.error('Error en evaluacion rapida de indicadores para sesion %s: %s', session_id, exc)
        try:
            session = AnalysisSession.objects.get(pk=session_id)
            session.status = 'error'
            session.save(update_fields=['status', 'updated_at'])
        except Exception:
            pass
        raise


@shared_task(bind=True, name='analysis.extract_team_profiles_task')
def extract_team_profiles_task(self, session_id):
    """
    Extrae perfiles de equipo de trabajo requeridos del pliego.
    Guarda ProfileRequirementList en session.team_profiles_json.
    """
    connection.close()
    from apps.core.models import AnalysisSession
    _t0 = time.time()
    _estado = 'ok'
    try:
        from tendermod.evaluation.profile_inference import get_team_profiles_from_pdf

        session = AnalysisSession.objects.get(pk=session_id)
        session.celery_task_id = self.request.id
        session.save(update_fields=['celery_task_id', 'updated_at'])

        logger.info('Extrayendo perfiles de equipo para sesion %s', session_id)
        profiles = get_team_profiles_from_pdf()
        connection.close()

        session.team_profiles_json = profiles.model_dump_json()
        session.save(update_fields=['team_profiles_json', 'updated_at'])
        logger.info(
            'Perfiles de equipo extraidos para sesion %s: %d perfiles',
            session_id, len(profiles.perfiles),
        )
        return {'status': 'ok', 'session_id': session_id, 'count': len(profiles.perfiles)}

    except Exception as exc:
        _estado = 'error'
        logger.error('Error extrayendo perfiles de equipo para sesion %s: %s', session_id, exc)
        raise
    finally:
        _record_timing(session_id, 'Extraccion de perfiles de equipo de trabajo', 'extract_team_profiles_task', time.time() - _t0, _estado)


@shared_task(bind=True, name='analysis.evaluate_team_profiles_task')
def evaluate_team_profiles_task(self, session_id):
    """
    Evalua cumplimiento de perfiles de equipo contra los datos del equipo de la empresa.
    Guarda TeamProfileComplianceList en result.team_compliance_json.
    """
    connection.close()
    from apps.core.models import AnalysisSession, AnalysisResult
    _t0 = time.time()
    _estado = 'ok'
    try:
        from tendermod.evaluation.profile_inference import evaluate_team_profiles
        from tendermod.evaluation.schemas import ProfileRequirementList

        session = AnalysisSession.objects.get(pk=session_id)
        session.celery_task_id = self.request.id
        session.save(update_fields=['celery_task_id', 'updated_at'])

        if not session.team_profiles_json:
            raise ValueError('team_profiles_json vacio — ejecutar extract_team_profiles_task primero')

        profiles = ProfileRequirementList.model_validate_json(session.team_profiles_json)
        logger.info(
            'Evaluando %d perfiles de equipo para sesion %s',
            len(profiles.perfiles), session_id,
        )
        compliance = evaluate_team_profiles(profiles)
        connection.close()

        result, _ = AnalysisResult.objects.get_or_create(session=session)
        result.team_compliance_json = compliance.model_dump_json()
        result.cumple_equipo = compliance.cumple_equipo
        result.save(update_fields=['team_compliance_json', 'cumple_equipo'])

        logger.info(
            'Evaluacion de equipo completada para sesion %s — cumple_equipo=%s',
            session_id, compliance.cumple_equipo,
        )
        return {
            'status': 'ok',
            'session_id': session_id,
            'cumple_equipo': compliance.cumple_equipo,
        }

    except Exception as exc:
        _estado = 'error'
        logger.error('Error evaluando perfiles de equipo para sesion %s: %s', session_id, exc)
        raise
    finally:
        _record_timing(session_id, 'Evaluacion de equipo de trabajo', 'evaluate_team_profiles_task', time.time() - _t0, _estado)


@shared_task(bind=True, name='analysis.generate_conclusion_task')
def generate_conclusion_task(self, session_id):
    """
    Genera la conclusion ejecutiva sintetizando todos los resultados de evaluacion.
    Guarda EvaluacionConclusionResult en result.conclusion_json.
    """
    connection.close()
    from apps.core.models import AnalysisSession, AnalysisResult
    _t0 = time.time()
    _estado = 'ok'
    try:
        from tendermod.evaluation.llm_client import run_llm_conclusion
        from tendermod.evaluation.schemas import (
            ExperienceComplianceResult,
            IndicatorComplianceResult,
            TeamProfileComplianceList,
        )

        session = AnalysisSession.objects.get(pk=session_id)
        session.celery_task_id = self.request.id
        session.save(update_fields=['celery_task_id', 'updated_at'])

        result = AnalysisResult.objects.get(session=session)

        # Construir contexto JSON con los datos relevantes
        context = {
            'cumple_experiencia': result.cumple_experiencia,
            'cumple_indicadores': result.cumple_indicadores,
            'cumple_equipo': result.cumple_equipo,
            'cumple_final': result.cumple_final,
        }

        if result.experience_result_json:
            exp = ExperienceComplianceResult.model_validate_json(result.experience_result_json)
            context['experiencia'] = {
                'codigos_requeridos': exp.codigos_requeridos,
                'valor_requerido_cop': exp.valor_requerido_cop,
                'objeto_requerido': exp.objeto_requerido,
                'rups_cumplen': exp.rups_cumplen,
                'rups_evaluados': [
                    {
                        'numero_rup': r.numero_rup,
                        'cliente': r.cliente,
                        'valor_cop': r.valor_cop,
                        'objeto_contrato': (r.objeto_contrato or '')[:200] if r.objeto_contrato else None,
                        'cumple_codigos': r.cumple_codigos,
                        'cumple_valor': r.cumple_valor,
                        'cumple_objeto': r.cumple_objeto,
                        'cumple_total': r.cumple_total,
                    }
                    for r in exp.rups_evaluados
                ],
            }

        if result.indicators_result_json:
            ind = IndicatorComplianceResult.model_validate_json(result.indicators_result_json)
            context['indicadores'] = {
                'cumple': ind.cumple,
                'detalle': ind.detalle[:500] if ind.detalle else '',
                'indicadores_detalle': [
                    {
                        'indicador': d.indicador,
                        'valor_empresa': d.valor_empresa,
                        'condicion': d.condicion,
                        'umbral': d.umbral,
                        'cumple': d.cumple,
                    }
                    for d in ind.indicadores_detalle
                ],
            }

        if result.team_compliance_json:
            team = TeamProfileComplianceList.model_validate_json(result.team_compliance_json)
            context['equipo'] = {
                'cumple_equipo': team.cumple_equipo,
                'perfiles': [
                    {
                        'rol': p.rol,
                        'cantidad_requerida': p.cantidad_requerida,
                        'personas_que_cumplen': p.personas_que_cumplen,
                        'cumple': p.cumple,
                    }
                    for p in team.perfiles_evaluados
                ],
            }

        context_json = json.dumps(context, ensure_ascii=False, default=str)
        logger.info('Generando conclusion ejecutiva para sesion %s', session_id)
        conclusion = run_llm_conclusion(context_json)
        connection.close()

        result.conclusion_json = conclusion.model_dump_json()
        result.save(update_fields=['conclusion_json'])

        logger.info('Conclusion ejecutiva generada para sesion %s', session_id)
        return {'status': 'ok', 'session_id': session_id}

    except Exception as exc:
        _estado = 'error'
        logger.error('Error generando conclusion para sesion %s: %s', session_id, exc)
        raise
    finally:
        _record_timing(session_id, 'Generacion de conclusion ejecutiva', 'generate_conclusion_task', time.time() - _t0, _estado)


@shared_task(bind=True, name='analysis.finalize_auto_flow_task')
def finalize_auto_flow_task(self, session_id):
    """Marca la sesion como 'completed' al terminar el chain de evaluacion automatica."""
    connection.close()
    from apps.core.models import AnalysisSession
    try:
        session = AnalysisSession.objects.get(pk=session_id)
        session.status = 'completed'
        session.auto_flow_active = False
        session.save(update_fields=['status', 'auto_flow_active', 'updated_at'])
        logger.info('Flujo automatico finalizado para sesion %s', session_id)
        return {'status': 'ok', 'session_id': session_id}
    except Exception as exc:
        logger.error('Error finalizando flujo automatico para sesion %s: %s', session_id, exc)
        raise


@shared_task(bind=True, name='analysis.mark_auto_error_task')
def mark_auto_error_task(self, request, exc, traceback, session_id):
    """
    Callback link_error del chain automatico: marca la sesion como 'error'.
    La firma (request, exc, traceback) es la que Celery pasa a un errback.
    """
    connection.close()
    from apps.core.models import AnalysisSession
    try:
        session = AnalysisSession.objects.get(pk=session_id)
        session.status = 'error'
        session.auto_flow_active = False
        session.save(update_fields=['status', 'auto_flow_active', 'updated_at'])
        logger.error('Flujo automatico marcado como error para sesion %s: %s', session_id, exc)
    except Exception as e:
        logger.error('No se pudo marcar error en sesion %s: %s', session_id, e)
