# app/auth/middleware.py
from typing import Optional, Dict, Any
from fastapi import HTTPException, status, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
import requests
from datetime import datetime, timedelta
import logging
from functools import wraps
import asyncio

from ..config import settings

logger = logging.getLogger(__name__)

# JWT配置
JWT_ALGORITHMS = ["RS256"]
MICROSOFT_KEYS_URL = "https://login.microsoftonline.com/common/discovery/v2.0/keys"
TENANT_ID = "7dbc552d-50d7-4396-aeb9-04d0d393261b"
CLIENT_ID = "244a9262-04ff-4f5b-8958-2eeb0cedb928"

# 缓存Microsoft公钥
_microsoft_keys_cache = {
    "keys": None,
    "expires_at": None
}

security = HTTPBearer(auto_error=False)

class AuthenticationError(Exception):
    """认证错误"""
    pass

class AuthorizationError(Exception):
    """授权错误"""
    pass

async def get_microsoft_public_keys() -> Dict[str, Any]:
    """获取Microsoft公钥，带缓存"""
    global _microsoft_keys_cache
    
    # 检查缓存是否有效
    if (_microsoft_keys_cache["keys"] and 
        _microsoft_keys_cache["expires_at"] and 
        datetime.utcnow() < _microsoft_keys_cache["expires_at"]):
        return _microsoft_keys_cache["keys"]
    
    try:
        # 获取新的公钥
        response = requests.get(MICROSOFT_KEYS_URL, timeout=10)
        response.raise_for_status()
        
        keys_data = response.json()
        
        # 缓存1小时
        _microsoft_keys_cache["keys"] = keys_data
        _microsoft_keys_cache["expires_at"] = datetime.utcnow() + timedelta(hours=1)
        
        logger.info("Microsoft public keys refreshed")
        return keys_data
        
    except Exception as e:
        logger.error(f"Failed to fetch Microsoft public keys: {e}")
        # 如果缓存中有旧的keys，返回旧的
        if _microsoft_keys_cache["keys"]:
            logger.warning("Using cached Microsoft public keys")
            return _microsoft_keys_cache["keys"]
        raise AuthenticationError("Unable to fetch Microsoft public keys")

def find_key_by_kid(keys_data: Dict[str, Any], kid: str) -> Optional[Dict[str, Any]]:
    """根据kid查找对应的公钥"""
    for key in keys_data.get("keys", []):
        if key.get("kid") == kid:
            return key
    return None

async def verify_jwt_token(token: str) -> Dict[str, Any]:
    """验证JWT token并返回payload"""
    try:
        # 解码header获取kid
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")
        
        if not kid:
            raise AuthenticationError("Token missing 'kid' in header")
        
        # 获取Microsoft公钥
        keys_data = await get_microsoft_public_keys()
        key_data = find_key_by_kid(keys_data, kid)
        
        if not key_data:
            raise AuthenticationError(f"Unable to find key with kid: {kid}")
        
        # 构造公钥
        public_key = jwt.algorithms.RSAAlgorithm.from_jwk(key_data)
        
        # 验证token
        payload = jwt.decode(
            token,
            public_key,
            algorithms=JWT_ALGORITHMS,
            audience=CLIENT_ID,  # 验证audience
            issuer=f"https://login.microsoftonline.com/{TENANT_ID}/v2.0",  # 验证issuer
            options={
                "verify_signature": True,
                "verify_aud": True,
                "verify_iss": True,
                "verify_exp": True,
                "verify_nbf": True,
                "verify_iat": True,
            }
        )
        
        logger.info(f"Token verified successfully for user: {payload.get('preferred_username', 'unknown')}")
        return payload
        
    except jwt.ExpiredSignatureError:
        raise AuthenticationError("Token has expired")
    except jwt.InvalidAudienceError:
        raise AuthenticationError("Invalid token audience")
    except jwt.InvalidIssuerError:
        raise AuthenticationError("Invalid token issuer")
    except jwt.InvalidTokenError as e:
        raise AuthenticationError(f"Invalid token: {str(e)}")
    except Exception as e:
        logger.error(f"Token verification failed: {e}")
        raise AuthenticationError(f"Token verification failed: {str(e)}")

class User:
    """用户信息类"""
    def __init__(self, payload: Dict[str, Any]):
        self.id = payload.get("sub") or payload.get("oid")
        self.name = payload.get("name", "")
        self.email = payload.get("preferred_username") or payload.get("email", "")
        self.roles = payload.get("roles", [])
        self.groups = payload.get("groups", [])
        self.tenant_id = payload.get("tid")
        self.app_id = payload.get("aud")
        self.payload = payload
    
    def has_role(self, role: str) -> bool:
        """检查用户是否拥有指定角色"""
        return role in self.roles
    
    def has_any_role(self, roles: list) -> bool:
        """检查用户是否拥有任意一个指定角色"""
        return any(role in self.roles for role in roles)
    
    def is_in_group(self, group_id: str) -> bool:
        """检查用户是否在指定组中"""
        return group_id in self.groups

async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[User]:
    """获取当前用户（可选认证）"""
    if not credentials:
        return None
    
    try:
        payload = await verify_jwt_token(credentials.credentials)
        return User(payload)
    except AuthenticationError as e:
        logger.warning(f"Authentication failed: {e}")
        return None

async def require_authentication(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> User:
    """要求认证的依赖"""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    try:
        payload = await verify_jwt_token(credentials.credentials)
        return User(payload)
    except AuthenticationError as e:
        logger.warning(f"Authentication failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )

def require_roles(required_roles: list):
    """要求特定角色的装饰器"""
    def decorator(user: User = Depends(require_authentication)) -> User:
        if not user.has_any_role(required_roles):
            logger.warning(f"User {user.email} lacks required roles: {required_roles}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient privileges. Required roles: {required_roles}"
            )
        return user
    return decorator

def require_admin(user: User = Depends(require_authentication)) -> User:
    """要求管理员权限"""
    admin_roles = ["admin", "administrator", "Admin", "Administrator"]
    if not user.has_any_role(admin_roles):
        logger.warning(f"User {user.email} attempted admin action without privileges")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator privileges required"
        )
    return user

async def optional_authentication(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[User]:
    """可选认证，不会抛出错误"""
    try:
        if credentials:
            payload = await verify_jwt_token(credentials.credentials)
            return User(payload)
    except Exception as e:
        logger.debug(f"Optional authentication failed: {e}")
    
    return None

# 自定义中间件用于记录认证信息
class AuthLoggingMiddleware:
    def __init__(self, app):
        self.app = app
    
    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            request = Request(scope, receive)
            
            # 记录认证头信息（仅用于调试）
            auth_header = request.headers.get("authorization")
            if auth_header and settings.DEBUG:
                logger.debug(f"Request to {request.url.path} with auth header present")
            
            # 记录用户信息
            try:
                if auth_header and auth_header.startswith("Bearer "):
                    token = auth_header[7:]
                    payload = await verify_jwt_token(token)
                    user_info = f"{payload.get('preferred_username', 'unknown')} ({payload.get('name', 'N/A')})"
                    logger.info(f"Authenticated request: {request.method} {request.url.path} by {user_info}")
            except Exception:
                pass  # 忽略认证错误，让后续处理器处理
        
        await self.app(scope, receive, send)

# 辅助函数
def create_auth_response_headers(user: User) -> Dict[str, str]:
    """创建包含用户信息的响应头"""
    return {
        "X-User-ID": user.id or "",
        "X-User-Name": user.name or "",
        "X-User-Email": user.email or "",
    }

# 权限验证辅助函数
def check_document_access(user: User, document_compound_id: str) -> bool:
    """检查用户是否有访问特定文档的权限"""
    # 这里可以实现更复杂的权限逻辑
    # 目前简化为：认证用户都可以访问
    return True

def check_admin_access(user: User) -> bool:
    """检查管理员访问权限"""
    admin_roles = ["admin", "administrator", "Admin", "Administrator"]
    return user.has_any_role(admin_roles)

# 速率限制（简化版）
class RateLimiter:
    def __init__(self):
        self.requests = {}
    
    def is_allowed(self, user_id: str, limit: int = 100, window: int = 3600) -> bool:
        """检查是否允许请求"""
        now = datetime.utcnow()
        
        if user_id not in self.requests:
            self.requests[user_id] = []
        
        # 清理过期请求
        self.requests[user_id] = [
            req_time for req_time in self.requests[user_id]
            if (now - req_time).seconds < window
        ]
        
        # 检查是否超过限制
        if len(self.requests[user_id]) >= limit:
            return False
        
        # 记录当前请求
        self.requests[user_id].append(now)
        return True

# 全局速率限制实例
rate_limiter = RateLimiter()

def check_rate_limit(user: User, limit: int = 100) -> User:
    """检查速率限制"""
    if not rate_limiter.is_allowed(user.id, limit):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded"
        )
    return user