from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.models.product import Product
from app.models.order import Cart
from fastapi import HTTPException


def cleanup_expired_carts(db: Session):
    """
    Remove all cart items that have passed their 24hr expiry.
    Called at the start of every cart-related request.
    """
    expired = db.query(Cart).filter(
        Cart.expires_at != None,
        Cart.expires_at < datetime.utcnow()
    ).all()

    for item in expired:
        db.delete(item)

    if expired:
        db.commit()

    return len(expired)


def cleanup_expired_reservations(db: Session):
    """
    Release stock reservations that have passed 15min window.
    Called at start of checkout and verify payment.
    """
    products = db.query(Product).filter(
        Product.reservation_expires_at != None,
        Product.reservation_expires_at < datetime.utcnow(),
        Product.reserved_quantity > 0
    ).all()

    for product in products:
        product.reserved_quantity = 0
        product.reservation_expires_at = None

    if products:
        db.commit()

    return len(products)


def reserve_stock(product: Product, quantity: int, db: Session):
    """
    Reserve stock for 15 minutes during checkout.
    Raises 400 if not enough available stock.
    """
    # First cleanup any expired reservations
    cleanup_expired_reservations(db)

    available = product.available_stock()

    if available < quantity:
        raise HTTPException(
            status_code=400,
            detail=f"Only {available} units of '{product.name}' available right now. "
                   f"Another user may be checking out the remaining units."
        )

    # Reserve for 15 minutes
    product.reserved_quantity = (product.reserved_quantity or 0) + quantity
    product.reservation_expires_at = (
        datetime.utcnow() + timedelta(minutes=15)
    )
    db.commit()


def release_stock_reservation(product: Product, quantity: int, db: Session):
    """
    Release a reservation — called when payment fails or times out.
    """
    product.reserved_quantity = max(
        0,
        (product.reserved_quantity or 0) - quantity
    )
    if product.reserved_quantity == 0:
        product.reservation_expires_at = None
    db.commit()


def deduct_stock_permanently(product: Product, quantity: int, db: Session):
    """
    Permanently deduct stock after successful payment.
    Also release the reservation.
    """
    product.stock = max(0, product.stock - quantity)
    product.reserved_quantity = max(
        0,
        (product.reserved_quantity or 0) - quantity
    )
    if product.reserved_quantity == 0:
        product.reservation_expires_at = None
    db.commit()