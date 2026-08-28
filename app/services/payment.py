import razorpay
import hmac
import hashlib
from fastapi import HTTPException
from app.config import settings

# Initialize Razorpay client
client = razorpay.Client(
    auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
)


def create_razorpay_order(amount: float, currency: str = "INR") -> dict:
    """
    Create a Razorpay order.
    Amount must be in paise (multiply rupees by 100).
    """
    try:
        amount_in_paise = int(amount * 100)

        order = client.order.create({
            "amount": amount_in_paise,
            "currency": currency,
            "payment_capture": 1  # Auto capture payment
        })

        return order

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Razorpay order creation failed: {str(e)}"
        )


def verify_razorpay_payment(
    razorpay_order_id: str,
    razorpay_payment_id: str,
    razorpay_signature: str
) -> bool:
    """
    Verify payment signature from Razorpay.
    This confirms payment is genuine and not tampered.
    """
    try:
        # Create expected signature
        message = f"{razorpay_order_id}|{razorpay_payment_id}"

        expected_signature = hmac.new(
            settings.RAZORPAY_KEY_SECRET.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()

        # Compare signatures
        return hmac.compare_digest(
            expected_signature,
            razorpay_signature
        )

    except Exception:
        return False