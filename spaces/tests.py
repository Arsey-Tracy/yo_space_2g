import io
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from account.models import CustomUser, Organization
# Subscription import removed
from spaces.models import Space, SpaceMember
from sms.models import Broadcast
from survey.models import Survey, SurveyQuestion
from wallet.models import Wallet


class YoSpacesBackendTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        # Seed Subscriptions & SMS Bundle
        # Subscription and SMS bundle seeding removed

        # Register Admin User
        self.register_url = reverse('auth-register')
        self.user_data = {
            'username': 'testadmin',
            'email': 'admin@test.com',
            'password': 'password123',
            'phone': '+256700000001',
            'organization_name': 'Test NGO'
        }
        res = self.client.post(self.register_url, self.user_data)
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.token = res.data['tokens']['access']
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.token}')

        self.user = CustomUser.objects.get(username='testadmin')
        self.org = Organization.objects.get(owner=self.user)

    def test_dashboard_stats(self):
        url = reverse('dashboard-stats')
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['organization'], 'Test NGO')
        self.assertEqual(res.data['total_spaces'], 0)

    def test_new_organization_starts_with_zero_balance(self):
        self.org.refresh_from_db()
        self.assertEqual(self.org.sms_balance, 0)
        self.assertFalse(Wallet.objects.filter(organization=self.org).exists())

    def test_space_creation_and_limits(self):
        url = reverse('space-list')
        res = self.client.post(url, {'name': 'Farmers Group 1', 'description': 'Maize growers'})
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Space.objects.count(), 1)

        # Unlimited spaces allowed; second space should be created successfully
        res2 = self.client.post(url, {'name': 'Farmers Group 2'})
        self.assertEqual(res2.status_code, status.HTTP_201_CREATED)

    def test_member_addition_and_csv_import(self):
        space = Space.objects.create(organization=self.org, name='Youth Group', host_phone='+256700000001')
        
        # Add Member
        member_url = reverse('space-members-list', kwargs={'space_pk': space.id})
        res = self.client.post(member_url, {'phone_number': '+256711111111', 'name': 'John Okello', 'role': 'member'})
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(SpaceMember.objects.count(), 1)

        # CSV Import
        import_url = reverse('space-members-import', kwargs={'space_pk': space.id})
        csv_data = "name,phone_number,role\nMary Achieng,+256722222222,secretary\nDavid Musoke,+256733333333,member"
        import_file = io.BytesIO(csv_data.encode('utf-8'))
        import_file.name = 'members.csv'
        
        res_import = self.client.post(import_url, {'file': import_file}, format='multipart')
        self.assertEqual(res_import.status_code, status.HTTP_200_OK)
        self.assertEqual(space.members.count(), 3)

    def test_broadcast_sms_creation(self):
        space = Space.objects.create(organization=self.org, name='Health Clinic', host_phone='+256700000001')
        SpaceMember.objects.create(space=space, phone_number='+256755555555', name='Nurse')

        broadcast_url = reverse('broadcast-list')
        res = self.client.post(broadcast_url, {
            'space': space.id,
            'message': 'Vaccination drive tomorrow at 9 AM.',
            'status': 'sent'
        })
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Insufficient SMS balance', str(res.data))
        self.org.refresh_from_db()
        self.assertEqual(self.org.sms_balance, 0)

        # Test for SMS bundle purchase removed as subscription model is deprecated

    def test_ussd_role_routing(self):
        ussd_url = reverse('ussd-callback')
        # Host USSD dial
        res_host = self.client.post(ussd_url, {'phoneNumber': '+256700000001', 'text': ''})
        self.assertIn("Welcome Host", res_host.content.decode('utf-8'))

        # End-User USSD dial
        res_user = self.client.post(ussd_url, {'phoneNumber': '+256799999999', 'text': ''})
        self.assertIn("Welcome to YoSpaces", res_user.content.decode('utf-8'))
        self.assertIn("Join Space via PIN", res_user.content.decode('utf-8'))
