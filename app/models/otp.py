from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, func
from sqlalchemy.orm import relationship
from app.database import Base


class PhoneVerificationOTP(Base):
    __tablename__ = "phone_verification_otps"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Hashed OTP — never store plaintext
    otp_hash = Column(String(255), nullable=False)

    # Expiry — 5 minutes from creation
    expires_at = Column(DateTime, nullable=False)

    # How many wrong attempts made
    attempts = Column(Integer, default=0, nullable=False)

    # True after successful verification — prevents replay
    used = Column(Boolean, default=False, nullable=False)

    # When this OTP was requested — used for resend cooldown
    created_at = Column(DateTime, server_default=func.now())

    user = relationship("User", backref="otps")