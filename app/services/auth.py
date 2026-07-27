from datetime import datetime, timedelta 
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from app.database import get_db
from sqlalchemy.orm import Session
from app.models.user import User
from app.config import settings

#TO tell fastapi where to look for the token
oauth2_scheme=OAuth2PasswordBearer(tokenUrl="/auth/login/swagger")

#bcrypt context for hashing password
pwd_context=CryptContext(schemes=["bcrypt"], deprecated="auto")

#password utilities
def hash_password(password: str)->str:
    return pwd_context.hash(password)
def verify_password(plain: str, hashed:str)->bool:
    return pwd_context.verify(plain, hashed)

#JWT Utilities
def create_access_token(data: dict)->str:
    """Create JWT token with expiry"""
    to_encode=data.copy()
    expire=datetime.utcnow()+timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    to_encode.update({"exp": expire})
    return jwt.encode(
        to_encode,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM
    )

def decode_token(token:str)->dict:
    """Decode and verify a JWT token"""
    try:
        payload=jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM]
        )
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate":"Bearer"},
        )

#Dependency Functions

def get_current_user(
        token: str=Depends(oauth2_scheme),
        db: Session=Depends(get_db)
)->User:
    """Extract user form JWT token
    Use this as a dependency on any protected route
    """

    payload=decode_token(token)
    user_id: int = payload.get("user_id")

    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload"
        )
    user=db.query(User).filter(User.id==user_id).first()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User Not Found"
        )
    return user

def get_admin_user(
        current_user: User=Depends(get_current_user)
)->User:
    """
    Only allow admin user
    Use this as a dependency on any admin-only route
    """
    if current_user.role!="admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    from app.config import settings
    allowed_admins=[settings.ADMIN_EMAIL_1, settings.ADMIN_EMAIL_2]

    if current_user.email not in allowed_admins:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorised as admin"
        )

    return current_user