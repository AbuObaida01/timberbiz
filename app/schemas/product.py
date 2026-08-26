from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from decimal import Decimal


class ProductCreate(BaseModel):
    name: str
    category: Optional[str] = None
    price: Decimal
    description: Optional[str] = None
    stock: int = 0
    image_url: Optional[str] = None


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    price: Optional[Decimal] = None
    description: Optional[str] = None
    stock: Optional[int] = None
    image_url: Optional[str] = None


class ProductResponse(BaseModel):
    id: int
    name: str
    category: Optional[str]
    price: Decimal
    description: Optional[str]
    stock: int
    image_url: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True