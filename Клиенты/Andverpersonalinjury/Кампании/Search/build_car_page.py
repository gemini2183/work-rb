# coding: utf-8
"""Сборка легковой страницы (Car) из готовых блоков Settlement + новых. Пишет 3 блока для Tilda, макет и копии .txt.
Запуск: python build_car_page.py   (Settlement-файлы лежат рядом, в этой же папке)
Источник правды по тексту — этот файл; правим здесь и пересобираем."""
import pathlib
import re

HERE = pathlib.Path(__file__).parent
OUT = HERE.parent.parent / "Tilda_страница_Car"
OUT.mkdir(exist_ok=True)

quiz_src = (HERE / "settlement_quiz_t123.html").read_text(encoding="utf-8")
body_src = (HERE / "settlement_body_t123.html").read_text(encoding="utf-8")
footer_src = (HERE / "settlement_footer_t123.html").read_text(encoding="utf-8")

# --- куски из Settlement: CSS шапки/плашки, их разметка, скрипт квиза, CSS квиза и тела ---
quiz_css = re.search(r"<style>(.*?)</style>", quiz_src, re.S).group(1)
hdr_css = quiz_css[quiz_css.index("/* шапка и закреплённая плашка */"):]
quiz_only_css = quiz_css[:quiz_css.index("/* шапка и закреплённая плашка */")]
hdr_html = re.search(r"(<header class=\"ldvh\">.*?</header>)", quiz_src, re.S).group(1)
sticky_html = re.search(r"(<div class=\"ldvs\">.*?</div>)", quiz_src, re.S).group(1)
sticky_html = sticky_html.replace("Get my free case review", "Leave my number")
cta_script = re.search(r"(<script>\ndocument\.addEventListener\('click'.*?</script>)", quiz_src, re.S).group(1)
quiz_script = [x for x in re.findall(r"<script>(.*?)</script>", quiz_src, re.S) if "var Q = [" in x][0]
body_css = re.search(r"<style>(.*?)</style>", body_src, re.S).group(1)
# квиз в нижней части ведёт к форме B
quiz_script = quiz_script.replace("form.href = '#ldv-form';", "form.href = '#ldv-form-2';")

# ------------------------------------------------------------------ БЛОК 1: шапка + первый экран + плашка
top_css = """
.ldvc{background:#101820;color:#fffdfa;font-family:Manrope,Arial,sans-serif;padding:20px 16px 24px}
.ldvc *,.ldvc *::before,.ldvc *::after{box-sizing:border-box}
.ldvc__wrap{max-width:760px;margin:0 auto}
.ldvc__h1{margin:0 0 10px;font-weight:800;font-size:clamp(30px,7.2vw,52px);line-height:1.08;letter-spacing:-.02em;color:#fffdfa}
.ldvc__h1 span{display:block;font-family:"DM Serif Display",Georgia,serif;font-weight:400;color:#efaa9e;letter-spacing:0}
.ldvc__sub{margin:0 0 14px;font-size:clamp(16px,2.4vw,19px);line-height:1.5;color:#ddd7ce}
.ldvc__trust{list-style:none;margin:0 0 16px;padding:0;display:flex;flex-wrap:wrap;gap:8px}
.ldvc__trust li{font-size:13px;font-weight:700;line-height:1.2;padding:7px 11px;border-radius:999px;background:#17242b;border:1px solid rgba(201,165,106,.35);color:#f6f2ea}
.ldvc__trust li b{color:#c9a56a;font-weight:800}
.ldvc__btns{display:grid;gap:10px}
.ldvc__btn{display:flex;align-items:center;justify-content:center;min-height:56px;padding:14px 18px;border-radius:12px;font:800 16.5px/1.2 Manrope,Arial,sans-serif;text-align:center;text-decoration:none;border:2px solid #e8563f}
.ldvc__btn--primary{background:#e8563f;color:#fff}
.ldvc__btn--primary:hover{background:#cf4633;border-color:#cf4633;color:#fff}
.ldvc__btn--ghost{background:transparent;color:#fffdfa;border-color:rgba(255,255,255,.4)}
.ldvc__btn--ghost:hover{border-color:#fffdfa;color:#fff}
.ldvc__anchor{display:block;height:0;scroll-margin-top:72px}
@media(min-width:700px){.ldvc{padding:44px 24px 40px}}
"""
top = f"""<!-- Landver Law: легковая страница (Car), БЛОК 1: шапка, первый экран, закреплённая плашка (Tilda T123 «HTML»). v1, 2026-10-23.
     Сразу под этим блоком ставится форма Tilda A (компактная: отступы сверху и снизу минимальные, чтобы форма была видна на первом экране телефона). -->
<style>
{hdr_css}
{top_css}
</style>

{hdr_html}

<section class="ldvc" id="ldvc" aria-labelledby="ldvc-h1">
  <div class="ldvc__wrap">
    <h1 class="ldvc__h1" id="ldvc-h1">California Car Accident Lawyer. <span>Free Case Review.</span></h1>
    <p class="ldvc__sub">Injured in a car or auto accident? Tell us what happened. An attorney reviews your case for free. No fee unless we win.</p>
    <ul class="ldvc__trust">
      <li><b>&#9733; 4.8</b> &middot; 45 Google reviews</li>
      <li>Serving all of California</li>
      <li>Call 24/7</li>
      <li>Practicing since 2004</li>
    </ul>
    <div class="ldvc__btns">
      <a class="ldvc__btn ldvc__btn--primary ldvq-phone" href="tel:+18444529465" data-ldv-cta="hero_call">Call (844) 452-9465 &middot; 24/7</a>
    </div>
    <a id="ldv-form" class="ldvc__anchor" aria-hidden="true" tabindex="-1"></a>
  </div>
</section>

{sticky_html}
{cta_script}
"""

# ------------------------------------------------------------------ БЛОК 2: все блоки под формой A + квиз вторым путём
extra_css = """
.ldvp__chips{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 14px;padding:0;list-style:none}
.ldvp__chips li{padding:9px 14px;border-radius:999px;background:#fffdfa;border:1px solid #ddd7ce;font-size:15px;font-weight:700;color:#17242b}
.ldvq--mid{padding:44px 16px}
.ldvq--mid .ldvq__q2{margin:0 0 8px;font-size:clamp(24px,5.4vw,36px);line-height:1.15;font-weight:800;letter-spacing:-.015em;color:#fffdfa}
.ldvq--mid .ldvq__eyebrow{margin:0 0 8px;font-size:12px;font-weight:800;letter-spacing:.14em;text-transform:uppercase;color:#c9a56a}
@media(min-width:700px){.ldvq--mid{padding:64px 24px}}
"""

faq = [
    ("Do I need a lawyer after a car accident in California?",
     "If you were injured, a free case review can tell you whether a lawyer can help. You do not have to decide alone or know the legal terms. Landver Law reviews your situation at no cost, and there is no fee unless we win."),
    ("How much does a car accident lawyer cost?",
     "The initial case review is free, and there is no fee unless we win. Landver Law handles personal-injury matters on a contingency basis, advances litigation costs and collects its legal fee when a recovery is obtained. Exact financial terms are confirmed in the written attorney-client agreement before representation begins."),
    ("My medical treatment is still ongoing. Is it too early to contact a lawyer?",
     "No. You do not have to wait until treatment is finished before asking for a case review. In a serious injury case, the eventual medical outcome may still be uncertain. The important starting point is understanding what happened, what treatment has occurred so far and what evidence may need to be preserved."),
    ("What if I may have been partly responsible for the accident?",
     "Partial responsibility does not automatically mean there is no claim. California uses comparative fault. If an injured person's own negligence contributed to the harm, damages can be reduced according to that person's percentage of responsibility. Do not assume the insurance company's initial fault assessment is necessarily the final allocation of responsibility."),
    ("The insurance company is asking for a recorded statement. What should I do?",
     "First identify who is requesting the statement and which insurer they represent. Obligations can differ depending on whether the request comes from your own insurer or another party's insurer. Avoid guessing about facts you do not know, minimizing injuries that are still being evaluated or signing releases you do not understand. If you are unsure about a recorded statement or release, consider getting legal advice before agreeing to it."),
    ("I already received a settlement offer. Can I still have the case reviewed?",
     "If you have not finalized the settlement and signed a release, you can still ask for legal advice about the situation. An early offer may arrive before the long-term medical picture, future treatment, income loss or permanent limitations are fully understood. If a release has already been signed, tell the lawyer immediately because that can materially change the analysis."),
    ("How long do I have to bring an injury claim in California?",
     "For many California personal-injury lawsuits, the general deadline is two years from the date of injury. But that is not a universal rule. Different facts can create different deadlines, and claims involving a California government agency can require an administrative claim much earlier. For many injury claims against a California government agency, the administrative claim deadline is generally six months from the injury. Do not use the general two-year period to assume your own deadline."),
]
faq_html = "\n".join(f"      <details><summary>{q}</summary>\n        <p>{a}</p></details>" for q, a in faq)

body = f"""<!-- Landver Law: легковая страница (Car), БЛОК 2: всё под формой A (Tilda T123 «HTML»). v1, 2026-10-23.
     Порядок: как проходит звонок, ситуации, что делает страховая, адвокат, отзывы, квиз «Not ready to call?», вопросы, финальный призыв.
     В конце якорь #ldv-form-2: сразу под блоком ставится форма B (копия формы A). -->
<style>
{body_css}
{quiz_only_css}
{extra_css}
</style>

<div class="ldvp">

  <section class="ldvp__sec ldvp__sec--cream" id="ldv-how">
    <div class="ldvp__in">
      <p class="ldvp__eyebrow">How it works</p>
      <h2 class="ldvp__h2">What happens when you call a car accident lawyer</h2>
      <ol class="ldvp__steps">
        <li><b>Tell us what happened</b>The crash, your injuries, your treatment so far. You don't need documents yet.</li>
        <li><b>We set up a free review of your case with an attorney</b>Free, with no obligation.</li>
        <li><b>The attorney explains what applies to you and what to avoid</b>You decide whether to move forward.</li>
      </ol>
      <div class="ldvp__btns">
        <a class="ldvp__btn" href="#ldv-form" data-ldv-cta="how_form">Get my free case review</a>
        <a class="ldvp__btn ldvp__btn--ghost ldvq-phone" href="tel:+18444529465" data-ldv-cta="how_call">Call (844) 452-9465 &middot; 24/7</a>
      </div>
    </div>
  </section>

  <section class="ldvp__sec ldvp__sec--white" id="ldv-situations">
    <div class="ldvp__in">
      <p class="ldvp__eyebrow">Car accident cases</p>
      <h2 class="ldvp__h2">Common car accident situations Landver Law reviews</h2>
      <ul class="ldvp__chips">
        <li>Rear-end car crash</li>
        <li>Intersection / T-bone crash</li>
        <li>Multi-vehicle collision</li>
        <li>DUI or wrong-way crash</li>
        <li>Rideshare or work-vehicle crash</li>
        <li>Pedestrian or cyclist hit by a car</li>
      </ul>
      <p class="ldvp__note">Not sure which one fits? That is okay. Tell us what happened and an attorney will review it. Every case depends on its own facts, injuries, evidence, liability and insurance coverage.</p>
    </div>
  </section>

  <section class="ldvp__sec ldvp__sec--cream" id="ldv-insurers">
    <div class="ldvp__in">
      <p class="ldvp__eyebrow">Before you talk to the insurer</p>
      <h2 class="ldvp__h2">What insurance companies often do first after a car accident</h2>
      <div class="ldvp__rows ldvp__rows--3">
        <div class="ldvp__row" style="background:#fffdfa"><b>Ask for a recorded statement</b><p>Know who is asking and why before you agree. Avoid guessing about facts you don't know.</p></div>
        <div class="ldvp__row" style="background:#fffdfa"><b>Make a quick offer</b><p>If you sign a release, the claim may be closed before the full medical picture is known.</p></div>
        <div class="ldvp__row" style="background:#fffdfa"><b>Point to your share of the blame</b><p>California reduces compensation by your percentage of fault, and the insurer's first number is not always the final one.</p></div>
      </div>
    </div>
  </section>

  <section class="ldvp__sec ldvp__sec--dark" id="ldv-attorney">
    <div class="ldvp__in ldvp__atty">
      <img src="https://landverpersonalinjury.com/wp-content/uploads/2025/04/Landver0290.jpg" width="800" height="1200" loading="lazy" alt="Alina Landver, car accident attorney at Landver Law in Beverly Hills">
      <div>
        <p class="ldvp__eyebrow">Your attorney</p>
        <h2 class="ldvp__h2">Your California car accident attorney: Alina Landver, Esq., MBA</h2>
        <ul class="ldvp__facts">
          <li>Managing Partner &middot; Trial Attorney</li>
          <li><b>California Bar</b> 231077</li>
          <li><b>Admitted</b> June 2004</li>
        </ul>
        <p class="ldvp__lead">Alina Landver began her career representing corporate clients on the defense side before focusing on injured plaintiffs. That background gives the firm a perspective on how claims may be challenged, discounted or prepared for litigation.</p>
        <p class="ldvp__src">Attorney status and admission date are based on State Bar of California records. Statements about Landver Law's experience are based on information published by the firm. Prior experience does not guarantee a particular outcome in any individual matter.</p>
      </div>
    </div>
  </section>

  <section class="ldvp__sec ldvp__sec--cream" id="ldv-reviews">
    <div class="ldvp__in">
      <p class="ldvp__eyebrow">Client reviews</p>
      <h2 class="ldvp__h2">What people say after working with Landver Law</h2>
      <div class="ldvp__rate"><b>4.8</b><div><div class="ldvp__stars" aria-hidden="true">&#9733;&#9733;&#9733;&#9733;&#9733;</div><span>out of 5 &middot; 45 Google reviews</span></div></div>
      <div class="ldvp__revs">
        <blockquote class="ldvp__rev"><div class="ldvp__stars" aria-hidden="true">&#9733;&#9733;&#9733;&#9733;&#9733;</div><p>&ldquo;Best attorney ever!&rdquo;</p><small>M. M. &middot; Google Review &middot; January 2026</small></blockquote>
        <blockquote class="ldvp__rev"><div class="ldvp__stars" aria-hidden="true">&#9733;&#9733;&#9733;&#9733;&#9733;</div><p>&ldquo;Great experience working with Landver Law Alina Landver esq.&rdquo;</p><small>D. O. Rothschild &middot; Google Review &middot; January 2026</small></blockquote>
        <blockquote class="ldvp__rev"><div class="ldvp__stars" aria-hidden="true">&#9733;&#9733;&#9733;&#9733;&#9733;</div><p>&ldquo;The attorney treated my case with great seriousness from the start.&rdquo;</p><small>Elsy Castellanos &middot; Google Review &middot; October 2025</small></blockquote>
      </div>
      <p class="ldvp__note">A review is someone else's experience, not a promise about yours. Reviews shown are excerpts from publicly displayed Google reviews. Rating and review count can change over time. Testimonials do not constitute a guarantee, warranty or prediction regarding the outcome of any legal matter.</p>
    </div>
  </section>

  <!-- Квиз вторым путём -->
  <section class="ldvq ldvq--mid" id="ldvq" aria-labelledby="ldvq-h2">
    <div class="ldvq__wrap">
      <p class="ldvq__eyebrow">Not ready to call?</p>
      <h2 class="ldvq__q2" id="ldvq-h2">Answer 5 quick questions to see what applies to your case</h2>
      <p class="ldvq__sub">See what can raise or lower the value of a car accident claim like yours, and what to avoid before you talk to the insurance company. Not a settlement calculator: no honest formula can name a number from a few answers.</p>
      <div class="ldvq__card" id="ldvq-card" aria-live="polite">
        <noscript><p class="ldvq__p">Please call us: <a href="tel:+18444529465" style="color:#efaa9e">(844) 452-9465</a> &middot; 24/7</p></noscript>
      </div>
    </div>
  </section>

  <section class="ldvp__sec ldvp__sec--white" id="ldv-faq">
    <div class="ldvp__in ldvp__faq">
      <p class="ldvp__eyebrow">Frequently asked questions</p>
      <h2 class="ldvp__h2">Questions about car accidents and hiring a lawyer</h2>
{faq_html}
      <p class="ldvp__note" style="margin-top:16px">This FAQ provides general information and is not legal advice. Deadlines, liability, insurance obligations and available claims depend on the specific facts and applicable law. An attorney-client relationship is not created by viewing this page or submitting a request for an initial case review.</p>
    </div>
  </section>

  <section class="ldvp__sec ldvp__sec--dark" id="ldv-final">
    <div class="ldvp__in">
      <p class="ldvp__eyebrow">Free case review</p>
      <h2 class="ldvp__h2">Get your free car accident case review</h2>
      <p class="ldvp__lead">Call or leave your number. We'll set up a free review of your case with an attorney, who can tell you:</p>
      <ul class="ldvp__ticks">
        <li>what applies to YOUR case, not general advice</li>
        <li>what NOT to do so you don't lose compensation</li>
        <li>your next steps, in plain language</li>
        <li>where your case stands, based on what you tell us</li>
      </ul>
      <p class="ldvp__fee">No fee unless we win.</p>
      <div class="ldvp__btns">
        <a class="ldvp__btn" href="#ldv-form-2" data-ldv-cta="final_form">Get my free case review</a>
        <a class="ldvp__btn ldvp__btn--ghost ldvq-phone" href="tel:+18444529465" data-ldv-cta="final_call">Call (844) 452-9465 &middot; 24/7</a>
      </div>
      <p class="ldvp__fine">Free. No obligation. Submitting a form does not by itself create an attorney-client relationship.</p>
    </div>
    <a id="ldv-form-2" class="ldvp__anchor" aria-hidden="true" tabindex="-1"></a>
  </section>

</div>

<script>{quiz_script}</script>
"""

# ------------------------------------------------------------------ подвал (тот же)
footer = footer_src.replace("Settlement page, подвал", "Car page, подвал")

(OUT / "1_blok_top.txt").write_text(top, encoding="utf-8")
(OUT / "2_blok_body.txt").write_text(body, encoding="utf-8")
(OUT / "3_blok_footer.txt").write_text(footer, encoding="utf-8")


# ------------------------------------------------------------------ макет (формы Tilda имитированы, компактные)
def form(i, compact):
    pad = "20px 16px 22px" if compact else "36px 16px"
    return f"""<div style="background:#f6f2ea;padding:{pad};font-family:Manrope,Arial,sans-serif;color:#17242b"><div style="max-width:520px;margin:0 auto">
<h2 style="margin:0 0 6px;font-size:{'22px' if compact else '28px'};font-weight:800">{'Prefer we call you? Leave your number.' if compact else 'Get my free case review'}</h2>
<p style="margin:0 0 12px;font-size:15px;line-height:1.45;color:#4d5a60">Leave your name and phone. We'll contact you to set up your free review with an attorney.</p>
<form class="t-form" id="form{i}"><input type="text" name="name" placeholder="First name" style="box-sizing:border-box;width:100%;height:50px;margin:0 0 8px;padding:0 14px;font-size:16px;border:1px solid #ddd7ce;border-radius:10px">
<input type="tel" name="phone" placeholder="Phone number" style="box-sizing:border-box;width:100%;height:50px;margin:0 0 8px;padding:0 14px;font-size:16px;border:1px solid #ddd7ce;border-radius:10px">
<button type="button" style="box-sizing:border-box;width:100%;height:54px;border:0;border-radius:12px;background:#e8563f;color:#fff;font:800 17px Manrope,Arial,sans-serif">Get my free case review</button></form>
<p style="margin:8px 0 0;font-size:12px;line-height:1.4;color:#68747a">Free. No obligation. Submitting this form does not by itself create an attorney-client relationship.</p></div></div>"""


preview = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>PREVIEW: Car page (локальный макет, формы Tilda имитированы)</title>
<link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=Manrope:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>body{{margin:0;background:#0d151b}}html{{scroll-behavior:smooth}}</style></head><body>
{top}
{form('A', True)}
{body}
{form('B', False)}
{footer}
</body></html>"""
(OUT / "0_maket_prosmotr.html").write_text(preview, encoding="utf-8")
print("OK", OUT)
