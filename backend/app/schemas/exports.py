from __future__ import annotations
import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class ExportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    model_run_id: Optional[uuid.UUID] = None
    export_type: str
    file_path: Optional[str] = None
    created_at: datetime


class ExportCreateRequest(BaseModel):
    model_run_id: uuid.UUID
    top_n: Optional[int] = None
