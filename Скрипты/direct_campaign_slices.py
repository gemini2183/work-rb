"""
Директ: срезы одной кампании за весь период работы (только чтение): условия показа (ключи / автотаргетинг),
регионы пользователя, устройства, объявления. Каждый срез — с конверсиями по заданным целям.

Нужен, потому что отчёт по поисковым запросам Директ отдаёт только за последние 180 дней (ошибка 4001), а остальные
срезы доступны за весь период. Токен клиента — из файла вне vault, в вывод не попадает.

Запуск:
    PYTHONUTF8=1 python direct_campaign_slices.py --login porg-juupcxo3 --token-file <файл> \
        --client-folder Novotel_Moscow_City --campaign-id 705894438 --date-from 2026-01-12 --date-to 2026-06-30 \
        --goals 498289834,498298013,511709344,498184341 [--slices criteria,geo,device,ad]
Выход: Клиенты/<папка>/Статистика/slice_<срез>_<campaign-id>.csv
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from direct_express_audit import Direct, read_token  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

SLICES = {
    "criteria": ("CRITERIA_PERFORMANCE_REPORT",
                 ["AdGroupId", "AdGroupName", "CriterionId", "Criterion", "CriterionType"]),
    "geo": ("CUSTOM_REPORT", ["LocationOfPresenceName"]),
    "device": ("CUSTOM_REPORT", ["Device"]),
    "slot": ("CUSTOM_REPORT", ["Slot"]),
    "ad": ("AD_PERFORMANCE_REPORT", ["AdGroupId", "AdId"]),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--login", required=True)
    ap.add_argument("--token-file", required=True)
    ap.add_argument("--client-folder", required=True)
    ap.add_argument("--campaign-id", required=True)
    ap.add_argument("--date-from", required=True)
    ap.add_argument("--date-to", required=True)
    ap.add_argument("--goals", default="")
    ap.add_argument("--slices", default=",".join(SLICES))
    a = ap.parse_args()

    api = Direct(a.login, read_token(a.token_file))
    out = ROOT / "Клиенты" / a.client_folder / "Статистика"
    flt = [{"Field": "CampaignId", "Operator": "EQUALS", "Values": [a.campaign_id]}]
    goals = [g for g in a.goals.split(",") if g]

    for name in a.slices.split(","):
        rtype, dims = SLICES[name]
        base = api.report(rtype, dims + ["Impressions", "Clicks", "Cost"], a.date_from, a.date_to,
                          name=f"s_{name}_{a.campaign_id}", filters=flt)
        if base is None or base.empty:
            print(f"[{name}] пусто или ошибка")
            continue
        base = base.groupby(dims, as_index=False, dropna=False)[["Impressions", "Clicks", "Cost"]].sum()
        if goals:
            g = api.report(rtype, dims + ["Conversions"], a.date_from, a.date_to, goals=goals,
                           name=f"sg_{name}_{a.campaign_id}", filters=flt)
            if g is not None and not g.empty:
                gcols = [c for c in g.columns if c.startswith("Conversions_")]
                g = g.groupby(dims, as_index=False, dropna=False)[gcols].sum(min_count=1)
                base = base.merge(g, on=dims, how="left")
        path = out / f"slice_{name}_{a.campaign_id}.csv"
        base.to_csv(path, index=False, encoding="utf-8")
        print(f"[{name}] строк {len(base)}, расход {base['Cost'].sum():.0f} ₽ -> {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
