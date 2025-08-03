from celery import shared_task
from django.core.mail import send_mail
from users.models import User
from auth_users.models import AuthCode
from django.conf import settings
import logging

logger = logging.getLogger("tasks.email")


@shared_task
def send_code_via_email(id):
    try:
        user = User.objects.get(pk=id)
        token = AuthCode.objects.get(user=user)
        confirm_code = token.code 

        subject = 'Your Confirmation Code'
        message = (
            f"Hello {user.username},\n\n"
            f"Your confirmation code is {confirm_code}.\n\n"
            f"Thank you for registering!"
        )
        
        from_email = settings.EMAIL_ADDR
        recipient_list = [user.email]

        if settings.DEBUG:
            logger.info(f"[DEBUG MODE] Email to {user.email}:\n{message}")
        else:
            send_mail(
                subject=subject,
                message=message,
                from_email=from_email,
                recipient_list=recipient_list,
                fail_silently=False,
            )

    except User.DoesNotExist:
        logger.error(f"User with ID {id} does not exist.")
    except AuthCode.DoesNotExist:
        logger.error(f"AuthCode for user ID {id} does not exist.")
    except Exception as e:
        logger.exception(f"Unhandled exception in send_code_via_email: {str(e)}")
