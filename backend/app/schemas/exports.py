from __future__ import annotations
import uuid
import os
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, computed_field


class ExportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    model_run_id: Optional[uuid.UUID] = None
    export_type: str
    file_path: Optional[str] = None
    created_at: datetime

    @computed_field
    @property
    def format(self) -> str:
        return self.export_type

    @computed_field
    @property
    def filename(self) -> Optional[str]:
        if self.file_path:
            return os.path.basename(self.file_path)
        return None

    @computed_field
    @property
    def size_bytes(self) -> Optional[int]:
        if self.file_path and os.path.exists(self.file_path):
            try:
                return os.path.getsize(self.file_path)
            except OSError:
                return None
        return None

    @computed_field
    @property
    def download_url(self) -> str:
        return f"/api/exports/{self.id}/download"


class ExportCreateRequest(BaseModel):
    model_run_id: uuid.UUID
    top_n: Optional[int] = None


class ExportDispatchRequest(BaseModel):
    """Frontend-facing shape: dispatches to csv or excel by format field."""
    format: str  # 'csv' or 'xlsx'
    model_run_id: uuid.UUID
    top_n: Optional[int] = None
    pool_config_id: Optional[uuid.UUID] = None  # accepted but not used
