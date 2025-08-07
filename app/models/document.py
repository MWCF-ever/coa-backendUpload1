from sqlalchemy import Column, String, DateTime, ForeignKey, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
import enum

from ..database import Base


class ProcessingStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class COADocument(Base):
    __tablename__ = "coa_documents"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    compound_id = Column(UUID(as_uuid=True), ForeignKey("compounds.id"), nullable=False)
    filename = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    file_size = Column(String(50), nullable=True)
    processing_status = Column(
        Enum(ProcessingStatus), 
        default=ProcessingStatus.PENDING.value, 
        nullable=False
    )
    error_message = Column(String(500), nullable=True)
    uploaded_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    processed_at = Column(DateTime, nullable=True)
    
    # Relationships
    compound = relationship("Compound", back_populates="documents")
    extracted_data = relationship("ExtractedData", back_populates="document", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<COADocument(filename={self.filename}, status={self.processing_status})>"