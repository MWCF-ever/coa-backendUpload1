"""
Initialize default data for COA processor
"""
import asyncio
from sqlalchemy.orm import Session
from app.database import SessionLocal, engine, Base
from app.models import Compound, Template, RegionEnum
from app.config import settings
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def init_database():
    """Create all tables"""
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created")


def create_default_compounds(db: Session):
    """Create default compounds"""
    compounds_data = [
        {
            "code": "BGB-21447",
            "name": "BGB-21447 Compound",
            "description": "BeiGene compound BGB-21447 for COA processing"
        },
        {
            "code": "BGB-16673",
            "name": "BGB-16673 Compound",
            "description": "BeiGene compound BGB-16673 for COA processing"
        },
        {
            "code": "BGB-43395",
            "name": "BGB-43395 Compound",
            "description": "BeiGene compound BGB-43395 for COA processing"
        }
    ]
    
    created_compounds = []
    for data in compounds_data:
        existing = db.query(Compound).filter(Compound.code == data["code"]).first()
        if not existing:
            compound = Compound(**data)
            db.add(compound)
            created_compounds.append(compound)
            logger.info(f"Created compound: {data['code']}")
        else:
            logger.info(f"Compound already exists: {data['code']}")
            created_compounds.append(existing)
    
    db.commit()
    return created_compounds


def create_default_templates(db: Session, compounds):
    """Create default templates for each compound and region"""
    template_content = {
        "CN": """【分析证书】
化合物编号：{compound_code}
批号：{lot_number}
生产商：{manufacturer}
储存条件：{storage_condition}

检测项目：
- 外观：符合标准
- 纯度：≥98%
- 水分：≤0.5%

结论：合格""",
        
        "EU": """CERTIFICATE OF ANALYSIS
Compound: {compound_code}
Lot Number: {lot_number}
Manufacturer: {manufacturer}
Storage Condition: {storage_condition}

Test Results:
- Appearance: Conforms
- Purity: ≥98%
- Water Content: ≤0.5%

Conclusion: Pass""",
        
        "US": """CERTIFICATE OF ANALYSIS
Product Code: {compound_code}
Batch/Lot No.: {lot_number}
Manufactured by: {manufacturer}
Storage Requirements: {storage_condition}

Analysis Results:
- Physical Appearance: Meets specifications
- Assay (HPLC): ≥98.0%
- Moisture Content: ≤0.5%

Quality Status: APPROVED"""
    }
    
    for compound in compounds:
        for region in RegionEnum:
            existing = db.query(Template).filter(
                Template.compound_id == compound.id,
                Template.region == region
            ).first()
            
            if not existing:
                template = Template(
                    compound_id=compound.id,
                    region=region,
                    template_content=template_content[region.value],
                    field_mapping={
                        "compound_code": "{compound_code}",
                        "lot_number": "{lot_number}",
                        "manufacturer": "{manufacturer}",
                        "storage_condition": "{storage_condition}"
                    }
                )
                db.add(template)
                logger.info(f"Created template for {compound.code} - {region.value}")
            else:
                logger.info(f"Template already exists for {compound.code} - {region.value}")
    
    db.commit()


def main():
    """Main initialization function"""
    logger.info("Starting COA processor data initialization...")
    
    # Create database tables
    init_database()
    
    # Create session
    db = SessionLocal()
    
    try:
        # Create default compounds
        compounds = create_default_compounds(db)
        
        # Create default templates
        create_default_templates(db, compounds)
        
        logger.info("Data initialization completed successfully!")
        
    except Exception as e:
        logger.error(f"Error during initialization: {str(e)}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()