from pydantic import BaseModel, Field  # Field 是可选的，用于添加更多元数据
from typing import Optional, List, Dict


class DefragRequest(BaseModel):
    avg_arrival_interval: float
    avg_holding_time: float
    service_arrival_time_max: int


class DefragService(BaseModel):
    service_id: int
    source_id: str
    destination_id: str = None
    arrival_time: float = None
    departure_time: float = None
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


# -------- 辅助模型 --------

class NewServiceAllocationInfo(BaseModel):
    """
    表示新服务在重排后成功分配的路径和波长信息。
    """
    path: List[str]
    wavelength: int

class ServiceReallocationDetails(BaseModel):
    """
    表示单个服务在重排过程中被重新分配前后的路径和波长信息。
    """
    service_id: int
    # original_service_dict2_for_defrag 里取出的服务，其 path 和 wavelength 可能为 None
    old_path: Optional[List[str]] = None
    old_wavelength: Optional[int] = None
    # 重排后，如果服务被成功重新分配，则有新值；
    # 如果服务被释放但未能重新分配，则变为 None。
    new_path: Optional[List[str]] = None
    new_wavelength: Optional[int] = None

# -------- 主要事件模型 --------

class DefragmentationEvent(BaseModel):
    """
    表示一次重排事件的完整详情。
    """
    trigger_service_id: int = Field(..., description="触发此次重排的新业务ID")
    arrival_time: float = Field(..., description="触发重排时的新业务到达时间")
    departure_time: float = Field(..., description="触发重排时的新业务持有时间")
    reallocations: List[ServiceReallocationDetails] = Field(
        ...,
        description="在此次重排尝试中，被重新分配或尝试重新分配的服务列表及其路径和波长变化"
    )
    final_blocked: bool = Field(
        ...,
        description="重排后新业务是否仍然阻塞（未被分配）"
    )
    new_service_allocation: Optional[NewServiceAllocationInfo] = Field(
        None,
        description="如果新业务最终被成功分配，则包含其路径和波长信息"
    )


class DefragResponse(BaseModel):
    services: List[DefragService]
    result: DefragResult
    defragmentation_events: List[DefragmentationEvent]
