import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"D:\GitHub\work-rb\Скрипты")
from google.ads.googleads.client import GoogleAdsClient
from gads_stats import GOOGLE_ADS_YAML
c = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
ga = c.get_service("GoogleAdsService")
for r in ga.search(customer_id="7552781705", query="SELECT ad_group_criterion.criterion_id, ad_group_criterion.negative, ad_group_criterion.user_list.user_list, user_list.name, user_list.id FROM ad_group_criterion WHERE campaign.id = 24468615055 AND ad_group_criterion.type = USER_LIST"):
    x = r.ad_group_criterion
    print(x.criterion_id, "NEG" if x.negative else "POS", x.user_list.user_list, "|", r.user_list.name)
try:
    for r in ga.search(customer_id="7552781705", query="SELECT ad_group.id, ad_group.demand_gen_ad_group_settings.channel_controls.selected_channels.discover, ad_group.demand_gen_ad_group_settings.channel_controls.selected_channels.gmail, ad_group.demand_gen_ad_group_settings.channel_controls.selected_channels.display, ad_group.demand_gen_ad_group_settings.channel_controls.lookalike_expansion_level FROM ad_group WHERE campaign.id = 24468615055"):
        print(r)
except Exception as e:
    print("ERR", [x.message for x in e.failure.errors] if hasattr(e,"failure") else e)
