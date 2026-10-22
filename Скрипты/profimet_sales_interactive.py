#!/usr/bin/env python
# coding: utf-8
"""ProfiMet: ИНТЕРАКТИВНЫЙ дашборд «заявки → продажи» — ТОЛЬКО ЧТЕНИЕ (запрос пользователя 2026-10-21).

Одна самодостаточная HTML-страница (данные внутри, графики рисует JS без внешних библиотек). В браузере выбираются: источники, какие заявки считать,
группировка (день / неделя / скользящие 7 дней), период и метрики (расход, заявки, продажи, цена заявки, цена продажи, конверсия в продажу двух видов).

Определения:
  • Продажа — проданный заказ без отмены, источник — первое обращение номера за 60 дн до заказа; «Телефон» в рекламу не входит. ДАТА продажи в дашборде — дата ПЕРВОГО ОБРАЩЕНИЯ (не дата продажи): продажа попадает в день, когда человек обратился впервые.
  • Заявка — новое обращение (звонок/форма) по правилу 60 дн. у Google Ads, Facebook, «Нет метки». Качество заявки берётся из тега звонка в CRM
    (колонка «Причина» у звонка без заказа): мусор = Сервис, Ошибка, Спам, Дубль, Тест, Не отвечен; «не продать» = Нет модели, Отказ: монтаж;
    остальное — обычные (в т.ч. «Не размечено», обращения с заказом и формы).
  • Конверсия «по датам» = продажи в эти даты ÷ заявки в эти же даты (грубая: продажа происходит позже заявки).
  • Конверсия «по заявкам» (когорта) = доля заявок этих дат, у номера которых есть проданный заказ без отмены в течение 60 дн после обращения.
    Свежие заявки (моложе 14 дней) не дозрели, на графике они пунктиром.
  • Цена продажи = расход выбранных рекламных источников (Google Ads, Facebook) ÷ продажи выбранных источников.
Использование: PYTHONIOENCODING=utf-8 python profimet_sales_interactive.py [--from 2026-08-01] [--usd-eur 0.8244] [--no-open]
Пишет `Клиенты/ProfiMet/Статистика/dashboard_sales_interactive.html`. Запускать без -I.
"""
import argparse
import json
import os
from datetime import timedelta

import pandas as pd

from _config import client_stats_dir
from profimet_sales_vs_ringostat import SHEET_ID, load_sheet
from profimet_sales_trend import AD_SRC, sales_table
from profimet_sources_dashboard import SITE, WINDOW, ads_daily, contacts_with_new_flag, fb_daily

JUNK = {"сервис", "ошибка", "спам", "дубль", "тест", "не отвечен"}
NOSELL = {"нет модели", "отказ: монтаж"}


def quality(row):
    """0 обычная, 1 «не продать» (нет модели / монтаж), 2 мусор. Тег звонка смотрим только у звонков без заказа."""
    if row["type"] != "звонок" or row["status"] != "нет заказа":
        return 0
    r = str(row["reason"]).strip().lower()
    return 2 if r in JUNK else 1 if r in NOSELL else 0


def sold_orders(sheet):
    """Номер (последние 9 цифр) → даты продаж непроданных-без-отмены заказов."""
    s = sheet[sheet["site"] == SITE]
    out = {}
    for order, grp in s[s["order"] != ""].groupby("order"):
        sd = [d for d in grp["sale_date"] if d]
        if not sd or any(grp["cancel_date"] != ""):
            continue
        day = pd.Timestamp(min(sd)).date()
        for p in set(grp["p9"]):
            if p:
                out.setdefault(p, []).append(day)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="frm", default="2026-08-01")
    ap.add_argument("--usd-eur", type=float, default=0.8244)
    ap.add_argument("--target", type=float, default=30.0)
    ap.add_argument("--no-open", action="store_true")
    a = ap.parse_args()

    sheet = load_sheet(SHEET_ID)
    last_ts = sheet[sheet["site"] == SITE]["ts"].max().tz_convert("Europe/Warsaw")
    end = last_ts.date()  # последний день выгрузки включаем; он неполный (CRM до last_ts), в странице помечен
    frm = pd.Timestamp(a.frm).date()
    ads, fb = ads_daily(frm, end), fb_daily(frm, end)
    contacts = contacts_with_new_flag(sheet)
    c = contacts[contacts["new"] & contacts["src2"].isin(AD_SRC) & (contacts["day"] >= frm) & (contacts["day"] <= end)].copy()
    c["q"] = c.apply(quality, axis=1)
    sold = sold_orders(sheet)
    c["sold"] = [any(0 <= (d - day).days <= WINDOW for d in sold.get(p, [])) for p, day in zip(c["p9"], c["day"])]
    sales, cancelled = sales_table(sheet)
    sales = sales[(sales["touch_date"] >= frm) & (sales["touch_date"] <= end)]  # продажа относится к ДАТЕ ПЕРВОГО ОБРАЩЕНИЯ (решение пользователя 2026-10-21)

    ga, fa = ads.set_index("date")["cost"], fb.set_index("date")["cost"] * a.usd_eur
    rows = []
    for d in pd.date_range(frm, end).date:
        for src in AD_SRC:
            cc = c[(c["day"] == d) & (c["src2"] == src)]
            r = {"d": str(d), "s": src, "cost": round(float(ga.get(d, 0)) if src == "Google Ads" else float(fa.get(d, 0)) if src == "Facebook" else 0.0, 2),
                 "sales": int(((sales["touch_date"] == d) & (sales["src2"] == src)).sum())}
            for q in (0, 1, 2):
                x = cc[cc["q"] == q]
                r[f"l{q}"], r[f"k{q}"] = len(x), int(x["sold"].sum())
            rows.append(r)
    phone = sales[sales["src2"] == "Телефон"].groupby("touch_date").size()
    meta = {"last_crm": f"{last_ts:%d.%m.%Y %H:%M}", "end": str(end), "target": a.target, "cancelled": cancelled, "partial": last_ts.hour < 23,
            "phone": {str(k): int(v) for k, v in phone.items()}}
    page = TEMPLATE.replace("__DATA__", json.dumps(rows, ensure_ascii=False)).replace("__META__", json.dumps(meta, ensure_ascii=False))
    out = client_stats_dir("ProfiMet") / "dashboard_sales_interactive.html"
    out.write_text(page, encoding="utf-8")
    q_all = c.groupby("q").size().to_dict()
    print(f"Заявок рекламных источников {frm}–{end}: {len(c)} (обычных {q_all.get(0, 0)}, «не продать» {q_all.get(1, 0)}, мусор {q_all.get(2, 0)}); "
          f"дошли до продажи {int(c['sold'].sum())}")
    print("Файл:", out)
    if not a.no_open:
        os.startfile(str(out))


TEMPLATE = r"""<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>ProfiMet заявки и продажи</title><style>
:root{--bg:#fff;--fg:#1a1a1a;--mut:#666;--line:#e3e3e3;--acc:#1b7f4a;--card:#f7f8f7;--red:#c0392b}
@media (prefers-color-scheme:dark){:root{--bg:#161616;--fg:#eee;--mut:#9a9a9a;--line:#333;--acc:#4cc28a;--card:#1e1e1e;--red:#ff7a6b}}
body{margin:0;padding:20px 16px;background:var(--bg);color:var(--fg);font:15px/1.45 system-ui,Segoe UI,Arial,sans-serif;max-width:1200px;margin:auto}
h1{font-size:22px;margin:0 0 4px} .m{color:var(--mut);font-size:13px}
.ctl{display:flex;flex-wrap:wrap;gap:14px 28px;background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px;margin:14px 0}
.ctl b{display:block;font-size:12px;color:var(--mut);margin-bottom:4px;font-weight:600}
.ctl label{display:inline-flex;align-items:center;gap:5px;margin-right:12px;white-space:nowrap}
select,input[type=date],button{font:inherit;padding:3px 6px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--fg)}
button{cursor:pointer} .ch{margin:16px 0}.ch h3{font-size:15px;margin:0 0 2px;color:var(--acc)} .ch .d{font-size:12px;color:var(--mut);margin-bottom:2px}
.sum{display:flex;flex-wrap:wrap;gap:10px;margin:10px 0}.k{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:8px 14px;min-width:130px}
.k span{display:block;font-size:12px;color:var(--mut)}.k strong{font-size:20px}
.w{overflow-x:auto}table{border-collapse:collapse;width:100%}th,td{padding:6px 10px;text-align:right;border-bottom:1px solid var(--line);white-space:nowrap}th{font-size:12px;color:var(--mut)}.l{text-align:left}
ul{color:var(--mut);font-size:13px;padding-left:18px}
</style></head><body>
<h1>ProfiMet: заявки → продажи</h1><div class="m" id="meta"></div>
<div class="ctl">
 <div><b>Источники</b><label><input type="checkbox" class="src" value="Google Ads" checked>Google Ads</label><label><input type="checkbox" class="src" value="Facebook" checked>Facebook</label><label><input type="checkbox" class="src" value="Нет метки" checked>Нет метки</label></div>
 <div><b>Какие заявки считать</b><select id="q"><option value="2">Все</option><option value="1" selected>Без мусора (Сервис, Ошибка, Спам, Дубль…)</option><option value="0">Только продаваемые (без «Нет модели», «Монтаж»)</option></select></div>
 <div><b>Группировка</b><select id="g"><option value="r7" selected>Скользящие 7 дней</option><option value="w">Неделя (пн–вс)</option><option value="d">День</option></select></div>
 <div><b>Период</b><input type="date" id="from"> — <input type="date" id="to"> <button id="b30">30 дн</button> <button id="ball">Всё</button></div>
 <div><b>Метрики</b><label><input type="checkbox" class="met" value="cost" checked>Расход</label><label><input type="checkbox" class="met" value="leads" checked>Заявки</label><label><input type="checkbox" class="met" value="sales" checked>Продажи</label><label><input type="checkbox" class="met" value="cpl">Цена заявки</label><label><input type="checkbox" class="met" value="cps" checked>Цена продажи</label><label><input type="checkbox" class="met" value="cr1" checked>Конверсия по датам</label><label><input type="checkbox" class="met" value="cr2" checked>Конверсия по заявкам</label></div>
</div>
<div class="sum" id="sum"></div><div id="charts"></div>
<div class="w"><table id="tbl"></table></div>
<ul><li>Продажа — проданный заказ без отмены; её дата в дашборде — дата первого обращения номера (а не дата продажи), источник — первое обращение номера за 60 дн. «Телефон» (звонок без метки и без рекламного следа) в рекламу не входит и в цифры не попадает.</li>
<li>Теги качества — из CRM: у звонка без заказа тег («Сервис», «Ошибка», «Спам», «Дубль», «Нет модели», «Отказ: монтаж»). Тег относится к звонку, а не к продаже и не к отмене. «Не размечено» считается обычной заявкой.</li>
<li>Конверсия «по датам» — продажи ÷ заявки за те же даты, грубая, колеблется. Конверсия «по заявкам» — доля заявок, у которых номер купил в течение 60 дней; свежие 14 дней не дозрели (пунктир).</li>
<li>Цена продажи = расход выбранных рекламных источников ÷ продажи выбранных источников; «Нет метки» расхода не имеет. Если выбран только он, цены нет.</li>
<li>* — в окно или день входит последний день выгрузки CRM, он неполный: точка занижена.</li><li>В режиме «Неделя» неполные недели (на краях периода) скрыты.</li><li>Продажи неровные (менеджеры проставляют даты пачками, в выходные почти нет), по одной точке вывод не делать.</li></ul>
<script>
const DATA=__DATA__, META=__META__;
const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)];
const days=[...new Set(DATA.map(r=>r.d))].sort(), last=days[days.length-1];
$('#from').value=days[0];$('#to').value=last;$('#from').min=$('#to').min=days[0];$('#from').max=$('#to').max=last;
$('#meta').textContent=`Данные CRM до ${META.last_crm}${META.partial?' — последний день ('+last+') неполный, его цифры занижены':''}. Цель по цене продажи — ${META.target} €. Отменённых заказов исключено: ${META.cancelled}.`;
const MET={cost:{n:'Расход, €',f:v=>v.toFixed(0)},leads:{n:'Заявки',f:v=>v.toFixed(0)},sales:{n:'Рекламные продажи',f:v=>v.toFixed(0)},cpl:{n:'Цена заявки, €',f:v=>v.toFixed(1)},cps:{n:'Цена продажи, €',f:v=>v.toFixed(1)},cr1:{n:'Конверсия по датам, %',f:v=>v.toFixed(1)},cr2:{n:'Конверсия по заявкам, %',f:v=>v.toFixed(1)}};
const DESC={cr1:'продажи этих дат ÷ заявки этих дат',cr2:'доля заявок этих дат, дошедших до продажи (когорта); пунктир — ещё не дозрели',cps:'расход Google+Facebook ÷ продажи; красная линия — цель'};
const addDays=(s,n)=>{const d=new Date(s+'T00:00:00Z');d.setUTCDate(d.getUTCDate()+n);return d.toISOString().slice(0,10)};
const dow=s=>(new Date(s+'T00:00:00Z').getUTCDay()+6)%7;
function dayRows(){const srcs=$$('.src:checked').map(x=>x.value),q=+$('#q').value,by={};
 DATA.forEach(r=>{if(!srcs.includes(r.s))return;const o=by[r.d]||(by[r.d]={d:r.d,cost:0,leads:0,sales:0,sold:0});
  o.cost+=r.cost;o.sales+=r.sales;for(let k=0;k<=q;k++){o.leads+=r['l'+k];o.sold+=r['k'+k];}});
 return days.map(d=>by[d]||{d,cost:0,leads:0,sales:0,sold:0});}
function bucket(rows,g){
 if(g==='d')return rows.map(r=>({d:r.d,end:r.d,...r}));
 if(g==='r7')return rows.map((r,i)=>{const s=rows.slice(Math.max(0,i-6),i+1);if(i<6)return null;return {d:r.d,end:r.d,cost:sum(s,'cost'),leads:sum(s,'leads'),sales:sum(s,'sales'),sold:sum(s,'sold')};}).filter(Boolean);
 const m={};rows.forEach(r=>{const k=addDays(r.d,-dow(r.d));(m[k]||(m[k]=[])).push(r);});
 return Object.keys(m).sort().map(k=>{const s=m[k];return {d:k,end:s[s.length-1].d,cost:sum(s,'cost'),leads:sum(s,'leads'),sales:sum(s,'sales'),sold:sum(s,'sold'),part:s.length<7};});}
const sum=(a,k)=>a.reduce((t,x)=>t+x[k],0);
function val(b,m,paid){switch(m){case 'cost':return b.cost;case 'leads':return b.leads;case 'sales':return b.sales;case 'cpl':return b.leads&&paid?b.cost/b.leads:null;
 case 'cps':return b.sales>=1&&paid?b.cost/b.sales:null;case 'cr1':return b.leads?b.sales/b.leads*100:null;case 'cr2':return b.leads?b.sold/b.leads*100:null;}}
function chart(m,bs,paid){const W=1100,H=210,L=46,R=14,T=10,B=26;const pts=bs.map(b=>({d:b.d,v:val(b,m,paid),b}));const vs=pts.map(p=>p.v).filter(v=>v!=null);
 if(!vs.length)return '<div class="d">нет данных (для цены нужен рекламный источник)</div>';
 let ymax=Math.max(...vs,m==='cps'?META.target:0)*1.12||1;const X=i=>L+(bs.length>1?i*(W-L-R)/(bs.length-1):0),Y=v=>H-B-v/ymax*(H-B-T);
 let g='';for(let k=0;k<=4;k++){const v=ymax*k/4;g+=`<line x1="${L}" x2="${W-R}" y1="${Y(v)}" y2="${Y(v)}" stroke="var(--line)"/><text x="${L-6}" y="${Y(v)+4}" font-size="11" fill="var(--mut)" text-anchor="end">${MET[m].f(v)}</text>`;}
 const step=Math.max(1,Math.floor(bs.length/9));for(let i=0;i<bs.length;i+=step)g+=`<text x="${X(i)}" y="${H-8}" font-size="11" fill="var(--mut)" text-anchor="middle">${bs[i].d.slice(8)}.${bs[i].d.slice(5,7)}</text>`;
 if(m==='cps')g+=`<line x1="${L}" x2="${W-R}" y1="${Y(META.target)}" y2="${Y(META.target)}" stroke="var(--red)" stroke-dasharray="5 4"/><text x="${W-R}" y="${Y(META.target)-4}" font-size="11" fill="var(--red)" text-anchor="end">цель ${META.target} €</text>`;
 const immature=b=>m==='cr2'&&addDays(b.end,14)>last; let solid='',dash='',prev=null;
 pts.forEach((p,i)=>{if(p.v==null){prev=null;return;}const x=X(i).toFixed(1),y=Y(p.v).toFixed(1);if(prev){const seg=`M${prev.x},${prev.y}L${x},${y}`;if(immature(p.b))dash+=seg;else solid+=seg;}prev={x,y};});
 const dots=pts.filter(p=>p.v!=null&&bs.length<=40).map(p=>`<circle cx="${X(pts.indexOf(p)).toFixed(1)}" cy="${Y(p.v).toFixed(1)}" r="2.6" fill="${immature(p.b)?'var(--bg)':'var(--acc)'}" stroke="var(--acc)"><title>${p.d}: ${MET[m].f(p.v)}</title></circle>`).join('');
 return `<svg viewBox="0 0 ${W} ${H}" width="100%">${g}<path d="${solid}" fill="none" stroke="var(--acc)" stroke-width="2.2"/><path d="${dash}" fill="none" stroke="var(--acc)" stroke-width="2" stroke-dasharray="4 4"/>${dots}</svg>`;}
function render(){const f=$('#from').value,t=$('#to').value,g=$('#g').value;const paid=$$('.src:checked').some(x=>x.value!=='Нет метки');
 const all=bucket(dayRows(),g).filter(b=>!b.part),bs=all.filter(b=>b.end>=f&&b.d<=t&&b.end<=t||g==='w'&&b.end>=f&&b.d<=t);
 const inR=dayRows().filter(r=>r.d>=f&&r.d<=t),T={cost:sum(inR,'cost'),leads:sum(inR,'leads'),sales:sum(inR,'sales'),sold:sum(inR,'sold')};
 const K=[['Расход',T.cost.toFixed(0)+' €'],['Заявки',T.leads],['Продажи',T.sales],['Цена заявки',paid&&T.leads?(T.cost/T.leads).toFixed(1)+' €':'—'],['Цена продажи',paid&&T.sales?(T.cost/T.sales).toFixed(1)+' €':'—'],['Конверсия по датам',T.leads?(T.sales/T.leads*100).toFixed(1)+' %':'—']];
 $('#sum').innerHTML=K.map(k=>`<div class="k"><span>${k[0]} за период</span><strong>${k[1]}</strong></div>`).join('');
 const mets=$$('.met:checked').map(x=>x.value);
 $('#charts').innerHTML=mets.map(m=>`<div class="ch"><h3>${MET[m].n}</h3><div class="d">${DESC[m]||''}</div>${chart(m,bs,paid)}</div>`).join('');
 $('#tbl').innerHTML='<thead><tr><th class="l">'+({r7:'Окно 7 дней до',w:'Неделя с',d:'День'})[g]+'</th>'+mets.map(m=>`<th>${MET[m].n}</th>`).join('')+'</tr></thead><tbody>'+bs.slice().reverse().map(b=>`<tr><td class="l">${b.d.slice(8)}.${b.d.slice(5,7)}${b.part?' (неполная)':''}${META.partial&&b.end===last?' *':''}</td>`+mets.map(m=>{const v=val(b,m,paid);return `<td>${v==null?'—':MET[m].f(v)}</td>`;}).join('')+'</tr>').join('')+'</tbody>';}
$$('.src,.met,#q,#g,#from,#to').forEach(e=>e.addEventListener('input',render));
$('#b30').onclick=()=>{$('#from').value=addDays(last,-29)<days[0]?days[0]:addDays(last,-29);$('#to').value=last;render();};
$('#ball').onclick=()=>{$('#from').value=days[0];$('#to').value=last;render();};
render();
</script></body></html>"""

if __name__ == "__main__":
    main()
