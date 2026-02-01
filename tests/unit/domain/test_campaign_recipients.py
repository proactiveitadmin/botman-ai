from src.services.campaign_service import CampaignService

def test_select_recipients_simple_list():
    svc = CampaignService()
    campaign = {"recipients": ["a", "b", "c"]}
    assert svc.select_recipients(campaign) == ["a", "b", "c"]

def test_select_recipients_dicts_without_filters():
    svc = CampaignService()
    campaign = {
        "recipients": [
            {"phone": "a", "tags": ["vip"]},
            {"phone": "b", "tags": []},
        ]
    }
    assert svc.select_recipients(campaign) == ["a", "b"]

def test_select_recipients_with_include_tags():
    svc = CampaignService()
    campaign = {
        "include_tags": ["vip"],
        "recipients": [
            {"phone": "a", "tags": ["vip"]},
            {"phone": "b", "tags": ["regular"]},
        ],
    }
    assert svc.select_recipients(campaign) == ["a"]

def test_select_recipients_with_exclude_tags():
    svc = CampaignService()
    campaign = {
        "exclude_tags": ["blocked"],
        "recipients": [
            {"phone": "a", "tags": ["vip"]},
            {"phone": "b", "tags": ["blocked"]},
        ],
    }
    assert svc.select_recipients(campaign) == ["a"]

def test_select_recipients_include_and_exclude():
    svc = CampaignService()
    campaign = {
        "include_tags": ["vip"],
        "exclude_tags": ["blocked"],
        "recipients": [
            {"phone": "a", "tags": ["vip"]},
            {"phone": "b", "tags": ["vip", "blocked"]},
            {"phone": "c", "tags": ["regular"]},
        ],
    }
    assert svc.select_recipients(campaign) == ["a"]
