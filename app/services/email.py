import logging
from app.config import settings

logger = logging.getLogger(__name__)


def send_password_reset_email(
    to_email: str,
    reset_token: str,
    user_name: str
) -> bool:
    """
    Send password reset email via Resend.
    The reset_token is embedded in the link — never logged.
    Returns True on success, False on failure.
    """
    try:
        import resend

        resend.api_key = settings.RESEND_API_KEY

        reset_link = (
            f"{settings.FRONTEND_URL}/reset-password?token={reset_token}"
        )

        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="font-family: Arial, sans-serif; background-color: #f4f4f4; margin: 0; padding: 20px;">
            <div style="max-width: 500px; margin: 0 auto; background: white; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.1);">

                <!-- Header -->
                <div style="background-color: #1A4D17; padding: 28px 32px;">
                    <h1 style="color: white; margin: 0; font-size: 22px;">🌲 TimberBiz</h1>
                </div>

                <!-- Body -->
                <div style="padding: 32px;">
                    <h2 style="color: #1C1C1C; margin-top: 0; font-size: 20px;">
                        Reset Your Password
                    </h2>
                    <p style="color: #555; line-height: 1.6;">
                        Hi {user_name},
                    </p>
                    <p style="color: #555; line-height: 1.6;">
                        Someone requested a password reset for your TimberBiz account.
                        Click the button below to set a new password.
                    </p>

                    <!-- Reset Button -->
                    <div style="text-align: center; margin: 32px 0;">
                        <a href="{reset_link}"
                           style="background-color: #1A4D17; color: white; padding: 14px 32px;
                                  text-decoration: none; border-radius: 8px; font-weight: bold;
                                  font-size: 16px; display: inline-block;">
                            Reset Password
                        </a>
                    </div>

                    <p style="color: #888; font-size: 13px; line-height: 1.6;">
                        This link expires in <strong>30 minutes</strong>.
                    </p>
                    <p style="color: #888; font-size: 13px; line-height: 1.6;">
                        If you did not request this, you can safely ignore this email.
                        Your password will not be changed.
                    </p>

                    <!-- Fallback link -->
                    <div style="background: #f8f8f8; border-radius: 8px; padding: 12px; margin-top: 24px;">
                        <p style="color: #888; font-size: 11px; margin: 0 0 4px 0;">
                            If the button doesn't work, copy this link:
                        </p>
                        <p style="color: #1A4D17; font-size: 11px; margin: 0; word-break: break-all;">
                            {reset_link}
                        </p>
                    </div>
                </div>

                <!-- Footer -->
                <div style="background: #f8f8f8; padding: 16px 32px; text-align: center;">
                    <p style="color: #aaa; font-size: 12px; margin: 0;">
                        © 2026 TimberBiz · Greater Noida
                    </p>
                </div>
            </div>
        </body>
        </html>
        """

        resend.Emails.send({
            "from": settings.EMAIL_FROM,
            "to": [to_email],
            "subject": "Reset your TimberBiz password",
            "html": html_body
        })

        # Log success without logging the token
        logger.info(
            f"Password reset email sent to {to_email[:3]}***@***"
        )
        return True

    except Exception as e:
        logger.error(
            f"Email send failed for {to_email[:3]}***: {type(e).__name__}"
        )
        return False