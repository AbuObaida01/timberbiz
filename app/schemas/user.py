from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional
from datetime import datetime


class UserRegister(BaseModel):
    name: str
    email: EmailStr
    phone: str  # Required now — needed for OTP
    password: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    village_city: Optional[str] = None
    district: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None
    full_address: Optional[str] = None

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v):
        digits = v.replace("+", "").replace("-", "").replace(" ", "")
        if not digits.isdigit():
            raise ValueError("Phone number must contain only digits")
        if len(digits) < 10 or len(digits) > 15:
            raise ValueError("Phone number must be 10-15 digits")
        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: int
    name: str
    email: str
    phone: Optional[str]
    role: str
    phone_verified: bool
    latitude: Optional[float]
    longitude: Optional[float]
    village_city: Optional[str]
    district: Optional[str]
    state: Optional[str]
    pincode: Optional[str]
    full_address: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse
    phone_verified: bool
    requires_phone_verification: bool = False


class LocationUpdate(BaseModel):
    latitude: float
    longitude: float
    village_city: Optional[str] = None
    district: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None
    full_address: Optional[str] = None


# ── New schemas for OTP and Password Reset ──────────────

class VerifyPhoneRequest(BaseModel):
    otp: str

    @field_validator("otp")
    @classmethod
    def validate_otp(cls, v):
        if not v.isdigit() or len(v) != 6:
            raise ValueError("OTP must be exactly 6 digits")
        return v


class ResendOTPRequest(BaseModel):
    pass  # User identified by JWT token


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v