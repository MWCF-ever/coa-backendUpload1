from sqlalchemy import Column, String, DateTime, Float, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

from ..database import Base


class ExtractedData(Base):
    __tablename__ = "extracted_data"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("coa_documents.id"), nullable=False)
    field_name = Column(String(100), nullable=False)  # e.g., 'lot_number', 'manufacturer', 'storage_condition'
    field_value = Column(Text, nullable=False)
    confidence_score = Column(Float, default=0.0, nullable=False)
    original_text = Column(Text, nullable=True)  # Original text from PDF
    page_number = Column(String(10), nullable=True)
    bounding_box = Column(Text, nullable=True)  # JSON string of coordinates
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    document = relationship("COADocument", back_populates="extracted_data")
    
    def __repr__(self):
        return f"<ExtractedData(field_name={self.field_name}, confidence={self.confidence_score})>"