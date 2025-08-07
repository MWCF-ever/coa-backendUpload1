from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List
from uuid import UUID


class CompoundBase(BaseModel):
    code: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None


class CompoundCreate(CompoundBase):
    pass


class CompoundUpdate(BaseModel):
    code: Optional[str] = Field(None, min_length=1, max_length=50)
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None


class CompoundInDB(CompoundBase):
    id: UUID
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class CompoundResponse(CompoundInDB):
    pass


class CompoundListResponse(BaseModel):
    success: bool = True
    data: List[CompoundResponse]
    total: int
    message: Optional[str] = None