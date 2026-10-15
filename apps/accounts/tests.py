from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse


class LoginViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="operator", email="operator@example.com", password="S3cure-pass!"
        )

    def test_login_page_renders(self):
        response = self.client.get(reverse("accounts:login"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Welcome Back")
        self.assertContains(response, reverse("accounts:password_reset"))

    def test_login_without_remember_me_expires_at_browser_close(self):
        response = self.client.post(
            reverse("accounts:login"), {"username": "operator", "password": "S3cure-pass!"}
        )
        self.assertRedirects(response, reverse("dashboard:home"))
        self.assertTrue(self.client.session.get_expire_at_browser_close())

    def test_login_with_remember_me_keeps_session(self):
        self.client.post(
            reverse("accounts:login"),
            {"username": "operator", "password": "S3cure-pass!", "remember_me": "on"},
        )
        self.assertFalse(self.client.session.get_expire_at_browser_close())

    def test_invalid_credentials_show_error(self):
        response = self.client.post(
            reverse("accounts:login"), {"username": "operator", "password": "wrong"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "alert--error")

    def test_next_parameter_is_respected(self):
        response = self.client.post(
            reverse("accounts:login") + "?next=/admin/",
            {"username": "operator", "password": "S3cure-pass!", "next": "/admin/"},
        )
        self.assertRedirects(response, "/admin/", fetch_redirect_response=False)

    def test_sso_button_hidden_without_endpoint(self):
        with self.settings(SSO_LOGIN_URL=""):
            response = self.client.get(reverse("accounts:login"))
        self.assertNotContains(response, "Login with Company SSO")

    @override_settings(SSO_LOGIN_URL="https://sso.example.com/start")
    def test_sso_button_shown_with_endpoint(self):
        response = self.client.get(reverse("accounts:login"))
        self.assertContains(response, "Login with Company SSO")
        self.assertContains(response, "https://sso.example.com/start")

    def test_dashboard_requires_login(self):
        response = self.client.get(reverse("dashboard:home"))
        self.assertRedirects(response, reverse("accounts:login") + "?next=/")

    def test_logout(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("accounts:logout"))
        self.assertRedirects(response, reverse("accounts:login"))


class PasswordResetTests(TestCase):
    def test_reset_email_contains_working_link(self):
        get_user_model().objects.create_user(
            username="operator", email="operator@example.com", password="S3cure-pass!"
        )
        response = self.client.post(
            reverse("accounts:password_reset"), {"email": "operator@example.com"}
        )
        self.assertRedirects(response, reverse("accounts:password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)

        link = next(line for line in mail.outbox[0].body.splitlines() if "/password-reset/" in line)
        path = link.split("testserver", 1)[1]
        response = self.client.get(path, follow=True)
        self.assertContains(response, "Set a New Password")
