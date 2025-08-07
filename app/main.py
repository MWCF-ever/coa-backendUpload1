# app/main.py - 修复307重定向问题
from fastapi import FastAPI, Request, Depends
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import logging

from .config import settings
from .database import engine, Base
from .api.v1 import compounds, templates, documents, health
from .auth.middleware import AuthLoggingMiddleware, require_authentication, optional_authentication, User

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle application lifecycle events"""
    # Startup
    logger.info("Starting up COA Document Processor API with SSO Authentication...")
    
    # Create database tables
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables created/verified")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
    
    # 验证认证配置
    logger.info("Authentication configuration:")
    logger.info(f"  - Tenant ID: 7dbc552d-50d7-4396-aeb9-04d0d393261b")
    logger.info(f"  - Client ID: 244a9262-04ff-4f5b-8958-2eeb0cedb928")
    logger.info(f"  - Debug mode: {settings.DEBUG}")
    
    yield
    
    # Shutdown
    logger.info("Shutting down...")

# Create FastAPI app
app = FastAPI(
    title=settings.APP_NAME + " (SSO Enabled)",
    version=settings.APP_VERSION,
    openapi_url="/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
    description="COA Document Processor API with Azure AD SSO Authentication",
    # 禁用自动重定向
    redirect_slashes=False
)

# Add authentication logging middleware
app.add_middleware(AuthLoggingMiddleware)

# 请求头修复中间件 - 处理APISIX转发
@app.middleware("http")
async def fix_forwarded_headers(request: Request, call_next):
    # 修复APISIX转发的协议问题
    forwarded_proto = request.headers.get("x-forwarded-proto", "https")
    if forwarded_proto == "https" and "location" in request.headers:
        # 确保重定向使用HTTPS
        location = request.headers.get("location", "")
        if location.startswith("http://"):
            request.headers._list = [
                (k, v) if k != b"location" else (k, location.replace("http://", "https://", 1).encode())
                for k, v in request.headers._list
            ]
    
    # 记录请求
    logger.info(f"📨 {request.method} {request.url.path} from {request.client.host if request.client else 'unknown'}")
    
    # 检查认证头
    auth_header = request.headers.get("authorization")
    if auth_header:
        logger.info(f"🔐 Request includes Authorization header")
    
    response = await call_next(request)
    
    # 修复重定向响应
    if response.status_code == 307:
        location = response.headers.get("location", "")
        if location.startswith("http://service-"):
            # 替换内部服务地址为正确的HTTPS地址
            new_location = location.replace("http://service-aimta-server", "https://beone-d.beigenecorp.net")
            response.headers["location"] = new_location
    
    logger.info(f"📤 Response: {response.status_code}")
    
    return response

# 健康检查路由 - 明确指定路径，避免重定向
app.include_router(
    health.router,
    prefix="/health",
    tags=["health"]
)

# 需要认证的路由
app.include_router(
    compounds.router,
    prefix="/compounds", 
    tags=["compounds"],
    dependencies=[Depends(require_authentication)]
)

app.include_router(
    templates.router,
    prefix="/templates",
    tags=["templates"],
    dependencies=[Depends(require_authentication)]
)

app.include_router(
    documents.router,
    prefix="/documents",
    tags=["documents"],
    dependencies=[Depends(require_authentication)]
)

# Root endpoint
@app.get("/", include_in_schema=False)
async def root(request: Request, user: User = Depends(optional_authentication)):
    return {
        "message": "COA Document Processor API (SSO Enabled)",
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "health": "/health",
        "authentication": {
            "enabled": True,
            "type": "Azure AD SSO",
            "tenant_id": "7dbc552d-50d7-4396-aeb9-04d0d393261b",
            "client_id": "244a9262-04ff-4f5b-8958-2eeb0cedb928"
        },
        "user_info": {
            "authenticated": user is not None,
            "name": user.name if user else None,
            "email": user.email if user else None,
            "roles": user.roles if user else []
        } if user else {"authenticated": False}
    }

# 认证状态检查端点 - 避免路径冲突
@app.get("/auth/status", tags=["auth"])
async def check_auth_status(user: User = Depends(optional_authentication)):
    """检查认证状态"""
    if user:
        return {
            "authenticated": True,
            "user": {
                "id": user.id,
                "name": user.name,
                "email": user.email,
                "roles": user.roles
            }
        }
    else:
        return {
            "authenticated": False,
            "message": "No valid authentication token provided"
        }

# 连接测试端点
@app.get("/test-connection", tags=["test"])
async def test_connection_authenticated(
    request: Request, 
    user: User = Depends(require_authentication)
):
    """需要认证的连接测试端点"""
    return {
        "status": "connected",
        "message": "API连接正常 (已认证)",
        "api_version": settings.APP_VERSION,
        "user_info": {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "roles": user.roles,
            "tenant_id": user.tenant_id
        }
    }

# 用户信息端点
@app.get("/user/me", tags=["user"])
async def get_current_user_info(user: User = Depends(require_authentication)):
    """获取当前用户信息"""
    return {
        "success": True,
        "data": {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "roles": user.roles,
            "groups": user.groups,
            "tenant_id": user.tenant_id,
            "app_id": user.app_id
        }
    }

# Exception handlers
@app.exception_handler(404)
async def not_found_handler(request, exc):
    return JSONResponse(
        {
            "detail": "Resource not found",
            "status_code": 404,
            "path": str(request.url.path)
        },
        status_code=404
    )

@app.exception_handler(401)
async def unauthorized_handler(request: Request, exc):
    logger.warning(f"Unauthorized access attempt: {request.url}")
    return JSONResponse(
        {
            "detail": "Authentication required",
            "status_code": 401,
            "auth_info": {
                "type": "Bearer",
                "description": "Please provide a valid Azure AD access token"
            }
        },
        status_code=401,
        headers={
            "WWW-Authenticate": "Bearer"
        }
    )

@app.exception_handler(403)
async def forbidden_handler(request: Request, exc):
    logger.warning(f"Forbidden access attempt: {request.url}")
    return JSONResponse(
        {
            "detail": "Access forbidden",
            "status_code": 403
        },
        status_code=403
    )

@app.exception_handler(500)
async def internal_error_handler(request: Request, exc):
    logger.error(f"Internal error on {request.url}: {exc}")
    
    return JSONResponse({
        "detail": "Internal server error",
        "status_code": 500
    }, status_code=500)