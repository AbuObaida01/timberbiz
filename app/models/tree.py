from sqlalchemy import Column, Integer, String, Float, Text, DateTime, ForeignKey, Numeric, func
from sqlalchemy.orm import relationship
from app.database import Base

class Tree(Base):
    __tablename__="trees"

    id=Column(Integer, primary_key=True, index=True)
    uploader_id=Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title=Column(String(200), nullable=False)
    description=Column(Text, nullable=True)
    price=Column(Numeric(10,2),nullable=False)
    status=Column(String(20),default="pending",nullable=False,index=True)
    latitude=Column(Float, index=True, nullable=True)
    longitude=Column(Float, index=True, nullable=True)
    # Structured address — NEW
    village_city = Column(String(100), nullable=True)
    district = Column(String(100), nullable=True)
    state = Column(String(100), nullable=True)
    pincode = Column(String(10), nullable=True)
    full_address = Column(String(300), nullable=True)
    created_at=Column(DateTime, server_default=func.now())
    updated_at=Column(DateTime, onupdate=func.now())

    uploader=relationship("User", back_populates="trees")
    images=relationship("TreeImage", backref="tree",cascade="all,delete")

class TreeImage(Base):
    __tablename__="tree_image"
    id=Column(Integer, primary_key=True, index=True)
    tree_id=Column(Integer,ForeignKey("trees.id"),nullable=False,index=True)
    image_url=Column(Text, nullable=False)
    created_at=Column(DateTime, server_default=func.now())