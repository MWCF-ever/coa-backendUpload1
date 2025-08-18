from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List
from uuid import UUID
from ..models.document import ProcessingStatus


class DocumentBase(BaseModel):
    compound_id: UUID
    filename: str


class DocumentUploadResponse(BaseModel):
    documentId: UUID = Field(..., alias="document_id")
    filename: str
    status: ProcessingStatus
    
    class Config:
        populate_by_name = True


class DocumentInDB(DocumentBase):
    id: UUID
    file_path: str
    file_size: Optional[str] = None
    processing_status: ProcessingStatus
    error_message: Optional[str] = None
    uploaded_at: datetime
    processed_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class DocumentResponse(DocumentInDB):
    pass


class DocumentProcessRequest(BaseModel):
    document_id: UUID


class DirectoryProcessRequest(BaseModel):
    """Request model for processing PDF files in a directory"""
    compound_id: str = Field(..., description="Compound ID")
    template_id: str = Field(..., description="Template ID") 
    directory_path: Optional[str] = Field(None, description="Optional directory path")
    force_reprocess: Optional[bool] = Field(False, description="Force reprocess files")
    class Config:
        extra = "forbid"  # 不允许额外字段，更严格的验证
        schema_extra = {
            "example": {
                "compound_id": "10842aa6-546f-4f70-a410-ca572ec5140f",
                "template_id": "e5c8754a-bb1e-453b-9a31-b2a8179f4cc6",
                "force_reprocess": False
            }
        }    


class VeevaProcessRequest(BaseModel):
    """Request model for processing documents from Veeva Vault"""
    compound_id: str = Field(..., description="Compound ID")
    template_id: str = Field(..., description="Template ID")
    document_ids: List[str] = Field(
        ..., 
        description="List of Veeva document IDs (e.g., VV-QDOC-25441)",
        min_items=1
    )
    force_reprocess: Optional[bool] = Field(False, description="Force reprocess even if cached")
    
    class Config:
        extra = "forbid"
        schema_extra = {
            "example": {
                "compound_id": "10842aa6-546f-4f70-a410-ca572ec5140f",
                "template_id": "e5c8754a-bb1e-453b-9a31-b2a8179f4cc6",
                "document_ids": ["VV-QDOC-25441", "VV-QDOC-25442", "VV-QDOC-25443"],
                "force_reprocess": False
            }
        }


class HybridProcessRequest(BaseModel):
    """Request model for hybrid processing (local or Veeva)"""
    compound_id: str = Field(..., description="Compound ID")
    template_id: str = Field(..., description="Template ID")
    source: str = Field(
        "auto", 
        description="Processing source: 'local', 'veeva', or 'auto'",
        pattern="^(local|veeva|auto)$"
    )
    document_ids: Optional[List[str]] = Field(
        None,
        description="Veeva document IDs (required if source is 'veeva')"
    )
    directory_path: Optional[str] = Field(
        None,
        description="Local directory path (required if source is 'local')"
    )
    force_reprocess: Optional[bool] = Field(False, description="Force reprocess")
    
    class Config:
        extra = "forbid"
        schema_extra = {
            "example": {
                "compound_id": "10842aa6-546f-4f70-a410-ca572ec5140f",
                "template_id": "e5c8754a-bb1e-453b-9a31-b2a8179f4cc6",
                "source": "veeva",
                "document_ids": ["VV-QUAL-001851", "VV-QUAL-001852", "VV-QUAL-001853", "VV-QUAL-001854", "VV-QUAL-001855", "VV-QUAL-001856"],
                "force_reprocess": False
            }
        }


class DocumentListResponse(BaseModel):
    success: bool = True
    data: List[DocumentResponse]
    total: int
    message: Optional[str] = None