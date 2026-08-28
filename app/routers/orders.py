from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from decimal import Decimal

from app.database import get_db
from app.models.order import Cart, Order, OrderItem
from app.models.product import Product
from app.models.user import User
from app.schemas.order import (
    CheckoutRequest,
    PaymentVerifyRequest,
    OrderResponse
)
from app.services.auth import get_current_user, get_admin_user
from app.services.payment import create_razorpay_order, verify_razorpay_payment

router = APIRouter(prefix="/orders", tags=["Orders & Payments"])


# ── CUSTOMER ROUTES ───────────────────────────────────

@router.post("/checkout")
def checkout(
    checkout_data: CheckoutRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Step 1 of payment flow.
    Creates a Razorpay order from cart items.
    Returns razorpay_order_id to frontend for payment popup.
    """

    # Get cart items
    cart_items = db.query(Cart).filter(
        Cart.user_id == current_user.id
    ).all()

    if not cart_items:
        raise HTTPException(
            status_code=400,
            detail="Your cart is empty"
        )

    # Validate stock and calculate total
    total_amount = Decimal("0")
    order_items_data = []

    for item in cart_items:
        product = db.query(Product).filter(
            Product.id == item.product_id
        ).first()

        if not product:
            raise HTTPException(
                status_code=400,
                detail=f"Product {item.product_id} no longer exists"
            )

        if product.stock < item.quantity:
            raise HTTPException(
                status_code=400,
                detail=f"'{product.name}' only has {product.stock} units left. Update your cart."
            )

        item_total = product.price * item.quantity
        total_amount += item_total

        order_items_data.append({
            "product_id": product.id,
            "product_name": product.name,
            "quantity": item.quantity,
            "price": product.price,
            "item_total": item_total
        })

    # Create Razorpay order
    razorpay_order = create_razorpay_order(float(total_amount))

    # Save order in DB with pending status
    new_order = Order(
        user_id=current_user.id,
        total_amount=total_amount,
        payment_status="pending",
        razorpay_order_id=razorpay_order["id"],
        delivery_address=checkout_data.delivery_address,
        delivery_phone=checkout_data.delivery_phone
    )
    db.add(new_order)
    db.commit()
    db.refresh(new_order)

    # Save order items
    for item_data in order_items_data:
        order_item = OrderItem(
            order_id=new_order.id,
            product_id=item_data["product_id"],
            quantity=item_data["quantity"],
            price=item_data["price"]
        )
        db.add(order_item)

    db.commit()

    return {
        "message": "Order created. Proceed to payment.",
        "order_id": new_order.id,
        "razorpay_order_id": razorpay_order["id"],
        "razorpay_key_id": razorpay_order["id"],
        "total_amount": float(total_amount),
        "total_amount_paise": int(total_amount * 100),
        "currency": "INR",
        "items": order_items_data
    }


@router.post("/verify-payment")
def verify_payment(
    payment_data: PaymentVerifyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Step 2 of payment flow.
    Frontend sends payment details after user pays.
    Backend verifies signature and marks order as paid.
    """

    # Find the order
    order = db.query(Order).filter(
        Order.razorpay_order_id == payment_data.razorpay_order_id,
        Order.user_id == current_user.id
    ).first()

    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    if order.payment_status == "paid":
        raise HTTPException(
            status_code=400,
            detail="Payment already verified for this order"
        )

    # Verify payment signature
    is_valid = verify_razorpay_payment(
        payment_data.razorpay_order_id,
        payment_data.razorpay_payment_id,
        payment_data.razorpay_signature
    )

    if not is_valid:
        # Mark as failed
        order.payment_status = "failed"
        db.commit()
        raise HTTPException(
            status_code=400,
            detail="Payment verification failed. Invalid signature."
        )

    # Payment verified — update order
    order.payment_status = "paid"
    order.razorpay_payment_id = payment_data.razorpay_payment_id
    db.commit()

    # Reduce stock for each ordered item
    for item in order.items:
        product = db.query(Product).filter(
            Product.id == item.product_id
        ).first()
        if product:
            product.stock = max(0, product.stock - item.quantity)

    # Clear the user's cart
    db.query(Cart).filter(
        Cart.user_id == current_user.id
    ).delete()

    db.commit()
    db.refresh(order)

    return {
        "message": "Payment verified successfully! Order confirmed.",
        "order_id": order.id,
        "payment_status": order.payment_status,
        "total_amount": float(order.total_amount),
        "razorpay_payment_id": order.razorpay_payment_id
    }


@router.get("/my")
def get_my_orders(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Customer views their own order history"""
    orders = db.query(Order).filter(
        Order.user_id == current_user.id
    ).order_by(Order.created_at.desc()).all()

    result = []
    for order in orders:
        items = []
        for item in order.items:
            items.append({
                "product_id": item.product_id,
                "product_name": item.product.name if item.product else "Deleted Product",
                "quantity": item.quantity,
                "price": float(item.price),
                "item_total": float(item.price * item.quantity)
            })

        result.append({
            "order_id": order.id,
            "total_amount": float(order.total_amount),
            "payment_status": order.payment_status,
            "delivery_address": order.delivery_address,
            "delivery_phone": order.delivery_phone,
            "created_at": order.created_at,
            "items": items,
            "items_count": len(items)
        })

    return result


@router.get("/my/{order_id}")
def get_single_order(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get single order detail"""
    order = db.query(Order).filter(
        Order.id == order_id,
        Order.user_id == current_user.id
    ).first()

    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    return {
        "order_id": order.id,
        "total_amount": float(order.total_amount),
        "payment_status": order.payment_status,
        "razorpay_order_id": order.razorpay_order_id,
        "delivery_address": order.delivery_address,
        "delivery_phone": order.delivery_phone,
        "created_at": order.created_at,
        "items": [
            {
                "product_name": item.product.name if item.product else "Deleted",
                "quantity": item.quantity,
                "price": float(item.price),
                "item_total": float(item.price * item.quantity)
            }
            for item in order.items
        ]
    }


# ── ADMIN ROUTES ──────────────────────────────────────

@router.get("/admin/all")
def admin_get_all_orders(
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user)
):
    """Admin sees ALL orders across all users"""
    orders = db.query(Order).order_by(
        Order.created_at.desc()
    ).all()

    result = []
    for order in orders:
        result.append({
            "order_id": order.id,
            "customer_name": order.user.name,
            "customer_email": order.user.email,
            "total_amount": float(order.total_amount),
            "payment_status": order.payment_status,
            "delivery_address": order.delivery_address,
            "delivery_phone": order.delivery_phone,
            "created_at": order.created_at,
            "items_count": len(order.items)
        })

    return result


@router.get("/admin/stats")
def admin_order_stats(
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user)
):
    """Admin gets order statistics"""
    total_orders = db.query(Order).count()
    paid_orders = db.query(Order).filter(
        Order.payment_status == "paid"
    ).count()
    pending_orders = db.query(Order).filter(
        Order.payment_status == "pending"
    ).count()
    failed_orders = db.query(Order).filter(
        Order.payment_status == "failed"
    ).count()

    # Total revenue
    from sqlalchemy import func
    total_revenue = db.query(
        func.sum(Order.total_amount)
    ).filter(
        Order.payment_status == "paid"
    ).scalar() or 0

    return {
        "total_orders": total_orders,
        "paid_orders": paid_orders,
        "pending_orders": pending_orders,
        "failed_orders": failed_orders,
        "total_revenue": float(total_revenue)
    }