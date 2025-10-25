from pydantic import BaseModel, Field
from typing import List, Literal, Union, Optional, Annotated


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
    power: float = None
    path: List[str] = None  # 假设 path 是一个整数列表
    wavelength: int = None
    snr_requirement: float
    gsnr: float
    utilization: float


class DefragResult(BaseModel):
    blocknum1: int
    blocknum2: int


# 2. 为每种 event_type 的 "details" 定义模型
# ALLOCATION 事件的 details 就是整个 Service 对象
class AllocationDetails(DefragService):
    pass


class ReleaseExpiredDetails(BaseModel):
    departure_time: float


class ReallocationDetails(DefragService):
    defrag_service_id: int
    pass


# 3. 为每种完整事件定义模型，并使用 Literal 类型作为 "标签"
class AllocationEvent(BaseModel):
    timestamp: float
    event_type: Literal['ALLOCATION']
    service_id: int
    details: AllocationDetails


class ReleaseExpiredEvent(BaseModel):
    timestamp: float
    event_type: Literal['RELEASE_EXPIRED']
    service_id: int
    details: ReleaseExpiredDetails


class ReallocationEvent(BaseModel):
    timestamp: float
    event_type: Literal['REALLOCATION']
    service_id: int
    details: ReallocationDetails


# 4. 使用 Union 和 discriminator 创建标记联合
AnyEvent = Annotated[
    Union[AllocationEvent, ReleaseExpiredEvent, ReallocationEvent],
    Field(discriminator='event_type')
]


class DefragResponse(BaseModel):
    result: DefragResult
    defrag_timeline_events: List[AnyEvent]
