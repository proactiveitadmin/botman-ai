from src.services.campaign_service import CampaignService

def test_select_recipients_simple_list():
    svc = CampaignService()
    campaign = {"recipients": ["a", "b", "c"]}
    assert svc.select_recipients(campaign) == ["a", "b", "c"]

def test_select_recipients_dicts_without_filters():
    svc = CampaignService()
    campaign = {
        "recipients": [
            {"token": "a", "tags": ["vip"]},
            {"token": "b", "tags": []},
        ]
    }
    assert svc.select_recipients(campaign) == [{"token": "a"}, {"token": "b"}]

def test_select_include_tags():
    svc = CampaignService()
    campaign = {
        "include_tags": ["vip"],
        "recipients": [
            {"token": "a", "tags": ["vip"]},
            {"token": "b", "tags": ["regular"]},
        ],
    }
    assert svc.select_recipients(campaign) == [{"token": "a"},{"token": "b"}]
    assert svc.select_include_tags(campaign) == ["vip"]
def test_select_exclude_tags():
    svc = CampaignService()
    campaign = {
        "exclude_tags": ["blocked"],
        "recipients": [
            {"token": "a"},
            {"token": "b"},
        ],
    }
    assert svc.select_recipients(campaign) == [{"token": "a"},{"token": "b"}]
    assert svc.select_exclude_tags(campaign) == ["blocked"]
