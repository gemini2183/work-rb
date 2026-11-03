"""
Novotel: Excel с разбивкой кампании по группам и ключам (без API, из выгрузок в Статистика/).

Источники: keywords_full.csv (все ключи и состояние), slice_criteria_<id>.csv (показы, клики, расход, цели за период кампании).
Обращение = формы 498289834 + звонки 498298013 (счётчик 105965383); «Квал MICE» и «90 секунд» — отдельными колонками, в обращения не входят.
Листы: Группы, Ключи, Темы, Классы. Класс ключа — novotel_keyword_structure.cls (грубо, по подстрокам).
Запуск: PYTHONUTF8=1 python novotel_campaign_xlsx.py --campaign-id 705894438
"""
import argparse
import sys
from pathlib import Path

import pandas as pd
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

sys.path.insert(0, str(Path(__file__).resolve().parent))
from novotel_keyword_structure import clean, cls  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CL = ROOT / "Клиенты" / "Novotel_Moscow_City"
ST = CL / "Статистика"


def fin(df):
    df["CTR %"] = (df["Клики"] / df["Показы"].where(df["Показы"] > 0) * 100).round(1)
    df["CPC, ₽"] = (df["Расход, ₽"] / df["Клики"].where(df["Клики"] > 0)).round(0)
    df["₽/обращение"] = (df["Расход, ₽"] / df["Обращений"].where(df["Обращений"] > 0)).round(0)
    df["Расход, ₽"] = df["Расход, ₽"].round(0)
    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--campaign-id", default="705894438")
    a = ap.parse_args()
    cid = int(a.campaign_id)
    k = pd.read_csv(ST / "keywords_full.csv", encoding="utf-8-sig")
    k = k[k.CampaignId == cid].rename(columns={"Группа": "Группа", "Ключевое слово": "Ключ", "Состояние ключа": "Включён"})
    s = pd.read_csv(ST / f"slice_criteria_{cid}.csv")
    s = s.rename(columns={"AdGroupName": "Группа_с", "Criterion": "Ключ", "Impressions": "Показы", "Clicks": "Клики", "Cost": "Расход, ₽",
                          "Conversions_498289834_AUTO": "Формы", "Conversions_498298013_AUTO": "Звонки",
                          "Conversions_511709344_AUTO": "Квал MICE", "Conversions_498184341_AUTO": "90 секунд"})
    num = ["Показы", "Клики", "Расход, ₽", "Формы", "Звонки", "Квал MICE", "90 секунд"]
    s[num] = s[num].fillna(0)
    m = k.merge(s[["AdGroupId", "Ключ"] + num], on=["AdGroupId", "Ключ"], how="outer", indicator=True)
    # условия, которых нет в keywords_full (автотаргетинг): имя группы из среза
    gname = s.drop_duplicates("AdGroupId").set_index("AdGroupId").Группа_с
    m["Группа"] = m.Группа.fillna(m.AdGroupId.map(gname))
    m[num] = m[num].fillna(0)
    m["Включён"] = m["Включён"].fillna("—")
    m["Тип"] = m.Ключ.map(lambda x: "автотаргетинг" if str(x).startswith("---autotargeting") or "autotarget" in str(x).lower() else "ключ")
    m["Фраза без минус-слов"] = m.Ключ.map(clean)
    m["Класс"] = [("автотаргетинг" if t == "автотаргетинг" else cls(p)) for t, p in zip(m.Тип, m["Фраза без минус-слов"])]
    m["Ставка, ₽"] = m["Ставка, ₽"]
    m["Обращений"] = m.Формы + m.Звонки
    m["Тема"] = m.Группа.str.replace(r"_(Москва|Регионы)$", "", regex=True)
    m["Гео группы"] = m.Группа.str.extract(r"_(Москва|Регионы)$")[0]
    keys = fin(m[["Группа", "Гео группы", "Тема", "Ключ", "Фраза без минус-слов", "Класс", "Тип", "Включён", "Ставка, ₽", "Показы", "Клики", "Расход, ₽",
                  "Формы", "Звонки", "Обращений", "Квал MICE", "90 секунд"]].copy()).sort_values(["Расход, ₽"], ascending=False)
    agg = dict(Ключей=("Ключ", "count"), Включено=("Включён", lambda x: (x == "ON").sum()), Показы=("Показы", "sum"), Клики=("Клики", "sum"),
               **{"Расход, ₽": ("Расход, ₽", "sum")}, Формы=("Формы", "sum"), Звонки=("Звонки", "sum"), Обращений=("Обращений", "sum"),
               **{"Квал MICE": ("Квал MICE", "sum"), "90 секунд": ("90 секунд", "sum")})
    gr = fin(m.groupby(["Группа", "Гео группы", "Тема"], dropna=False).agg(**agg).reset_index()).sort_values("Расход, ₽", ascending=False)
    th = fin(m.groupby("Тема").agg(Групп=("Группа", "nunique"), **agg).reset_index()).sort_values("Расход, ₽", ascending=False)
    cs = fin(m.groupby("Класс").agg(**agg).reset_index()).sort_values("Расход, ₽", ascending=False)
    tot = m[num].sum()
    cs["Доля расхода %"] = (cs["Расход, ₽"] / tot["Расход, ₽"] * 100).round(1)
    out = CL / f"Тест_Сайта_{cid}_группы_и_ключи.xlsx"
    with pd.ExcelWriter(out, engine="openpyxl") as w:
        for name, df in (("Группы", gr), ("Ключи", keys), ("Темы", th), ("Классы", cs)):
            df.to_excel(w, sheet_name=name, index=False)
            ws = w.sheets[name]
            ws.freeze_panes = "A2"
            ws.auto_filter.ref = ws.dimensions
            for c in ws[1]:
                c.font = Font(bold=True)
                c.fill = PatternFill("solid", fgColor="DDEBF7")
            for i, col in enumerate(df.columns, 1):
                width = max(len(str(col)), *(len(str(v)) for v in df[col].head(200))) if len(df) else len(str(col))
                ws.column_dimensions[get_column_letter(i)].width = min(max(width + 2, 8), 60)
    print("сохранено:", out)
    print(f"групп {len(gr)}, строк ключей {len(keys)} (автотаргетинг {int((m.Тип == 'автотаргетинг').sum())}), "
          f"расход {tot['Расход, ₽']:,.0f}, обращений {tot['Формы'] + tot['Звонки']:.0f}")
    print("строк только в срезе без ключа в keywords_full:", int((m._merge == "right_only").sum()),
          "| ключей без статистики:", int((m._merge == "left_only").sum()))


if __name__ == "__main__":
    main()
