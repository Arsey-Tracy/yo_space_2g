"""this is a sample code using the marzpay sdk
"""
from marzpay import MarzPay, MarzPayError
client = MarzPay(
    api_key='MARZPAY_API_KEY',
    api_secret='MARZPAY_API_SECRET',
)

res = client.collections.collect(
    {
        "phone_number": 'phone_number',
        "amount": 'amount_for_api',
        'description': "Payment sevice"
    }
)