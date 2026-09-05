from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from decimal import Decimal

from app.database import get_db
from app.models.order import Cart
from app.models.product import Product
from app.models.user import User
from app.schemas.cart import CartAddItem, CartUpdateItem
from app.services.auth import get_current_user
from app.services.stock import cleanup_expired_carts

router = APIRouter(prefix="/cart", tags=["Cart"])

CART_EXPIRY_HOURS = 24


@router.post("/", status_code=201)
def add_to_cart(
    item: CartAddItem,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Add product to cart.
    Cart item expires after 24 hours automatically.
    Stock is NOT deducted here — only during checkout.
    """
    # Cleanup expired carts first
    cleanup_expired_carts(db)

    # Check product exists
    product = db.query(Product).filter(
        Product.id == item.product_id
    ).first()

    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # Check available stock (total - reserved)
    available = product.available_stock()

    if available <= 0:
        raise HTTPException(
            status_code=400,
            detail="Product is currently out of stock or fully reserved"
        )

    if item.quantity <= 0:
        raise HTTPException(
            status_code=400,
            detail="Quantity must be at least 1"
        )

    if item.quantity > available:
        raise HTTPException(
            status_code=400,
            detail=f"Only {available} units available"
        )

    # Check if already in cart (not expired)
    existing = db.query(Cart).filter(
        Cart.user_id == current_user.id,
        Cart.product_id == item.product_id
    ).first()

    expires_at = datetime.utcnow() + timedelta(hours=CART_EXPIRY_HOURS)

    if existing:
        # Update quantity and reset expiry
        new_quantity = existing.quantity + item.quantity
        if new_quantity > available:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot add more. Only {available} units available"
            )
        existing.quantity = new_quantity
        existing.expires_at = expires_at
        db.commit()
        db.refresh(existing)

        return {
            "message": "Cart updated",
            "product": product.name,
            "new_quantity": existing.quantity,
            "cart_expires_at": expires_at.isoformat(),
            "available_stock": available
        }

    # Add new cart item with 24hr expiry
    cart_item = Cart(
        user_id=current_user.id,
        product_id=item.product_id,
        quantity=item.quantity,
        expires_at=expires_at
    )
    db.add(cart_item)
    db.commit()
    db.refresh(cart_item)

    return {
        "message": f"{product.name} added to cart",
        "cart_item_id": cart_item.id,
        "quantity": cart_item.quantity,
        "price_per_unit": float(product.price),
        "item_total": float(product.price * item.quantity),
        "cart_expires_at": expires_at.isoformat(),
        "available_stock": available,
        "note": "This item will be removed from cart after 24 hours if not purchased"
    }


@router.get("/")
def get_cart(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """View cart — expired items auto-removed, shows time remaining"""

    # Cleanup expired items first
    removed = cleanup_expired_carts(db)

    cart_items = db.query(Cart).filter(
        Cart.user_id == current_user.id
    ).all()

    if not cart_items:
        return {
            "items": [],
            "total_items": 0,
            "total_price": 0.0,
            "message": "Your cart is empty",
            "expired_items_removed": removed
        }

    items = []
    total_price = Decimal("0")
    total_items = 0

    for item in cart_items:
        product = item.product
        available = product.available_stock()
        item_total = product.price * item.quantity
        total_price += item_total
        total_items += item.quantity

        # Calculate time remaining before cart expiry
        time_remaining = None
        if item.expires_at:
            remaining = item.expires_at - datetime.utcnow()
            total_seconds = int(remaining.total_seconds())
            if total_seconds > 0:
                hours = total_seconds // 3600
                minutes = (total_seconds % 3600) // 60
                time_remaining = f"{hours}h {minutes}m remaining"
            else:
                time_remaining = "Expiring soon"

        items.append({
            "cart_item_id": item.id,
            "product_id": product.id,
            "product_name": product.name,
            "category": product.category,
            "price_per_unit": float(product.price),
            "quantity": item.quantity,
            "item_total": float(item_total),
            "product_image": product.image_url,
            "available_stock": available,
            "in_stock": available >= item.quantity,
            "expires_at": item.expires_at.isoformat() if item.expires_at else None,
            "time_remaining": time_remaining,
            "low_stock": available <= 3
        })

    return {
        "items": items,
        "total_items": total_items,
        "total_price": float(total_price),
        "items_count": len(items),
        "expired_items_removed": removed
    }


@router.patch("/{cart_item_id}")
def update_cart_item(
    cart_item_id: int,
    update: CartUpdateItem,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update cart item quantity"""
    cleanup_expired_carts(db)

    cart_item = db.query(Cart).filter(
        Cart.id == cart_item_id,
        Cart.user_id == current_user.id
    ).first()

    if not cart_item:
        raise HTTPException(
            status_code=404,
            detail="Cart item not found or expired"
        )

    if update.quantity <= 0:
        raise HTTPException(
            status_code=400,
            detail="Quantity must be at least 1. To remove use DELETE."
        )

    available = cart_item.product.available_stock()
    if update.quantity > available:
        raise HTTPException(
            status_code=400,
            detail=f"Only {available} units available"
        )

    cart_item.quantity = update.quantity
    # Reset expiry on update
    cart_item.expires_at = datetime.utcnow() + timedelta(hours=CART_EXPIRY_HOURS)
    db.commit()
    db.refresh(cart_item)

    return {
        "message": "Cart updated",
        "cart_item_id": cart_item_id,
        "new_quantity": cart_item.quantity,
        "new_item_total": float(
            cart_item.product.price * cart_item.quantity
        ),
        "expires_at": cart_item.expires_at.isoformat()
    }


@router.delete("/{cart_item_id}")
def remove_from_cart(
    cart_item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Remove item from cart"""
    cart_item = db.query(Cart).filter(
        Cart.id == cart_item_id,
        Cart.user_id == current_user.id
    ).first()

    if not cart_item:
        raise HTTPException(status_code=404, detail="Cart item not found")

    db.delete(cart_item)
    db.commit()

    return {"message": "Item removed from cart"}


@router.delete("/")
def clear_cart(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Clear entire cart"""
    db.query(Cart).filter(
        Cart.user_id == current_user.id
    ).delete()
    db.commit()
    return {"message": "Cart cleared successfully"}