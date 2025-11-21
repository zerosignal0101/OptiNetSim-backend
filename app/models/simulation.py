from datetime import datetime
from typing import Any, Dict, List, Literal, Optional, Union,  Annotated

from bson import ObjectId
from pydantic import BaseModel, Field, model_validator, ValidationError
from uuid6 import uuid6

class SingleLinkSimulationRequest(BaseModel):
    source_id: str = Field(..., description="The source of the network.")
    destination_id: str = Field(..., description="The destination of the network.")

class SNRResult(BaseModel):
    element_id: str
    snr_01nm: float
    snr: float
    osnr_ase: float
    osnr_ase_01nm: float

class PowerResult(BaseModel):
    element_id: str
    pch_out_dbm: float

class SingleLinkSimulationResponse(BaseModel):
    path: List[str]
    snr_results: List[SNRResult]
    power_results: List[PowerResult]
