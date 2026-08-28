from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from decimal import Decimal


class CheckoutRequest(BaseModel):
    # Optional: user can add delivery address at checkout
    delivery_address: Optional[str] = None
    delivery_phone: Optional[str] = None


class PaymentVerifyRequest(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


class OrderItemResponse(BaseModel):
    id: int
    product_id: int
    quantity: int
    price: Decimal
    product_name: Optional[str] = None

    class Config:
        from_attributes = True


class OrderResponse(BaseModel):
    id: int
    user_id: int
    total_amount: Decimal
    payment_status: str
    razorpay_order_id: Optional[str]
    delivery_address: Optional[str]
    delivery_phone: Optional[str]
    created_at: datetime
    items: List[OrderItemResponse] = []

    class Config:
        from_attributes = True