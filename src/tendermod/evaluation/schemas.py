from pydantic import BaseModel, Field, ConfigDict
from typing import List, Union, Optional, Literal

class ExperienceSubRequirement(BaseModel):
    """Un sub-requisito de experiencia especifica del pliego."""
    descripcion: str = Field(
        description="Descripcion exacta del sub-requisito tal como aparece en el pliego"
    )
    codigos_unspsc: List[str] = Field(
        default=[],
        description="Codigos UNSPSC especificos de este sub-req (hereda globales si vacio)"
    )
    cantidad_minima_contratos: int = Field(
        default=1,
        description="Minimo de contratos distintos que deben cubrir este sub-requisito"
    )
    valor_minimo: str = Field(
        default="None",
        description="Valor minimo para este sub-req especifico. 'None' si no aplica."
    )
    objeto_exige_relevancia: Literal["SI", "NO", "NO_ESPECIFICADO"] = Field(
        default="NO_ESPECIFICADO"
    )


class SubRequirementComplianceResult(BaseModel):
    """Resultado de evaluacion para un sub-requisito individual."""
    indice: int
    descripcion: str
    rups_candidatos: List[Union[int, str]] = Field(default=[])
    rup_elegido: Optional[Union[int, str]] = Field(default=None)
    score_objeto: Optional[float] = Field(default=None)
    objeto_contrato: Optional[str] = Field(default=None)
    cumple: bool = Field(default=False)


class Indicator(BaseModel):
    indicador: str = Field(description="El nombre del indicador")
    valor: Union[str, float] = Field(description="El valor del indicador")
    

class MultipleIndicatorResponse(BaseModel):
    answer:List[Indicator]


class ExperienceResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    listado_codigos: List[str] = Field(
        default = [],
        description="Lista de códigos UNSPSC de 8 dígitos",
        alias="Listado de codigos"
    )
    cantidad_codigos: str = Field(
        default = "None",
        description="Cantidad total de códigos UNSPSC solicitados",
        alias="Cuantos codigos"
    )
    objeto: str = Field(
        default = "None",
        description="Descripción del objeto o alcance requerido para la experiencia",
        alias="Objeto"
    )
    cantidad_contratos: str = Field(
        default = "None",
        description="Requisito sobre la cantidad de contratos a presentar",
        alias="Cantidad de contratos"
    )
    valor: str = Field(
        default = "None",
        description="Valor mínimo que debe acreditar el proponente",
        alias="Valor a acreditar"
    )
    pagina: str = Field(
        default = "None",
        description="Número de página donde se encuentra la información",
        alias="Pagina"
    )
    seccion: str = Field(
        default = "None",
        description="Nombre de la sección del documento",
        alias="Seccion"
    )
    regla_codigos: Literal["ALL", "AT_LEAST_ONE"] = Field(
        default="AT_LEAST_ONE",
        description="Regla lógica de validación: ALL si el pliego exige todos los códigos simultáneamente, AT_LEAST_ONE si basta con uno",
        alias="Regla codigos"
    )
    objeto_exige_relevancia: Literal["SI", "NO", "NO_ESPECIFICADO"] = Field(
        default="NO_ESPECIFICADO",
        description=(
            "SI si el pliego exige explícitamente que la experiencia sea relacionada "
            "con el objeto del proceso. NO si lo descarta. NO_ESPECIFICADO si no hay "
            "suficiente información para determinarlo."
        ),
        alias="Objeto exige relevancia"
    )
    modo_evaluacion: Literal["GLOBAL", "MULTI_CONDICION"] = Field(
        default="GLOBAL",
        alias="Modo evaluacion",
        description="MULTI_CONDICION cuando el pliego exige contratos distintos por actividad"
    )
    sub_requisitos: List[ExperienceSubRequirement] = Field(
        default=[],
        alias="Sub requisitos",
        description="Lista de sub-requisitos. Vacia en modo GLOBAL."
    )


class GeneralRequirement(BaseModel):
    id: int
    categoria: Literal[
        "JURIDICO",
        "TECNICO",
        "DOCUMENTACION",
        "CAPACIDAD",
        "FINANCIERO_OTRO",
        "GARANTIA",
        "CAUSAL_RECHAZO",
        "EVALUACION",
        "EXPERIENCIA",
        "IDIOMA",
        "OTRO",
    ]
    tipo: Literal[
        "HABILITANTE",
        "HABILITANTE-EXPERIENCIA",
        "HABILITANTE-INDICADORES",
        "PUNTUABLE",
        "DOCUMENTAL",
        "GARANTIA",
        "CAUSAL_RECHAZO",
        "OBLIGACION",
        "IDIOMA",
        "NO_ESPECIFICADO",
    ] = "NO_ESPECIFICADO"
    descripcion: str
    documento_formato: str = "N/A"
    obligatorio: Literal["SI", "NO", "NO_ESPECIFICADO"] = "SI"
    pagina: str = "N/A"
    seccion: str = "N/A"
    estado: Literal[
        "PENDIENTE",      # legacy — sesiones anteriores; UI lo trata como EN_REVISION
        "EN_REVISION",
        "CUMPLE",
        "NO_CUMPLE",
        "N/A",
    ] = "EN_REVISION"
    nota: str = ""
    origen: Literal["EXTRACCION", "QA", "MANUAL"] = "EXTRACCION"
    extracto_pliego: str = ""
    citation_verified: Optional[bool] = None  # True=cita confirmada en bloque fuente, False=no encontrada, None=no verificado
    confidence: Optional[float] = None  # 0.0-1.0: heurística basada en sección+extracto+verificación


class GeneralRequirementList(BaseModel):
    requisitos: List[GeneralRequirement] = []


class IndicatorDetail(BaseModel):
    indicador: str
    valor_empresa: Optional[float] = None
    condicion: Optional[str] = None
    umbral: Optional[float] = None
    cumple: Optional[bool] = None


class IndicatorComplianceResult(BaseModel):
    cumple: Optional[bool] = Field(default=None, description="True si cumple, False si no, None si no se pudo determinar")
    detalle: str = Field(default="", description="Texto completo del LLM con la argumentación")
    indicadores_evaluados: List[str] = Field(default=[], description="Nombres de indicadores que se compararon")
    indicadores_faltantes: List[str] = Field(default=[], description="Indicadores requeridos sin datos en SQLite")
    indicadores_detalle: List[IndicatorDetail] = Field(default=[], description="Detalle por indicador: valor, condicion, umbral, cumple")


class RupExperienceResult(BaseModel):
    numero_rup: Union[int, str] = Field(description="Número RUP del proponente")
    cliente: Optional[str] = Field(default=None, description="Nombre del cliente/entidad del contrato")
    valor_cop: Optional[float] = Field(default=None, description="Valor del contrato en COP")
    cumple_codigos: bool = Field(description="True si cumple los códigos UNSPSC requeridos")
    cumple_valor: Optional[bool] = Field(default=None, description="True si cumple valor mínimo. None si no aplica")
    cumple_objeto: Optional[bool] = Field(default=None, description="True si el objeto es compatible. None si no aplica")
    score_objeto: Optional[float] = Field(
        default=None,
        description="Score de similitud semántica con el objeto requerido (0.0-1.0). None si no aplica o no hay datos en ChromaDB."
    )
    objeto_contrato: Optional[str] = Field(
        default=None,
        description="Texto del contrato con mayor similitud semántica al objeto requerido"
    )
    cumple_total: bool = Field(description="True solo si todos los criterios evaluables son True")


class ExperienceComplianceResult(BaseModel):
    codigos_requeridos: List[str] = Field(default=[], description="Códigos UNSPSC extraídos del pliego")
    valor_requerido_cop: Optional[float] = Field(default=None, description="Valor mínimo requerido en COP")
    objeto_requerido: Optional[str] = Field(default=None, description="Objeto/alcance requerido del pliego")
    rups_evaluados: List[RupExperienceResult] = Field(default=[], description="Resultados por RUP")
    rups_candidatos_codigos: List[Union[int, str]] = Field(
        default=[],
        description="Pool completo de RUPs que cumplen códigos UNSPSC (antes de aplicar top-N)"
    )
    cantidad_contratos_requerida: Optional[int] = Field(
        default=None,
        description="N máximo de contratos a seleccionar para acreditar experiencia (None = sin límite)"
    )
    rups_cumplen: List[Union[int, str]] = Field(default=[], description="RUPs que cumplen todos los criterios evaluables")
    total_valor_cop: Optional[float] = Field(default=None, description="Suma total en COP de los RUPs seleccionados (top-N)")
    rups_excluidos_por_objeto: List[Union[int, str]] = Field(
        default=[],
        description="RUPs del top-N excluidos por no cumplir relevancia semántica con el objeto del proceso (Fase 2)"
    )
    objeto_exige_relevancia: Optional[str] = Field(
        default=None,
        description="Valor extraído del pliego para el filtro de objeto (SI/NO/NO_ESPECIFICADO)"
    )
    similarity_threshold_usado: float = Field(
        default=0.75,
        description="Umbral de similitud semántica utilizado en la evaluación de objeto"
    )
    cumple: bool = Field(default=False, description="True si al menos 1 RUP cumple todos los criterios")
    modo_evaluacion: str = Field(default="GLOBAL", description="Modo de evaluacion usado: GLOBAL o MULTI_CONDICION")
    sub_requisitos_resultado: List[SubRequirementComplianceResult] = Field(
        default=[],
        description="Resultados por sub-requisito en modo MULTI_CONDICION"
    )
    sub_requisitos_cumplidos: int = Field(default=0, description="Cantidad de sub-requisitos que cumplen")
    sub_requisitos_totales: int = Field(default=0, description="Cantidad total de sub-requisitos evaluados")


class ProfileRequirement(BaseModel):
    """Perfil de rol requerido extraído del pliego."""
    rol: str = Field(description="Nombre del rol o cargo requerido (ej: GERENTE DE PROYECTO)")
    cantidad: int = Field(default=1, description="Número de personas requeridas para este rol")
    formacion_requerida: List[str] = Field(
        default=[],
        description="Títulos profesionales aceptables con lógica OR (ej: ['Ing. Sistemas', 'Telecomunicaciones', 'afines'])",
    )
    posgrado_requerido: List[str] = Field(
        default=[],
        description="Posgrados o certificaciones equivalentes con lógica OR (ej: ['Gerencia de Proyectos', 'PMP', 'ITIL'])",
    )
    certificaciones_requeridas: List[str] = Field(
        default=[],
        description="Certificaciones técnicas requeridas (ej: ['Cisco vigente', 'PMP vigente', 'ITIL'])",
    )
    anios_experiencia_min: Optional[int] = Field(default=None, description="Años mínimos de experiencia profesional")
    contratos_min: Optional[int] = Field(default=None, description="Número mínimo de contratos en el rol")
    descripcion_experiencia: str = Field(default="", description="Texto descriptivo del tipo de experiencia requerida")
    disponibilidad: str = Field(default="", description="Requisito de disponibilidad (ej: 'parcial en sitio, 7x5')")
    seccion: str = Field(default="N/A", description="Sección del pliego donde se define el perfil")
    pagina: str = Field(default="N/A", description="Página aproximada del pliego")


class ProfileRequirementList(BaseModel):
    perfiles: List[ProfileRequirement] = []


class PersonaProfileResult(BaseModel):
    """Resultado de evaluar una persona contra un perfil de rol."""
    persona: str
    cargo: str
    cumple: bool
    justificacion: str = Field(description="Explicación detallada de por qué cumple o no cumple")
    evidencia: List[str] = Field(
        default=[],
        description="Certificaciones/títulos concretos que satisfacen cada requisito (ej: 'PMP vigente satisface PMP requerido')",
    )
    gaps: List[str] = Field(
        default=[],
        description="Requisitos específicos que la persona no satisface",
    )


class ProfileComplianceResult(BaseModel):
    """Resultado de evaluación de un rol completo."""
    rol: str
    cantidad_requerida: int
    personas_evaluadas: List[PersonaProfileResult] = []
    personas_que_cumplen: List[str] = Field(default=[], description="Nombres de personas que cumplen el perfil")
    cumple: bool = Field(description="True si personas_que_cumplen >= cantidad_requerida")


class TeamProfileComplianceList(BaseModel):
    perfiles_evaluados: List[ProfileComplianceResult] = []
    cumple_equipo: bool = Field(default=False, description="True si TODOS los perfiles requeridos tienen suficientes candidatos")


class TeamQuery(BaseModel):
    """Intención parseada de una pregunta sobre el equipo de la empresa."""
    action: Literal["count", "list", "detail"] = Field(
        default="list",
        description="count=cuántos, list=quiénes/qué, detail=info completa con fechas",
    )
    filter_cert: Optional[str] = Field(
        default=None,
        description="Término parcial del nombre de certificación (ej: 'CCNA', 'Crowdstrike', 'CCNP')",
    )
    filter_categoria: Optional[str] = Field(
        default=None,
        description="Término parcial de la categoría/marca (ej: 'CISCO', 'FORTINET', 'SEGURIDAD')",
    )
    filter_persona: Optional[str] = Field(
        default=None,
        description="Nombre parcial de la persona",
    )
    filter_cert_list: Optional[List[str]] = Field(
        default=None,
        description="Lista de términos de certificación cuando se requieren MÚLTIPLES con lógica AND. Ej: ['CCNA', 'ITIL']",
    )
    filter_categoria_list: Optional[List[str]] = Field(
        default=None,
        description="Lista de categorías cuando se requieren MÚLTIPLES con lógica AND. Ej: ['CISCO', 'FORTINET']",
    )
    filter_vencimiento: Optional[Literal["vigente", "vencida"]] = Field(
        default=None,
        description="Filtrar por estado de vencimiento",
    )
    group_by: Optional[Literal["persona", "certificacion", "categoria"]] = Field(
        default=None,
        description="Agrupar resultados por esta dimensión",
    )


class RupRecomendado(BaseModel):
    numero_rup: Union[int, str]
    cliente: Optional[str] = None
    valor_cop: Optional[float] = None
    relevancia: str = ""


class PersonaRecomendada(BaseModel):
    rol: str
    personas: List[str] = []


class EvaluacionConclusionResult(BaseModel):
    veredicto_general: str = Field(description="Texto narrativo ejecutivo de 2-3 párrafos con el veredicto global")
    rups_recomendados: List[RupRecomendado] = Field(default=[], description="Contratos RUP que deben incluirse en la propuesta")
    personas_recomendadas: List[PersonaRecomendada] = Field(default=[], description="Personas recomendadas por perfil requerido")
    brechas: List[str] = Field(default=[], description="Brechas concretas detectadas (indicadores, experiencia, equipo)")
    recomendaciones: List[str] = Field(default=[], description="Acciones concretas para subsanar brechas o fortalecer la propuesta")