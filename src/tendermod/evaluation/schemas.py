from pydantic import BaseModel, Field
from typing import List, Union

class Indicator(BaseModel):
    indicador: str = Field(description="El nombre del indicador")
    valor: Union[str, float] = Field(description="El valor del indicador")
    

class MultipleIndicatorResponse(BaseModel):
    answer:List[Indicator]