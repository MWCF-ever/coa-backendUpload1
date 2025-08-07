from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List
from uuid import UUID


class ExtractedDataBase(BaseModel):
    document_id: UUID
    field_name: str = Field(..., min_length=1, max_length=100)
    field_value: str
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    original_text: Optional[str] = None
    page_number: Optional[str] = None
    bounding_box: Optional[str] = None


class ExtractedDataCreate(ExtractedDataBase):
    pass


class ExtractedDataUpdate(BaseModel):
    field_value: Optional[str] = None
    confidence_score: Optional[float] = Field(None, ge=0.0, le=1.0)


class ExtractedDataInDB(ExtractedDataBase):
    id: UUID
    created_at: datetime
    
    class Config:
        from_attributes = True


class ExtractedDataResponse(ExtractedDataInDB):
    pass


class ProcessingResultResponse(BaseModel):
    success: bool = True
    documentId: UUID = Field(..., alias="document_id")
    extractedData: List[ExtractedDataResponse] = Field(..., alias="extracted_data")
    status: str
    message: Optional[str] = None
    
    class Config:
        populate_by_name = True


class ApiResponse(BaseModel):
    success: bool
    data: Optional[dict] = None
    error: Optional[str] = None
    message: Optional[str] = None