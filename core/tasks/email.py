import logging

import resend
from celery import shared_task
from django.conf import settings

from users.models import User
from auth_users.models import AuthCode


logger = logging.getLogger("tasks.email")


@shared_task
def send_code_via_email(user_id):
    try:
        user = User.objects.get(pk=user_id)
        token = AuthCode.objects.get(user=user)

        confirm_code = token.code

        subject = "Your Confirmation Code"

        html_message = f"""
        <!DOCTYPE html>
        <html>
        <body>
            <h2>Hello {user.username},</h2>

            <p>
                Your confirmation code is:
            </p>

            <h1>{confirm_code}</h1>

            <p>
                Please use this code to verify your account.
            </p>

            <p>
                Thank you for registering!
            </p>
        </body>
        </html>
        """

        # Resend API key
        resend.api_key = settings.RESEND_API_KEY

        response = resend.Emails.send({
            "from": settings.EMAIL_ADDR,
            "to": user.email,
            "subject": subject,
            "html": html_message,
        })

        logger.info(
            "Confirmation email sent successfully to %s. Resend response: %s",
            user.email,
            response,
        )

        return {
            "success": True,
            "email": user.email,
            "resend_response": response,
        }

    except User.DoesNotExist:
        logger.error(
            "User with ID %s does not exist.",
            user_id,
        )

        return {
            "success": False,
            "error": "User does not exist.",
        }

    except AuthCode.DoesNotExist:
        logger.error(
            "AuthCode for user ID %s does not exist.",
            user_id,
        )

        return {
            "success": False,
            "error": "AuthCode does not exist.",
        }

    except Exception as e:
        logger.exception(
            "Unhandled exception in send_code_via_email: %s",
            str(e),
        )

        return {
            "success": False,
            "error": str(e),
        }
