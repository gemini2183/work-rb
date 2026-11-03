"""
Novotel: структура кампании «группа → какие в ней ключи» в Excel, без статистики (без API, из выгрузок в Статистика/).

Источники: keywords_full.csv (все ключи, состояние, ставка), adgroups_<id>.json (регионы показа групп из API Директа, снят 2026-11-03).
Листы: Структура (одна строка = один ключ, сгруппировано по теме и группе), Группы (одна строка = группа, ключи списком в ячейке).
Запуск: PYTHONUTF8=1 python novotel_structure_xlsx.py --campaign-id 705894438
"""
import argparse
import json
import sys
from pathlib import Path

import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

sys.path.insert(0, str(Path(__file__).resolve().parent))
from novotel_keyword_structure import clean  # noqa: E402

CL = Path(__file__).resolve().parent.parent / "Клиенты" / "Novotel_Moscow_City"
ST = CL / "Статистика"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--campaign-id", default="705894438")
    a = ap.parse_args()
    cid = int(a.campaign_id)
    k = pd.read_csv(ST / "keywords_full.csv", encoding="utf-8-sig")
    k = k[k.CampaignId == cid].copy()
    gj = {g["Id"]: g for g in json.load(open(ST / f"adgroups_{cid}.json", encoding="utf-8"))}
    k["Тема"] = k.Группа.str.replace(r"_(Москва|Регионы)$", "", regex=True)
    k["Регион показа"] = k.AdGroupId.map(lambda i: ", ".join(gj[i]["RegionNames"]) if i in gj else "")
    k["Тип"] = k["Ключевое слово"].map(lambda x: "автотаргетинг" if str(x).startswith("---autotargeting") else "ключ")
    k["Фраза без минус-слов"] = [("автотаргетинг" if t == "автотаргетинг" else clean(x)) for t, x in zip(k.Тип, k["Ключевое слово"])]
    k["Минус-слова в ключе"] = k["Ключевое слово"].map(lambda x: " ".join(w for w in str(x).split() if w.startswith("-") and not w.startswith("---")))
    k["Состояние"] = k["Состояние ключа"].map({"ON": "включён", "SUSPENDED": "приостановлен"}).fillna(k["Состояние ключа"])
    k["Включён_ключ"] = ((k.Состояние == "включён") & (k.Тип == "ключ")).astype(int)
    k["_o"] = (k.Тип == "автотаргетинг").astype(int)
    k = k.sort_values(["Тема", "Группа", "_o", "Фраза без минус-слов"])
    k["№"] = k.groupby("Группа").cumcount() + 1
    s = k.rename(columns={"Ключевое слово": "Ключ (как в кабинете)", "Ставка, ₽": "Ставка, ₽"})[
        ["Тема", "Группа", "Регион показа", "№", "Тип", "Ключ (как в кабинете)", "Фраза без минус-слов", "Минус-слова в ключе", "Состояние"]]
    g = k.groupby(["Тема", "Группа", "Регион показа"], sort=True).agg(
        Ключей=("Тип", lambda x: (x == "ключ").sum()), Включено=("Включён_ключ", "sum"),
        Ключи=("Фраза без минус-слов", lambda x: "\n".join(x))).reset_index()
    out = CL / f"Тест_Сайта_{cid}_структура_группы_и_ключи.xlsx"
    with pd.ExcelWriter(out, engine="openpyxl") as w:
        for name, df in (("Структура", s), ("Группы", g)):
            df.to_excel(w, sheet_name=name, index=False)
            ws = w.sheets[name]
            ws.freeze_panes = "A2"
            ws.auto_filter.ref = ws.dimensions
            for c in ws[1]:
                c.font = Font(bold=True)
                c.fill = PatternFill("solid", fgColor="DDEBF7")
            for i, col in enumerate(df.columns, 1):
                width = max(len(str(col)), *(len(str(v).split("\n")[0]) for v in df[col].head(300)))
                ws.column_dimensions[get_column_letter(i)].width = min(max(width + 2, 6), 70)
            if name == "Группы":
                for row in ws.iter_rows(min_row=2):
                    for c in row:
                        c.alignment = Alignment(wrap_text=True, vertical="top")
    print("сохранено:", out)
    print(f"групп {k.Группа.nunique()}, тем {k.Тема.nunique()}, ключей {int((k.Тип == 'ключ').sum())}, автотаргетинг {int((k.Тип != 'ключ').sum())}")
    print("регионы показа:", k.groupby("Регион показа").Группа.nunique().to_dict())
    # совпадают ли наборы фраз у пары групп «_Москва» и «_Регионы» одной темы
    ph = k[k.Тип == "ключ"].groupby(["Тема", "Регион показа"])["Фраза без минус-слов"].apply(set).unstack()
    same = sum(1 for _, r in ph.iterrows() if isinstance(r.iloc[0], set) and isinstance(r.iloc[1], set) and r.iloc[0] == r.iloc[1])
    print(f"тем с парой групп: {int(ph.notna().all(axis=1).sum())}, из них с одинаковым набором фраз: {same}")


if __name__ == "__main__":
    main()
