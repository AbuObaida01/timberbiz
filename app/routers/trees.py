from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
    UploadFile,
    File,
    Form
)
from sqlalchemy.orm import Session
from typing import List, Optional
from decimal import Decimal
import logging

from app.database import get_db
from app.models.tree import Tree, TreeImage
from app.models.user import User
from app.schemas.tree import (
    TreePublicResponse,
    TreePrivateResponse,
    TreeStatusUpdate
)
from app.services.auth import (
    get_current_user,
    get_admin_user,
    get_current_user_optional
)
from app.services.geo import check_within_range
from app.services.cloudinary_service import upload_image
from app.services.tree_classifier import check_all_images


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/trees",
    tags=["Tree Listings"]
)


# ============================================================
# PUBLIC ROUTES
# ============================================================

@router.get("/", response_model=List[TreePublicResponse])
def get_all_approved_trees(
    db: Session = Depends(get_db)
):
    """
    Public route — anyone can see approved listings.
    NO sensitive data returned here.
    """

    trees = (
        db.query(Tree)
        .filter(Tree.status == "approved")
        .order_by(Tree.created_at.desc())
        .all()
    )

    return trees


# ============================================================
# PROTECTED ROUTES
# ============================================================

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

    Every image is checked by ML classifier separately.
    All images must pass — any failure blocks the listing.
    """

    # ========================================================
    # 1. GEO CHECK
    # ========================================================

    listing_lat = (
        latitude
        if latitude is not None
        else current_user.latitude
    )

    listing_lng = (
        longitude
        if longitude is not None
        else current_user.longitude
    )

    distance = check_within_range(
        listing_lat,
        listing_lng
    )

    # ========================================================
    # 2. IMAGE COUNT VALIDATION
    # ========================================================

    if not images or len(images) == 0:
        raise HTTPException(
            status_code=400,
            detail="At least one image is required"
        )

    if len(images) > 5:
        raise HTTPException(
            status_code=400,
            detail="Maximum 5 images allowed per listing"
        )

    # ========================================================
    # 3. READ AND VALIDATE ALL IMAGE BYTES
    # ========================================================
    # We read and validate everything BEFORE creating
    # anything in the database.

    image_data = []

    for image in images:

        # Validate file type
        if image.content_type not in [
            "image/jpeg",
            "image/png",
            "image/webp"
        ]:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Image {image.filename}: "
                    f"Invalid file type '{image.content_type}'. "
                    f"Only JPEG, PNG, WEBP allowed."
                )
            )

        # Read file
        file_bytes = await image.read()

        # Validate file size
        # Maximum 10MB per image
        if len(file_bytes) > 10 * 1024 * 1024:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Image {image.filename} is too large. "
                    f"Maximum 10MB per image."
                )
            )

        image_data.append({
            "filename": image.filename,
            "bytes": file_bytes,
            "content_type": image.content_type
        })

    # ========================================================
    # 4. ML CLASSIFICATION
    # ========================================================

    logger.info(
        f"Running ML classification on "
        f"{len(image_data)} images..."
    )

    image_bytes_list = [
        img["bytes"]
        for img in image_data
    ]

    classification_result = check_all_images(
        image_bytes_list
    )

    logger.info(
        f"ML Result: "
        f"{classification_result['passed']}/"
        f"{classification_result['total_images']} passed"
    )

    # ========================================================
    # 5. BLOCK LISTING IF ANY IMAGE FAILS
    # ========================================================

    if not classification_result["all_passed"]:

        failed_nums = (
            classification_result["failed_image_numbers"]
        )

        failed_results = [
            result
            for result in classification_result["results"]
            if not result["is_tree"]
        ]

        # Build individual error messages
        error_details = []

        for result in failed_results:
            error_details.append(
                f"Image {result['image_number']}: "
                f"{result['reason']}"
            )

        raise HTTPException(
            status_code=400,
            detail={
                "message": (
                    f"{classification_result['failed']} out of "
                    f"{classification_result['total_images']} "
                    f"image(s) failed the tree verification check."
                ),
                "failed_images": failed_nums,
                "details": error_details,
                "tip": (
                    "Please upload clear photos showing the actual "
                    "tree. Avoid blurry, dark, or irrelevant images."
                )
            }
        )

    # ========================================================
    # 6. CREATE LISTING IN DATABASE
    # ========================================================

    new_tree = Tree(
        uploader_id=current_user.id,
        title=title,
        description=description,
        price=price,
        status="pending",

        latitude=listing_lat,
        longitude=listing_lng,

        village_city=(
            village_city
            or current_user.village_city
        ),

        district=(
            district
            or current_user.district
        ),

        state=(
            state
            or current_user.state
        ),

        pincode=(
            pincode
            or current_user.pincode
        ),

        full_address=(
            full_address
            or current_user.full_address
        )
    )

    db.add(new_tree)
    db.commit()
    db.refresh(new_tree)

    # ========================================================
    # 7. UPLOAD ALL IMAGES TO CLOUDINARY
    # ========================================================

    uploaded_urls = []

    for img_data in image_data:

        try:

            image_url = upload_image(
                img_data["bytes"],
                folder="timberbiz/trees"
            )

            tree_image = TreeImage(
                tree_id=new_tree.id,
                image_url=image_url
            )

            db.add(tree_image)

            uploaded_urls.append(
                image_url
            )

        except Exception as e:

            logger.exception(
                "Image upload failed"
            )

            # Delete TreeImage records created so far
            db.query(TreeImage).filter(
                TreeImage.tree_id == new_tree.id
            ).delete()

            # Delete the tree listing
            db.delete(new_tree)

            db.commit()

            raise HTTPException(
                status_code=500,
                detail=f"Image upload failed: {str(e)}"
            )

    # Save image records
    db.commit()

    db.refresh(new_tree)

    # ========================================================
    # 8. RESPONSE
    # ========================================================

    return {
        "message": (
            "Listing submitted successfully. "
            "Waiting for admin approval."
        ),
        "listing_id": new_tree.id,
        "status": new_tree.status,
        "distance_from_shop_km": distance,
        "images_uploaded": len(uploaded_urls),
        "ml_verification": {
            "passed": classification_result["passed"],
            "total": classification_result["total_images"],
            "message": "All images verified as trees"
        }
    }


# ============================================================
# MY LISTINGS
# ============================================================

@router.get("/my/listings")
def get_my_listings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    User sees all their own listings with full details.
    """

    trees = (
        db.query(Tree)
        .filter(
            Tree.uploader_id == current_user.id
        )
        .order_by(Tree.created_at.desc())
        .all()
    )

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
            "images": [
                {
                    "id": img.id,
                    "url": img.image_url
                }
                for img in tree.images
            ]
        })

    return result


# ============================================================
# ADMIN ROUTES
# ============================================================

@router.get("/admin/pending")
def admin_get_pending_listings(
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user)
):
    """
    Admin sees all pending listings waiting for approval.
    """

    trees = (
        db.query(Tree)
        .filter(
            Tree.status == "pending"
        )
        .order_by(Tree.created_at.asc())
        .all()
    )

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
            "images": [
                {
                    "id": img.id,
                    "url": img.image_url
                }
                for img in tree.images
            ]
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

    if status_data.status not in [
        "approved",
        "rejected"
    ]:
        raise HTTPException(
            status_code=400,
            detail=(
                "Status must be 'approved' "
                "or 'rejected'"
            )
        )

    tree = (
        db.query(Tree)
        .filter(Tree.id == tree_id)
        .first()
    )

    if not tree:
        raise HTTPException(
            status_code=404,
            detail="Listing not found"
        )

    if tree.status != "pending":
        raise HTTPException(
            status_code=400,
            detail=(
                "Can only update pending listings. "
                f"Current status: {tree.status}"
            )
        )

    tree.status = status_data.status

    db.commit()
    db.refresh(tree)

    return {
        "message": (
            f"Listing {status_data.status} successfully"
        ),
        "listing_id": tree.id,
        "new_status": tree.status
    }


@router.get("/admin/all")
def admin_get_all_listings(
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user)
):
    """
    Admin sees ALL listings regardless of status.
    """

    trees = (
        db.query(Tree)
        .order_by(Tree.created_at.desc())
        .all()
    )

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


# ============================================================
# SINGLE TREE DETAIL
# ============================================================

@router.get("/{tree_id}")
def get_tree_detail(
    tree_id: int,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(
        get_current_user_optional
    )
):
    """
    Get single tree detail.

    Public:
        Sees basic information only.

    Admin or uploader:
        Sees full information including
        price, phone and location.
    """

    tree = (
        db.query(Tree)
        .filter(Tree.id == tree_id)
        .first()
    )

    if not tree:
        raise HTTPException(
            status_code=404,
            detail="Listing not found"
        )

    # Check if current user is admin
    # or the uploader
    is_admin = (
        current_user is not None
        and current_user.role == "admin"
    )

    is_uploader = (
        current_user is not None
        and current_user.id == tree.uploader_id
    )

    # ========================================================
    # FULL DATA FOR ADMIN / UPLOADER
    # ========================================================

    if is_admin or is_uploader:

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

    # ========================================================
    # PUBLIC DATA
    # ========================================================

    return {
        "id": tree.id,
        "title": tree.title,
        "description": tree.description,
        "status": tree.status,
        "created_at": tree.created_at,
        "images": tree.images,
        "data_access": "public"
    }


# ============================================================
# DELETE TREE LISTING
# ============================================================

@router.delete("/{tree_id}")
def delete_tree_listing(
    tree_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Delete a listing.

    Only the uploader or admin can delete.
    """

    tree = (
        db.query(Tree)
        .filter(Tree.id == tree_id)
        .first()
    )

    if not tree:
        raise HTTPException(
            status_code=404,
            detail="Listing not found"
        )

    is_admin = (
        current_user.role == "admin"
    )

    is_uploader = (
        current_user.id == tree.uploader_id
    )

    if not is_admin and not is_uploader:
        raise HTTPException(
            status_code=403,
            detail=(
                "You are not authorised "
                "to delete this listing"
            )
        )

    # Delete image records first
    db.query(TreeImage).filter(
        TreeImage.tree_id == tree_id
    ).delete()

    # Delete tree
    db.delete(tree)

    db.commit()

    return {
        "message": "Listing deleted successfully"
    }