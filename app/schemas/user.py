from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime

class UserRegister(BaseModel):
    name: str=Field(min_length=3, max_length=100)
    email:EmailStr
    phone: Optional[str]=Field(default=None, max_length=15)
    password: str=Field(min_length=8)
    latitude:Optional[float]=None
    longitude:Optional[float]=None

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    id:int
    name:str
    email:str
    phone:Optional[str]
    role:str
    latitude:Optional[float]
    longitude: Optional[float]
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes=True

class TokenResponse(BaseModel):
    access_token: str
    token_type:str="bearer"
    user:UserResponse

class LocationUpdate(BaseModel):
    latitude: float
    longitude: float