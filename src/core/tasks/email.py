import logging

import requests
import resend
from celery import shared_task
from django.conf import settings

from users.models import User
from auth_users.models import AuthCode


logger = logging.getLogger("tasks.email")


def configure_resend_proxy():
    """
    Configure proxy for Resend's requests-based HTTP client.

    If SEND_EMAIL_WITH_PROXY is enabled, all requests made by
    the Resend SDK will use EMAIL_PROXY.
    """

    if not settings.SEND_EMAIL_WITH_PROXY:
        return

    proxy = settings.EMAIL_PROXY

    if not proxy:
        logger.warning(
            "SEND_EMAIL_WITH_PROXY is enabled but EMAIL_PROXY is empty."
        )
        return

    proxies = {
        "http": proxy,
        "https": proxy,
    }

    # Avoid wrapping requests.request multiple times
    if getattr(requests.request, "_resend_proxy_configured", False):
        return

    original_request = requests.request

    def proxied_request(method, url, **kwargs):
        kwargs.setdefault("proxies", proxies)
        return original_request(method, url, **kwargs)

    proxied_request._resend_proxy_configured = True

    requests.request = proxied_request

    logger.info(
        "Resend email proxy enabled: %s",
        proxy,
    )


@shared_task
def send_code_via_email(user_id):
    try:
        user = User.objects.get(pk=user_id)
        token = AuthCode.objects.get(user=user)

        confirm_code = token.code

        subject = "Your Confirmation Code"

        html_message = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">

    <meta
        name="viewport"
        content="width=device-width, initial-scale=1.0"
    >

    <title>Confirmation Code</title>
</head>

<body
    style="
        margin: 0;
        padding: 0;
        background-color: #081325;
        font-family:
            -apple-system,
            BlinkMacSystemFont,
            'Segoe UI',
            Roboto,
            Helvetica,
            Arial,
            sans-serif;
        color: #ffffff;
    "
>

    <table
        width="100%"
        cellpadding="0"
        cellspacing="0"
        border="0"
        style="
            background-color: #081325;
            padding: 40px 20px;
        "
    >
        <tr>
            <td align="center">

                <table
                    width="100%"
                    cellpadding="0"
                    cellspacing="0"
                    border="0"
                    style="
                        max-width: 560px;
                        background-color: #101d33;
                        border: 1px solid #243451;
                        border-radius: 16px;
                        overflow: hidden;
                    "
                >

                    <!-- Header -->
                    <tr>
                        <td
                            style="
                                padding: 32px 32px 24px 32px;
                                text-align: center;
                                background-color: #0d1a2f;
                            "
                        >

                            <div
                                style="
                                    display: inline-block;
                                    width: 56px;
                                    height: 56px;
                                    line-height: 56px;
                                    border-radius: 14px;
                                    background-color: #ffffff;
                                    color: #081325;
                                    font-size: 20px;
                                    font-weight: 800;
                                    letter-spacing: -1px;
                                "
                            >
                                PD
                            </div>

                            <h1
                                style="
                                    margin: 20px 0 0 0;
                                    font-size: 24px;
                                    line-height: 32px;
                                    font-weight: 700;
                                    color: #ffffff;
                                "
                            >
                                Verify your account
                            </h1>

                        </td>
                    </tr>

                    <!-- Content -->
                    <tr>
                        <td
                            style="
                                padding: 32px;
                            "
                        >

                            <p
                                style="
                                    margin: 0 0 16px 0;
                                    font-size: 16px;
                                    line-height: 26px;
                                    color: #d6deeb;
                                "
                            >
                                Hello
                                <strong style="color: #ffffff;">
                                    {user.username}
                                </strong>,
                            </p>

                            <p
                                style="
                                    margin: 0 0 24px 0;
                                    font-size: 15px;
                                    line-height: 25px;
                                    color: #aebbd0;
                                "
                            >
                                Use the confirmation code below to verify
                                your account. This code is required to
                                complete your registration.
                            </p>

                            <!-- Code -->
                            <table
                                width="100%"
                                cellpadding="0"
                                cellspacing="0"
                                border="0"
                            >
                                <tr>
                                    <td
                                        align="center"
                                        style="
                                            padding: 24px;
                                            background-color: #081325;
                                            border: 1px solid #2b3c5b;
                                            border-radius: 12px;
                                        "
                                    >

                                        <p
                                            style="
                                                margin: 0 0 8px 0;
                                                font-size: 12px;
                                                line-height: 18px;
                                                text-transform: uppercase;
                                                letter-spacing: 2px;
                                                color: #7f90aa;
                                            "
                                        >
                                            Confirmation code
                                        </p>

                                        <div
                                            style="
                                                font-size: 36px;
                                                line-height: 44px;
                                                font-weight: 800;
                                                letter-spacing: 8px;
                                                color: #ffffff;
                                            "
                                        >
                                            {confirm_code}
                                        </div>

                                    </td>
                                </tr>
                            </table>

                            <p
                                style="
                                    margin: 24px 0 0 0;
                                    font-size: 13px;
                                    line-height: 21px;
                                    color: #7f90aa;
                                    text-align: center;
                                "
                            >
                                If you did not create this account,
                                you can safely ignore this email.
                            </p>

                        </td>
                    </tr>

                    <!-- Footer -->
                    <tr>
                        <td
                            style="
                                padding: 20px 32px;
                                background-color: #0d1a2f;
                                border-top: 1px solid #243451;
                                text-align: center;
                            "
                        >

                            <p
                                style="
                                    margin: 0;
                                    font-size: 12px;
                                    line-height: 20px;
                                    color: #64748b;
                                "
                            >
                                © EchoNode
                                <br>
                                This is an automated message.
                            </p>

                        </td>
                    </tr>

                </table>

            </td>
        </tr>
    </table>

</body>
</html>
"""

        # Configure Resend
        resend.api_key = settings.RESEND_API_KEY

        # Configure proxy if enabled
        configure_resend_proxy()

        response = resend.Emails.send(
            {
                "from": settings.EMAIL_ADDR,
                "to": [user.email],
                "subject": subject,
                "html": html_message,
            }
        )

        logger.info(
            "Confirmation email sent successfully to %s. "
            "Resend response: %s",
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
