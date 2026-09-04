from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import List, Optional
from decimal import Decimal

from app.database import get_db
from app.models.tree import Tree, TreeImage
from app.models.user import User
from app.schemas.tree import (
    TreePublicResponse,
    TreePrivateResponse,
    TreeStatusUpdate
)
from app.services.auth import get_current_user, get_admin_user, get_current_user_optional
from app.services.geo import check_within_range
from app.services.cloudinary_service import upload_image
from app.services.tree_classifier import classify_tree_image

router = APIRouter(prefix="/trees", tags=["Tree Listings"])


# ── PUBLIC ROUTES ────────────────────────────────────

@router.get("/", response_model=List[TreePublicResponse])
def get_all_approved_trees(db: Session = Depends(get_db)):
    """
    Public route — anyone can see approved listings.
    NO sensitive data returned here.
    """
    trees = db.query(Tree).filter(
        Tree.status == "approved"
    ).order_by(Tree.created_at.desc()).all()
    return trees


@router.get("/{tree_id}")
def get_tree_detail(
    tree_id: int,
    db: Session = Depends(get_db),
    # current_user: Optional[User] = None
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    Get single tree detail.
    Public → sees basic info only.
    Admin or Uploader → sees full info including price, phone, location.
    """
    tree = db.query(Tree).filter(Tree.id == tree_id).first()

    if not tree:
        raise HTTPException(status_code=404, detail="Listing not found")

    # Check if current user is admin or uploader
    is_admin = current_user and current_user.role == "admin"
    is_uploader = current_user and current_user.id == tree.uploader_id

    if is_admin or is_uploader:
        # Return FULL private data
        return {
            "id": tree.id,
            "uploader_id": tree.uploader_id,
            "title": tree.title,
            "description": tree.description,
            "price": float(tree.price),
            "status": tree.status,
            "latitude": tree.latitude,
            "longitude": tree.longitude,
            "created_at": tree.created_at,
            "images": tree.images,
            "uploader_name": tree.uploader.name,
            "uploader_phone": tree.uploader.phone,
            "uploader_email": tree.uploader.email,
            "data_access": "full"
        }

    # Return PUBLIC data only
    return {
        "id": tree.id,
        "title": tree.title,
        "description": tree.description,
        "status": tree.status,
        "created_at": tree.created_at,
        "images": tree.images,
        "data_access": "public"
    }


# ── PROTECTED ROUTES ─────────────────────────────────

@router.post("/", status_code=201)
async def create_tree_listing(
    title: str = Form(...),
    description: Optional[str] = Form(None),
    price: Decimal = Form(...),
    latitude: Optional[float] = Form(None),
    longitude: Optional[float] = Form(None),
    village_city: Optional[str] = Form(None),
    district: Optional[str] = Form(None),
    state: Optional[str] = Form(None),
    pincode: Optional[str] = Form(None),
    full_address: Optional[str] = Form(None),
    images: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Create a new tree listing.
    Only users within 10km of shop can post.
    Requires at least 1 image.
    Status starts as 'pending' — admin must approve.
    """

    # Use listing location if provided, else use user's registered location
    listing_lat = latitude or current_user.latitude
    listing_lng = longitude or current_user.longitude

    # ── GEO CHECK ──────────────────────────────
    distance = check_within_range(listing_lat, listing_lng)

    # ── VALIDATE IMAGES ────────────────────────
    if not images:
        raise HTTPException(
            status_code=400,
            detail="At least one image is required"
        )

    # Max 5 images per listing
    if len(images) > 5:
        raise HTTPException(
            status_code=400,
            detail="Maximum 5 images allowed per listing"
        )

    # ── CREATE LISTING ─────────────────────────
    new_tree = Tree(
        uploader_id=current_user.id,
        title=title,
        description=description,
        price=price,
        status="pending",
        latitude=listing_lat,
        longitude=listing_lng,
        village_city=village_city or current_user.village_city,
        district=district or current_user.district,
        state=state or current_user.state,
        pincode=pincode or current_user.pincode,
        full_address=full_address or current_user.full_address,
    )
    db.add(new_tree)
    db.commit()
    db.refresh(new_tree)

    # ── UPLOAD IMAGES TO CLOUDINARY ───────────
    uploaded_urls = []
    for image in images:
        # Validate file type
        if image.content_type not in ["image/jpeg", "image/png", "image/webp"]:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file type: {image.content_type}. Only JPEG, PNG, WEBP allowed."
            )

        file_bytes = await image.read()
        image_url = upload_image(file_bytes)

        # Save image record
        tree_image = TreeImage(
            tree_id=new_tree.id,
            image_url=image_url
        )
        db.add(tree_image)
        uploaded_urls.append(image_url)

    db.commit()
    db.refresh(new_tree)

    return {
        "message": "Tree listing submitted successfully. Waiting for admin approval.",
        "listing_id": new_tree.id,
        "status": new_tree.status,
        "distance_from_shop_km": distance,
        "images_uploaded": len(uploaded_urls),
        "image_urls": uploaded_urls
    }


@router.get("/my/listings")
def get_my_listings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """User sees all their own listings with full details"""
    trees = db.query(Tree).filter(
        Tree.uploader_id == current_user.id
    ).order_by(Tree.created_at.desc()).all()

    result = []
    for tree in trees:
        result.append({
            "id": tree.id,
            "title": tree.title,
            "description": tree.description,
            "price": float(tree.price),
            "status": tree.status,
            "latitude": tree.latitude,
            "longitude": tree.longitude,
            "created_at": tree.created_at,
            "images": [{"id": img.id, "url": img.image_url} for img in tree.images]
        })

    return result


@router.delete("/{tree_id}")
def delete_tree_listing(
    tree_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a listing — only the uploader or admin can delete"""
    tree = db.query(Tree).filter(Tree.id == tree_id).first()

    if not tree:
        raise HTTPException(status_code=404, detail="Listing not found")

    is_admin = current_user.role == "admin"
    is_uploader = current_user.id == tree.uploader_id

    if not is_admin and not is_uploader:
        raise HTTPException(
            status_code=403,
            detail="You are not authorised to delete this listing"
        )

    # Delete images first
    db.query(TreeImage).filter(TreeImage.tree_id == tree_id).delete()
    db.delete(tree)
    db.commit()

    return {"message": "Listing deleted successfully"}


# ── ADMIN ROUTES ─────────────────────────────────────

@router.get("/admin/pending")
def admin_get_pending_listings(
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user)
):
    """Admin sees all pending listings waiting for approval"""
    trees = db.query(Tree).filter(
        Tree.status == "pending"
    ).order_by(Tree.created_at.asc()).all()

    result = []
    for tree in trees:
        result.append({
            "id": tree.id,
            "title": tree.title,
            "description": tree.description,
            "price": float(tree.price),
            "status": tree.status,
            "latitude": tree.latitude,
            "longitude": tree.longitude,
            "created_at": tree.created_at,
            "uploader_name": tree.uploader.name,
            "uploader_phone": tree.uploader.phone,
            "uploader_email": tree.uploader.email,
            "images": [{"id": img.id, "url": img.image_url} for img in tree.images]
        })

    return result


@router.patch("/admin/{tree_id}/status")
def admin_update_tree_status(
    tree_id: int,
    status_data: TreeStatusUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user)
):
    """
    Admin approves or rejects a tree listing.
    Status must be 'approved' or 'rejected'.
    """
    if status_data.status not in ["approved", "rejected"]:
        raise HTTPException(
            status_code=400,
            detail="Status must be 'approved' or 'rejected'"
        )

    tree = db.query(Tree).filter(Tree.id == tree_id).first()

    if not tree:
        raise HTTPException(status_code=404, detail="Listing not found")

    if tree.status != "pending":
        raise HTTPException(
            status_code=400,
            detail=f"Can only update pending listings. Current status: {tree.status}"
        )

    tree.status = status_data.status
    db.commit()
    db.refresh(tree)

    return {
        "message": f"Listing {status_data.status} successfully",
        "listing_id": tree.id,
        "new_status": tree.status
    }


@router.get("/admin/all")
def admin_get_all_listings(
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user)
):
    """Admin sees ALL listings regardless of status"""
    trees = db.query(Tree).order_by(Tree.created_at.desc()).all()

    result = []
    for tree in trees:
        result.append({
            "id": tree.id,
            "title": tree.title,
            "price": float(tree.price),
            "status": tree.status,
            "created_at": tree.created_at,
            "uploader_name": tree.uploader.name,
            "uploader_email": tree.uploader.email,
            "images_count": len(tree.images)
        })

    return result