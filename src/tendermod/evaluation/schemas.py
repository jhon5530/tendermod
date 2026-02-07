from pydantic import BaseModel, Field
from typing import List, Union

class Indicator(BaseModel):
    indicador: str = Field(description="El nombre del indicador")
    valor: Union[str, float] = Field(description="El valor del indicador")
    

class MultipleIndicatorResponse(BaseModel):
    answer:List[Indicator]


class ExperienceResponse(BaseModel):
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