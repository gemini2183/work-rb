---
status: не внесено в кабинет Ringostat
updated: 2026-10-06
---

# Правила подмены Ringostat — landverpersonalinjury.tilda.ws/california-car-truck-accident

Основа: замер `phone_swap_check.py` (строгая версия) под UTM google/cpc, 2026-10-06. Каждый XPath проверен
Playwright'ом на живой странице: ровно 1 совпадение, маска воспроизводит оригинальную разметку.

Принцип (см. [[Решения]] 2026-09-04): правило нацеливаем на сам `<a>`, чтобы Ringostat менял и `href`, и содержимое;
маска НЕ содержит внешнего `<a>` (иначе самодублирование), только внутренности — иконка + label + номер.

Мобильная плашка `ldv-mob-call` уже подменяется (и текст, и href) — правило не нужно.

## 1. Header — ЗАМЕНИТЬ старое правило
Старое: `//a[contains(@class,"ldv-h__phone")]//span[contains(@class,"ldv-h__phone-number")]` — удалить.
Причина: оно меняет только текст внутри span, `href` родительского `<a>` остаётся +18444529465 (клик набирает основной номер).
Это же правило работает на dog-bite — там та же проблема.

XPath: `//a[contains(@class,"ldv-h__phone")]`

Маска:
```
<span class="ldv-h__phone-icon"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 3H4a1 1 0 0 0-1 1c0 9.4 7.6 17 17 17a1 1 0 0 0 1-1v-3l-4-2-2 2c-3.5-1.5-6.5-4.5-8-8l2-2-2-4Z"/></svg></span><span class="ldv-h__phone-copy"><span class="ldv-h__phone-label">Free Consultation</span><span class="ldv-h__phone-number">(###) ###-####</span></span>
```

## 2. Hero — новое
XPath: `//a[contains(@class,"ldv-ai-hero__call")]`

Маска:
```
<span class="ldv-ai-hero__call-icon"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 3H4a1 1 0 0 0-1 1c0 9.4 7.6 17 17 17a1 1 0 0 0 1-1v-3l-4-2-2 2c-3.5-1.5-6.5-4.5-8-8l2-2-2-4Z"/></svg></span><span class="ldv-ai-hero__call-copy"><span class="ldv-ai-hero__call-label">Free Consultation</span><span class="ldv-ai-hero__call-number">(###) ###-####</span></span>
```

## 3. Финальный блок — новое
XPath: `//a[contains(@class,"ldv-fr__phone")]`

Маска (внимание: label здесь с классом `-small`, не `-label`):
```
<span class="ldv-fr__phone-icon"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 3H4a1 1 0 0 0-1 1c0 9.4 7.6 17 17 17a1 1 0 0 0 1-1v-3l-4-2-2 2c-3.5-1.5-6.5-4.5-8-8l2-2-2-4Z"/></svg></span><span class="ldv-fr__phone-copy"><span class="ldv-fr__phone-small">Free Consultation</span><span class="ldv-fr__phone-number">(###) ###-####</span></span>
```

## 4. Footer — новое
`<a>` содержит только номер, ничего не ломается.

XPath: `//a[contains(@class,"ldv-ft__phone")]`

Маска: `(###) ###-####`

## После внесения
1. `python phone_swap_check.py --client-folder "Andverpersonalinjury" --pool-file "Коллтрекинг/Пул_номеров_car_truck_tilda.yaml"` — ждём OK на всех 4 случаях.
2. То же для dog-bite: `--pool-file "Коллтрекинг/Пул_номеров_dog_bite_tilda.yaml"` (замена правила header его меняет).
3. Глазами: иконка и "Free Consultation" на месте во всех трёх кнопках, нет "кнопки в кнопке".
4. Живой звонок с header — на какой номер идёт.
