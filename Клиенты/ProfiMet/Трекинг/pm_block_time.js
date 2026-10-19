// GTM: пользовательский HTML-тег «pm block_time» (ProfiMet, mocnaszklarnia.pl, главная). Триггер: All Pages.
// По образцу Landver (Клиенты/Andverpersonalinjury/Трекинг/gtm_block_time.js), но без stay_10s / engaged_*: в контейнере ProfiMet
// уже есть time_15sec…time_300sec и engage_low/mid/hi — не дублируем.
// Считает секунды на каждом блоке и пушит в dataLayer: {event: 'block_time', block_name: '<имя блока>', block_seconds: <целые секунды>}
// Правила: блок = последний, верх которого выше середины экрана; таймер стоит, если вкладка скрыта или 10 с нет
// движения/прокрутки/кликов; отправка block_time при смене блока, каждые 30 с и при уходе. Блоки Tilda — по id `rec…`.
<script>
(function () {
  if (window.__pmBlockTime) return;
  window.__pmBlockTime = true;
  var NAMES = {
    rec2905989103: 'hero', rec2907573403: 'materials', rec2999230203: 'models_intro', rec2958154103: 'mocna',
    rec3211747203: 'nordstar', rec3210912503: 'hobby', rec3211915203: 'went_plus', rec3212364203: 'standard_plus',
    rec3219096603: 'kompakt', rec3219324903: 'mini', rec3219455303: 'maxi', rec3221657503: 'szeroka',
    rec3015645203: 'all_models_cta', rec2906074503: 'discount_100', rec2907832003: 'accessories', rec2908500503: 'accessories',
    rec2906175303: 'features', rec3008493103: 'reviews', rec3008527103: 'reviews', rec3008441503: 'reviews',
    rec2906212003: 'about_company', rec2906284003: 'delivery_payment', rec2907388203: 'faq', rec2907392403: 'faq',
    rec2907407503: 'final_contact'
  };
  var IDS = Object.keys(NAMES);
  // по одному «якорному» блоку на имя: block_view считаем один раз на имя (составные блоки — reviews, faq, accessories)
  var VIEW_IDS = ['rec2905989103', 'rec2907573403', 'rec2999230203', 'rec2958154103', 'rec3211747203', 'rec3210912503',
    'rec3211915203', 'rec3212364203', 'rec3219096603', 'rec3219324903', 'rec3219455303', 'rec3221657503', 'rec3015645203',
    'rec2906074503', 'rec2908500503', 'rec2906175303', 'rec3008493103', 'rec2906212003', 'rec2906284003', 'rec2907392403',
    'rec2907407503'];
  var TICK = 500, IDLE = 10000, FLUSH = 30000;
  var acc = {}, current = 'top', lastTick = Date.now(), lastActive = Date.now(), lastFlush = Date.now();
  window.dataLayer = window.dataLayer || [];

  function nameOf(id) { return NAMES[id]; }
  function currentBlock() {
    var mid = window.innerHeight / 2, name = 'top';
    for (var i = 0; i < IDS.length; i++) {
      var el = document.getElementById(IDS[i]);
      if (el && el.getBoundingClientRect().top <= mid) name = nameOf(IDS[i]);
    }
    return name;
  }
  function flush(final) {
    for (var k in acc) {
      var s = final ? Math.round(acc[k]) : Math.floor(acc[k]);
      if (s >= 1) {
        window.dataLayer.push({ event: 'block_time', block_name: k, block_seconds: s });
        acc[k] -= s;
      }
    }
    lastFlush = Date.now();
  }
  // block_view: блок виден минимум на 10% хотя бы 1 секунду, один раз за загрузку страницы (вместо триггера «видимость элемента» GTM:
  // он давал лишнее событие click_tel без параметра)
  if ('IntersectionObserver' in window) {
    var timers = {}, seen = {};
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        var id = en.target.id;
        if (en.isIntersecting && en.intersectionRatio >= 0.1) {
          if (!seen[id] && !timers[id]) {
            timers[id] = setTimeout(function () {
              seen[id] = true;
              window.dataLayer.push({ event: 'block_view', block_name: nameOf(id) });
            }, 1000);
          }
        } else if (timers[id]) { clearTimeout(timers[id]); timers[id] = null; }
      });
    }, { threshold: [0, 0.1] });
    VIEW_IDS.forEach(function (id) { var el = document.getElementById(id); if (el) io.observe(el); });
  }
  function active() { lastActive = Date.now(); }
  ['scroll', 'mousemove', 'keydown', 'touchstart', 'click', 'wheel'].forEach(function (e) {
    window.addEventListener(e, active, { passive: true });
  });
  setInterval(function () {
    var now = Date.now(), dt = now - lastTick;
    lastTick = now;
    var block = currentBlock();
    if (document.visibilityState === 'visible' && now - lastActive <= IDLE && dt < 5000) {
      acc[block] = (acc[block] || 0) + dt / 1000;
    }
    if (block !== current) { flush(false); current = block; }
    else if (now - lastFlush >= FLUSH) { flush(false); }
  }, TICK);
  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'hidden') flush(true);
  });
  window.addEventListener('pagehide', function () { flush(true); });
})();
</script>
