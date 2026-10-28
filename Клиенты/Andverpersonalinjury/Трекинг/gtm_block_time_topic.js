// GTM: пользовательский HTML-тег «vb block_time script [topic pages]» (Landver, тематические страницы *-lawyer-california, блоки vb-*).
// Триггер: «topic pages pageview [topic pages]» (Page Path заканчивается на -lawyer-california). Старый «ldv block_time script» на этих страницах
// исключён блокирующим тем же триггером, поэтому stay_10s / engaged_30s / engaged_90s пушит ЭТОТ тег (без дублей).
// Блок = заголовок страницы с id vb-…-h1 / -h2 / -title; имя блока = первые 5 слов заголовка (латиница, цифры, «_»), как у block_view.
// Блок под экраном выбирается по заголовку с наибольшим верхом выше середины экрана; до первого заголовка — «top».
// Пушит {event:'block_time', block_name, block_seconds}; таймер стоит, если вкладка скрыта или 10 с нет движения/прокрутки/кликов.
<script>
(function () {
  if (window.__vbBlockTime) return;
  window.__vbBlockTime = true;
  var SEL = '[id^="vb-"][id$="-h1"], [id^="vb-"][id$="-h2"], [id^="vb-"][id$="-title"]';
  var STEPS = [[10, 'stay_10s'], [30, 'engaged_30s'], [90, 'engaged_90s']];
  var TICK = 500, IDLE = 10000, FLUSH = 30000;
  var acc = {}, total = 0, current = 'top', lastTick = Date.now(), lastActive = Date.now(), lastFlush = Date.now();
  window.dataLayer = window.dataLayer || [];

  function nameOf(el) {
    var t = (el.textContent || '').replace(/\s+/g, ' ').trim().toLowerCase().replace(/[^a-z0-9 ]+/g, '').split(' ').slice(0, 5).join('_');
    return t || el.id;
  }
  function currentBlock() {
    var mid = window.innerHeight / 2, name = 'top', best = -1e9;
    var els = document.querySelectorAll(SEL);
    for (var i = 0; i < els.length; i++) {
      var top = els[i].getBoundingClientRect().top;
      if (top <= mid && top > best) { best = top; name = nameOf(els[i]); }
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
