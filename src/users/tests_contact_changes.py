from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from auth_users.models import AuthCode, UserContactChange
from users.models import User


class ContactChangeAPITests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="contact-owner",
            email="old@example.test",
            phone_number="+989121111111",
            password="pass12345",
        )
        self.other = User.objects.create_user(
            username="other-contact-owner",
            email="taken@example.test",
            phone_number="+989122222222",
            password="pass12345",
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    @patch("users.contact_api.send_otp")
    def test_email_change_is_pending_until_new_destination_otp_is_confirmed(self, send_otp):
        def create_code(**kwargs):
            return AuthCode.create_or_refresh(
                user=kwargs["user"],
                contact=kwargs["contact"],
                purpose=kwargs["purpose"],
            ).code

        send_otp.side_effect = create_code
        response = self.client.post(
            "/api/users/user/contact-change/",
            {"email": "NEW@example.test"},
            format="json",
        )

        self.assertEqual(response.status_code, 202)
        change = UserContactChange.objects.get()
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "old@example.test")
        self.assertEqual(change.old_value, "old@example.test")
        self.assertEqual(change.new_value, "new@example.test")
        self.assertEqual(change.status, UserContactChange.Status.PENDING)
        self.assertEqual(AuthCode.objects.get().contact, "new@example.test")

        code = AuthCode.objects.get().code
        confirmation = self.client.post(
            f"/api/users/user/contact-change/{change.public_id}/confirm/",
            {"code": code},
            format="json",
        )

        self.assertEqual(confirmation.status_code, 200)
        self.user.refresh_from_db()
        change.refresh_from_db()
        self.assertEqual(self.user.email, "new@example.test")
        self.assertTrue(self.user.email_verified)
        self.assertEqual(change.status, UserContactChange.Status.VERIFIED)
        self.assertIsNotNone(change.verified_at)
        self.assertFalse(AuthCode.objects.exists())

    @patch("users.contact_api.send_otp")
    def test_wrong_code_does_not_change_contact(self, send_otp):
        send_otp.side_effect = lambda **kwargs: AuthCode.create_or_refresh(
            user=kwargs["user"], contact=kwargs["contact"], purpose=kwargs["purpose"]
        ).code
        response = self.client.post(
            "/api/users/user/contact-change/",
            {"phone_number": "+989123333333"},
            format="json",
        )
        change = UserContactChange.objects.get()

        confirmation = self.client.post(
            f"/api/users/user/contact-change/{change.public_id}/confirm/",
            {"code": "wrong-code"},
            format="json",
        )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(confirmation.status_code, 400)
        self.user.refresh_from_db()
        self.assertEqual(str(self.user.phone_number), "+989121111111")
        self.assertEqual(change.status, UserContactChange.Status.PENDING)

    @patch("users.contact_api.send_otp")
    def test_contact_is_unique_and_direct_profile_update_is_rejected(self, send_otp):
        direct = self.client.put(
            "/api/users/user/",
            {"email": "bypass@example.test"},
            format="json",
        )
        self.assertEqual(direct.status_code, 400)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "old@example.test")

        duplicate = self.client.post(
            "/api/users/user/contact-change/",
            {"email": self.other.email},
            format="json",
        )
        self.assertEqual(duplicate.status_code, 400)
        send_otp.assert_not_called()

    @patch("users.contact_api.send_otp")
    def test_new_contact_cancels_other_pending_contact_transaction(self, send_otp):
        send_otp.side_effect = lambda **kwargs: AuthCode.create_or_refresh(
            user=kwargs["user"], contact=kwargs["contact"], purpose=kwargs["purpose"]
        ).code
        first = self.client.post(
            "/api/users/user/contact-change/",
            {"email": "first@example.test"},
            format="json",
        )
        second = self.client.post(
            "/api/users/user/contact-change/",
            {"phone_number": "+989124444444"},
            format="json",
        )

        self.assertEqual(first.status_code, 202)
        self.assertEqual(second.status_code, 202)
        self.assertEqual(
            UserContactChange.objects.filter(status=UserContactChange.Status.PENDING).count(),
            1,
        )
        self.assertEqual(
            UserContactChange.objects.get(field=UserContactChange.Field.EMAIL).status,
            UserContactChange.Status.CANCELLED,
        )
