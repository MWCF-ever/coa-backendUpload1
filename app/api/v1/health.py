from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime
import os

from ...database import get_db
from ...config import settings

router = APIRouter()

# 注意：不要在路径末尾加斜杠
@router.get("", status_code=status.HTTP_200_OK)
async def health_check():
    """Basic health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION
    }

@router.get("/ready", status_code=status.HTTP_200_OK)
async def readiness_check(db: Session = Depends(get_db)):
    """Check if the service is ready to handle requests"""
    try:
        # Check database connection
        db.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception as e:
        db_status = f"error: {str(e)}"
        return {
            "status": "not ready",
            "database": db_status
        }
    
    # Check upload directory
    upload_dir_exists = os.path.exists(settings.UPLOAD_DIR)
    upload_dir_writable = os.access(settings.UPLOAD_DIR, os.W_OK) if upload_dir_exists else False
    
    # Check AI service configuration
    ai_config = {}
    if settings.USE_AZURE_OPENAI:
        ai_config = {
            "type": "Azure OpenAI",
            "configured": bool(settings.AZURE_OPENAI_API_KEY),
            "endpoint": settings.AZURE_OPENAI_BASE_URL,
            "deployment": settings.AZURE_OPENAI_DEPLOYMENT_NAME,
            "api_version": settings.AZURE_OPENAI_API_VERSION
        }
    else:
        ai_config = {
            "type": "OpenAI",
            "configured": bool(settings.OPENAI_API_KEY),
            "model": settings.OPENAI_MODEL
        }
    
    return {
        "status": "ready",
        "timestamp": datetime.utcnow().isoformat(),
        "checks": {
            "database": db_status,
            "upload_directory": {
                "exists": upload_dir_exists,
                "writable": upload_dir_writable
            },
            "ai_service": ai_config
        }
    }

@router.get("/debug/processing-status", status_code=status.HTTP_200_OK)
async def debug_processing_status():
    """调试 ProcessingStatus 枚举值 - 临时端点"""
    try:
        from ...models.document import ProcessingStatus
        
        # 收集枚举信息
        enum_info = {}
        all_lowercase = True
        database_compatible = True
        allowed_values = ['pending', 'processing', 'completed', 'failed']
        
        for status in ProcessingStatus:
            value = status.value
            is_lowercase = value.islower()
            is_compatible = value in allowed_values
            
            enum_info[status.name] = {
                "value": value,
                "is_lowercase": is_lowercase,
                "database_compatible": is_compatible,
                "type": str(type(value))
            }
            
            if not is_lowercase:
                all_lowercase = False
            if not is_compatible:
                database_compatible = False
        
        return {
            "status": "success",
            "timestamp": datetime.utcnow().isoformat(),
            "enum_values": enum_info,
            "summary": {
                "all_lowercase": all_lowercase,
                "database_compatible": database_compatible,
                "total_statuses": len(enum_info)
            },
            "database_constraint": {
                "expected_values": allowed_values,
                "constraint_type": "CHECK (processing_status IN ('pending', 'processing', 'completed', 'failed'))"
            },
            "recommendations": {
                "problem_detected": not (all_lowercase and database_compatible),
                "fix_needed": "Enum values must be lowercase to match database constraint" if not all_lowercase else None
            }
        }
        
    except Exception as e:
        import traceback
        return {
            "status": "error",
            "error": str(e),
            "traceback": traceback.format_exc(),
            "timestamp": datetime.utcnow().isoformat()
        }

@router.get("/live", status_code=status.HTTP_200_OK)
async def liveness_check():
    """Simple liveness check for container orchestration"""
    return {"status": "alive"}
