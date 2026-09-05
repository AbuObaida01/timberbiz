from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import List, Optional
from decimal import Decimal

from app.database import get_db
from app.models.product import Product
from app.schemas.product import ProductCreate, ProductUpdate, ProductResponse
from app.services.auth import get_current_user, get_admin_user
from app.services.cloudinary_service import upload_image
from app.models.user import User

router = APIRouter(prefix="/products", tags=["Furniture Products"])


# ── PUBLIC ROUTES ─────────────────────────────────────

@router.get("/", response_model=List[ProductResponse])
def get_all_products(
    category: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    db: Session = Depends(get_db)
):
    """Public product listing — shows available stock only"""
    # Cleanup expired reservations first
    from app.services.stock import cleanup_expired_reservations
    cleanup_expired_reservations(db)

    query = db.query(Product)

    if category:
        query = query.filter(Product.category.ilike(f"%{category}%"))
    if min_price is not None:
        query = query.filter(Product.price >= min_price)
    if max_price is not None:
        query = query.filter(Product.price <= max_price)

    products = query.order_by(Product.created_at.desc()).all()

    # Add available_stock to each product response
    result = []
    for p in products:
        result.append({
            "id": p.id,
            "name": p.name,
            "category": p.category,
            "price": float(p.price),
            "description": p.description,
            "stock": p.stock,
            "available_stock": p.available_stock(),
            "image_url": p.image_url,
            "created_at": p.created_at,
            "low_stock": p.available_stock() <= 3 and p.available_stock() > 0,
            "out_of_stock": p.available_stock() == 0
        })

    return result


@router.get("/categories")
def get_all_categories(db: Session = Depends(get_db)):
    """Get all unique product categories"""
    categories = db.query(Product.category).distinct().all()
    return {
        "categories": [c[0] for c in categories if c[0] is not None]
    }


@router.get("/{product_id}", response_model=ProductResponse)
def get_product_detail(
    product_id: int,
    db: Session = Depends(get_db)
):
    """Get single product detail"""
    product = db.query(Product).filter(
        Product.id == product_id
    ).first()

    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    return product


# ── ADMIN ROUTES ──────────────────────────────────────

@router.post("/", status_code=201)
async def admin_create_product(
    name: str = Form(...),
    category: Optional[str] = Form(None),
    price: Decimal = Form(...),
    description: Optional[str] = Form(None),
    stock: int = Form(0),
    image: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user)
):
    """Admin adds a new furniture product with optional image upload"""

    image_url = None

    # Upload image if provided
    if image:
        if image.content_type not in ["image/jpeg", "image/png", "image/webp"]:
            raise HTTPException(
                status_code=400,
                detail="Only JPEG, PNG, WEBP images allowed"
            )
        file_bytes = await image.read()
        image_url = upload_image(file_bytes, folder="timberbiz/products")

    new_product = Product(
        name=name,
        category=category,
        price=price,
        description=description,
        stock=stock,
        image_url=image_url
    )

    db.add(new_product)
    db.commit()
    db.refresh(new_product)

    return {
        "message": "Product created successfully",
        "product_id": new_product.id,
        "name": new_product.name,
        "price": float(new_product.price),
        "stock": new_product.stock,
        "image_url": new_product.image_url
    }


@router.put("/{product_id}")
def admin_update_product(
    product_id: int,
    product_data: ProductUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user)
):
    """Admin updates product details"""
    product = db.query(Product).filter(
        Product.id == product_id
    ).first()

    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # Only update fields that were provided
    update_data = product_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(product, field, value)

    db.commit()
    db.refresh(product)

    return {
        "message": "Product updated successfully",
        "product": product
    }


@router.patch("/{product_id}/stock")
def admin_update_stock(
    product_id: int,
    stock: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user)
):
    """Admin updates product stock level"""
    product = db.query(Product).filter(
        Product.id == product_id
    ).first()

    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    if stock < 0:
        raise HTTPException(
            status_code=400,
            detail="Stock cannot be negative"
        )

    product.stock = stock
    db.commit()

    return {
        "message": "Stock updated",
        "product_id": product_id,
        "new_stock": stock
    }


@router.delete("/{product_id}")
def admin_delete_product(
    product_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user)
):
    """Admin deletes a product"""
    product = db.query(Product).filter(
        Product.id == product_id
    ).first()

    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    db.delete(product)
    db.commit()

    return {"message": "Product deleted successfully"}