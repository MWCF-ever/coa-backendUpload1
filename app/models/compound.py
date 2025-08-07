from sqlalchemy import Column, String, DateTime, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

from ..database import Base


class Compound(Base):
    __tablename__ = "compounds"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    templates = relationship("Template", back_populates="compound", cascade="all, delete-orphan")
    documents = relationship("COADocument", back_populates="compound", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Compound(code={self.code}, name={self.name})>"