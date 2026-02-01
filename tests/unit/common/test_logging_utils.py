from src.common.logging_utils import mask_phone, shorten_body, mask_email, mask_twilio_messaging_sid


def test_mask_phone_none_and_short():
    assert mask_phone(None) is None
    assert mask_phone('') == ''
    masked = mask_phone('+48123456789')
    assert masked.startswith('...6789#')
    # hash suffix length 8
    assert len(masked.split('#')[1]) == 8


def test_shorten_body():
    assert shorten_body(None) is None
    assert shorten_body('abc', max_len=5) == 'abc'
    assert shorten_body('0123456789', max_len=5) == '01234...'


def test_mask_email():
    assert mask_email(None) is None
    assert mask_email('') == ''
    assert mask_email('not-an-email') == 'not-an-email'
    assert mask_email('a@example.com') == 'a...@example.com'
    assert mask_email('@example.com') == '@example.com'


def test_mask_twilio_messaging_sid():
    assert mask_twilio_messaging_sid(None) is None
    assert mask_twilio_messaging_sid('') == ''
    assert mask_twilio_messaging_sid('ABC') == 'ABC'
    assert mask_twilio_messaging_sid('MG1234567890') == 'MG...7890'
