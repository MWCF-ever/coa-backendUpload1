from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List, Dict
from uuid import UUID
from ..models.template import RegionEnum


class TemplateBase(BaseModel):
    compound_id: UUID
    region: RegionEnum
    template_content: str = Field(..., min_length=1)
    field_mapping: Optional[Dict[str, str]] = None


class TemplateCreate(TemplateBase):
    pass


class TemplateUpdate(BaseModel):
    template_content: Optional[str] = Field(None, min_length=1)
    field_mapping: Optional[Dict[str, str]] = None


class TemplateInDB(TemplateBase):
    id: UUID
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class TemplateResponse(TemplateInDB):
    pass


class TemplateListResponse(BaseModel):
    success: bool = True
    data: List[TemplateResponse]
    total: int
    message: Optional[str] = None