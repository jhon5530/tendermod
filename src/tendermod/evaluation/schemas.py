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


class IndicatorComplianceResult(BaseModel):
    cumple: Optional[bool] = Field(default=None, description="True si cumple, False si no, None si no se pudo determinar")
    detalle: str = Field(default="", description="Texto completo del LLM con la argumentación")
    indicadores_evaluados: List[str] = Field(default=[], description="Nombres de indicadores que se compararon")
    indicadores_faltantes: List[str] = Field(default=[], description="Indicadores requeridos sin datos en SQLite")


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