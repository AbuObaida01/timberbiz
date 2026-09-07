import secrets
import hashlib
import logging
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.models.password_reset import PasswordResetToken
from app.models.user import User
from fastapi import HTTPException, status

logger = logging.getLogger(__name__)

RESET_TOKEN_EXPIRE_MINUTES = 30


def generate_reset_token() -> str:
    """
    Generate a cryptographically secure URL-safe reset token.
    64 bytes = 512 bits of entropy — impossible to brute force.
    Never stored raw — only its SHA-256 hash is stored.
    """
    return secrets.token_urlsafe(64)


def hash_token(raw_token: str) -> str:
    """SHA-256 hash of raw token for safe DB storage."""
    return hashlib.sha256(raw_token.encode()).hexdigest()


def create_reset_token_for_user(user_id: int, db: Session) -> str:
    """
    Create a password reset token for a user.
    Invalidates all previous reset tokens for this user.
    Returns the raw token — caller sends it via email.
    Raw token is NEVER stored in DB.
    """

    # Invalidate all previous reset tokens for this user
    db.query(PasswordResetToken).filter(
        PasswordResetToken.user_id == user_id,
        PasswordResetToken.used == False
    ).update({"used": True})
    db.commit()

    # Generate new token
    raw_token = generate_reset_token()
    token_hash = hash_token(raw_token)

    new_token = PasswordResetToken(
        user_id=user_id,
        token_hash=token_hash,
        expires_at=datetime.utcnow() + timedelta(
            minutes=RESET_TOKEN_EXPIRE_MINUTES
        ),
        used=False
    )
    db.add(new_token)
    db.commit()

    # Return raw token — to be embedded in email link
    # It is NEVER logged here
    return raw_token


def validate_reset_token(raw_token: str, db: Session) -> PasswordResetToken:
    """
    Validate a password reset token.
    Checks: exists, not expired, not used.
    Returns the token record on success.
    Raises HTTPException on failure.
    """
    token_hash = hash_token(raw_token)

    token_record = db.query(PasswordResetToken).filter(
        PasswordResetToken.token_hash == token_hash,
        PasswordResetToken.used == False
    ).first()

    if not token_record:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset link. Please request a new one."
        )

    if datetime.utcnow() > token_record.expires_at:
        token_record.used = True
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reset link has expired. Please request a new one."
        )

    return token_record