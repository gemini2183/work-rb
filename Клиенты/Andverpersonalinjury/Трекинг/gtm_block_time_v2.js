// GTM: пользовательский HTML-тег «ldv block_time script» v2 (Landver, tilda: car+truck и california-car-accident-lawyer). Триггер: All Pages.
// Отличие от v1 (2026-10-15): блок = элемент с наибольшим верхом выше середины экрана (порядок в массиве не важен);
// список блоков содержит и старую страницу, и новую, отсутствующие на странице пропускаются; форму A находим по классу .ldv2-native.
// 1) Считает секунды на каждом блоке и пушит в dataLayer:
//    {event: 'block_time', block_name: '<имя блока>', block_seconds: <целые секунды>}
// 2) По общему активному времени пушит один раз за визит: stay_10s, engaged_30s, engaged_90s.
// Правила: таймер стоит, если вкладка скрыта или 10 с нет движения/прокрутки/кликов; отправка block_time при смене блока, каждые 30 с и при уходе.
<script>
(function () {
  if (window.__ldvBlockTime) return;
  window.__ldvBlockTime = true;
  var NAMES = { 'ldvc': 'hero', 'ldv-form-section': 'form_a', '.ldv2-native': 'form_a', 'ldvq': 'quiz' };
  var IDS = ['ldv-ai-hero', 'ldv-your-crash', 'ldv-crash-scenarios', 'ldv-case-examples', 'ldv-truck-cases',
    'ldv-evidence', 'ldv-mid-review', 'ldv-public-library', 'ldv-injuries', 'ldv-early-offer', 'ldv-case-value',
    'ldv-case-process', 'ldv-why-landver', 'ldv-reviews', 'ldv-faq', 'ldv-final-review', 'ldv-footer',
    'ldvc', 'ldv-form-section', '.ldv2-native', 'ldv-insurers', 'ldv-how', 'ldv-fee', 'ldv-team', 'ldv-situations',
    'ldv-attorney', 'ldvq', 'ldv-final'];
  var STEPS = [[10, 'stay_10s'], [30, 'engaged_30s'], [90, 'engaged_90s']];
  var TICK = 500, IDLE = 10000, FLUSH = 30000;
  var acc = {}, total = 0, current = 'header', lastTick = Date.now(), lastActive = Date.now(), lastFlush = Date.now();
  window.dataLayer = window.dataLayer || [];

  function nameOf(id) { return NAMES[id] || id.replace(/^ldv-/, '').replace(/-/g, '_'); }
  function find(id) { return id.charAt(0) === '.' ? document.querySelector(id) : document.getElementById(id); }
  function currentBlock() {
    var mid = window.innerHeight / 2, name = 'header', best = -1e9;
    for (var i = 0; i < IDS.length; i++) {
      var el = find(IDS[i]);
      if (!el) continue;
      var top = el.getBoundingClientRect().top;
      if (top <= mid && top > best) { best = top; name = nameOf(IDS[i]); }
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
      total += dt / 1000;
      while (STEPS.length && total >= STEPS[0][0]) {
        window.dataLayer.push({ event: STEPS[0][1] });
        STEPS.shift();
      }
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
