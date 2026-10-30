// Снимает с экрана Yelp Ads → Ad performance (biz.yelp.com/ads/<id>/analytics/clicks)
// показы и клики по дням из подсказок графика (react-vis) и итоги периодов из таблицы под графиком.
// Запуск: выполнить через javascript_tool в Chrome (с `await` перед выражением) или вставить в консоль страницы.
// Возвращает JSON-строку. Дальше JSON сохраняется в Клиенты/LuxeBrokers/Статистика/yelp_daily_<ГГГГ-ММ-ДД>.json
// и подаётся в yelp_stats_to_sheet.py. Скачивание CSV не используется.
// Подсказка графика не подписана вкладкой, поэтому метрика определяется по тексту подсказки («Ad impressions» / «Ad clicks»),
// а не по ожиданию: если вкладка не переключилась, скрипт упадёт, а не запишет клики в показы.
await (async () => {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const MON = {Jan:1,Feb:2,Mar:3,Apr:4,May:5,Jun:6,Jul:7,Aug:8,Sep:9,Oct:10,Nov:11,Dec:12};
  const iso = (mon, d, y) => `${y}-${String(MON[mon]).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
  const num = s => Number(String(s).replace(/[,$]/g, ''));

  function press(el) {
    for (const t of ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'])
      el.dispatchEvent(new MouseEvent(t, {bubbles: true, cancelable: true, view: window}));
  }

  async function scan(metric, label) {
    const tab = [...document.querySelectorAll('[role=tab]')].find(t => t.textContent.includes(metric));
    if (!tab) throw new Error('нет вкладки ' + metric);
    press(tab);
    await sleep(800);
    const svg = document.querySelector('svg.rv-xy-plot__inner');
    const plot = svg.closest('.rv-xy-plot').parentElement;
    const r = svg.getBoundingClientRect();
    const out = {};
    for (let x = Math.floor(r.left); x <= r.right + 10; x += 3) {
      svg.dispatchEvent(new MouseEvent('mousemove', {bubbles: true, clientX: x, clientY: r.top + 100, view: window}));
      await sleep(40);
      const m = plot.textContent.match(/(\w{3}) (\d+), (\d{4})Ad (impressions|clicks)([\d,]+)/);
      if (!m) continue;
      if (m[4] !== label) throw new Error(`вкладка ${metric}: подсказка показывает ${m[4]}, ждали ${label}`);
      out[iso(m[1], m[2], m[3])] = num(m[5]);
    }
    return out;
  }

  const imp = await scan('Ad impressions', 'impressions');
  const clk = await scan('Ad clicks', 'clicks');
  // Компактная запись «дата,показы,клики;…»: длинный JSON обрезается в выводе инструмента.
  const days = Object.keys(imp).sort().map(d => `${d},${imp[d]},${clk[d]}`).join(';');

  // Таблица периодов под графиком: «Oct 1 - Oct 29, 2026 | показы | клики | $ср.клик | $расход»
  const text = document.body.innerText.replace(/\s+/g, ' ');
  const periods = [];
  const re = /([A-Z][a-z]{2} \d+(?: - [A-Z][a-z]{2} \d+)?, \d{4}) ([\d,]+) ([\d,]+) \$([\d.,]+) \$([\d.,]+)/g;
  let m;
  while ((m = re.exec(text))) periods.push({period: m[1], impressions: num(m[2]), clicks: num(m[3]), avg_cpc: num(m[4]), spend: num(m[5])});

  const header = (text.match(/Overview\s*([A-Z][a-z]{2} \d+, \d{4} - [A-Z][a-z]{2} \d+, \d{4})/) || [])[1] || null;
  return JSON.stringify({captured_for: header, days, periods});
})()
