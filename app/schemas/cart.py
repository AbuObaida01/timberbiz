from pydantic import BaseModel
from typing import Optional
from decimal import Decimal


class CartAddItem(BaseModel):
    product_id: int
    quantity: int = 1


class CartUpdateItem(BaseModel):
    quantity: int


class CartItemResponse(BaseModel):
    id: int
    product_id: int
    quantity: int
    product_name: str
    product_price: Decimal
    product_image: Optional[str]
    item_total: Decimal

    class Config:
        from_attributes = True


class CartSummaryResponse(BaseModel):
    items: list[CartItemResponse]
    total_items: int
    total_price: Decimal