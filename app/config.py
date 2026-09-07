from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str
    SECRET_KEY: str
    ALGORITHM: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int

    CLOUDINARY_CLOUD_NAME: str
    CLOUDINARY_API_KEY: str
    CLOUDINARY_API_SECRET: str

    SHOP_LATITUDE: float
    SHOP_LONGITUDE: float
    MAX_DISTANCE_KM: float

    ADMIN_EMAIL_1: str
    ADMIN_EMAIL_2: str
    ADMIN_PASSWORD_1: str
    ADMIN_PASSWORD_2: str

    RAZORPAY_KEY_ID: str
    RAZORPAY_KEY_SECRET: str

    # Twilio — SMS / OTP
    TWILIO_ACCOUNT_SID: str
    TWILIO_AUTH_TOKEN: str
    TWILIO_PHONE_NUMBER: str

    # Resend — Email / Password Reset
    RESEND_API_KEY: str
    EMAIL_FROM: str
    FRONTEND_URL: str

    class Config:
        env_file = ".env"


settings = Settings()