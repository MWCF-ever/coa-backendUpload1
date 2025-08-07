from sqlalchemy import create_engine, MetaData
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import CreateSchema
from sqlalchemy.exc import ProgrammingError

from .config import settings

# Create engine
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    echo=settings.DEBUG
)

# Create schema if not exists
try:
    with engine.begin() as conn:
        conn.execute(CreateSchema(settings.DB_SCHEMA, if_not_exists=True))
except ProgrammingError:
    # Schema might already exist
    pass

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
metadata = MetaData(schema=settings.DB_SCHEMA)
Base = declarative_base(metadata=metadata)

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()