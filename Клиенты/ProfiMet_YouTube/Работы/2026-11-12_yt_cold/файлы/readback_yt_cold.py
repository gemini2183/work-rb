import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"D:\GitHub\work-rb\Скрипты")
from google.ads.googleads.client import GoogleAdsClient
from gads_stats import GOOGLE_ADS_YAML
from google.protobuf.json_format import MessageToDict

CID = "7552781705"
CAMP = "24468615055"
client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
ga = client.get_service("GoogleAdsService")


def q(title, query, full=False):
    print("\n=== " + title)
    try:
        n = 0
        for row in ga.search(customer_id=CID, query=query):
            n += 1
            d = MessageToDict(row, preserving_proto_field_name=True)
            print(d)
        print("-- строк:", n)
    except Exception as e:
        msg = getattr(e, "failure", None)
        if msg:
            print("ОШИБКА:", "; ".join(x.message for x in e.failure.errors))
        else:
            print("ОШИБКА:", e)


q("customer", "SELECT customer.id, customer.currency_code, customer.time_zone FROM customer")
q("кампании с именем yt_cold (все статусы)", "SELECT campaign.id, campaign.name, campaign.status FROM campaign WHERE campaign.name = 'yt_cold'")
q("campaign", f"""SELECT campaign.id, campaign.name, campaign.status, campaign.primary_status, campaign.advertising_channel_type,
 campaign.bidding_strategy_type, campaign.maximize_conversions.target_cpa_micros, campaign.tracking_url_template,
 campaign.demand_gen_campaign_settings.upgraded_targeting, campaign.resource_name, campaign.campaign_budget,
 campaign.contains_eu_political_advertising
 FROM campaign WHERE campaign.id = {CAMP}""")
q("budget", f"""SELECT campaign_budget.id, campaign_budget.name, campaign_budget.amount_micros, campaign_budget.explicitly_shared,
 campaign_budget.delivery_method, campaign_budget.status FROM campaign_budget WHERE campaign_budget.id = 16029616032""")
q("метрики", f"SELECT metrics.impressions, metrics.clicks, metrics.cost_micros FROM campaign WHERE campaign.id = {CAMP}")
q("campaign_criterion", f"""SELECT campaign_criterion.criterion_id, campaign_criterion.type, campaign_criterion.negative,
 campaign_criterion.location.geo_target_constant, campaign_criterion.language.language_constant,
 campaign_criterion.ad_schedule.day_of_week, campaign_criterion.ad_schedule.start_hour, campaign_criterion.ad_schedule.start_minute,
 campaign_criterion.ad_schedule.end_hour, campaign_criterion.ad_schedule.end_minute, campaign_criterion.bid_modifier
 FROM campaign_criterion WHERE campaign.id = {CAMP}""")
q("geo_target_constant 2616", "SELECT geo_target_constant.id, geo_target_constant.name, geo_target_constant.canonical_name FROM geo_target_constant WHERE geo_target_constant.id = 2616")
q("geo settings", f"SELECT campaign.geo_target_type_setting.positive_geo_target_type, campaign.geo_target_type_setting.negative_geo_target_type FROM campaign WHERE campaign.id = {CAMP}")
q("ad_group", f"SELECT ad_group.id, ad_group.name, ad_group.status, ad_group.type, ad_group.demand_gen_ad_group_settings.channel_controls.selected_channels.youtube_in_stream, ad_group.demand_gen_ad_group_settings.channel_controls.selected_channels.youtube_in_feed, ad_group.demand_gen_ad_group_settings.channel_controls.selected_channels.youtube_shorts, ad_group.demand_gen_ad_group_settings.channel_controls.selected_channels.discover, ad_group.demand_gen_ad_group_settings.channel_controls.selected_channels.gmail, ad_group.demand_gen_ad_group_settings.channel_controls.selected_channels.display FROM ad_group WHERE campaign.id = {CAMP}")
q("ad_group (альт. поля каналов)", f"SELECT ad_group.id, ad_group.name, ad_group.status, ad_group.type FROM ad_group WHERE campaign.id = {CAMP}")
q("ad_group_criterion", f"""SELECT ad_group_criterion.criterion_id, ad_group_criterion.type, ad_group_criterion.negative, ad_group_criterion.status,
 ad_group_criterion.audience.audience, ad_group_criterion.resource_name
 FROM ad_group_criterion WHERE campaign.id = {CAMP}""")
q("audience 364509195", "SELECT audience.id, audience.name, audience.status, audience.dimensions, audience.exclusion_dimension FROM audience WHERE audience.id = 364509195")
q("ad_group_ad", f"""SELECT ad_group_ad.ad.id, ad_group_ad.ad.name, ad_group_ad.status, ad_group_ad.ad.final_urls, ad_group_ad.ad.tracking_url_template,
 ad_group_ad.policy_summary.approval_status, ad_group_ad.policy_summary.review_status, ad_group_ad.policy_summary.policy_topic_entries,
 ad_group_ad.ad.demand_gen_video_responsive_ad.headlines, ad_group_ad.ad.demand_gen_video_responsive_ad.long_headlines,
 ad_group_ad.ad.demand_gen_video_responsive_ad.descriptions, ad_group_ad.ad.demand_gen_video_responsive_ad.videos,
 ad_group_ad.ad.demand_gen_video_responsive_ad.logo_images, ad_group_ad.ad.demand_gen_video_responsive_ad.business_name,
 ad_group_ad.ad.demand_gen_video_responsive_ad.call_to_actions
 FROM ad_group_ad WHERE campaign.id = {CAMP}""")
q("campaign_asset", f"SELECT campaign.id, campaign_asset.asset, campaign_asset.field_type, campaign_asset.status, asset.type, asset.name FROM campaign_asset WHERE campaign.id = {CAMP}")
q("customer_asset", "SELECT customer_asset.asset, customer_asset.field_type, customer_asset.status, asset.type, asset.name FROM customer_asset")
q("asset 39375000429", "SELECT asset.id, asset.type, asset.name, asset.call_to_action_asset.call_to_action FROM asset WHERE asset.id = 39375000429")

q("ad_group optimized targeting", f"SELECT ad_group.id, ad_group.optimized_targeting_enabled FROM ad_group WHERE campaign.id = {CAMP}")
