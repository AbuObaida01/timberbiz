from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from decimal import Decimal

from app.database import get_db
from app.models.order import Cart, Order, OrderItem
from app.models.product import Product
from app.models.user import User
from app.schemas.order import CheckoutRequest, PaymentVerifyRequest
from app.services.auth import get_current_user, get_admin_user
from app.services.payment import create_razorpay_order, verify_razorpay_payment
from app.services.stock import (
    cleanup_expired_carts,
    cleanup_expired_reservations,
    reserve_stock,
    release_stock_reservation,
    deduct_stock_permanently
)

router = APIRouter(prefix="/orders", tags=["Orders & Payments"])


@router.post("/checkout")
def checkout(
    checkout_data: CheckoutRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Step 1 of payment flow.
    Creates Razorpay order + reserves stock for 15 minutes.
    """
    # Cleanup expired carts and reservations first
    cleanup_expired_carts(db)
    cleanup_expired_reservations(db)

    # Get active cart items
    cart_items = db.query(Cart).filter(
        Cart.user_id == current_user.id
    ).all()

    if not cart_items:
        raise HTTPException(
            status_code=400,
            detail="Your cart is empty or all items have expired"
        )

    total_amount = Decimal("0")
    order_items_data = []

    # Validate and reserve stock for each item
    for item in cart_items:
        product = db.query(Product).filter(
            Product.id == item.product_id
        ).first()

        if not product:
            raise HTTPException(
                status_code=400,
                detail=f"Product no longer exists"
            )

        # This raises 400 if not enough available stock
        reserve_stock(product, item.quantity, db)

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

    # Save pending order in DB
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
        "message": "Order created. Stock reserved for 15 minutes. Complete payment now.",
        "order_id": new_order.id,
        "razorpay_order_id": razorpay_order["id"],
        "total_amount": float(total_amount),
        "total_amount_paise": int(total_amount * 100),
        "currency": "INR",
        "reservation_expires_in_minutes": 15,
        "items": [
            {
                "product_name": i["product_name"],
                "quantity": i["quantity"],
                "item_total": float(i["item_total"])
            }
            for i in order_items_data
        ]
    }


@router.post("/verify-payment")
def verify_payment(
    payment_data: PaymentVerifyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Step 2 of payment flow.
    Verifies Razorpay signature.
    On success → permanently deduct stock + clear cart.
    On failure → release reservations.
    """
    cleanup_expired_reservations(db)

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

    # Verify Razorpay signature
    is_valid = verify_razorpay_payment(
        payment_data.razorpay_order_id,
        payment_data.razorpay_payment_id,
        payment_data.razorpay_signature
    )

    if not is_valid:
        # Payment failed — release all reservations
        for item in order.items:
            product = db.query(Product).filter(
                Product.id == item.product_id
            ).first()
            if product:
                release_stock_reservation(product, item.quantity, db)

        order.payment_status = "failed"
        db.commit()

        raise HTTPException(
            status_code=400,
            detail="Payment verification failed. Stock reservation released."
        )

    # Payment successful
    order.payment_status = "paid"
    order.razorpay_payment_id = payment_data.razorpay_payment_id
    db.commit()

    # Permanently deduct stock for each item
    for item in order.items:
        product = db.query(Product).filter(
            Product.id == item.product_id
        ).first()
        if product:
            deduct_stock_permanently(product, item.quantity, db)

    # Clear user's cart
    db.query(Cart).filter(
        Cart.user_id == current_user.id
    ).delete()
    db.commit()
    db.refresh(order)

    return {
        "message": "Payment verified! Order confirmed. 🎉",
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
    """Customer views their order history"""
    orders = db.query(Order).filter(
        Order.user_id == current_user.id
    ).order_by(Order.created_at.desc()).all()

    result = []
    for order in orders:
        items = []
        for item in order.items:
            items.append({
                "product_id": item.product_id,
                "product_name": (
                    item.product.name if item.product else "Deleted Product"
                ),
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
                "product_name": (
                    item.product.name if item.product else "Deleted"
                ),
                "quantity": item.quantity,
                "price": float(item.price),
                "item_total": float(item.price * item.quantity)
            }
            for item in order.items
        ]
    }


@router.get("/admin/all")
def admin_get_all_orders(
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user)
):
    """Admin sees all orders"""
    orders = db.query(Order).order_by(
        Order.created_at.desc()
    ).all()

    return [
        {
            "order_id": o.id,
            "customer_name": o.user.name,
            "customer_email": o.user.email,
            "total_amount": float(o.total_amount),
            "payment_status": o.payment_status,
            "delivery_address": o.delivery_address,
            "delivery_phone": o.delivery_phone,
            "created_at": o.created_at,
            "items_count": len(o.items)
        }
        for o in orders
    ]


@router.get("/admin/stats")
def admin_order_stats(
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user)
):
    """Admin order statistics"""
    from sqlalchemy import func

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