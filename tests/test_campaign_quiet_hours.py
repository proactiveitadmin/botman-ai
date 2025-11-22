from datetime import datetime
from src.services.campaign_service import CampaignService


def test_is_within_send_window_inside_default():
    # 10:00 – wewnątrz domyślnego okna 09:00–20:00
    svc = CampaignService(now_fn=lambda: datetime(2024, 1, 1, 10, 0))
    assert svc.is_within_send_window({}) is True


def test_is_within_send_window_outside_default():
    # 21:00 – poza domyślnym oknem 09:00–20:00
    svc = CampaignService(now_fn=lambda: datetime(2024, 1, 1, 21, 0))
    assert svc.is_within_send_window({}) is False


def test_is_within_send_window_custom_window():
    campaign = {
        "send_from": "12:00",
        "send_to": "14:00",
    }
    svc_inside = CampaignService(now_fn=lambda: datetime(2024, 1, 1, 13, 0))
    svc_outside = CampaignService(now_fn=lambda: datetime(2024, 1, 1, 15, 0))

    assert svc_inside.is_within_send_window(campaign) is True
    assert svc_outside.is_within_send_window(campaign) is False


def test_is_within_send_window_overnight_window():
    # Okno przez północ: 22:00–06:00
    campaign = {
        "send_from": "22:00",
        "send_to": "06:00",
    }
    svc_night = CampaignService(now_fn=lambda: datetime(2024, 1, 1, 23, 0))
    svc_morning = CampaignService(now_fn=lambda: datetime(2024, 1, 2, 5, 0))
    svc_day = CampaignService(now_fn=lambda: datetime(2024, 1, 1, 12, 0))

    assert svc_night.is_within_send_window(campaign) is True
    assert svc_morning.is_within_send_window(campaign) is True
    assert svc_day.is_within_send_window(campaign) is False
