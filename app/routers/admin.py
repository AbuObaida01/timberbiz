from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, extract
from datetime import datetime, timedelta
from app.database import get_db
from app.models.user import User
from app.models.tree import Tree
from app.models.product import Product
from app.models.order import Order, OrderItem
from app.models.cutting_request import CuttingRequest
from app.services.auth import get_admin_user

router = APIRouter(prefix="/admin", tags=["Admin Dashboard"])


# ── MAIN DASHBOARD ────────────────────────────────────

@router.get("/dashboard")
def get_dashboard(
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user)
):
    """
    Complete admin dashboard in one call.
    Shows all platform statistics at a glance.
    """

    # ── USER STATS ──────────────────────────────
    total_users = db.query(User).filter(
        User.role == "user"
    ).count()

    new_users_today = db.query(User).filter(
        User.role == "user",
        func.date(User.created_at) == datetime.utcnow().date()
    ).count()

    new_users_this_week = db.query(User).filter(
        User.role == "user",
        User.created_at >= datetime.utcnow() - timedelta(days=7)
    ).count()

    # ── TREE LISTING STATS ───────────────────────
    total_listings = db.query(Tree).count()
    pending_listings = db.query(Tree).filter(
        Tree.status == "pending"
    ).count()
    approved_listings = db.query(Tree).filter(
        Tree.status == "approved"
    ).count()
    rejected_listings = db.query(Tree).filter(
        Tree.status == "rejected"
    ).count()

    # ── ORDER STATS ──────────────────────────────
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

    # ── REVENUE ──────────────────────────────────
    total_revenue = db.query(
        func.sum(Order.total_amount)
    ).filter(
        Order.payment_status == "paid"
    ).scalar() or 0

    revenue_today = db.query(
        func.sum(Order.total_amount)
    ).filter(
        Order.payment_status == "paid",
        func.date(Order.created_at) == datetime.utcnow().date()
    ).scalar() or 0

    revenue_this_week = db.query(
        func.sum(Order.total_amount)
    ).filter(
        Order.payment_status == "paid",
        Order.created_at >= datetime.utcnow() - timedelta(days=7)
    ).scalar() or 0

    # ── CUTTING REQUEST STATS ────────────────────
    total_cutting_requests = db.query(CuttingRequest).count()
    pending_cutting = db.query(CuttingRequest).filter(
        CuttingRequest.status == "pending"
    ).count()
    completed_cutting = db.query(CuttingRequest).filter(
        CuttingRequest.status == "completed"
    ).count()

    cutting_revenue = db.query(
        func.sum(CuttingRequest.quoted_price)
    ).filter(
        CuttingRequest.status.in_(["paid", "completed"])
    ).scalar() or 0

    # ── PRODUCT STATS ────────────────────────────
    total_products = db.query(Product).count()
    out_of_stock = db.query(Product).filter(
        Product.stock == 0
    ).count()
    low_stock = db.query(Product).filter(
        Product.stock > 0,
        Product.stock <= 5
    ).count()

    return {
        "users": {
            "total": total_users,
            "new_today": new_users_today,
            "new_this_week": new_users_this_week
        },
        "tree_listings": {
            "total": total_listings,
            "pending": pending_listings,
            "approved": approved_listings,
            "rejected": rejected_listings
        },
        "orders": {
            "total": total_orders,
            "paid": paid_orders,
            "pending": pending_orders,
            "failed": failed_orders
        },
        "revenue": {
            "total": float(total_revenue),
            "today": float(revenue_today),
            "this_week": float(revenue_this_week),
            "cutting_requests": float(cutting_revenue),
            "grand_total": float(total_revenue) + float(cutting_revenue)
        },
        "cutting_requests": {
            "total": total_cutting_requests,
            "pending": pending_cutting,
            "completed": completed_cutting
        },
        "products": {
            "total": total_products,
            "out_of_stock": out_of_stock,
            "low_stock": low_stock
        }
    }


# ── USER MANAGEMENT ───────────────────────────────────

@router.get("/users")
def get_all_users(
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user)
):
    """Admin sees all registered users with details"""
    users = db.query(User).filter(
        User.role == "user"
    ).order_by(User.created_at.desc()).all()

    result = []
    for user in users:
        # Count their listings and orders
        listing_count = db.query(Tree).filter(
            Tree.uploader_id == user.id
        ).count()
        order_count = db.query(Order).filter(
            Order.user_id == user.id
        ).count()
        cutting_count = db.query(CuttingRequest).filter(
            CuttingRequest.user_id == user.id
        ).count()

        result.append({
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "phone": user.phone,
            "latitude": user.latitude,
            "longitude": user.longitude,
            "created_at": user.created_at,
            "activity": {
                "tree_listings": listing_count,
                "orders": order_count,
                "cutting_requests": cutting_count
            }
        })

    return {
        "total_users": len(result),
        "users": result
    }


@router.get("/users/{user_id}")
def get_user_detail(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user)
):
    """Admin views a single user's full profile and activity"""
    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Get their listings
    listings = db.query(Tree).filter(
        Tree.uploader_id == user_id
    ).all()

    # Get their orders
    orders = db.query(Order).filter(
        Order.user_id == user_id
    ).all()

    # Get their cutting requests
    cutting_requests = db.query(CuttingRequest).filter(
        CuttingRequest.user_id == user_id
    ).all()

    # Total spent
    total_spent = db.query(
        func.sum(Order.total_amount)
    ).filter(
        Order.user_id == user_id,
        Order.payment_status == "paid"
    ).scalar() or 0

    return {
        "user": {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "phone": user.phone,
            "latitude": user.latitude,
            "longitude": user.longitude,
            "created_at": user.created_at
        },
        "stats": {
            "total_listings": len(listings),
            "total_orders": len(orders),
            "total_cutting_requests": len(cutting_requests),
            "total_spent": float(total_spent)
        },
        "listings": [
            {
                "id": t.id,
                "title": t.title,
                "status": t.status,
                "price": float(t.price),
                "created_at": t.created_at
            } for t in listings
        ],
        "orders": [
            {
                "id": o.id,
                "total_amount": float(o.total_amount),
                "payment_status": o.payment_status,
                "created_at": o.created_at
            } for o in orders
        ],
        "cutting_requests": [
            {
                "id": c.id,
                "wood_type": c.wood_type,
                "status": c.status,
                "quoted_price": float(c.quoted_price) if c.quoted_price else None,
                "created_at": c.created_at
            } for c in cutting_requests
        ]
    }


@router.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user)
):
    """Admin deletes/bans a user account"""
    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.role == "admin":
        raise HTTPException(
            status_code=403,
            detail="Cannot delete an admin account"
        )

    db.delete(user)
    db.commit()

    return {"message": f"User {user.name} deleted successfully"}


# ── REVENUE ANALYTICS ─────────────────────────────────

@router.get("/analytics/revenue")
def revenue_analytics(
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user)
):
    """Monthly revenue breakdown for the current year"""

    current_year = datetime.utcnow().year

    monthly_revenue = db.query(
        extract("month", Order.created_at).label("month"),
        func.sum(Order.total_amount).label("revenue"),
        func.count(Order.id).label("orders")
    ).filter(
        Order.payment_status == "paid",
        extract("year", Order.created_at) == current_year
    ).group_by(
        extract("month", Order.created_at)
    ).order_by("month").all()

    months = [
        "Jan", "Feb", "Mar", "Apr", "May", "Jun",
        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"
    ]

    result = []
    for row in monthly_revenue:
        result.append({
            "month": months[int(row.month) - 1],
            "month_number": int(row.month),
            "revenue": float(row.revenue),
            "orders": int(row.orders)
        })

    # Total annual revenue
    annual_revenue = db.query(
        func.sum(Order.total_amount)
    ).filter(
        Order.payment_status == "paid",
        extract("year", Order.created_at) == current_year
    ).scalar() or 0

    return {
        "year": current_year,
        "annual_revenue": float(annual_revenue),
        "monthly_breakdown": result
    }


@router.get("/analytics/top-products")
def top_products(
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user)
):
    """Top 5 best selling furniture products"""

    top = db.query(
        Product.id,
        Product.name,
        Product.category,
        Product.price,
        func.sum(OrderItem.quantity).label("total_sold"),
        func.sum(
            OrderItem.quantity * OrderItem.price
        ).label("total_revenue")
    ).join(
        OrderItem, OrderItem.product_id == Product.id
    ).join(
        Order, Order.id == OrderItem.order_id
    ).filter(
        Order.payment_status == "paid"
    ).group_by(
        Product.id,
        Product.name,
        Product.category,
        Product.price
    ).order_by(
        func.sum(OrderItem.quantity).desc()
    ).limit(5).all()

    return {
        "top_products": [
            {
                "product_id": t.id,
                "name": t.name,
                "category": t.category,
                "price": float(t.price),
                "total_sold": int(t.total_sold),
                "total_revenue": float(t.total_revenue)
            } for t in top
        ]
    }


@router.get("/analytics/listings")
def listing_analytics(
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user)
):
    """Tree listing analytics"""

    # Listings by status
    by_status = db.query(
        Tree.status,
        func.count(Tree.id).label("count")
    ).group_by(Tree.status).all()

    # Listings this week
    this_week = db.query(Tree).filter(
        Tree.created_at >= datetime.utcnow() - timedelta(days=7)
    ).count()

    # Most active uploaders
    top_uploaders = db.query(
        User.name,
        User.email,
        func.count(Tree.id).label("listing_count")
    ).join(
        Tree, Tree.uploader_id == User.id
    ).group_by(
        User.id,
        User.name,
        User.email
    ).order_by(
        func.count(Tree.id).desc()
    ).limit(5).all()

    return {
        "by_status": {
            row.status: row.count for row in by_status
        },
        "new_this_week": this_week,
        "top_uploaders": [
            {
                "name": u.name,
                "email": u.email,
                "listings": u.listing_count
            } for u in top_uploaders
        ]
    }