"""
API Dependencies
"""
from typing import Generator, Optional
from fastapi import Depends, HTTPException, status, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from jose import JWTError, jwt
from datetime import datetime, timedelta

from ..database import SessionLocal
from ..config import settings


# Security scheme for API documentation
security = HTTPBearer(auto_error=False)


def get_db() -> Generator:
    """
    Database dependency
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[dict]:
    """
    Get current user from JWT token (placeholder for future implementation)
    Currently returns None to allow unauthenticated access
    """
    # TODO: Implement JWT validation when authentication is added
    if not credentials:
        return None
    
    # Placeholder for JWT validation
    # try:
    #     payload = jwt.decode(
    #         credentials.credentials,
    #         settings.SECRET_KEY,
    #         algorithms=[settings.ALGORITHM]
    #     )
    #     return payload
    # except JWTError:
    #     raise HTTPException(
    #         status_code=status.HTTP_401_UNAUTHORIZED,
    #         detail="Could not validate credentials",
    #         headers={"WWW-Authenticate": "Bearer"},
    #     )
    
    return None


def require_auth(
    current_user: Optional[dict] = Depends(get_current_user)
) -> dict:
    """
    Require authentication for protected endpoints
    """
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return current_user


def get_api_key(
    x_api_key: Optional[str] = Header(None)
) -> Optional[str]:
    """
    Get API key from header (alternative authentication method)
    """
    return x_api_key


def verify_api_key(
    api_key: Optional[str] = Depends(get_api_key)
) -> Optional[str]:
    """
    Verify API key if provided
    """
    # TODO: Implement API key validation
    # For now, accept any non-empty API key in development
    if settings.DEBUG:
        return api_key
    
    if api_key and api_key != "expected-api-key":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key"
        )
    
    return api_key


class RateLimiter:
    """
    Simple rate limiter (placeholder for future implementation)
    """
    def __init__(self, calls: int = 10, period: int = 60):
        self.calls = calls
        self.period = period
        self.requests = {}
    
    def __call__(self, request_id: str = Depends(lambda: "default")) -> None:
        """
        Check rate limit
        """
        # TODO: Implement proper rate limiting with Redis
        # This is a simplified in-memory implementation
        now = datetime.now()
        
        if request_id not in self.requests:
            self.requests[request_id] = []
        
        # Clean old requests
        self.requests[request_id] = [
            req_time for req_time in self.requests[request_id]
            if (now - req_time).seconds < self.period
        ]
        
        if len(self.requests[request_id]) >= self.calls:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded"
            )
        
        self.requests[request_id].append(now)


# Create rate limiter instances
general_limiter = RateLimiter(calls=100, period=60)  # 100 calls per minute
upload_limiter = RateLimiter(calls=10, period=60)    # 10 uploads per minute


def get_pagination_params(
    skip: int = 0,
    limit: int = 100
) -> dict:
    """
    Common pagination parameters
    """
    if skip < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Skip value must be non-negative"
        )
    
    if limit <= 0 or limit > 1000:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Limit must be between 1 and 1000"
        )
    
    return {"skip": skip, "limit": limit}


def create_access_token(
    data: dict,
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    Create JWT access token (for future use)
    """
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    
    encoded_jwt = jwt.encode(
        to_encode,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM
    )
    
    return encoded_jwt


class PermissionChecker:
    """
    Check user permissions (placeholder for future implementation)
    """
    def __init__(self, required_permissions: list):
        self.required_permissions = required_permissions
    
    def __call__(
        self,
        current_user: Optional[dict] = Depends(get_current_user)
    ) -> bool:
        """
        Check if user has required permissions
        """
        if not current_user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required"
            )
        
        # TODO: Implement permission checking
        # user_permissions = current_user.get("permissions", [])
        # for permission in self.required_permissions:
        #     if permission not in user_permissions:
        #         raise HTTPException(
        #             status_code=status.HTTP_403_FORBIDDEN,
        #             detail="Insufficient permissions"
        #         )
        
        return True


# Permission checkers
can_upload = PermissionChecker(["document:upload"])
can_process = PermissionChecker(["document:process"])
can_manage_compounds = PermissionChecker(["compound:manage"])
can_manage_templates = PermissionChecker(["template:manage"])