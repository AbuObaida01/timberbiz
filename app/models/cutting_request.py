from sqlalchemy import Column, Integer, String, Float, Text, DateTime, ForeignKey, Numeric, func
from sqlalchemy.orm import relationship
from app.database import Base

class CuttingRequest(Base):
    __tablename__ = "cutting_requests"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Wood specifications
    wood_type = Column(String(100), nullable=False)
    length_feet = Column(Float, nullable=False)
    width_feet = Column(Float, nullable=False)
    thickness_inches = Column(Float, nullable=False)
    num_planks = Column(Integer, nullable=False)
    purpose = Column(String(100), nullable=True)
    special_instructions = Column(Text, nullable=True)
    preferred_date = Column(String(50), nullable=True)
    contact_phone = Column(String(15), nullable=False)

    # Admin fields
    quoted_price = Column(Numeric(10, 2), nullable=True)
    rejection_reason = Column(Text, nullable=True)
    admin_notes = Column(Text, nullable=True)

    # Payment fields
    razorpay_order_id = Column(String, nullable=True)
    razorpay_payment_id = Column(String, nullable=True)

    # Status
    status = Column(String(30), default="pending")

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    user = relationship("User", backref="cutting_requests")