from sqlalchemy import Column, Integer, String, Float, Text, DateTime, ForeignKey, Numeric, func
from sqlalchemy.orm import relationship
from app.database import Base

class Tree(Base):
    __tablename__ = "trees"

    id = Column(Integer, primary_key=True, index=True)
    uploader_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    price = Column(Numeric(10, 2), nullable=False)
    status = Column(String(20), default="pending")

    # GPS
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)

    # Structured address — NEW
    village_city = Column(String(100), nullable=True)
    district = Column(String(100), nullable=True)
    state = Column(String(100), nullable=True)
    pincode = Column(String(10), nullable=True)
    full_address = Column(String(300), nullable=True)

    created_at = Column(DateTime, server_default=func.now())

    uploader = relationship("User", backref="trees")
    images = relationship("TreeImage", backref="tree")


class TreeImage(Base):
    __tablename__ = "tree_images"

    id = Column(Integer, primary_key=True, index=True)
    tree_id = Column(Integer, ForeignKey("trees.id"), nullable=False)
    image_url = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=func.now())