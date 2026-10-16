// GTM: пользовательский HTML-тег «ldv block_time» (Landver, tilda car+truck). Триггер: All Pages.
// 1) Считает секунды на каждом блоке и пушит в dataLayer:
//    {event: 'block_time', block_name: '<id без ldv-, дефисы → _>', block_seconds: <целые секунды>}
// 2) По общему активному времени пушит один раз за визит: stay_10s, engaged_30s, engaged_90s.
// Правила: блок = последний, верх которого выше середины экрана; таймер стоит, если вкладка скрыта
// или 10 с нет движения/прокрутки/кликов; отправка block_time при смене блока, каждые 30 с и при уходе.
<script>
(function () {
  if (window.__ldvBlockTime) return;
  window.__ldvBlockTime = true;
  var IDS = ['ldv-ai-hero', 'ldv-your-crash', 'ldv-crash-scenarios', 'ldv-case-examples', 'ldv-truck-cases',
    'ldv-evidence', 'ldv-mid-review', 'ldv-public-library', 'ldv-injuries', 'ldv-early-offer', 'ldv-case-value',
    'ldv-case-process', 'ldv-why-landver', 'ldv-reviews', 'ldv-faq', 'ldv-final-review', 'ldv-footer'];
  var STEPS = [[10, 'stay_10s'], [30, 'engaged_30s'], [90, 'engaged_90s']];
  var TICK = 500, IDLE = 10000, FLUSH = 30000;
  var acc = {}, total = 0, current = 'header', lastTick = Date.now(), lastActive = Date.now(), lastFlush = Date.now();
  window.dataLayer = window.dataLayer || [];

  function nameOf(id) { return id.replace(/^ldv-/, '').replace(/-/g, '_'); }
  function currentBlock() {
    var mid = window.innerHeight / 2, name = 'header';
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
