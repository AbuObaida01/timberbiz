from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.models.cutting_request import CuttingRequest
from app.models.user import User
from app.schemas.cutting_request import (
    CuttingRequestCreate,
    CuttingRequestResponse,
    AdminQuoteRequest,
    AdminRejectRequest
)
from app.services.auth import get_current_user, get_admin_user

router = APIRouter(prefix="/cutting-requests", tags=["Wood Cutting Requests"])


# ── CUSTOMER ROUTES ─────────────────────────────────

@router.post("/", response_model=CuttingRequestResponse, status_code=201)
def create_cutting_request(
    data: CuttingRequestCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Any logged in user can submit a wood cutting request"""
    request = CuttingRequest(
        user_id=current_user.id,
        **data.model_dump()
    )
    db.add(request)
    db.commit()
    db.refresh(request)
    return request


@router.get("/my", response_model=List[CuttingRequestResponse])
def get_my_requests(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Customer sees all their own cutting requests"""
    return db.query(CuttingRequest).filter(
        CuttingRequest.user_id == current_user.id
    ).order_by(CuttingRequest.created_at.desc()).all()


@router.get("/{request_id}", response_model=CuttingRequestResponse)
def get_request_detail(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """View a single request — only owner or admin can see"""
    req = db.query(CuttingRequest).filter(
        CuttingRequest.id == request_id
    ).first()

    if not req:
        raise HTTPException(status_code=404, detail="Request not found")

    # Only the owner or admin can view
    if req.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorised")

    return req


# ── PAYMENT ROUTE ────────────────────────────────────

@router.post("/{request_id}/pay")
def initiate_payment(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Customer initiates payment after admin sets quote.
    Razorpay integration goes here in Phase 7.
    For now returns the quoted price to confirm.
    """
    req = db.query(CuttingRequest).filter(
        CuttingRequest.id == request_id,
        CuttingRequest.user_id == current_user.id
    ).first()

    if not req:
        raise HTTPException(status_code=404, detail="Request not found")

    if req.status != "quoted":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot pay at this stage. Current status: {req.status}"
        )

    # Will be connected to Razorpay in Phase 7
    req.status = "payment_pending"
    db.commit()
    db.refresh(req)

    return {
        "message": "Proceed to payment",
        "request_id": req.id,
        "amount": float(req.quoted_price),
        "status": req.status
    }


# ── ADMIN ROUTES ─────────────────────────────────────

@router.get("/admin/all", response_model=List[CuttingRequestResponse])
def admin_get_all_requests(
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user)
):
    """Admin sees ALL cutting requests across all users"""
    return db.query(CuttingRequest).order_by(
        CuttingRequest.created_at.desc()
    ).all()


@router.get("/admin/pending", response_model=List[CuttingRequestResponse])
def admin_get_pending(
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user)
):
    """Admin sees only pending requests that need attention"""
    return db.query(CuttingRequest).filter(
        CuttingRequest.status == "pending"
    ).order_by(CuttingRequest.created_at.asc()).all()


@router.patch("/admin/{request_id}/quote")
def admin_set_quote(
    request_id: int,
    quote_data: AdminQuoteRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user)
):
    """Admin sets price and confirms the request"""
    req = db.query(CuttingRequest).filter(
        CuttingRequest.id == request_id
    ).first()

    if not req:
        raise HTTPException(status_code=404, detail="Request not found")

    if req.status != "pending":
        raise HTTPException(
            status_code=400,
            detail=f"Can only quote pending requests. Current: {req.status}"
        )

    req.quoted_price = quote_data.quoted_price
    req.admin_notes = quote_data.admin_notes
    req.status = "quoted"

    db.commit()
    db.refresh(req)

    return {
        "message": "Quote set successfully",
        "request_id": req.id,
        "quoted_price": float(req.quoted_price),
        "status": req.status
    }


@router.patch("/admin/{request_id}/reject")
def admin_reject_request(
    request_id: int,
    reject_data: AdminRejectRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user)
):
    """Admin rejects a cutting request with reason"""
    req = db.query(CuttingRequest).filter(
        CuttingRequest.id == request_id
    ).first()

    if not req:
        raise HTTPException(status_code=404, detail="Request not found")

    if req.status in ["completed", "rejected"]:
        raise HTTPException(
            status_code=400,
            detail="Cannot reject a completed or already rejected request"
        )

    req.status = "rejected"
    req.rejection_reason = reject_data.rejection_reason
    db.commit()
    db.refresh(req)

    return {
        "message": "Request rejected",
        "request_id": req.id,
        "reason": req.rejection_reason
    }


@router.patch("/admin/{request_id}/start")
def admin_start_cutting(
    request_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user)
):
    """Admin marks cutting as in progress after payment confirmed"""
    req = db.query(CuttingRequest).filter(
        CuttingRequest.id == request_id
    ).first()

    if not req:
        raise HTTPException(status_code=404, detail="Request not found")

    if req.status != "paid":
        raise HTTPException(
            status_code=400,
            detail=f"Can only start paid requests. Current: {req.status}"
        )

    req.status = "in_progress"
    db.commit()
    db.refresh(req)

    return {"message": "Cutting started", "status": req.status}


@router.patch("/admin/{request_id}/complete")
def admin_complete_request(
    request_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user)
):
    """Admin marks the cutting job as completed"""
    req = db.query(CuttingRequest).filter(
        CuttingRequest.id == request_id
    ).first()

    if not req:
        raise HTTPException(status_code=404, detail="Request not found")

    if req.status != "in_progress":
        raise HTTPException(
            status_code=400,
            detail=f"Can only complete in-progress requests. Current: {req.status}"
        )

    req.status = "completed"
    db.commit()
    db.refresh(req)

    return {"message": "Request completed successfully", "status": req.status}