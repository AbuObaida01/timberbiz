from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from decimal import Decimal

from app.database import get_db
from app.models.order import Cart
from app.models.product import Product
from app.models.user import User
from app.schemas.cart import CartAddItem, CartUpdateItem
from app.services.auth import get_current_user

router = APIRouter(prefix="/cart", tags=["Cart"])


@router.post("/", status_code=201)
def add_to_cart(
    item: CartAddItem,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Add a product to cart. If already in cart, increase quantity."""

    # Check product exists and has stock
    product = db.query(Product).filter(
        Product.id == item.product_id
    ).first()

    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    if product.stock <= 0:
        raise HTTPException(
            status_code=400,
            detail="Product is out of stock"
        )

    if item.quantity <= 0:
        raise HTTPException(
            status_code=400,
            detail="Quantity must be at least 1"
        )

    if item.quantity > product.stock:
        raise HTTPException(
            status_code=400,
            detail=f"Only {product.stock} units available"
        )

    # Check if already in cart
    existing = db.query(Cart).filter(
        Cart.user_id == current_user.id,
        Cart.product_id == item.product_id
    ).first()

    if existing:
        # Update quantity
        new_quantity = existing.quantity + item.quantity
        if new_quantity > product.stock:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot add more. Only {product.stock} units available"
            )
        existing.quantity = new_quantity
        db.commit()
        db.refresh(existing)
        return {
            "message": "Cart updated",
            "product": product.name,
            "new_quantity": existing.quantity
        }

    # Add new cart item
    cart_item = Cart(
        user_id=current_user.id,
        product_id=item.product_id,
        quantity=item.quantity
    )
    db.add(cart_item)
    db.commit()
    db.refresh(cart_item)

    return {
        "message": f"{product.name} added to cart",
        "cart_item_id": cart_item.id,
        "quantity": cart_item.quantity,
        "price_per_unit": float(product.price),
        "item_total": float(product.price * item.quantity)
    }


@router.get("/")
def get_cart(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """View your cart with full summary"""
    cart_items = db.query(Cart).filter(
        Cart.user_id == current_user.id
    ).all()

    if not cart_items:
        return {
            "items": [],
            "total_items": 0,
            "total_price": 0.0,
            "message": "Your cart is empty"
        }

    items = []
    total_price = Decimal("0")
    total_items = 0

    for item in cart_items:
        product = item.product
        item_total = product.price * item.quantity
        total_price += item_total
        total_items += item.quantity

        items.append({
            "cart_item_id": item.id,
            "product_id": product.id,
            "product_name": product.name,
            "category": product.category,
            "price_per_unit": float(product.price),
            "quantity": item.quantity,
            "item_total": float(item_total),
            "product_image": product.image_url,
            "in_stock": product.stock >= item.quantity
        })

    return {
        "items": items,
        "total_items": total_items,
        "total_price": float(total_price),
        "items_count": len(items)
    }


@router.patch("/{cart_item_id}")
def update_cart_item(
    cart_item_id: int,
    update: CartUpdateItem,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update quantity of a cart item"""
    cart_item = db.query(Cart).filter(
        Cart.id == cart_item_id,
        Cart.user_id == current_user.id
    ).first()

    if not cart_item:
        raise HTTPException(status_code=404, detail="Cart item not found")

    if update.quantity <= 0:
        raise HTTPException(
            status_code=400,
            detail="Quantity must be at least 1. To remove use DELETE."
        )

    # Check stock
    product = cart_item.product
    if update.quantity > product.stock:
        raise HTTPException(
            status_code=400,
            detail=f"Only {product.stock} units available"
        )

    cart_item.quantity = update.quantity
    db.commit()
    db.refresh(cart_item)

    return {
        "message": "Cart updated",
        "cart_item_id": cart_item_id,
        "new_quantity": cart_item.quantity,
        "new_item_total": float(cart_item.product.price * cart_item.quantity)
    }


@router.delete("/{cart_item_id}")
def remove_from_cart(
    cart_item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Remove a specific item from cart"""
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