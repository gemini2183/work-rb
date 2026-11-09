#!/usr/bin/env python
# coding: utf-8
"""Цели GA4 + сеансы -> один самодостаточный HTML с таблицей и фильтрами — ТОЛЬКО ЧТЕНИЕ GA4.

Зачем: одна страница «какие цели у нас заведены, сколько сеансов, сколько дошло до каждой цели», с разбивкой
по источнику, устройству, кампании, посадочной. Открывается двойным щелчком (данные внутри файла, интернет не нужен).

Что считается: «сеансов с целью» = метрика GA4 `sessions` в разрезе `eventName` (сеанс, где событие было хотя бы раз);
знаменатель — все сеансы среза (запрос без eventName). Фильтры по датам, источнику, устройству, кампании, посадочной
считаются в браузере из строк «день × источник × устройство × кампания × посадочная × страна».

Тесты: по умолчанию исключаются страны Spain/Ukraine/Albania и кампании с utm claude_/envybox_/widget_ (переключатель на странице).

Использование:
    PYTHONUTF8=1 python ga4_goals_dashboard.py --property 549802233 --client-folder Andverpersonalinjury --from 2026-10-01
Результат: Клиенты/<клиент>/Статистика/goals_dashboard.html (+ goals_dashboard_events.csv).
Ключ сервисного аккаунта — GA4_KEY_FILE или значение по умолчанию из ga4_behavior.py; в вики не копировать.
"""
import argparse
import csv
import datetime as dt
import json
import os

from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.oauth2 import service_account

from _config import client_stats_dir
from ga4_behavior import DEFAULT_KEY, run

DIMS = ["date", "sessionSourceMedium", "deviceCategory", "sessionCampaignName", "landingPage", "country"]

# Каталог целей: (событие, группа, понятное название, что это). Порядок = порядок в таблице.
GOALS = [
    ("session_start", "Трафик", "Сеанс", "начало сеанса (знаменатель)"),
    ("stay_10s", "Вовлечение", "10 секунд на странице", "GTM 15.10, активное время вкладки"),
    ("engaged_30s", "Вовлечение", "30 секунд", "GTM 15.10"),
    ("engaged_90s", "Вовлечение", "90 секунд", "GTM 15.10"),
    ("scroll_depth", "Вовлечение", "Глубина прокрутки", "GTM, пороги 25/50/75"),
    ("block_view", "Вовлечение", "Показ блока страницы", "GTM, 17+ блоков Tilda"),
    ("faq_open", "Вовлечение", "Открыт вопрос FAQ", "GTM"),
    ("cta_click", "Действие", "Клик по кнопке CTA", "GTM 24.10"),
    ("click_tel", "Действие", "Клик по номеру телефона", "GTM 15.10, tel:"),
    ("email_click", "Действие", "Клик по email", "GTM 15.10"),
    ("form_popup_open", "Действие", "Открыто окно формы", "GTM 24.10"),
    ("quiz_start", "Квиз", "Квиз: ответ на 1-й вопрос", "первый тап по ответу; контакт не оставлен"),
    ("quiz_step", "Квиз", "Квиз: ответ на любой вопрос", "каждый тап (событий больше, чем сеансов)"),
    ("quiz_complete", "Квиз", "Квиз: ответил на все 5 вопросов, показан результат", "это ещё НЕ заявка: ни телефона, ни формы"),
    ("quiz_cta", "Квиз", "Квиз: нажал кнопку на экране результата", "«Get my free case review» (скролл к форме) или «Call»; заявка — только form_submit"),
    ("quiz_restart", "Квиз", "Квиз: «Change my answers»", "прошёл заново"),
    ("lead_form_start", "Заявка", "Начал заполнять форму", "фокус в поле формы; ещё не отправлено"),
    ("form_start", "Заявка", "Фокус в поле формы (авто GA4)", "улучшенная статистика"),
    ("form_submit", "Заявка", "ЗАЯВКА: форма отправлена", "ключевое событие GA4; считается и после квиза, и отдельная форма"),
    ("callback_request", "Заявка", "Запрос звонка (виджет Envybox)", "GTM v14 27.10, ключевое событие GA4"),
]
KEY = ["form_submit", "callback_request"]

# С какой даты событие вообще могло отправляться (публикации GTM по Журнал_изменений.md): до неё «0» — не «не дошли», а «не измеряли».
START = {
    "stay_10s": "2026-10-15", "engaged_30s": "2026-10-15", "engaged_90s": "2026-10-15", "block_view": "2026-10-15",
    "block_time": "2026-10-15", "faq_open": "2026-10-15", "email_click": "2026-10-15",   # И-048, GTM v6
    "scroll_depth": "2026-10-24", "cta_click": "2026-10-24", "form_popup_open": "2026-10-24", "lead_form_start": "2026-10-24",
    "quiz_start": "2026-10-24", "quiz_step": "2026-10-24", "quiz_complete": "2026-10-24", "quiz_cta": "2026-10-24",
    "quiz_restart": "2026-10-24",                                                          # И-070, GTM v7-8; первые события 26.10
    "callback_request": "2026-10-27",                                                      # GTM v14
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--property", required=True)
    ap.add_argument("--client-folder", required=True)
    ap.add_argument("--from", dest="d1", default="2026-10-01")
    ap.add_argument("--to", dest="d2", default=dt.date.today().isoformat())
    a = ap.parse_args()

    key = os.environ.get("GA4_KEY_FILE", DEFAULT_KEY)
    cl = BetaAnalyticsDataClient(credentials=service_account.Credentials.from_service_account_file(key))
    S = run(cl, a.property, a.d1, a.d2, DIMS, ["sessions", "engagedSessions"], [], limit=100000)
    E = run(cl, a.property, a.d1, a.d2, DIMS + ["eventName"], ["sessions", "eventCount"], [], limit=100000)
    S = [r[:6] + [int(r[6]), int(r[7])] for r in S]
    E = [r[:7] + [int(r[7]), int(r[8])] for r in E]
    names = {g[0] for g in GOALS}
    extra = sorted({r[6] for r in E} - names)
    data = {"S": S, "E": E, "goals": GOALS, "start": START, "key": KEY, "extra": extra, "from": a.d1, "to": a.d2,
            "gen": dt.datetime.now().strftime("%Y-%m-%d %H:%M"), "prop": a.property}

    out_dir = client_stats_dir(a.client_folder)
    html = HTML.replace("__DATA__", json.dumps(data, ensure_ascii=False))
    p = out_dir / "goals_dashboard.html"
    p.write_text(html, encoding="utf-8")
    with open(out_dir / "goals_dashboard_events.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(DIMS + ["eventName", "sessions", "eventCount"])
        w.writerows(E)
    print(f"сеансов-строк {len(S)}, событий-строк {len(E)}, нестандартные события: {extra}")
    print(p)


HTML = r"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Цели и сеансы GA4</title>
<style>
:root{--bg:#f6f7f9;--card:#fff;--tx:#1b2430;--mu:#6b7686;--ln:#e3e7ee;--ac:#2f6fed;--ac2:#c9d9fb;--ok:#1d8a5b;--wa:#b7791f}.wa{color:var(--wa)}
@media (prefers-color-scheme:dark){:root{--bg:#12161c;--card:#1b222b;--tx:#e6ebf2;--mu:#93a0b2;--ln:#2a3340;--ac:#6aa0ff;--ac2:#27406f;--ok:#4cc38a;--wa:#e0b25a}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--tx);font:14px/1.4 system-ui,Segoe UI,Roboto,sans-serif}
.wrap{max-width:1280px;margin:0 auto;padding:16px}
h1{font-size:20px;margin:0 0 4px}.sub{color:var(--mu);font-size:12px;margin-bottom:12px}
.card{background:var(--card);border:1px solid var(--ln);border-radius:10px;padding:12px;margin-bottom:12px}
.filters{display:flex;flex-wrap:wrap;gap:10px;align-items:end}
.filters label{display:flex;flex-direction:column;font-size:11px;color:var(--mu);gap:3px}
select,input[type=date]{background:var(--bg);color:var(--tx);border:1px solid var(--ln);border-radius:6px;padding:6px;font-size:13px;min-width:130px}
button{background:var(--ac);color:#fff;border:0;border-radius:6px;padding:7px 12px;cursor:pointer;font-size:13px}
button.sec{background:transparent;color:var(--ac);border:1px solid var(--ac)}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}
.tile .v{font-size:26px;font-weight:650}.tile .l{font-size:12px;color:var(--mu)}
table{border-collapse:collapse;width:100%}th,td{padding:6px 8px;border-bottom:1px solid var(--ln);text-align:right;white-space:nowrap}
th{font-size:11px;color:var(--mu);font-weight:600;cursor:pointer;position:sticky;top:0;background:var(--card)}
td:first-child,th:first-child,td.t,th.t{text-align:left}
.grp td{background:var(--bg);font-weight:600;color:var(--mu);font-size:11px;text-transform:uppercase;letter-spacing:.04em}
.bar{display:inline-block;height:8px;background:var(--ac);border-radius:4px;vertical-align:middle;margin-left:6px;min-width:1px}
.key{color:var(--ok);font-weight:600}.mu{color:var(--mu)}.zero{color:var(--mu);opacity:.6}
.scroll{overflow:auto;max-height:520px}.row{display:flex;gap:12px;flex-wrap:wrap;align-items:center;margin-bottom:8px}
svg text{fill:var(--mu);font-size:10px}.note{font-size:12px;color:var(--mu);margin-top:6px}
</style></head><body><div class="wrap">
<h1>Цели и сеансы — GA4</h1>
<div class="sub" id="sub"></div>
<div class="card filters">
 <label>С<input type="date" id="f1"></label><label>По<input type="date" id="f2"></label>
 <label>Источник / канал<select id="fsm"></select></label>
 <label>Устройство<select id="fdev"></select></label>
 <label>Кампания<select id="fcamp"></select></label>
 <label>Посадочная<select id="fland"></select></label>
 <label style="flex-direction:row;align-items:center;gap:6px"><input type="checkbox" id="ftest" checked> исключить тесты</label>
 <button class="sec" id="reset">Сбросить</button>
</div>
<div class="tiles" id="tiles"></div>
<div class="card" style="margin-top:12px"><div class="row"><b>Цели в выбранном срезе</b>
 <span class="mu" id="gsub"></span><button class="sec" id="csv1" style="margin-left:auto">CSV</button></div>
 <div class="scroll"><table id="goals"></table></div>
 <div class="note">«Сеансов с целью» — сеансы, где событие было хотя бы раз. «Событий» — всего срабатываний. Зелёным — ключевые события GA4. Выборка мала: проценты на единицах сеансов — не вывод. ⚠ — событие начали измерять позже начала периода: до той даты в GTM его не было, проценты считаются только от сеансов после неё.</div></div>
<div class="card"><div class="row"><b>Разбивка по</b>
 <select id="pdim"><option value="3">кампании</option><option value="4">посадочной</option><option value="1">источнику / каналу</option><option value="2">устройству</option><option value="6">направлению (по посадочной)</option><option value="0">дню</option></select>
 <span class="mu">сеансов с целью; в скобках доля от сеансов строки с даты, когда событие начали измерять</span><button class="sec" id="csv2" style="margin-left:auto">CSV</button></div>
 <div class="scroll"><table id="pivot"></table></div></div>
<div class="card"><div class="row"><b>По дням:</b> сеансы и сеансы с целью
 <select id="cgoal"></select></div><div id="chart"></div></div>
</div>
<script>
const D=__DATA__;
const $=id=>document.getElementById(id);
const TEST_COUNTRY=new Set(['Spain','Ukraine','Albania']);
const TEST_CAMP=/claude_|envybox_|widget_|^test/i;
const LAND=p=>{p=(p||'').split('?')[0];const m={'/':'Главная','/california-car-truck-accident':'Car+Truck (старая)','/california-car-accident-lawyer':'Car (новая)','/california-car-accident-settlement':'Settlement','/uber-lyft-accident-lawyer-california':'Uber/Lyft','/pedestrian-accident-lawyer-california':'Pedestrian','/motorcycle-accident-lawyer-california':'Motorcycle','/bicycle-accident-lawyer-california':'Bicycle','/brain-injury-lawyer-california':'Brain injury','/wrongful-death-lawyer-california':'Wrongful death','/dog-bite':'Dog bite'};return m[p]||p||'(not set)'};
const KEYS=new Set(D.key);
const ST=g=>(D.start[g]||'0000-00-00');
const dmy=s=>s.slice(8)+'.'+s.slice(5,7);
const goalName=Object.fromEntries(D.goals.map(g=>[g[0],g]));
function fill(sel,vals,all='Все'){sel.innerHTML='<option value="">'+all+'</option>'+vals.map(v=>`<option>${v}</option>`).join('')}
const uniq=(arr,i)=>[...new Set(arr.map(r=>r[i]))].sort();
const fmtDate=s=>s.length==8?s.slice(0,4)+'-'+s.slice(4,6)+'-'+s.slice(6):s;
D.S.forEach(r=>r[0]=fmtDate(r[0]));D.E.forEach(r=>r[0]=fmtDate(r[0]));
fill($('fsm'),uniq(D.S,1));fill($('fdev'),uniq(D.S,2));fill($('fcamp'),uniq(D.S,3));
fill($('fland'),[...new Set(D.S.map(r=>LAND(r[4])))].sort());
$('f1').value=D.from;$('f2').value=D.to;
const cg=$('cgoal');cg.innerHTML=D.goals.filter(g=>g[0]!='session_start').map(g=>`<option value="${g[0]}">${g[2]}</option>`).join('');cg.value='stay_10s';
$('sub').textContent=`Свойство GA4 ${D.prop} · данные ${D.from} — ${D.to} · выгружено ${D.gen}. Только чтение.`;
function pass(r){const t=$('ftest').checked;
 if(r[0]<$('f1').value||r[0]>$('f2').value)return false;
 if($('fsm').value&&r[1]!==$('fsm').value)return false;
 if($('fdev').value&&r[2]!==$('fdev').value)return false;
 if($('fcamp').value&&r[3]!==$('fcamp').value)return false;
 if($('fland').value&&LAND(r[4])!==$('fland').value)return false;
 if(t&&(TEST_COUNTRY.has(r[5])||TEST_CAMP.test(r[3])))return false;return true}
const pct=(a,b)=>b?(100*a/b).toFixed(1)+'%':'—';
let lastGoals=[],lastPivot=[];
function render(){
 const S=D.S.filter(pass),E=D.E.filter(pass);
 const ses=S.reduce((a,r)=>a+r[6],0),eng=S.reduce((a,r)=>a+r[7],0);
 const agg={};E.forEach(r=>{const a=agg[r[6]]||(agg[r[6]]={s:0,c:0});a.s+=r[7];a.c+=r[8]});
 const keyS=D.key.reduce((a,k)=>a+(agg[k]?agg[k].s:0),0);
 const den={};const denOf=g=>{if(!(g in den))den[g]=S.filter(r=>r[0]>=ST(g)).reduce((a,r)=>a+r[6],0);return den[g]};
 $('tiles').innerHTML=[['Сеансов',ses],['Вовлечённых',eng+' ('+pct(eng,ses)+')'],['10+ секунд (с 15.10)',(agg.stay_10s||{s:0}).s+' ('+pct((agg.stay_10s||{s:0}).s,denOf('stay_10s'))+')'],['Клик по телефону',(agg.click_tel||{s:0}).s],['Ключевые (заявки)',keyS]].map(x=>`<div class="card tile"><div class="v">${x[1]}</div><div class="l">${x[0]}</div></div>`).join('');
 $('gsub').textContent=`сеансов в срезе: ${ses}`;
 let h='<tr><th class="t">Цель</th><th class="t">Событие</th><th class="t">Измеряется с</th><th>Сеансов с целью</th><th>% от сеансов за период измерения</th><th>Событий</th></tr>';lastGoals=[['Группа','Цель','Событие','Измеряется с','Сеансов с целью','Сеансов в период измерения','% от сеансов','Событий']];
 let grp='';const rows=D.goals.concat(D.extra.map(e=>[e,'Прочее',e,'не в каталоге']));
 rows.forEach(g=>{const a=agg[g[0]]||{s:0,c:0};
  if(g[1]!==grp){grp=g[1];h+=`<tr class="grp"><td colspan="6">${grp}</td></tr>`}
  const dn=denOf(g[0]),late=ST(g[0])>$('f1').value,w=dn?Math.min(100,100*a.s/dn):0,k=KEYS.has(g[0])?' key':'',z=a.s?'':' zero';
  h+=`<tr class="${z}"><td class="t${k}">${g[2]}<div class="mu" style="font-size:11px">${g[3]||''}</div></td><td class="t mu">${g[0]}</td><td class="t ${late?'wa':'mu'}">${D.start[g[0]]?dmy(D.start[g[0]]):'весь период'}${late?' ⚠':''}</td><td class="${k}">${a.s}</td><td>${pct(a.s,dn)} <span class="mu">из ${dn}</span><span class="bar" style="width:${w*1.2}px"></span></td><td>${a.c}</td></tr>`;
  lastGoals.push([g[1],g[2],g[0],D.start[g[0]]||'',a.s,dn,pct(a.s,dn),a.c])});
 $('goals').innerHTML=h;
 // pivot
 const di=+$('pdim').value;const key=r=>di==6?LAND(r[4]):di==4?LAND(r[4]):r[di];
 const cols=['stay_10s','engaged_30s','cta_click','click_tel','quiz_start','quiz_complete','lead_form_start','form_submit','callback_request'];
 const P={};S.forEach(r=>{const k=key(r);const p=P[k]||(P[k]={s:0,e:0,g:{},d:{}});p.s+=r[6];p.e+=r[7];cols.forEach(c=>{if(r[0]>=ST(c))p.d[c]=(p.d[c]||0)+r[6]})});
 E.forEach(r=>{if(!cols.includes(r[6]))return;const k=key(r);const p=P[k];if(p)p.g[r[6]]=(p.g[r[6]]||0)+r[7]});
 let ph='<tr><th class="t">'+$('pdim').selectedOptions[0].text+'</th><th>Сеансов</th><th>Вовлеч.</th>'+cols.map(c=>`<th title="${c}: измеряется с ${D.start[c]||'начала'}">${goalName[c][2]}${D.start[c]?'<br><span class="mu">с '+dmy(D.start[c])+'</span>':''}</th>`).join('')+'</tr>';
 lastPivot=[['Срез','Сеансов','Вовлечённых'].concat(cols)];
 Object.entries(P).sort((a,b)=>di==0?(a[0]<b[0]?1:-1):b[1].s-a[1].s).forEach(([k,p])=>{
  ph+=`<tr><td class="t">${k}</td><td>${p.s}</td><td>${p.e}</td>`+cols.map(c=>{const n=p.g[c]||0;return `<td class="${n?'':'zero'}${KEYS.has(c)&&n?' key':''}">${n}${n?` <span class="mu">(${pct(n,p.d[c])})</span>`:''}</td>`}).join('')+'</tr>';
  lastPivot.push([k,p.s,p.e].concat(cols.map(c=>p.g[c]||0)))});
 $('pivot').innerHTML=ph;
 // chart
 const days={};S.forEach(r=>{(days[r[0]]=days[r[0]]||{s:0,g:0}).s+=r[6]});
 E.forEach(r=>{if(r[6]===cg.value){(days[r[0]]=days[r[0]]||{s:0,g:0}).g+=r[7]}});
 const ks=Object.keys(days).sort();const mx=Math.max(1,...ks.map(k=>days[k].s));const W=Math.max(600,ks.length*26),H=150;
 const bw=W/Math.max(ks.length,1);
 $('chart').innerHTML=`<svg viewBox="0 0 ${W} ${H+30}" style="width:100%;max-width:${W}px">`+ks.map((k,i)=>{const d=days[k],hs=H*d.s/mx,hg=H*d.g/mx,x=i*bw+3;
  return `<rect x="${x}" y="${H-hs}" width="${bw-6}" height="${hs}" fill="var(--ac2)"><title>${k}: сеансов ${d.s}, с целью ${d.g}</title></rect><rect x="${x+bw*0.2}" y="${H-hg}" width="${bw*0.4}" height="${hg}" fill="var(--ac)"><title>${k}: с целью ${d.g}</title></rect>${i%3==0?`<text x="${x}" y="${H+12}">${k.slice(5)}</text>`:''}`}).join('')+'</svg>';
}
['f1','f2','fsm','fdev','fcamp','fland','ftest','pdim','cgoal'].forEach(i=>$(i).addEventListener('change',render));
$('reset').onclick=()=>{['fsm','fdev','fcamp','fland'].forEach(i=>$(i).value='');$('f1').value=D.from;$('f2').value=D.to;$('ftest').checked=true;render()};
function dl(rows,name){const b=new Blob(['﻿'+rows.map(r=>r.map(x=>'"'+String(x).replace(/"/g,'""')+'"').join(';')).join('\n')],{type:'text/csv'});const a=document.createElement('a');a.href=URL.createObjectURL(b);a.download=name;a.click()}
$('csv1').onclick=()=>dl(lastGoals,'goals.csv');$('csv2').onclick=()=>dl(lastPivot,'pivot.csv');
render();
</script></body></html>
"""

if __name__ == "__main__":
    main()
