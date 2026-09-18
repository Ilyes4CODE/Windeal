# App: auth_app | File: tests.py
from unittest import mock
from django.test import TestCase
from django.core import mail
from rest_framework.test import APIClient

from .models import User, EmailOTP, ClientProfile, BusinessProfile


class EmailOTPFlowTest(TestCase):
    def setUp(self):
        self.c = APIClient()

    def _otp(self, email, purpose):
        return EmailOTP.objects.filter(email=email, purpose=purpose, is_used=False).latest("created_at").otp

    def test_register_client_then_email_login(self):
        email = "client@example.com"

        # 1. request a register OTP
        r = self.c.post("/api/auth/email/send-otp/",
                        {"email": email, "purpose": "register_client"}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(len(mail.outbox), 1)                     # email "sent" (locmem)
        otp = self._otp(email, "register_client")

        # 2. register with that OTP
        r = self.c.post("/api/auth/register/client/", {
            "email": email, "otp": otp, "phone": "+213555111222",
            "full_name": "Test Client", "wilaya": "Alger",
        }, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertIn("access", r.data["data"]["tokens"])
        self.assertTrue(User.objects.filter(email=email, role="client").exists())

        # 3. OTP is now consumed → reusing it fails
        r = self.c.post("/api/auth/register/client/", {
            "email": "other@example.com", "otp": otp, "phone": "+213555000000",
            "full_name": "X", "wilaya": "Oran",
        }, format="json")
        self.assertEqual(r.status_code, 400)

        # 4. email login: send login OTP, then verify
        r = self.c.post("/api/auth/email/send-otp/", {"email": email, "purpose": "login"}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        login_otp = self._otp(email, "login")
        r = self.c.post("/api/auth/email/verify-login/", {"email": email, "otp": login_otp}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["data"]["email"], email)
        self.assertIn("access", r.data["data"]["tokens"])

    def test_login_otp_unknown_email_404(self):
        r = self.c.post("/api/auth/email/send-otp/", {"email": "nobody@x.com", "purpose": "login"}, format="json")
        self.assertEqual(r.status_code, 404)

    def test_invalid_otp_rejected(self):
        User.objects.create_user(phone="+213555999888", role="client", email="a@b.com")
        r = self.c.post("/api/auth/email/verify-login/", {"email": "a@b.com", "otp": "000000"}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_rate_limit(self):
        email = "rl@example.com"
        for _ in range(3):
            self.c.post("/api/auth/email/send-otp/", {"email": email, "purpose": "register_client"}, format="json")
        r = self.c.post("/api/auth/email/send-otp/", {"email": email, "purpose": "register_client"}, format="json")
        self.assertEqual(r.status_code, 429)


class SocialAuthFlowTest(TestCase):
    def setUp(self):
        self.c = APIClient()

    @mock.patch("auth_app.views.verify_google")
    def test_google_new_user_then_complete(self, mock_verify):
        mock_verify.return_value = {"sub": "google-sub-123", "email": "g@gmail.com", "name": "Gina"}

        # 1. first sign-in → needs_completion (no account yet)
        r = self.c.post("/api/auth/social/google/", {"id_token": "x"}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertTrue(r.data["data"]["needs_completion"])
        self.assertEqual(r.data["data"]["social_id"], "google-sub-123")

        # 2. complete profile as a client
        r = self.c.post("/api/auth/social/complete-profile/", {
            "provider": "google", "social_id": "google-sub-123", "role": "client",
            "email": "g@gmail.com", "phone": "+213555222333",
            "full_name": "Gina", "wilaya": "Alger",
        }, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertIn("access", r.data["data"]["tokens"])
        user = User.objects.get(email="g@gmail.com")
        self.assertEqual(user.google_id, "google-sub-123")
        self.assertEqual(user.role, "client")

        # 3. second sign-in with same token → logs in directly (tokens, no completion)
        r = self.c.post("/api/auth/social/google/", {"id_token": "x"}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertIn("access", r.data["data"]["tokens"])
        self.assertNotIn("needs_completion", r.data["data"])

    @mock.patch("auth_app.views.verify_google")
    def test_google_links_existing_email_account(self, mock_verify):
        User.objects.create_user(phone="+213555444555", role="client", email="link@gmail.com")
        mock_verify.return_value = {"sub": "sub-link", "email": "link@gmail.com", "name": None}
        r = self.c.post("/api/auth/social/google/", {"id_token": "x"}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertIn("access", r.data["data"]["tokens"])
        self.assertEqual(User.objects.get(email="link@gmail.com").google_id, "sub-link")

    @mock.patch("auth_app.views.verify_apple")
    def test_apple_new_user_needs_completion(self, mock_verify):
        mock_verify.return_value = {"sub": "apple-sub-1", "email": "a@privaterelay.appleid.com", "name": None}
        r = self.c.post("/api/auth/social/apple/", {"identity_token": "x"}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertTrue(r.data["data"]["needs_completion"])
        self.assertEqual(r.data["data"]["provider"], "apple")

    @mock.patch("auth_app.views.verify_google", side_effect=__import__("auth_app.social", fromlist=["SocialVerifyError"]).SocialVerifyError("bad"))
    def test_google_bad_token_400(self, _mock):
        r = self.c.post("/api/auth/social/google/", {"id_token": "bad"}, format="json")
        self.assertEqual(r.status_code, 400)
