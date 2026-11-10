# coding: utf-8
"""EkspertAgro/ProfiMet: общие заказы, ПЕРВЫМ созданные в листе ProfiMet (кандидаты для проверки, в чьём дашборде клиента стоит заказ) — ТОЛЬКО ЧТЕНИЕ.

Печатает общие заказы листов `Ekspertagro.pl` и `mocnaszklarnia.pl` с 2026-09-01, у которых создание в ProfiMet раньше, чем в EA, с датами продажи/отмены.
Для еженедельной проверки (задача в Клиенты/EkspertAgro/Задачи.md): нужен проданный и не отменённый заказ; затем сверить его номер (8 знаков)
со списками продаж клиента обоих проектов. Использование (из папки Скрипты): PYTHONUTF8=1 python ea_pm_pm_first_orders.py
"""
import sys
sys.path.insert(0, r"d:\GitHub\work-rb\Скрипты")
import pandas as pd
from ea_pm_shared_orders import load, orders_of
ea, pm = load("Ekspertagro.pl"), load("mocnaszklarnia.pl")
oe, op = orders_of(ea), orders_of(pm)
common = oe.index.intersection(op.index)
rows=[]
for i in common:
    if op.loc[i,"created"] < oe.loc[i,"created"] and op.loc[i,"created"] >= pd.Timestamp("2026-09-01",tz="UTC"):
        rows.append((str(i)[:8], str(op.loc[i,"created"])[:16], str(oe.loc[i,"created"])[:16], op.loc[i,"first_type"], op.loc[i,"first_src"],
                     str(op.loc[i,"sale"])[:10] if pd.notna(op.loc[i,"sale"]) else "-", str(op.loc[i,"cancel"])[:10] if pd.notna(op.loc[i,"cancel"]) else "-",
                     str(oe.loc[i,"sale"])[:10] if pd.notna(oe.loc[i,"sale"]) else "-", oe.loc[i,"status_last"]))
d = pd.DataFrame(rows, columns=["id8","создан в PM (UTC)","создан в EA (UTC)","тип1 PM","ист1 PM","продан PM","отмена PM","продан EA","статус EA"]).sort_values("создан в PM (UTC)")
print(len(d)); print(d.to_string(index=False))
