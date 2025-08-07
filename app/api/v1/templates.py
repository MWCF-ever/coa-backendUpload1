from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Optional
from uuid import UUID

from ...database import get_db
from ...models.template import Template
from ...schemas.template import (
    TemplateCreate,
    TemplateUpdate,
    TemplateResponse,
    TemplateListResponse
)

router = APIRouter()


@router.get("", response_model=TemplateListResponse)
async def get_templates(
    compound_id: Optional[UUID] = Query(None),
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """Get all templates, optionally filtered by compound"""
    query = db.query(Template)
    
    if compound_id:
        query = query.filter(Template.compound_id == compound_id)
    
    templates = query.offset(skip).limit(limit).all()
    total = query.count()
    
    return TemplateListResponse(
        data=templates,
        total=total
    )


@router.get("/{template_id}", response_model=TemplateResponse)
async def get_template(
    template_id: UUID,
    db: Session = Depends(get_db)
):
    """Get a specific template by ID"""
    template = db.query(Template).filter(Template.id == template_id).first()
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template with id {template_id} not found"
        )
    return template


@router.post("", response_model=TemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_template(
    template: TemplateCreate,
    db: Session = Depends(get_db)
):
    """Create a new template"""
    # Check if template for compound and region already exists
    existing = db.query(Template).filter(
        Template.compound_id == template.compound_id,
        Template.region == template.region
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Template for compound {template.compound_id} and region {template.region} already exists"
        )
    
    db_template = Template(**template.dict())
    db.add(db_template)
    db.commit()
    db.refresh(db_template)
    
    return db_template


@router.put("/{template_id}", response_model=TemplateResponse)
async def update_template(
    template_id: UUID,
    template_update: TemplateUpdate,
    db: Session = Depends(get_db)
):
    """Update a template"""
    template = db.query(Template).filter(Template.id == template_id).first()
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template with id {template_id} not found"
        )
    
    # Update fields
    update_data = template_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(template, field, value)
    
    db.commit()
    db.refresh(template)
    
    return template


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    template_id: UUID,
    db: Session = Depends(get_db)
):
    """Delete a template"""
    template = db.query(Template).filter(Template.id == template_id).first()
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template with id {template_id} not found"
        )
    
    db.delete(template)
    db.commit()
    
    return None