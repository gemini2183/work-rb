# coding: utf-8
"""Полная выгрузка ассетов по ВСЕМ типам (быстрые ссылки, callout, сниппеты, звонки, картинки, логотип, цены, промо, лид-формы)
на трёх уровнях: аккаунт / включённые кампании / включённые группы включённых кампаний. Только чтение.
Запуск из Скрипты/: python gads_assets_full_dump.py <customer_id>   (по умолчанию Landver 2136216123)
Сверку текстов со страницей делать ПО СМЫСЛУ (CLAUDE.md), а не поиском слов."""
import sys
sys.path.insert(0, r"D:\GitHub\work-rb\Скрипты")
from google.ads.googleads.client import GoogleAdsClient
from gads_stats import GOOGLE_ADS_YAML
c = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
ga = c.get_service("GoogleAdsService")
CID = sys.argv[1] if len(sys.argv) > 1 else "2136216123"
def N(msg, field, v):
    m = msg._pb if hasattr(msg, "_pb") else msg
    return m.DESCRIPTOR.fields_by_name[field].enum_type.values_by_number[int(v)].name
def desc(a):
    t = N(a,"type_",a.type_)
    if t=="SITELINK": return f"{a.sitelink_asset.link_text} | {a.sitelink_asset.description1} | {a.sitelink_asset.description2}"
    if t=="CALLOUT": return a.callout_asset.callout_text
    if t=="STRUCTURED_SNIPPET": return f"{a.structured_snippet_asset.header}: {list(a.structured_snippet_asset.values)}"
    if t=="CALL": return a.call_asset.phone_number
    if t in("IMAGE","MEDIA_BUNDLE"): return a.name
    if t=="PROMOTION": return f"{a.promotion_asset.promotion_target} {a.promotion_asset.occasion}"
    if t=="PRICE": return f"{a.price_asset.type_} {a.price_asset.language_code} ({len(a.price_asset.price_offerings)} поз.)"
    if t=="LEAD_FORM": return a.lead_form_asset.business_name
    return a.name or ""
def ap(a):
    try: return N(a.policy_summary,"approval_status",a.policy_summary.approval_status)
    except Exception: return "?"
camps={}
for r in ga.search(customer_id=CID, query="SELECT campaign.id, campaign.name, campaign.status FROM campaign WHERE campaign.status='ENABLED'"):
    camps[r.campaign.id]=r.campaign.name
print("ENABLED кампании:", camps)
print("\n##### АККАУНТ (действует на все кампании)")
q="SELECT customer_asset.status, customer_asset.field_type, asset.id, asset.name, asset.type, asset.sitelink_asset.link_text, asset.sitelink_asset.description1, asset.sitelink_asset.description2, asset.callout_asset.callout_text, asset.structured_snippet_asset.header, asset.structured_snippet_asset.values, asset.call_asset.phone_number, asset.promotion_asset.promotion_target, asset.promotion_asset.occasion, asset.price_asset.type, asset.price_asset.language_code, asset.price_asset.price_offerings, asset.lead_form_asset.business_name, asset.policy_summary.approval_status FROM customer_asset WHERE customer_asset.status!='REMOVED'"
for r in ga.search(customer_id=CID, query=q):
    print(f"  {N(r.customer_asset,'field_type',r.customer_asset.field_type):18} {N(r.customer_asset,'status',r.customer_asset.status):8} {ap(r.asset):17} id {r.asset.id}: {desc(r.asset)}")
print("\n##### КАМПАНИИ")
q="SELECT campaign.id, campaign.name, campaign.status, campaign_asset.status, campaign_asset.field_type, asset.id, asset.name, asset.type, asset.sitelink_asset.link_text, asset.sitelink_asset.description1, asset.sitelink_asset.description2, asset.callout_asset.callout_text, asset.structured_snippet_asset.header, asset.structured_snippet_asset.values, asset.call_asset.phone_number, asset.promotion_asset.promotion_target, asset.promotion_asset.occasion, asset.price_asset.type, asset.price_asset.language_code, asset.price_asset.price_offerings, asset.lead_form_asset.business_name, asset.policy_summary.approval_status FROM campaign_asset WHERE campaign.status='ENABLED' AND campaign_asset.status!='REMOVED'"
rows=[]
for r in ga.search(customer_id=CID, query=q):
    rows.append((r.campaign.name, N(r.campaign_asset,'field_type',r.campaign_asset.field_type), N(r.campaign_asset,'status',r.campaign_asset.status), ap(r.asset), r.asset.id, desc(r.asset)))
for row in sorted(rows):
    print("  %s | %-18s %-8s %-17s id %s: %s" % (row[0][:42],*row[1:]))
print("\n##### ГРУППЫ (включённые группы включённых кампаний)")
q="SELECT campaign.name, campaign.status, ad_group.name, ad_group.status, ad_group_asset.status, ad_group_asset.field_type, asset.id, asset.name, asset.type, asset.sitelink_asset.link_text, asset.sitelink_asset.description1, asset.sitelink_asset.description2, asset.callout_asset.callout_text, asset.structured_snippet_asset.header, asset.structured_snippet_asset.values, asset.call_asset.phone_number, asset.promotion_asset.promotion_target, asset.promotion_asset.occasion, asset.price_asset.type, asset.price_asset.language_code, asset.price_asset.price_offerings, asset.lead_form_asset.business_name, asset.policy_summary.approval_status FROM ad_group_asset WHERE campaign.status='ENABLED' AND ad_group.status='ENABLED' AND ad_group_asset.status!='REMOVED'"
rows=[]
for r in ga.search(customer_id=CID, query=q):
    rows.append((r.campaign.name[:30], r.ad_group.name, N(r.ad_group_asset,'field_type',r.ad_group_asset.field_type), N(r.ad_group_asset,'status',r.ad_group_asset.status), ap(r.asset), r.asset.id, desc(r.asset)))
for row in sorted(rows):
    print("  %s | %s | %-18s %-8s %-17s id %s: %s" % row)
