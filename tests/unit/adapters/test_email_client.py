import types

from src.adapters.email_client import EmailClient


class DummySES:
    def __init__(self):
        self.calls = []

    def send_email(self, **kwargs):
        self.calls.append(kwargs)
        return {"MessageId": "mid-1"}


def test_send_otp_missing_from_email(monkeypatch):
    # Ensure no fallback from env/settings
    monkeypatch.delenv('SES_FROM_EMAIL', raising=False)
    client = EmailClient(from_email='')

    assert client.send_otp(
        tenant_id=None,
        to_email='user@example.com',
        subject='subj',
        body_text='body',
    ) is False


def test_send_otp_success_with_configuration_set_and_tenant_override(monkeypatch):
    dummy = DummySES()

    # Patch ses_client used by adapter
    monkeypatch.setattr('src.adapters.email_client.ses_client', lambda: dummy)

    client = EmailClient(from_email='fallback@example.com', from_name='Fallback')

    # Patch tenants repo method
    monkeypatch.setattr(
        client.tenants,
        'get_email_config',
        lambda tenant_id: {
            'from_email': 'tenant@example.com',
            'from_name': 'TenantName',
        },
    )

    ok = client.send_otp(
        tenant_id='t1',
        to_email='user@example.com',
        subject='OTP',
        body_text='1234',
        configuration_set='cfgset',
    )
    assert ok is True
    assert len(dummy.calls) == 1
    call = dummy.calls[0]
    assert call['Source'] == 'TenantName <tenant@example.com>'
    assert call['Destination']['ToAddresses'] == ['user@example.com']
    assert call['Message']['Subject']['Data'] == 'OTP'
    assert call['Message']['Body']['Text']['Data'] == '1234'
    assert call['ConfigurationSetName'] == 'cfgset'


def test_send_otp_handles_ses_exception(monkeypatch):
    class SESBoom(DummySES):
        def send_email(self, **kwargs):
            raise RuntimeError('boom')

    monkeypatch.setattr('src.adapters.email_client.ses_client', lambda: SESBoom())

    client = EmailClient(from_email='from@example.com')
    assert client.send_otp(
        tenant_id=None,
        to_email='user@example.com',
        subject='subj',
        body_text='body',
    ) is False
