from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from decimal import Decimal


class TreeCreate(BaseModel):
    title: str
    description: Optional[str] = None
    price: Decimal
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class TreeImageResponse(BaseModel):
    id: int
    image_url: str
    created_at: datetime

    class Config:
        from_attributes = True


# What public sees — NO sensitive data
class TreePublicResponse(BaseModel):
    id: int
    title: str
    description: Optional[str]
    status: str
    created_at: datetime
    images: List[TreeImageResponse] = []

    class Config:
        from_attributes = True


# What admin and uploader see — FULL data
class TreePrivateResponse(BaseModel):
    id: int
    uploader_id: int
    title: str
    description: Optional[str]
    price: Decimal
    status: str
    latitude: Optional[float]
    longitude: Optional[float]
    created_at: datetime
    images: List[TreeImageResponse] = []

    # Uploader contact info
    uploader_name: Optional[str] = None
    uploader_phone: Optional[str] = None
    uploader_email: Optional[str] = None

    class Config:
        from_attributes = True


class TreeStatusUpdate(BaseModel):
    status: str  # approved / rejected
    rejection_reason: Optional[str] = None