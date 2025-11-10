# app/models/network.py

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional, Union

from bson import ObjectId
from pydantic import BaseModel, Field, ValidationError  # 导入 ValidationError
from uuid6 import uuid6


# --- Helper Models for Global Settings ---

class Location(BaseModel):
    x: float
    y: float


class RamanParams(BaseModel):
    flag: bool = True
    result_spatial_resolution: int = 10
    solver_spatial_resolution: int = 50


class NliParams(BaseModel):
    method: str = "ggn_spectrally_separated"
    dispersion_tolerance: float = 1.0
    phase_shift_tolerance: float = 0.1
    computed_channels: List[int] = Field(default_factory=list)


class SimulationConfig(BaseModel):
    raman_params: RamanParams = Field(default_factory=RamanParams)
    nli_params: NliParams = Field(default_factory=NliParams)


class SIConfig(BaseModel):
    f_min: float = 190.3e12
    baud_rate: float = 3.57e9
    f_max: float = 196.1e12
    spacing: float = 50e9
    power_dbm: int = 2
    power_range_db: List[int] = Field(default_factory=lambda: [0, 0, 1])
    roll_off: float = 0.15
    tx_osnr: int = 35
    sys_margins: int = 2


class SpanConfig(BaseModel):
    power_mode: bool = True
    delta_power_range_db: List[int] = Field(default_factory=lambda: [0, 0, 0])
    max_fiber_lineic_loss_for_raman: float = 0.25
    target_extended_gain: int = 0
    max_length: int = 135
    length_units: str = "km"
    max_loss: int = 28
    padding: int = 11
    EOL: int = 0
    con_in: int = 0
    con_out: int = 0


# --- Element Models ---

class ElementParamsBase(BaseModel):
    pass


class FiberParams(ElementParamsBase):
    length: float = 80.0
    loss_coef: float = 0.215
    length_units: str = "km"
    att_in: float = 0.0


class RoadmParams(ElementParamsBase):
    target_pch_out_db: Optional[float] = None
    restrictions: Dict[str, Any] = Field(default_factory=dict)


class EdfaOperational(BaseModel):
    gain_target: Optional[float] = None
    tilt_target: Optional[float] = None


# Base Element Model
class ElementBase(BaseModel):
    name: str
    type: Literal["Transceiver", "Edfa", "Roadm", "Fiber", "Fused"]
    type_variety: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ElementCreate(ElementBase):
    # element_id is used for temporary linking during import/sub-topology insertion
    # It will be replaced by a newly generated UUID6 upon storage in DB.
    element_id: Optional[str] = None  # <-- 新增或修改此行
    params: Dict[str, Any] = Field(default_factory=dict)
    operational: Dict[str, Any] = Field(default_factory=dict)


class ElementInDB(ElementBase):
    element_id: str = Field(default_factory=lambda: str(uuid6()))
    params: Dict[str, Any] = Field(default_factory=dict)
    operational: Dict[str, Any] = Field(default_factory=dict)


class ElementUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[Literal["Transceiver", "Edfa", "Roadm", "Fiber", "Fused"]] = None
    type_variety: Optional[str] = None
    params: Optional[Dict[str, Any]] = None
    operational: Dict[str, Any] = Field(default_factory=dict)
    metadata: Optional[Dict[str, Any]] = None


# --- Connection Models ---

class ConnectionBase(BaseModel):
    from_node: str
    to_node: str


class ConnectionCreate(ConnectionBase):
    pass


class ConnectionInDB(ConnectionBase):
    connection_id: str = Field(default_factory=lambda: str(uuid6()))


# --- Service Models ---

class ServiceRequirements(BaseModel):
    bandwidth: int = 10000000000
    latency: float = 10.0


class ServiceBase(BaseModel):
    name: str
    source_id: str
    destination_id: str
    path: Optional[List[str]] = None
    service_requirements: ServiceRequirements = Field(default_factory=ServiceRequirements)
    service_constraints: Dict[str, Any] = Field(default_factory=dict)


class ServiceCreate(ServiceBase):
    pass


class ServiceInDB(ServiceBase):
    service_id: str = Field(default_factory=lambda: str(uuid6()))
    status: str = "Provisioning"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ServiceUpdate(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None
    source_id: Optional[str] = None
    destination_id: Optional[str] = None
    path: Optional[List[str]] = None
    service_requirements: Optional[ServiceRequirements] = None
    service_constraints: Optional[Dict[str, Any]] = None


# --- Network Models ---

class NetworkBase(BaseModel):
    network_name: str


class NetworkCreate(NetworkBase):
    pass


class NetworkUpdate(NetworkBase):
    pass


class NetworkInDB(NetworkBase):
    id: ObjectId = Field(default_factory=ObjectId, alias="_id")
    user_id: str = Field(..., description="Username of the network owner")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    elements: List[ElementInDB] = Field(default_factory=list)
    connections: List[ConnectionInDB] = Field(default_factory=list)
    services: List[ServiceInDB] = Field(default_factory=list)
    SI: SIConfig = Field(default_factory=SIConfig, alias="SI")
    Span: SpanConfig = Field(default_factory=SpanConfig, alias="Span")
    simulation_config: SimulationConfig = Field(default_factory=SimulationConfig)

    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
    }


class NetworkResponse(NetworkBase):
    network_id: str
    created_at: datetime
    updated_at: datetime


class NetworkListResponse(BaseModel):
    networks: List[NetworkResponse]
    total_count: int
    page: int
    limit: int


class NetworkDetailResponse(NetworkResponse):
    elements: List[ElementInDB]
    connections: List[ConnectionInDB]
    services: List[ServiceInDB]
    SI: SIConfig
    Span: SpanConfig
    simulation_config: SimulationConfig

    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
    }


# --- Import/Export Models ---

class NetworkImport(BaseModel):
    network_name: str
    elements: List[ElementCreate] = Field(default_factory=list)
    connections: List[ConnectionCreate] = Field(default_factory=list)
    services: List[ServiceCreate] = Field(default_factory=list)
    SI: SIConfig = Field(default_factory=SIConfig, alias="SI")
    Span: SpanConfig = Field(default_factory=SpanConfig, alias="Span")
    simulation_config: SimulationConfig = Field(default_factory=SimulationConfig)


class SubTopologyImport(BaseModel):
    elements: List[ElementCreate]
    connections: List[ConnectionCreate]
    strategy: Literal["generate_new_id", "error"] = "generate_new_id"
