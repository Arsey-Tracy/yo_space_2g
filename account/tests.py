from django.urls import reverse
from django.test import TestCase
from rest_framework.test import APIClient

from .models import CustomUser, Member, Organization


class AuthLoginTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = CustomUser.objects.create_user(
            username='alice',
            email='alice@example.com',
            password='StrongPass123!',
        )
        self.organization = Organization.objects.create(
            owner=self.user,
            name='Alice Org',
            default_language='en',
        )
        Member.objects.create(user=self.user, organization=self.organization, role='admin')

    def test_login_with_username_returns_tokens_and_org(self):
        response = self.client.post(
            reverse('auth-login'),
            {'identifier': 'alice', 'password': 'StrongPass123!'},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn('tokens', response.data)
        self.assertIn('access', response.data['tokens'])
        self.assertIn('refresh', response.data['tokens'])
        self.assertEqual(response.data['organization']['name'], 'Alice Org')

    def test_login_with_email_returns_tokens_and_org(self):
        response = self.client.post(
            reverse('auth-login'),
            {'identifier': 'alice@example.com', 'password': 'StrongPass123!'},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn('tokens', response.data)
        self.assertIn('access', response.data['tokens'])
        self.assertEqual(response.data['user']['email'], 'alice@example.com')

    def test_login_with_wrong_password_fails_cleanly(self):
        response = self.client.post(
            reverse('auth-login'),
            {'identifier': 'alice', 'password': 'WrongPassword!'},
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('non_field_errors', response.data)
