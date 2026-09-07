from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, func
from sqlalchemy.orm import relationship
from app.database import Base


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # SHA-256 hash of the raw token — never store raw token
    token_hash = Column(String(255), nullable=False, index=True)

    # Expiry — 30 minutes from creation
    expires_at = Column(DateTime, nullable=False)

    # True after use — prevents replay
    used = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime, server_default=func.now())

    user = relationship("User", backref="reset_tokens")