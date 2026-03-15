from pydantic import BaseModel, Field, ConfigDict
from typing import List, Union, Optional

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


class IndicatorComplianceResult(BaseModel):
    cumple: Optional[bool] = Field(default=None, description="True si cumple, False si no, None si no se pudo determinar")
    detalle: str = Field(default="", description="Texto completo del LLM con la argumentación")
    indicadores_evaluados: List[str] = Field(default=[], description="Nombres de indicadores que se compararon")
    indicadores_faltantes: List[str] = Field(default=[], description="Indicadores requeridos sin datos en SQLite")


class RupExperienceResult(BaseModel):
    numero_rup: Union[int, str] = Field(description="Número RUP del proponente")
    cumple_codigos: bool = Field(description="True si cumple los códigos UNSPSC requeridos")
    cumple_valor: Optional[bool] = Field(default=None, description="True si cumple valor mínimo. None si no aplica")
    cumple_objeto: Optional[bool] = Field(default=None, description="True si el objeto es compatible. None si no aplica")
    cumple_total: bool = Field(description="True solo si todos los criterios evaluables son True")


class ExperienceComplianceResult(BaseModel):
    codigos_requeridos: List[str] = Field(default=[], description="Códigos UNSPSC extraídos del pliego")
    valor_requerido_cop: Optional[float] = Field(default=None, description="Valor mínimo requerido en COP")
    objeto_requerido: Optional[str] = Field(default=None, description="Objeto/alcance requerido del pliego")
    rups_evaluados: List[RupExperienceResult] = Field(default=[], description="Resultados por RUP")
    rups_cumplen: List[Union[int, str]] = Field(default=[], description="RUPs que cumplen todos los criterios evaluables")
    cumple: bool = Field(default=False, description="True si al menos 1 RUP cumple todos los criterios")