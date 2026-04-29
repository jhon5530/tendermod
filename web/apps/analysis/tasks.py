import logging
from celery import shared_task
from django.db import connection

logger = logging.getLogger(__name__)


@shared_task(bind=True, name='analysis.ingest_pdf_task')
def ingest_pdf_task(self, session_id):
    """
    Ingesta el PDF copiado a data/ en ChromaDB para licitacion.
    Actualiza el estado de la sesion a 'pdf_ready' al completar.
    """
    connection.close()
    from apps.core.models import AnalysisSession
    try:
        from tendermod.ingestion.ingestion_flow import ingest_documents

        session = AnalysisSession.objects.get(pk=session_id)
        session.status = 'ingesting_pdf'
        session.celery_task_id = self.request.id
        session.save(update_fields=['status', 'celery_task_id', 'updated_at'])

        logger.info('Ingiriendo PDF para sesion %s', session_id)
        ingest_documents()

        session.status = 'pdf_ready'
        session.save(update_fields=['status', 'updated_at'])
        logger.info('PDF ingerido exitosamente para sesion %s', session_id)
        return {'status': 'ok', 'session_id': session_id}

    except Exception as exc:
        logger.error('Error ingiriendo PDF para sesion %s: %s', session_id, exc)
        try:
            session = AnalysisSession.objects.get(pk=session_id)
            session.status = 'error'
            session.save(update_fields=['status', 'updated_at'])
        except Exception:
            pass
        raise


@shared_task(bind=True, name='analysis.extract_general_requirements_task')
def extract_general_requirements_task(self, session_id):
    """
    Extrae requisitos habilitantes generales del pliego usando RAG.
    Guarda GeneralRequirementList en session.general_requirements_json.
    """
    connection.close()
    from apps.core.models import AnalysisSession
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
        logger.error('Error extrayendo requisitos generales para sesion %s: %s', session_id, exc)
        raise


@shared_task(bind=True, name='analysis.extract_experience_task')
def extract_experience_task(self, session_id):
    """
    Extrae requisitos de experiencia del pliego usando RAG.
    Guarda ExperienceResponse en session.experience_requirements_json.
    """
    connection.close()
    from apps.core.models import AnalysisSession
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

        session.experience_requirements_json = exp_response.model_dump_json()
        session.save(update_fields=['experience_requirements_json', 'updated_at'])

        from apps.core.models import AnalysisResult
        result, _ = AnalysisResult.objects.get_or_create(session=session)
        result.experience_context_text = experience_context or ''
        result.save(update_fields=['experience_context_text'])

        logger.info('Requisitos de experiencia extraidos para sesion %s', session_id)
        return {'status': 'ok', 'session_id': session_id}

    except Exception as exc:
        logger.error('Error extrayendo experiencia para sesion %s: %s', session_id, exc)
        raise


@shared_task(bind=True, name='analysis.extract_indicators_task')
def extract_indicators_task(self, session_id):
    """
    Extrae indicadores financieros del pliego usando RAG.
    Guarda MultipleIndicatorResponse en session.indicators_requirements_json.
    """
    connection.close()
    from apps.core.models import AnalysisSession
    try:
        from tendermod.evaluation.indicators_inference import get_indicators

        session = AnalysisSession.objects.get(pk=session_id)
        session.celery_task_id = self.request.id
        session.save(update_fields=['celery_task_id', 'updated_at'])

        query = (
            'Cuales son los indicadores financieros como: '
            'Rentabilidades, capacidades, endeudamiento, indices'
        )
        logger.info('Extrayendo indicadores para sesion %s', session_id)
        ind_response, indicators_context = get_indicators(user_input=query, k=2)
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
        logger.error('Error extrayendo indicadores para sesion %s: %s', session_id, exc)
        raise


@shared_task(bind=True, name='analysis.extract_general_info_task')
def extract_general_info_task(self, session_id):
    """
    Extrae informacion general del proceso (presupuesto, objeto, etc).
    Guarda texto libre en session.general_info_text.
    """
    connection.close()
    from apps.core.models import AnalysisSession
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
        logger.error('Error extrayendo info general para sesion %s: %s', session_id, exc)
        raise


@shared_task(bind=True, name='analysis.evaluate_experience_task')
def evaluate_experience_task(self, session_id, exp_dict, similarity_threshold=0.75):
    """
    Evalua cumplimiento de experiencia a partir del dict editado por el usuario.
    Crea o actualiza AnalysisResult con el resultado.
    """
    connection.close()
    from apps.core.models import AnalysisSession, AnalysisResult
    try:
        from tendermod.evaluation.schemas import ExperienceResponse
        from tendermod.evaluation.compare_experience import check_compliance_experience

        session = AnalysisSession.objects.get(pk=session_id)
        session.status = 'evaluating'
        session.celery_task_id = self.request.id
        session.save(update_fields=['status', 'celery_task_id', 'updated_at'])

        # Reconstruir ExperienceResponse desde el dict editado por el usuario
        exp_response = ExperienceResponse(**exp_dict)
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

        session.status = 'completed'
        session.save(update_fields=['status', 'updated_at'])
        logger.info('Evaluacion de experiencia completada para sesion %s — cumple=%s', session_id, compliance.cumple)
        return {'status': 'ok', 'session_id': session_id, 'cumple': compliance.cumple}

    except Exception as exc:
        logger.error('Error evaluando experiencia para sesion %s: %s', session_id, exc)
        try:
            session = AnalysisSession.objects.get(pk=session_id)
            session.status = 'error'
            session.save(update_fields=['status', 'updated_at'])
        except Exception:
            pass
        raise


@shared_task(bind=True, name='analysis.evaluate_indicators_task')
def evaluate_indicators_task(self, session_id, ind_list):
    """
    Evalua indicadores usando merge_indicators() + run_llm_indicators_comparation().
    ind_list: lista de dicts {indicador, valor} (editados por el usuario).
    """
    connection.close()
    from apps.core.models import AnalysisSession, AnalysisResult
    try:
        from tendermod.evaluation.compare_indicators import (
            merge_indicators, from_indicator_schema_to_simple_json, extract_compliance_bool,
        )
        from tendermod.evaluation.llm_client import run_llm_indicators_comparation
        from tendermod.evaluation.indicators_inference import get_general_info
        from tendermod.evaluation.schemas import IndicatorComplianceResult
        from tendermod.ingestion.db_loader import get_specific_gold_indicator

        session = AnalysisSession.objects.get(pk=session_id)
        session.status = 'evaluating'
        session.celery_task_id = self.request.id
        session.save(update_fields=['status', 'celery_task_id', 'updated_at'])

        logger.info('Evaluando indicadores para sesion %s', session_id)

        # Construir tender_indicators_json en el formato que espera merge_indicators()
        tender_indicators_json = {
            'result': [{'nombre': item['indicador'], 'valor': item['valor']} for item in ind_list]
        }

        # Obtener nombres de indicadores para construir la query al SQL agent
        indicator_names = '\n'.join(item['indicador'] for item in ind_list)
        query_gold = (
            'Devuelve un objeto JSON valido con los siguientes indicadores: '
            f'\n{indicator_names}\n\n'
            'REGLAS:\n'
            '1) Responde EXCLUSIVAMENTE con JSON valido (un unico objeto).\n'
            '2) Prohibido: explicaciones, markdown, texto adicional, encabezados, bloques ```json.\n'
            '3) Si un indicador no existe, no lo inventes: incluyelo en faltantes.\n'
            '4) valor debe ser numero cuando sea posible.\n\n'
            'FORMATO (exacto):\n'
            '{"indicadores":[{"nombre":"...","valor":0.0}]}'
        )

        gold_indicators = get_specific_gold_indicator(query_gold)
        indicadores_emparejados = merge_indicators(tender_indicators_json, gold_indicators['output'])

        general_info = get_general_info('Cual es el presupuesto del proceso?', k=2)
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

        session.status = 'completed'
        session.save(update_fields=['status', 'updated_at'])
        logger.info('Evaluacion de indicadores completada para sesion %s — cumple=%s', session_id, cumple)
        return {'status': 'ok', 'session_id': session_id, 'cumple': cumple}

    except Exception as exc:
        logger.error('Error evaluando indicadores para sesion %s: %s', session_id, exc)
        try:
            session = AnalysisSession.objects.get(pk=session_id)
            session.status = 'error'
            session.save(update_fields=['status', 'updated_at'])
        except Exception:
            pass
        raise


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
            merge_indicators, from_indicator_schema_to_simple_json, extract_compliance_bool,
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
            'Devuelve un objeto JSON valido con los siguientes indicadores: '
            f'\n{indicator_names}\n\n'
            'REGLAS:\n'
            '1) Responde EXCLUSIVAMENTE con JSON valido (un unico objeto).\n'
            '2) Prohibido: explicaciones, markdown, texto adicional, encabezados, bloques ```json.\n'
            '3) Si un indicador no existe, no lo inventes: incluyelo en faltantes.\n'
            '4) valor debe ser numero cuando sea posible.\n\n'
            'FORMATO (exacto):\n'
            '{"indicadores":[{"nombre":"...","valor":0.0}]}'
        )

        gold_indicators = get_specific_gold_indicator(query_gold)
        indicadores_emparejados = merge_indicators(tender_indicators_json, gold_indicators['output'])

        general_info = get_general_info('Cual es el presupuesto del proceso?', k=2)
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
