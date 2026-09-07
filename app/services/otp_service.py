import secrets
import hashlib
import logging
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.models.otp import PhoneVerificationOTP
from app.models.user import User
from fastapi import HTTPException, status

logger = logging.getLogger(__name__)

# Constants
OTP_EXPIRE_MINUTES = 5
OTP_MAX_ATTEMPTS = 5
OTP_RESEND_COOLDOWN_SECONDS = 60
OTP_MAX_RESENDS_PER_HOUR = 5


def generate_otp() -> str:
    """
    Generate a cryptographically secure 6-digit OTP.
    Uses secrets module — NOT random, NOT predictable.
    """
    # secrets.randbelow(900000) gives 0-899999, add 100000 = 100000-999999
    return str(100000 + secrets.randbelow(900000))


def hash_otp(otp: str) -> str:
    """
    Hash OTP using SHA-256.
    Never store plaintext OTP.
    """
    return hashlib.sha256(otp.encode()).hexdigest()


def create_otp_for_user(user_id: int, db: Session) -> str:
    """
    Create a new OTP for a user.
    Invalidates all previous OTPs for this user.
    Enforces resend cooldown and hourly limits.
    Returns the raw OTP (to be sent via SMS — never stored raw).
    """

    # Check resend cooldown — was an OTP sent in last 60 seconds?
    recent_otp = db.query(PhoneVerificationOTP).filter(
        PhoneVerificationOTP.user_id == user_id,
        PhoneVerificationOTP.used == False
    ).order_by(PhoneVerificationOTP.created_at.desc()).first()

    if recent_otp:
        seconds_since_last = (
            datetime.utcnow() - recent_otp.created_at
        ).total_seconds()

        if seconds_since_last < OTP_RESEND_COOLDOWN_SECONDS:
            remaining = int(OTP_RESEND_COOLDOWN_SECONDS - seconds_since_last)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Please wait {remaining} seconds before requesting a new OTP."
            )

    # Check hourly limit — max 5 OTPs per hour
    one_hour_ago = datetime.utcnow() - timedelta(hours=1)
    recent_count = db.query(PhoneVerificationOTP).filter(
        PhoneVerificationOTP.user_id == user_id,
        PhoneVerificationOTP.created_at >= one_hour_ago
    ).count()

    if recent_count >= OTP_MAX_RESENDS_PER_HOUR:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many OTP requests. Please try again in an hour."
        )

    # Invalidate all previous unused OTPs for this user
    db.query(PhoneVerificationOTP).filter(
        PhoneVerificationOTP.user_id == user_id,
        PhoneVerificationOTP.used == False
    ).delete()
    db.commit()

    # Generate new OTP
    raw_otp = generate_otp()
    otp_hash = hash_otp(raw_otp)

    new_otp = PhoneVerificationOTP(
        user_id=user_id,
        otp_hash=otp_hash,
        expires_at=datetime.utcnow() + timedelta(minutes=OTP_EXPIRE_MINUTES),
        attempts=0,
        used=False
    )
    db.add(new_otp)
    db.commit()

    # Return raw OTP — caller sends it via SMS, never stores it
    return raw_otp


def verify_otp_for_user(user_id: int, raw_otp: str, db: Session) -> bool:
    """
    Verify OTP for a user.
    Enforces:
    - Expiry check
    - Attempt limit (max 5 wrong attempts)
    - Single use (marks as used on success)
    - Replay prevention
    Returns True on success, raises HTTPException on failure.
    """

    # Get the latest unused OTP for this user
    otp_record = db.query(PhoneVerificationOTP).filter(
        PhoneVerificationOTP.user_id == user_id,
        PhoneVerificationOTP.used == False
    ).order_by(PhoneVerificationOTP.created_at.desc()).first()

    if not otp_record:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active OTP found. Please request a new one."
        )

    # Check expiry
    if datetime.utcnow() > otp_record.expires_at:
        # Mark as used so it can't be retried
        otp_record.used = True
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OTP has expired. Please request a new one."
        )

    # Check attempt limit
    if otp_record.attempts >= OTP_MAX_ATTEMPTS:
        otp_record.used = True
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many incorrect attempts. Please request a new OTP."
        )

    # Verify hash
    submitted_hash = hash_otp(raw_otp)
    if submitted_hash != otp_record.otp_hash:
        # Increment attempts
        otp_record.attempts += 1
        db.commit()

        remaining = OTP_MAX_ATTEMPTS - otp_record.attempts
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Incorrect OTP. {remaining} attempt(s) remaining."
        )

    # OTP is correct — mark as used (prevents replay)
    otp_record.used = True
    db.commit()

    return True