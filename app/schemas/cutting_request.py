from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from decimal import Decimal

# Customer submits this
class CuttingRequestCreate(BaseModel):
    wood_type: str
    length_feet: float
    width_feet: float
    thickness_inches: float
    num_planks: int
    purpose: Optional[str] = None
    special_instructions: Optional[str] = None
    preferred_date: Optional[str] = None
    contact_phone: str

# Admin sets price + confirms
class AdminQuoteRequest(BaseModel):
    quoted_price: Decimal
    admin_notes: Optional[str] = None

# Admin rejects
class AdminRejectRequest(BaseModel):
    rejection_reason: str

# Response shape
class CuttingRequestResponse(BaseModel):
    id: int
    user_id: int
    wood_type: str
    length_feet: float
    width_feet: float
    thickness_inches: float
    num_planks: int
    purpose: Optional[str]
    special_instructions: Optional[str]
    preferred_date: Optional[str]
    contact_phone: str
    quoted_price: Optional[Decimal]
    rejection_reason: Optional[str]
    admin_notes: Optional[str]
    razorpay_order_id: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True