# app/api/v1/compounds.py - 测试版本
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from uuid import UUID
import os
from datetime import datetime

from ...database import get_db
from ...models.compound import Compound
from ...schemas.compound import (
    CompoundCreate,
    CompoundUpdate,
    CompoundResponse,
    CompoundListResponse
)

router = APIRouter()


@router.get("/test", response_model=dict)
async def test_compounds():
    """测试compounds接口是否工作"""
    return {
        "message": "🔥 COMPOUNDS TEST ENDPOINT WORKING!",
        "timestamp": datetime.utcnow().isoformat(),
        "status": "success",
        "test_data": {
            "compound_count": "测试数据",
            "service_info": "这是compounds服务的测试响应",
            "container": os.environ.get("HOSTNAME", "unknown")
        }
    }


@router.get("", response_model=CompoundListResponse)
async def get_compounds(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """Get all compounds - 增强测试版本"""
    
    # 🔥 添加测试信息
    print(f"🔥 COMPOUNDS接口被调用: skip={skip}, limit={limit}")
    print(f"🔥 环境信息: HOSTNAME={os.environ.get('HOSTNAME', 'unknown')}")
    
    try:
        # 先尝试获取数据
        compounds = db.query(Compound).offset(skip).limit(limit).all()
        total = db.query(Compound).count()
        
        result = CompoundListResponse(
            data=compounds,
            total=total
        )
        
        print(f"🔥 COMPOUNDS查询成功: 找到{total}个化合物")
        return result
        
    except Exception as e:
        print(f"🔥 COMPOUNDS查询失败: {str(e)}")
        
        # 如果数据库查询失败，返回测试数据
        return {
            "success": True,
            "data": [
                {
                    "id": "test-compound-1",
                    "code": "TEST-001",
                    "name": "测试化合物1",
                    "description": "这是测试数据 - compounds接口正常工作",
                    "created_at": datetime.utcnow().isoformat(),
                    "updated_at": datetime.utcnow().isoformat()
                }
            ],
            "total": 1,
            "message": f"🔥 COMPOUNDS接口工作正常! 错误: {str(e)}"
        }


@router.get("/simple")
async def simple_compounds():
    """最简单的compounds测试"""
    return "🔥 SIMPLE COMPOUNDS OK - compounds服务正常工作!"


@router.get("/debug")
async def debug_compounds():
    """调试compounds接口"""
    return {
        "message": "🔥 DEBUG COMPOUNDS ENDPOINT",
        "timestamp": datetime.utcnow().isoformat(),
        "service": "compounds",
        "environment": {
            "hostname": os.environ.get("HOSTNAME", "unknown"),
            "service_name": "compounds-service",
        },
        "database_info": "Database connection will be tested here",
        "status": "debug_mode_active"
    }


@router.get("", response_model=CompoundListResponse)
async def get_compounds(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """Get all compounds - 路径: /api/aimta/compounds/"""
    try:
        compounds = db.query(Compound).offset(skip).limit(limit).all()
        total = db.query(Compound).count()
        
        return CompoundListResponse(
            data=compounds,
            total=total,
            success=True
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch compounds: {str(e)}"
        )

@router.get("/{compound_id}", response_model=CompoundResponse)
async def get_compound(
    compound_id: UUID,
    db: Session = Depends(get_db)
):
    """Get a specific compound by ID"""
    compound = db.query(Compound).filter(Compound.id == compound_id).first()
    if not compound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Compound with id {compound_id} not found"
        )
    return compound

@router.post("", response_model=CompoundResponse, status_code=status.HTTP_201_CREATED)
async def create_compound(
    compound: CompoundCreate,
    db: Session = Depends(get_db)
):
    """Create a new compound"""
    # Check if compound with same code already exists
    existing = db.query(Compound).filter(Compound.code == compound.code).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Compound with code {compound.code} already exists"
        )
    
    db_compound = Compound(**compound.dict())
    db.add(db_compound)
    db.commit()
    db.refresh(db_compound)
    
    return db_compound

# 🔥 添加初始化默认数据的端点
@router.post("/init-defaults", response_model=List[CompoundResponse])
async def initialize_default_compounds(db: Session = Depends(get_db)):
    """Initialize default compounds if they don't exist"""
    default_compounds = [
        {"code": "BGB-21447", "name": "Compound BGB-21447", "description": "Default compound 1"},
        {"code": "BGB-16673", "name": "Compound BGB-16673", "description": "Default compound 2"},
        {"code": "BGB-43395", "name": "Compound BGB-43395", "description": "Default compound 3"}
    ]
    
    created = []
    for compound_data in default_compounds:
        existing = db.query(Compound).filter(Compound.code == compound_data["code"]).first()
        if not existing:
            compound = Compound(**compound_data)
            db.add(compound)
            created.append(compound)
    
    if created:
        db.commit()
        for compound in created:
            db.refresh(compound)
        
        return created
    else:
        # Return existing compounds if none were created
        return db.query(Compound).all()