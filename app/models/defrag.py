from pydantic import BaseModel, Field  # Field 是可选的，用于添加更多元数据
from typing import Optional, List, Dict


class DefragRequest(BaseModel):
    erlang: float
    service_num: int


class DefragService(BaseModel):
    service_id: int
    source_id: str
    destination_id: str = None
    arrival_time: float = None
    holding_time: float = None
    bit_rate: float = None
    modulation: Optional[str] = None
    power: float = None
    path: List[str] = None  # 假设 path 是一个整数列表
    wavelength: int = None
    snr_requirement: float
    GSNR: float
    utilization: float


class DefragResult(BaseModel):
    blocknum1: int
    blocknum2: int


class DefragResponse(BaseModel):
    services: List[DefragService]
    result: DefragResult
