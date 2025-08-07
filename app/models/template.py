from sqlalchemy import Column, String, DateTime, Text, ForeignKey, JSON, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
import enum

from ..database import Base


class RegionEnum(str, enum.Enum):
    CN = "CN"
    EU = "EU"
    US = "US"


class Template(Base):
    __tablename__ = "templates"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    compound_id = Column(UUID(as_uuid=True), ForeignKey("compounds.id"), nullable=False)
    region = Column(Enum(RegionEnum), nullable=False)
    template_content = Column(Text, nullable=False)
    field_mapping = Column(JSON, nullable=True)  # Maps field names to template placeholders
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    compound = relationship("Compound", back_populates="templates")
    
    def __repr__(self):
        return f"<Template(compound_id={self.compound_id}, region={self.region})>"