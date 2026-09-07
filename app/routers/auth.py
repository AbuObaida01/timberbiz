import logging
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from fastapi.security import OAuth2PasswordRequestForm

from app.database import get_db
from app.models.user import User
from app.schemas.user import (
    UserRegister, UserLogin, UserResponse,
    TokenResponse, LocationUpdate,
    VerifyPhoneRequest, ForgotPasswordRequest,
    ResetPasswordRequest
)
from app.services.auth import (
    hash_password, verify_password,
    create_access_token, get_current_user
)
from app.services.geo import haversine_distance, check_within_range
from app.services.sms import send_otp_sms
from app.services.email import send_password_reset_email
from app.services.otp_service import create_otp_for_user, verify_otp_for_user
from app.services.reset_service import (
    create_reset_token_for_user, validate_reset_token
)
from app.config import settings
from app.limiter import limiter
from datetime import datetime

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])


# ── REGISTER ─────────────────────────────────────────────
# 3 registrations per minute per IP
@router.post("/register", response_model=TokenResponse, status_code=201)
@limiter.limit("3/minute")
def register(
    request: Request,
    user_data: UserRegister,
    db: Session = Depends(get_db)
):
    """
    Register a new user.
    Creates account in unverified state.
    Sends OTP to phone number.
    """
    existing_email = db.query(User).filter(
        User.email == user_data.email
    ).first()
    if existing_email:
        raise HTTPException(
            status_code=400,
            detail="An account with this email already exists"
        )

    if user_data.phone:
        existing_phone = db.query(User).filter(
            User.phone == user_data.phone
        ).first()
        if existing_phone:
            raise HTTPException(
                status_code=400,
                detail="An account with this phone number already exists"
            )

    new_user = User(
        name=user_data.name,
        email=user_data.email,
        phone=user_data.phone,
        password_hash=hash_password(user_data.password),
        role="user",
        phone_verified=False,
        token_version=0,
        latitude=user_data.latitude,
        longitude=user_data.longitude,
        village_city=user_data.village_city,
        district=user_data.district,
        state=user_data.state,
        pincode=user_data.pincode,
        full_address=user_data.full_address,
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    otp_sent = False
    if user_data.phone:
        try:
            raw_otp = create_otp_for_user(new_user.id, db)
            sms_success = send_otp_sms(user_data.phone, raw_otp)
            otp_sent = sms_success
            if not sms_success:
                logger.warning(
                    f"SMS failed for user {new_user.id}"
                )
        except Exception as e:
            logger.error(
                f"OTP creation failed for user {new_user.id}: "
                f"{type(e).__name__}"
            )

    token = create_access_token({
        "user_id": new_user.id,
        "token_version": new_user.token_version
    })

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user=new_user,
        phone_verified=new_user.phone_verified,
        requires_phone_verification=not new_user.phone_verified
    )


# ── LOGIN ─────────────────────────────────────────────────
# 5 login attempts per minute per IP
@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")
def login(
    request: Request,
    credentials: UserLogin,
    db: Session = Depends(get_db)
):
    """Login and get JWT token."""
    user = db.query(User).filter(
        User.email == credentials.email
    ).first()

    if not user or not verify_password(
        credentials.password, user.password_hash
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )

    token = create_access_token({
        "user_id": user.id,
        "token_version": user.token_version
    })

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user=user,
        phone_verified=user.phone_verified,
        requires_phone_verification=not user.phone_verified
    )


# ── SWAGGER LOGIN ─────────────────────────────────────────
@router.post("/login/swagger", include_in_schema=False)
@limiter.limit("10/minute")
def login_swagger(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    """Swagger UI login — accepts form data."""
    user = db.query(User).filter(
        User.email == form_data.username
    ).first()

    if not user or not verify_password(
        form_data.password, user.password_hash
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )

    token = create_access_token({
        "user_id": user.id,
        "token_version": user.token_version
    })

    return {"access_token": token, "token_type": "bearer"}


# ── VERIFY PHONE ──────────────────────────────────────────
# 10 OTP attempts per minute per IP
@router.post("/verify-phone")
@limiter.limit("10/minute")
def verify_phone(
    request: Request,
    data: VerifyPhoneRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Verify phone number using OTP."""
    if current_user.phone_verified:
        return {
            "message": "Phone number is already verified.",
            "phone_verified": True
        }

    verify_otp_for_user(current_user.id, data.otp, db)

    current_user.phone_verified = True
    current_user.phone_verified_at = datetime.utcnow()
    db.commit()
    db.refresh(current_user)

    logger.info(f"Phone verified for user {current_user.id}")

    return {
        "message": "Phone number verified successfully! ✅",
        "phone_verified": True
    }


# ── RESEND OTP ────────────────────────────────────────────
# 3 resend attempts per minute per IP
@router.post("/resend-phone-otp")
@limiter.limit("3/minute")
def resend_phone_otp(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Resend OTP — enforces 60s cooldown and hourly limit."""
    if current_user.phone_verified:
        return {
            "message": "Phone is already verified.",
            "phone_verified": True
        }

    if not current_user.phone:
        raise HTTPException(
            status_code=400,
            detail="No phone number on this account."
        )

    raw_otp = create_otp_for_user(current_user.id, db)
    sms_success = send_otp_sms(current_user.phone, raw_otp)

    if not sms_success:
        raise HTTPException(
            status_code=500,
            detail="Failed to send OTP. Please try again in a moment."
        )

    return {
        "message": (
            f"OTP sent to your registered phone number ending in "
            f"****{current_user.phone[-3:]}"
        ),
        "expires_in_minutes": 5,
        "resend_cooldown_seconds": 60
    }


# ── FORGOT PASSWORD ───────────────────────────────────────
# 3 requests per minute per IP — prevents email spam
@router.post("/forgot-password")
@limiter.limit("3/minute")
def forgot_password(
    request: Request,
    data: ForgotPasswordRequest,
    db: Session = Depends(get_db)
):
    """
    Request password reset link.
    Always returns same message — prevents account enumeration.
    """
    SAFE_RESPONSE = {
        "message": (
            "If an account exists with this email, "
            "a password reset link has been sent."
        )
    }

    user = db.query(User).filter(User.email == data.email).first()

    if not user:
        return SAFE_RESPONSE

    try:
        raw_token = create_reset_token_for_user(user.id, db)
        send_password_reset_email(
            to_email=user.email,
            reset_token=raw_token,
            user_name=user.name
        )
    except Exception as e:
        logger.error(
            f"Forgot password error for user {user.id}: "
            f"{type(e).__name__}"
        )

    return SAFE_RESPONSE


# ── RESET PASSWORD ────────────────────────────────────────
# 5 attempts per minute per IP
@router.post("/reset-password")
@limiter.limit("5/minute")
def reset_password(
    request: Request,
    data: ResetPasswordRequest,
    db: Session = Depends(get_db)
):
    """
    Reset password using email token.
    Increments token_version — invalidates all existing JWTs.
    """
    token_record = validate_reset_token(data.token, db)

    user = db.query(User).filter(
        User.id == token_record.user_id
    ).first()

    if not user:
        raise HTTPException(
            status_code=400,
            detail="Invalid reset token."
        )

    user.password_hash = hash_password(data.new_password)
    user.token_version = (user.token_version or 0) + 1
    token_record.used = True

    db.commit()

    logger.info(f"Password reset successful for user {user.id}")

    return {
        "message": (
            "Password reset successfully. "
            "Please log in with your new password."
        ),
        "success": True
    }


# ── PROFILE ───────────────────────────────────────────────
# 30 requests per minute — normal browsing
@router.get("/me", response_model=UserResponse)
@limiter.limit("30/minute")
def get_my_profile(
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """Get your own profile."""
    return current_user


# ── TEST ADMIN ────────────────────────────────────────────
@router.get("/test-admin")
@limiter.limit("20/minute")
def test_admin_access(
    request: Request,
    current_user: User = Depends(get_current_user)
):
    return {
        "message": f"Hello {current_user.name}",
        "role": current_user.role,
        "email": current_user.email,
        "is_admin": current_user.role == "admin",
        "phone_verified": current_user.phone_verified
    }


# ── UPDATE LOCATION ───────────────────────────────────────
@router.patch("/update-location", response_model=UserResponse)
@limiter.limit("20/minute")
def update_location(
    request: Request,
    location: LocationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """User can update their GPS location."""
    current_user.latitude = location.latitude
    current_user.longitude = location.longitude
    if location.village_city:
        current_user.village_city = location.village_city
    if location.district:
        current_user.district = location.district
    if location.state:
        current_user.state = location.state
    if location.pincode:
        current_user.pincode = location.pincode
    if location.full_address:
        current_user.full_address = location.full_address
    db.commit()
    db.refresh(current_user)
    return current_user


# ── CHECK DISTANCE ────────────────────────────────────────
@router.get("/check-my-distance")
@limiter.limit("30/minute")
def check_my_distance(
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """Check distance from shop."""
    if current_user.latitude is None or current_user.longitude is None:
        return {
            "message": "Location not set",
            "distance_km": None,
            "within_range": False,
            "max_allowed_km": settings.MAX_DISTANCE_KM
        }

    distance = haversine_distance(
        current_user.latitude,
        current_user.longitude,
        settings.SHOP_LATITUDE,
        settings.SHOP_LONGITUDE
    )

    return {
        "your_location": {
            "latitude": current_user.latitude,
            "longitude": current_user.longitude
        },
        "shop_location": {
            "latitude": settings.SHOP_LATITUDE,
            "longitude": settings.SHOP_LONGITUDE
        },
        "distance_km": distance,
        "max_allowed_km": settings.MAX_DISTANCE_KM,
        "within_range": distance <= settings.MAX_DISTANCE_KM
    }