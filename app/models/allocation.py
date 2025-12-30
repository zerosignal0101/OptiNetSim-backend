from pydantic import BaseModel, Field
from typing import List, Literal, Union, Optional, Annotated

from app.models.defrag import DefragRequest


class KSPAllocationRequest(DefragRequest):
    service_max_bitrate: int
    num_channels: int

