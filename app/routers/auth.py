import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from fastapi.security import OAuth2PasswordRequestForm

from app.database import get_db
from app.models.user import User
from app.models.otp import PhoneVerificationOTP
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
from datetime import datetime

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])


# ── REGISTER ─────────────────────────────────────────────

@router.post("/register", response_model=TokenResponse, status_code=201)
def register(user_data: UserRegister, db: Session = Depends(get_db)):
    """
    Register a new user.
    Creates account in unverified state.
    Sends OTP to phone number.
    Returns token — but phone_verified will be False.
    """

    # Check duplicate email
    existing_email = db.query(User).filter(
        User.email == user_data.email
    ).first()
    if existing_email:
        raise HTTPException(
            status_code=400,
            detail="An account with this email already exists"
        )

    # Check duplicate phone
    if user_data.phone:
        existing_phone = db.query(User).filter(
            User.phone == user_data.phone
        ).first()
        if existing_phone:
            raise HTTPException(
                status_code=400,
                detail="An account with this phone number already exists"
            )

    # Create user — phone_verified starts as False
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

    # Generate and send OTP
    otp_sent = False
    if user_data.phone:
        try:
            raw_otp = create_otp_for_user(new_user.id, db)
            sms_success = send_otp_sms(user_data.phone, raw_otp)
            otp_sent = sms_success
            if not sms_success:
                logger.warning(
                    f"SMS failed for user {new_user.id} — "
                    f"user can resend from app"
                )
        except Exception as e:
            logger.error(f"OTP creation failed for user {new_user.id}: {type(e).__name__}")

    # Create JWT with token_version
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

@router.post("/login", response_model=TokenResponse)
def login(credentials: UserLogin, db: Session = Depends(get_db)):
    """Login and get JWT token."""

    user = db.query(User).filter(User.email == credentials.email).first()

    if not user or not verify_password(credentials.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )

    # Include token_version in JWT
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
def login_swagger(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    """Swagger UI login — accepts form data."""
    user = db.query(User).filter(User.email == form_data.username).first()

    if not user or not verify_password(form_data.password, user.password_hash):
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

@router.post("/verify-phone")
def verify_phone(
    data: VerifyPhoneRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Verify phone number using OTP.
    User must be logged in (JWT required).
    """
    if current_user.phone_verified:
        return {
            "message": "Phone number is already verified.",
            "phone_verified": True
        }

    # Verify OTP — raises HTTPException on failure
    verify_otp_for_user(current_user.id, data.otp, db)

    # Mark phone as verified
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

@router.post("/resend-phone-otp")
def resend_phone_otp(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Resend OTP to registered phone.
    Enforces 60-second cooldown and hourly limit.
    """
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

    # create_otp_for_user enforces cooldown and hourly limits
    raw_otp = create_otp_for_user(current_user.id, db)
    sms_success = send_otp_sms(current_user.phone, raw_otp)

    if not sms_success:
        raise HTTPException(
            status_code=500,
            detail="Failed to send OTP. Please try again in a moment."
        )

    return {
        "message": f"OTP sent to your registered phone number ending in "
                   f"****{current_user.phone[-3:]}",
        "expires_in_minutes": 5,
        "resend_cooldown_seconds": 60
    }


# ── FORGOT PASSWORD ───────────────────────────────────────

@router.post("/forgot-password")
def forgot_password(
    data: ForgotPasswordRequest,
    db: Session = Depends(get_db)
):
    """
    Request a password reset link.
    ALWAYS returns the same generic message whether email
    exists or not — prevents account enumeration.
    """
    SAFE_RESPONSE = {
        "message": "If an account exists with this email, "
                   "a password reset link has been sent."
    }

    user = db.query(User).filter(User.email == data.email).first()

    # If user doesn't exist — return safe response without doing anything
    if not user:
        return SAFE_RESPONSE

    try:
        raw_token = create_reset_token_for_user(user.id, db)
        email_sent = send_password_reset_email(
            to_email=user.email,
            reset_token=raw_token,
            user_name=user.name
        )

        if not email_sent:
            logger.error(
                f"Password reset email failed for user {user.id}"
            )
            # Still return safe response — don't reveal failure

    except Exception as e:
        logger.error(
            f"Forgot password error for user {user.id}: {type(e).__name__}"
        )
        # Still return safe response

    return SAFE_RESPONSE


# ── RESET PASSWORD ────────────────────────────────────────

@router.post("/reset-password")
def reset_password(
    data: ResetPasswordRequest,
    db: Session = Depends(get_db)
):
    """
    Reset password using token from email.
    Validates token, hashes new password, increments
    token_version to invalidate all existing JWTs.
    """

    # Validate token — raises HTTPException if invalid/expired/used
    token_record = validate_reset_token(data.token, db)

    # Get user
    user = db.query(User).filter(
        User.id == token_record.user_id
    ).first()

    if not user:
        raise HTTPException(
            status_code=400,
            detail="Invalid reset token."
        )

    # Update password
    user.password_hash = hash_password(data.new_password)

    # Increment token_version — invalidates ALL existing JWTs
    # Any logged-in sessions will get 401 on next request
    user.token_version = (user.token_version or 0) + 1

    # Mark token as used — prevents replay
    token_record.used = True

    db.commit()

    logger.info(f"Password reset successful for user {user.id}")

    return {
        "message": "Password reset successfully. "
                   "Please log in with your new password.",
        "success": True
    }


# ── PROFILE ───────────────────────────────────────────────

@router.get("/me", response_model=UserResponse)
def get_my_profile(current_user: User = Depends(get_current_user)):
    """Get your own profile — requires login."""
    return current_user


@router.get("/test-admin")
def test_admin_access(
    current_user: User = Depends(get_current_user)
):
    """Test route — returns your role and email."""
    return {
        "message": f"Hello {current_user.name}",
        "role": current_user.role,
        "email": current_user.email,
        "is_admin": current_user.role == "admin",
        "phone_verified": current_user.phone_verified
    }

@router.patch("/update-location", response_model=UserResponse)
def update_location(
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


@router.get("/check-my-distance")
def check_my_distance(
    current_user: User = Depends(get_current_user)
):
    """Check how far you are from the shop."""
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