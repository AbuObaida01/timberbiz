import logging
from app.config import settings

logger = logging.getLogger(__name__)


def send_otp_sms(phone_number: str, otp: str) -> bool:
    """
    Send OTP via Twilio SMS.
    Returns True on success, False on failure.
    Never logs OTP value.
    """
    try:
        from twilio.rest import Client

        client = Client(
            settings.TWILIO_ACCOUNT_SID,
            settings.TWILIO_AUTH_TOKEN
        )

        message = client.messages.create(
            body=(
                f"Your TimberBiz verification code is: {otp}\n"
                f"This code expires in 5 minutes.\n"
                f"Do not share this code with anyone."
            ),
            from_=settings.TWILIO_PHONE_NUMBER,
            to=phone_number
        )

        logger.info(
            f"OTP SMS sent successfully. SID: {message.sid} "
            f"To: {phone_number[:4]}****"  # Partial log only
        )
        return True

    except Exception as e:
        # Log error but NEVER log the OTP or credentials
        logger.error(f"SMS send failed for {phone_number[:4]}****: {type(e).__name__}")
        return False