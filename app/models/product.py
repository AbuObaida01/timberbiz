from sqlalchemy import Column, Integer, String, Text, Numeric, DateTime, func, CheckConstraint
from app.database import Base
from datetime import datetime
class Product(Base):
    __tablename__="products"

    __table_args__=(
        CheckConstraint('stock>=0', name='check_stock_non_negative'),
        CheckConstraint('price>=0', name='check_price_non_negative'),
    )
    id=Column(Integer, primary_key=True, index=True)
    name=Column(String(200),nullable=False, index=True)
    category=Column(String(100), nullable=True,index=True)
    price=Column(Numeric(10,2), nullable=False)
    description=Column(Text, nullable=True)
    stock=Column(Integer, default=0, nullable=False)
    image_url=Column(Text, nullable=True)
    # NEW — units currently reserved during active checkouts
    reserved_quantity = Column(Integer, default=0)

    # NEW — when reservation expires (15 min from checkout start)
    reservation_expires_at = Column(DateTime, nullable=True)
    created_at=Column(DateTime, server_default=func.now())
    updated_at=Column(DateTime, onupdate=func.now())

    def available_stock(self):
        """
        Real available stock = total stock minus active reservations.
        If reservation has expired, don't count it.
        """
        if (self.reservation_expires_at and
            datetime.utcnow() > self.reservation_expires_at):
            return self.stock  # Reservation expired — full stock available
        return max(0, self.stock - (self.reserved_quantity or 0))