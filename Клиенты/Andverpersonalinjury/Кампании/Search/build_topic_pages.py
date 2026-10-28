# coding: utf-8
"""Сборка тематических посадочных Landver (без квиза) из общего шаблона. Тексты каждой страницы — в словаре PAGES ниже.
Запуск: python build_topic_pages.py motorcycle   (папка Tilda_страница_<Тема> создаётся в Клиенты/Andverpersonalinjury)
Источник правды по тексту — этот файл: правим здесь и пересобираем, в Tilda вставляем всегда файлы из папки.
Общее для всех страниц (шапка, плашка, форма, подвал, адвокат, отзывы, значки, оплата, как проходит звонок) — в шаблоне; своё у темы — только PAGES[<тема>].
Правила сборки (ловушки прошлых страниц, База_знаний/Агенты/Запуск_трекинга_новой_посадочной.md):
 - каждая ссылка tel: — кнопка (не внутри фразы), класс ldvq-phone и data-ldv-cta из набора, на который уже есть правила Ringostat;
 - тексты кнопок звонка совпадают с масками Ringostat: «Call (844) 452-9465 · 24/7» (hero/how/fee/final) и «Call (844) 452-9465» (attorney_call);
 - как на живой Car (28.10): ОДНА форма, все кнопки «Get my free case review» ведут на якорь #ldv-form (стоит сразу под первым экраном); второй формы и окна нет (якорь окно не открывает);
 - палитра и шрифт — как у живой Car после «Global brand restyle V2»: кремовый/белый, оливково-золотые кнопки #826510, тёмно-коричневые блоки #302d28, Montserrat;
 - фото в блоках — те же файлы Tilda, что на живой Car (бумаги страховой, юридический офис, панорама Лос-Анджелеса, командное фото);
 - нет динамических кнопок (создаваемых скриптом), нет мёртвых якорей, один H1, у всех картинок alt."""
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).parent
CLIENT = HERE.parent.parent

PHONE = "(844) 452-9465"
TEL = "tel:+18444529465"
SITE = "https://landverpersonalinjury.com"

quiz_src = (HERE / "settlement_quiz_t123.html").read_text(encoding="utf-8")
body_src = (HERE / "settlement_body_t123.html").read_text(encoding="utf-8")
footer_src = (HERE / "settlement_footer_t123.html").read_text(encoding="utf-8")

quiz_css = re.search(r"<style>(.*?)</style>", quiz_src, re.S).group(1)
hdr_css = quiz_css[quiz_css.index("/* шапка и закреплённая плашка */"):]
hdr_html = re.search(r"(<header class=\"ldvh\">.*?</header>)", quiz_src, re.S).group(1)
hdr_html = hdr_html.replace('href="#ldvq"', 'href="#ldvc"')  # в Settlement якорь вёл на квиз; здесь квиза нет
sticky_html = re.search(r"(<div class=\"ldvs\">.*?</div>)", quiz_src, re.S).group(1)
sticky_html = sticky_html.replace("Get my free case review", "Leave my number")
cta_script = re.search(r"(<script>\ndocument\.addEventListener\('click'.*?</script>)", quiz_src, re.S).group(1)
body_css = re.search(r"<style>(.*?)</style>", body_src, re.S).group(1)


BRAND_MAP = [  # старая палитра Settlement/Car v1 -> палитра живой Car (Global brand restyle V2)
    ("#e8563f", "#826510"), ("#cf4633", "#6e530d"), ("#b65241", "#937a4e"), ("#c9a56a", "#d2b16d"),
    ("#101820", "#302d28"), ("#0d151b", "#302d28"), ("#17242b", "#292929"), ("#4d5a60", "#66615b"),
    ("#f6f2ea", "#f7f2ea"), ("#ddd7ce", "#e7dfd2"), ("#fffdfa", "#ffffff"), ("#efaa9e", "#d2b16d"),
    ("#929a9e", "#b5ada0"), ("#68747a", "#77716a"), ("#c9893a", "#b19154"), ("#b9b4ab", "#b5ada0"),
    ("rgba(201,165,106,", "rgba(210,177,109,"), ("Manrope", "Montserrat"),
]


def brand(css):
    for a, b in BRAND_MAP:
        css = css.replace(a, b)
    return css

# ------------------------------------------------------------------ общие данные
BADGES = [  # значки с главной клиента (подтверждены клиентом 28.10, со слов пользователя); Top 100 и CAALA с главной не берём — их нет в подтверждённом списке
    ("image-1.png", "Litigator Awards, ranked top 1% lawyers"),
    ("image-2.png", "Super Lawyers"),
    ("image-3.png", "American Institute of Trial Lawyers, Litigator of the Year 2021"),
    ("image-4.png", "National Alliance of Attorneys, Member, Attorney of the Year 2021"),
    ("image-5.png", "Million Dollar Advocates Forum"),
    ("image-6.png", "Los Angeles County Bar Association (LACBA)"),
]
REVIEWS = [  # статичный блок лучших отзывов; ссылка на профиль автора в Google (с главной клиента, 28.10)
    ("Francis Padilla", "September 2025", "106434070416505315970",
     "They walked me through every step of my case and took care of virtually everything, which made my life easier. Everyone on the team was so helpful and knowledgeable, always available when I needed help with any question I may have had."),
    ("Elsy Castellanos", "October 2025", "106611924844132641706",
     "The attorney treated my case with great seriousness from the start. They were very clear in communication, answered all my questions, and fought relentlessly for me."),
    ("Nureet Cohen", "August 2025", "100250608118481741255",
     "Landver Law Personnel, and especially Alina Landver came to my, and my family rescue several times in the past 10 years. No matter if the case is big or small, we always felt we are treated with the best advise. Always ready to listen and act on our behalf."),
]
RATING, RATING_COUNT = "4.8", "45"  # профиль Google, прочитано 28.10.2026 (виджет на сайте клиента отстаёт: 4.9 / 39)
GOOGLE_PROFILE = "https://maps.google.com/?cid=14462387040831338871"
RESULT_NOTE = ("Past results do not guarantee, predict or imply a similar outcome in any other matter. Every case depends on its own "
               "facts, injuries, evidence, liability, insurance coverage and applicable law.")
RESULTS_ALL = {  # тексты — с главной клиента (23.10.2026)
    "motorcycle": ("$18.5M", "Motorcycle accident", "A driver's failure to yield resulted in severe fractures and an extensive recovery."),
    "truck": ("$35.2M", "Truck accident", "One of the firm's most contested cases. The result was a top verdict for the client."),
    "bus": ("$17.1M", "Bus accident", "A public transit passenger was hurt through no fault of their own. The firm pursued the agency and obtained a result that reflected the severity of the injury."),
    "wrongful": ("$14M", "Wrongful death", "A parent's death. The firm held the responsible party accountable on behalf of the family."),
    "mva": ("$38.5M", "Motor vehicle accident", "A highway rear-end collision caused severe spinal injuries and a prolonged recovery. The firm built a comprehensive evidentiary record and secured a top verdict."),
}
FAQ_COMMON = {
    "cost": ("How much does a {topic} lawyer cost?",
             "The initial case review is free, and there is no fee unless we win. Landver Law handles personal-injury matters on a contingency basis, advances litigation costs and collects its legal fee when a recovery is obtained. Exact financial terms are confirmed in the written attorney-client agreement before representation begins."),
    "treatment": ("My treatment is still ongoing. Is it too early to contact a lawyer?",
                  "No. You do not have to wait until treatment is finished before asking for a case review. In a serious injury case, the eventual medical outcome may still be uncertain. The important starting point is understanding what happened, what treatment has occurred so far and what evidence may need to be preserved."),
}

# ------------------------------------------------------------------ тексты страниц
PAGES = {}
PAGES["motorcycle"] = dict(
    folder="Tilda_страница_Motorcycle",
    slug="california-motorcycle-accident-lawyer",
    title="California Motorcycle Accident Lawyer | Landver Law",
    desc="Hurt in a motorcycle crash in California? Get a free case review from Landver Law. No fee unless we win. Call 24/7 or leave your number.",
    h1="California Motorcycle Accident Lawyer. Free Case Review.",
    sub="Hurt in a motorcycle crash? After a crash, insurance companies often look for a way to put part of the blame on the rider. Tell us what happened. An attorney reviews your case for free.",
    topic="motorcycle accident",
    atty_alt="Alina Landver, motorcycle accident attorney at Landver Law in Beverly Hills",
    result_chip=("$18.5M", "motorcycle accident result*"),
    results=["motorcycle", "truck", "mva"],
    worries=dict(
        eyebrow="After the crash",
        h2="What insurance companies often tell a rider after a crash",
        cards=[
            ("&ldquo;You were lane splitting.&rdquo;",
             "Lane splitting is legal in California when it is done safely and prudently. Whether it was in your crash depends on the facts: speed, traffic, space. It can matter for fault, but it does not end a claim by itself."),
            ("&ldquo;You weren't wearing a helmet.&rdquo;",
             "California law requires riders to wear a helmet. Riding without one does not automatically mean there is no claim, but an insurer may argue it affected your injuries, especially head injuries. Tell the attorney exactly what happened."),
            ("&ldquo;The driver says they didn't see you.&rdquo;",
             "That is an explanation, not a legal conclusion. Who was at fault depends on what happened: where each vehicle was, speeds, signals, witnesses and video."),
            ("&ldquo;Here is a quick offer for your bike and bills.&rdquo;",
             "If you sign a release, the claim may be closed before the full medical picture is known."),
        ],
        note="California reduces compensation by your percentage of fault. It does not automatically cancel it, and the insurer's first number is not always the final one.",
    ),
    checklist=dict(
        eyebrow="First days",
        h2="After a motorcycle crash: what to do now, and what to hold off on",
        do_title="Do now",
        do=["Get medical care. Tell the doctor everything that hurts, even if it seems small.",
            "Take photos of the scene, the bike and your gear if you can.",
            "Keep your helmet, jacket, gloves and boots as they are.",
            "Write down names and phone numbers of witnesses and save the police report number."],
        hold_title="Hold off until you have talked to an attorney",
        hold=["Repairing, selling or scrapping the bike. It can show how the crash happened. If an insurer asks to inspect it, ask before you move it.",
              "Giving a recorded statement to the other driver's insurer.",
              "Signing a release or accepting a quick offer.",
              "Posting about the crash on social media."],
        note="This is general information, not legal advice.",
    ),
    steps_h2="What happens when you call a motorcycle accident lawyer",
    situations_h2="Common motorcycle accident situations Landver Law reviews",
    situations=["A driver turned left in front of you or failed to yield",
                "A driver changed lanes without seeing you",
                "Rear-ended at a light or in slow traffic",
                "A car door opened into your path",
                "Hit by a distracted, speeding or drunk driver",
                "Gravel, debris, a pothole or poor road design",
                "Hit while riding as a passenger",
                "A loved one died in a motorcycle crash"],
    atty_h2="Your California motorcycle accident attorney: Alina Landver, Esq., MBA",
    faq_h2="Questions about motorcycle accidents and hiring a lawyer",
    faq=[
        ("Can I still have a claim if I was lane splitting?",
         "Possibly. Lane splitting is legal in California when it is done safely and prudently. An insurer may argue that you were at fault anyway. California uses comparative fault: if a rider's own actions contributed to the crash, damages can be reduced by the rider's percentage of responsibility, not automatically denied. Whether the lane splitting was safe and prudent depends on the facts, such as speed, traffic and space. A free case review looks at what happened in your crash."),
        ("What if I wasn't wearing a helmet?",
         "Not wearing a helmet does not automatically end a claim. California law requires riders to wear a helmet, and an insurer may argue it affected your injuries, especially head injuries. How much it matters depends on your injuries and how the crash happened. Tell the attorney exactly what happened, including the helmet. It is better to know now than to be surprised later."),
        ("The driver says &ldquo;I didn't see him.&rdquo; Does that help them?",
         "It is an explanation, not a legal conclusion. Drivers are expected to watch for motorcycles too. Who was at fault depends on what happened: where each vehicle was, speeds, signals, witnesses and video where it exists. Tell us what you remember and what evidence may exist."),
        ("The other driver's insurance company called me. What should I do?",
         "First identify who is calling and which insurer they represent. Avoid guessing about facts you do not know, minimizing injuries that are still being evaluated, or signing releases you do not understand. If you are unsure about a recorded statement or an offer, consider getting legal advice before agreeing to it."),
        ("Should I repair or sell my motorcycle before the review?",
         "If you can, wait. The bike, its damage and your gear can show how the crash happened. Take photos first. If an insurer asks to inspect the bike, ask before you move or repair it, and get advice if you are unsure."),
        "cost",
        ("How much is my motorcycle accident case worth?",
         "No honest number can be named without the facts. It depends on your injuries, medical costs, time off work, future care, who was at fault and the insurance coverage available. The review shows what applies to your case. Landver Law does not promise a result."),
        "treatment",
        ("How long do I have to bring a motorcycle injury claim in California?",
         "For many California personal-injury lawsuits, the general deadline is two years from the date of injury. But that is not a universal rule. Different facts can create different deadlines. For example, if a road hazard or road design is involved, a claim against a California government agency can require an administrative claim much earlier, generally within six months of the injury. Do not use the general two-year period to assume your own deadline."),
    ],
    final_h2="Get your free motorcycle accident case review",
    photos=dict(situations=None),  # на Car тут фото разбитых машин; для мотоцикла своего снимка пока нет
)


# ------------------------------------------------------------------ шаблон (палитра и блоки как на живой Car, 28.10)
TILDA = "https://static.tildacdn.net"
PHOTOS_COMMON = dict(  # те же файлы Tilda, что на живой california-car-accident-lawyer
    insurers=(f"{TILDA}/tila3838-3533-4565-a532-303733633138/landver_insurance_no.webp",
              "Insurance claim paperwork and accident documentation"),
    how=(f"{TILDA}/tila3935-6566-4461-b235-326364613238/landver_legal_office.webp",
         "Professional California law office with legal documents and scales of justice"),
    final=(f"{TILDA}/tila6434-3533-4135-a433-626566353864/landver_california_n.webp",
           "Los Angeles California skyline at golden hour with palm trees"),
    team=(f"{TILDA}/tila3339-6566-4261-b363-313039383634/IMG_8729-1_1.webp", "The Landver Law legal team"),
)


def btn_call(place, ghost=True, with_24=True, cls="ldvp__btn"):
    text = f"Call {PHONE}" + (" &middot; 24/7" if with_24 else "")
    g = " ldvp__btn--ghost" if ghost else ""
    return f'<a class="{cls}{g} ldvq-phone" href="{TEL}" data-ldv-cta="{place}">{text}</a>'


def btn_form(place, label="Get my free case review", ghost=False):
    g = " ldvp__btn--ghost" if ghost else ""
    return f'<a class="ldvp__btn{g}" href="#ldv-form" data-ldv-cta="{place}">{label}</a>'


FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
         '<link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500;600;700;800&display=swap" rel="stylesheet">')

HDR_V2 = """
/* шапка и плашка: как у живой Car (Global brand restyle V2) */
.ldvh{background:#fff !important;border-bottom:1px solid #e7dfd2 !important}
.ldvh__in{max-width:1200px;min-height:86px}
.ldvh__logo,.ldvh__logo b,.ldvh__logo span{color:#937a4e !important}
.ldvh__logo b{font-size:23px;font-weight:600;letter-spacing:-.045em}
.ldvh__logo span{font-size:9px;letter-spacing:.14em}
.ldvh__tel{color:#292929 !important;font-size:16px}
.ldvh__tel small{color:#937a4e !important}
.ldvh__cta{background:#826510 !important;color:#fff !important;border-radius:40px !important;font-weight:700}
.ldvh__cta:hover{background:#6e530d !important}
.ldvs{background:rgba(255,255,255,.98) !important;border-top:1px solid #e7dfd2 !important;box-shadow:0 -6px 20px rgba(0,0,0,.08)}
.ldvs__call{color:#826510 !important;border:2px solid #826510 !important;background:#fff !important}
.ldvs__form{color:#fff !important;background:#826510 !important;border-color:#826510 !important}
@media(max-width:699px){.ldvh__in{min-height:67px}.ldvh__logo b{font-size:19px}.ldvh__logo span{font-size:7.5px}.ldvh__cta{font-size:11px;padding:10px 12px}}
"""

TOP_CSS = """
.ldvc{background:linear-gradient(125deg,#f7f2ea 0%,#ffffff 75%);color:#292929;font-family:Montserrat,Arial,sans-serif;padding:30px 16px 36px}
.ldvc *,.ldvc *::before,.ldvc *::after{box-sizing:border-box}
.ldvc__wrap{max-width:760px;margin:0 auto}
.ldvc__h1{margin:0 0 12px;font-weight:800;font-size:clamp(29px,6.6vw,46px);line-height:1.1;letter-spacing:-.035em;color:#292929}
.ldvc__sub{margin:0 0 16px;font-size:clamp(17px,2.3vw,21px);line-height:1.45;font-weight:500;letter-spacing:-.01em;color:#826510}
.ldvc__eyebrow{margin:0 0 8px;font-size:12px;font-weight:800;letter-spacing:.12em;text-transform:uppercase;color:#937a4e}
.ldvc__why{list-style:none;margin:0 0 14px;padding:0}
.ldvc__why li{position:relative;margin:0 0 8px;padding-left:28px;font-size:16px;line-height:1.45;font-weight:500;color:#38332e}
.ldvc__why li::before{content:"\\2713";position:absolute;left:0;top:0;color:#b19154;font-weight:800}
.ldvc__why a{color:#826510;text-decoration:underline}
.ldvc__trust{list-style:none;margin:0 0 6px;padding:0;display:flex;flex-wrap:wrap;gap:8px}
.ldvc__trust li{font-size:13px;font-weight:700;line-height:1.2;padding:7px 11px;border-radius:999px;background:#fff;border:1px solid #e0d3b9;color:#3e3933}
.ldvc__trust li b{color:#826510;font-weight:800}
.ldvc__fn{margin:0 0 16px;font-size:12px;line-height:1.4;color:#77716a}
.ldvc__btns{display:grid;gap:10px}
.ldvc__btn{display:flex;align-items:center;justify-content:center;min-height:56px;padding:14px 18px;border-radius:10px;font:700 16.5px/1.2 Montserrat,Arial,sans-serif;text-align:center;text-decoration:none;border:2px solid #826510}
.ldvc__btn--primary{background:#826510;color:#fff}
.ldvc__btn--primary:hover{background:#6e530d;border-color:#6e530d;color:#fff}
.ldvc__anchor{display:block;height:0;scroll-margin-top:72px}
.ldvc__micro{margin:10px 0 0;font-size:13.5px;font-weight:600;color:#77716a}
.ldvc__photo{display:none}
.ldvc__who{display:flex;align-items:center;gap:12px;margin:0 0 12px}
.ldvc__who img{flex:0 0 56px;width:56px;height:56px;border-radius:50%;object-fit:cover;object-position:50% 14%;border:2px solid #d2b16d}
.ldvc__who span{font-size:12px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:#937a4e;line-height:1.35}
.ldvc__who b{display:block;font-size:15px;letter-spacing:0;text-transform:none;color:#292929}
@media(min-width:700px){.ldvc{padding:55px 24px 60px}}
@media(min-width:900px){
  .ldvc__wrap{max-width:1100px}
  .ldvc__grid{display:grid;grid-template-columns:1.2fr .8fr;gap:44px;align-items:center}
  .ldvc__who{display:none}
  .ldvc__photo{display:block;position:relative;border-radius:18px;overflow:hidden;border:1px solid #e7dfd2;box-shadow:0 18px 45px rgba(69,50,22,.13);max-height:520px}
  .ldvc__photo img{display:block;width:100%;height:520px;object-fit:cover;object-position:50% 20%}
  .ldvc__cap{position:absolute;left:0;right:0;bottom:0;padding:44px 18px 16px;background:linear-gradient(to top,rgba(35,30,23,.9),rgba(35,30,23,0));display:flex;flex-direction:column;gap:2px}
  .ldvc__cap b{font-size:17px;font-weight:800;color:#fff}
  .ldvc__cap span{font-size:12px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:#d2b16d}
}
"""

FORM_CSS = """
.ldv2{background:#f7f2ea;font-family:Montserrat,Arial,sans-serif;color:#292929;padding:48px 16px 6px}
.ldv2__inner{max-width:520px;margin:0 auto;text-align:left}
.ldv2__eyebrow{margin:0 0 8px;font-size:12px;font-weight:800;letter-spacing:.12em;text-transform:uppercase;color:#937a4e}
.ldv2__title{margin:0 0 10px;font-size:clamp(24px,5vw,32px);line-height:1.18;font-weight:800;letter-spacing:-.02em;color:#292929}
.ldv2__desc{margin:0 0 6px;font-size:15.5px;line-height:1.55;color:#66615b}
.ldv2-native{background:#f7f2ea !important;font-family:Montserrat,Arial,sans-serif !important}
.ldv2-native .t-form{max-width:520px !important;margin:0 auto !important}
.ldv2-native .t-input-group{margin-bottom:18px !important}
.ldv2-native .t-input-title{display:block;margin-bottom:9px !important;padding:0 !important;color:#62594c !important;font:700 12px/1.5 Montserrat,Arial,sans-serif !important;letter-spacing:.035em !important}
.ldv2-native .t-input{box-sizing:border-box !important;width:100% !important;min-height:56px !important;padding:0 17px !important;background:#fff !important;color:#292929 !important;border:1px solid #ded5c7 !important;border-radius:10px !important;font:500 16px Montserrat,Arial,sans-serif !important;box-shadow:none !important}
.ldv2-native .t-input:focus{border-color:#a88a48 !important;outline:none !important;box-shadow:0 0 0 3px rgba(168,138,72,.12) !important}
.ldv2-native .t-input::placeholder{color:#aaa49b !important;opacity:1 !important}
.ldv2-native .t-input-group_ph .t-input-block{max-width:100% !important;box-sizing:border-box !important}
.ldv2-native .t-submit{display:flex !important;align-items:center;justify-content:center;width:100% !important;min-height:58px !important;padding:15px 22px !important;background:#826510 !important;color:#fff !important;border:1px solid #826510 !important;border-radius:10px !important;font:700 15px/1.35 Montserrat,Arial,sans-serif !important;text-align:center;white-space:normal !important;cursor:pointer}
.ldv2-native .t-submit:hover{background:#6e530d !important;border-color:#6e530d !important}
.ldv2-native .t-form__successbox{border-radius:12px !important;background:#f1ebdd !important;color:#292929 !important;font-family:Montserrat,Arial,sans-serif !important;line-height:1.6}
@media(max-width:699px){.ldv2-native .t-input{min-height:54px !important}.ldv2-native .t-submit{min-height:58px !important;font-size:14px !important;padding:14px 12px !important}.ldv2-native .t-input-group{margin-bottom:15px !important}}
"""

FORM_JS = """
(function(){
  "use strict";
  /* Находит обычную форму Tilda сразу ПОСЛЕ этого блока, красит её и подписывает поля. Имена полей (name, phone, quiz_summary) не меняет. */
  function update() {
    var section = document.getElementById("ldv-form-section");
    if (!section) return;
    var rec = section.closest('.r, [id^="rec"]');
    var formRec = rec && rec.nextElementSibling;
    if (!formRec || !formRec.querySelector('form.t-form')) return;
    formRec.classList.add("ldv2-native");
    var form = formRec.querySelector('form.t-form');
    form.querySelectorAll('.t-input-group').forEach(function(group) {
      var input = group.querySelector('input:not([type="hidden"])');
      if (!input) return;
      var name = (input.getAttribute('name') || '').toLowerCase();
      var type = (input.getAttribute('type') || '').toLowerCase();
      var label = group.querySelector('.t-input-title');
      if (name === 'name' || name === 'firstname' || name === 'first_name') {
        if (label) label.textContent = 'Your name';
        input.placeholder = 'Enter your name';
      }
      if (type === 'tel' || name === 'phone' || name === 'tel') {
        if (label) label.textContent = 'Phone number';
        input.setAttribute('aria-label', 'Phone number');
      }
    });
    var button = form.querySelector('.t-submit');
    if (button) button.textContent = 'Get My Free Case Review';
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', update); else update();
  window.addEventListener('load', update);
})();
"""

EXTRA_CSS = """
.ldvp{font-family:Montserrat,Arial,sans-serif}
.ldvp__btn{border-radius:10px}
.ldvp__chips{display:flex;flex-wrap:wrap;gap:9px;margin:0 0 14px;padding:0;list-style:none}
.ldvp__chips li{padding:11px 15px;border-radius:10px;background:#fff;border:1px solid #e7dfd2;font-size:14.5px;line-height:1.4;font-weight:600;color:#292929}
.ldvp__cols{display:grid;gap:14px;margin:0 0 14px}
.ldvp__col{padding:20px;border-radius:14px;background:#fff;border:1px solid #e7dfd2}
.ldvp__col h3{margin:0 0 12px;font-size:18px;line-height:1.3;font-weight:800}
.ldvp__nots{margin:0;padding:0;list-style:none}
.ldvp__nots li{position:relative;margin:0 0 9px;padding-left:30px;font-size:16.5px;line-height:1.45}
.ldvp__nots li::before{content:"\\2715";position:absolute;left:0;top:0;color:#937a4e;font-weight:800}
.ldvp__badges{display:flex;flex-wrap:wrap;gap:10px;margin:0 0 14px;padding:0;list-style:none}
.ldvp__badges img{display:block;width:72px;height:72px;object-fit:contain;background:#fff;border-radius:10px;padding:4px}
.ldvp__revlinks{margin:0 0 14px;font-size:14.5px}
.ldvp__revlinks a,.ldvp__rev a{color:#826510}
.ldvp__revlinks a{font-weight:700}
.ldvp__rev{box-shadow:0 5px 22px rgba(69,50,22,.04)}
.ldvp__hl{margin:0 0 20px;padding:16px 18px;background:#f7f2ea;border:1px solid #d2b16d;border-radius:12px}
.ldvp__hl strong{display:block;font-size:17px;font-weight:800;color:#292929}
.ldvp__hl p{margin:4px 0 0;font-size:15px;line-height:1.5;color:#66615b}
.ldvp__faq details[open] summary::after{background:#826510;color:#fff}
.ldvp__faq summary:hover{color:#826510}
.ldvp__sec--dark .ldvp__btn--ghost{border-color:#d2b16d;color:#fff}
.ldvp__sec--dark .ldvp__btn--ghost:hover{background:#d2b16d;color:#302d28;border-color:#d2b16d}
.ldvp__card--note{padding:20px;background:#f7f2ea;border:0;border-left:4px solid #d2b16d;border-radius:12px}
#ldv-fee,#ldv-how{scroll-margin-top:72px}
/* фото в блоках: как на живой Car (Photography integration V1) */
.ldvmedia__split{display:grid;grid-template-columns:1fr;gap:26px;align-items:center;margin-top:12px}
.ldvmedia__photo{display:block;width:100%;margin:0;overflow:hidden;border-radius:12px;background:#f7f2ea;box-shadow:0 12px 35px rgba(69,50,22,.10)}
.ldvmedia__photo img{display:block;width:100%;height:auto;aspect-ratio:16/10;object-fit:cover}
.ldvmedia__content{min-width:0}
.ldvmedia__content>:last-child{margin-bottom:0}
.ldvmedia__content .ldvp__cards{grid-template-columns:1fr;margin:0}
#ldv-final .ldvmedia__photo{border:1px solid rgba(210,177,109,.25)}
.ldvmedia__content .ldvp__btns{grid-template-columns:1fr}
.ldv-team{background:#fff;padding:44px 16px;font-family:Montserrat,Arial,sans-serif;color:#292929}
.ldv-team *{box-sizing:border-box}
.ldv-team__inner{max-width:1040px;margin:0 auto;text-align:center}
.ldv-team__eyebrow{margin:0 0 10px;color:#937a4e;font-size:12px;font-weight:800;letter-spacing:.14em;text-transform:uppercase}
.ldv-team__title{margin:0 0 16px;font-size:clamp(28px,5vw,40px);font-weight:800;line-height:1.16;letter-spacing:-.02em}
.ldv-team__description{max-width:690px;margin:0 auto 22px;color:#66615b;font-size:15.5px;line-height:1.65}
.ldv-team__photo{margin:0}
.ldv-team__photo img{display:block;width:100%;max-width:850px;height:auto;margin:0 auto;border-radius:12px;object-fit:contain;box-shadow:0 12px 35px rgba(69,50,22,.1)}
.ldv-team__caption{margin-top:12px;font-size:13px;color:#66615b}
@media(min-width:700px){.ldv-team{padding:64px 24px}.ldv-team__description{font-size:16.5px;margin-bottom:30px}.ldv-team__photo img{border-radius:16px}}
@media(min-width:800px){
  .ldvmedia__photo{border-radius:16px}
  .ldvmedia__photo img{aspect-ratio:auto}
  #ldv-insurers .ldvmedia__split{grid-template-columns:minmax(0,.9fr) minmax(0,1.1fr);align-items:stretch}
  #ldv-insurers .ldvmedia__photo img{height:100%;min-height:320px;aspect-ratio:auto}
  #ldv-how .ldvmedia__split{grid-template-columns:minmax(0,1fr) minmax(0,.85fr)}
  #ldv-how .ldvmedia__photo img{aspect-ratio:4/5}
  #ldv-situations .ldvmedia__split{grid-template-columns:minmax(0,1fr) minmax(0,1fr)}
  #ldv-situations .ldvmedia__photo img{aspect-ratio:4/3}
  #ldv-final .ldvmedia__split{grid-template-columns:minmax(0,1.1fr) minmax(0,.9fr);gap:36px}
  #ldv-final .ldvmedia__photo img{aspect-ratio:4/5}
}
@media(min-width:700px){.ldvp__cols{grid-template-columns:1fr 1fr}}
"""


def build(key):
    P = PAGES[key]
    out = CLIENT / P["folder"]
    out.mkdir(exist_ok=True)
    topic = P["topic"]
    PH = dict(PHOTOS_COMMON)
    PH.update(P.get("photos", {}))

    def photo(slot):
        if not PH.get(slot):
            return ""
        url, alt = PH[slot]
        return f'<figure class="ldvmedia__photo"><img src="{url}" alt="{alt}" width="768" height="512" loading="lazy" decoding="async"></figure>'

    # ---------------- блок 1: шапка, первый экран, якорь формы, плашка
    chip_amt, chip_txt = P["result_chip"]
    chip_li = f"<li><b>{chip_amt}</b> {chip_txt}</li>" if chip_amt else f"<li>{chip_txt}</li>"
    fn_p = f'<p class="ldvc__fn">*{RESULT_NOTE.split(". Every")[0]}.</p>' if chip_amt else ""
    scope_p = f'<p class="ldvc__fn" style="margin:0 0 14px">{P["scope_line"]}</p>' if P.get("scope_line") else ""
    why = "\n".join(f"      <li>{x}</li>" for x in [
        "Alina Landver began her career on the defense side. She knows how insurers undervalue claims.",
        "Over 20 years in State and Federal Court throughout California.",
        'If you decide to hire the firm, you pay no fee unless you win. <a href="#ldv-fee" data-ldv-cta="hero_fee">See how it works</a>',
    ])
    top = f"""<!-- Landver Law: страница «{P['h1']}», БЛОК 1: шапка, первый экран, закреплённая плашка (Tilda T123 «HTML»). Собрано build_topic_pages.py.
     Сразу под этим блоком ставится блок 2 (подпись над формой), а за ним обычная форма Tilda. -->
{FONTS}
<style>
{brand(hdr_css)}
{HDR_V2}
{TOP_CSS}
</style>

{hdr_html}

<section class="ldvc" id="ldvc" aria-labelledby="ldvc-h1">
  <div class="ldvc__wrap ldvc__grid">
   <div class="ldvc__text">
    <p class="ldvc__eyebrow">Free case review &middot; Answered 24/7</p>
    <h1 class="ldvc__h1" id="ldvc-h1">{P['h1']}</h1>
    <p class="ldvc__sub">{P['sub']}</p>
    {scope_p}
    <div class="ldvc__who"><img src="{SITE}/wp-content/uploads/2025/04/Landver0290.jpg" width="56" height="56" loading="lazy" alt="Alina Landver, Managing Partner and Trial Attorney"><span><b>Alina Landver, Esq., MBA</b>Managing Partner &middot; Trial Attorney</span></div>
    <ul class="ldvc__why">
{why}
    </ul>
    <ul class="ldvc__trust">
      <li><b>&#9733; {RATING}</b> &middot; {RATING_COUNT} Google reviews</li>
      <li>Practicing since 2004</li>
      {chip_li}
    </ul>
    {fn_p}
    <div class="ldvc__btns">
      <a class="ldvc__btn ldvc__btn--primary ldvq-phone" href="{TEL}" data-ldv-cta="hero_call">Call {PHONE} &middot; 24/7</a>
    </div>
    <p class="ldvc__micro">No pressure: you decide after the review.</p>
   </div>
   <div class="ldvc__photo">
     <img src="{SITE}/wp-content/uploads/2025/06/Landver0374-scaled-1-e1750710392686.jpg" width="807" height="1200" loading="lazy" alt="Alina Landver in court">
     <div class="ldvc__cap"><b>Alina Landver, Esq., MBA</b><span>Managing Partner &middot; Trial Attorney</span></div>
   </div>
  </div>
</section>
<a id="ldv-form" class="ldvc__anchor" aria-hidden="true" tabindex="-1"></a>

{sticky_html}
{cta_script}
"""

    # ---------------- блок 2: подпись над формой + стиль формы Tilda (форма ставится сразу следом)
    form_intro = f"""<!-- Landver Law: БЛОК 2: подпись над формой и оформление обычной формы Tilda (T123 «HTML»). Собрано build_topic_pages.py.
     Ставится ПРЯМО ПЕРЕД обычной формой Tilda: скрипт находит форму в следующем за ним блоке и красит её. Между блоком 2 и формой ничего не вставлять. -->
{FONTS}
<style>
{FORM_CSS}
</style>
<section class="ldv2" id="ldv-form-section" aria-labelledby="ldv2-title">
  <div class="ldv2__inner">
    <p class="ldv2__eyebrow">Free consultation</p>
    <h2 class="ldv2__title" id="ldv2-title">Prefer we call you? Leave your number.</h2>
    <p class="ldv2__desc">Leave your name and phone. We'll contact you to set up your free review with an attorney.</p>
  </div>
</section>
<script>{FORM_JS}</script>
"""

    # ---------------- блок 3: всё под формой
    W = P["worries"]
    worry_cards = "\n".join(f'          <div class="ldvp__card ldvp__card--note"><b>{b}</b><p>{p}</p></div>' for b, p in W["cards"])
    C = P["checklist"]
    do_li = "\n".join(f"            <li>{x}</li>" for x in C["do"])
    hold_li = "\n".join(f"            <li>{x}</li>" for x in C["hold"])
    sit_li = "\n".join(f"          <li>{x}</li>" for x in P["situations"])
    res_cards = "\n".join(
        f'        <div class="ldvp__card"><b>{RESULTS_ALL[r][0]} &middot; {RESULTS_ALL[r][1]}</b><p>{RESULTS_ALL[r][2]}</p></div>' for r in P["results"])
    badges_li = "\n".join(
        f'            <li><img src="{SITE}/wp-content/uploads/2025/04/{f}" width="72" height="72" loading="lazy" alt="{a}"></li>' for f, a in BADGES)
    stars = "&#9733;" * 5
    revs = "\n".join(
        f'        <blockquote class="ldvp__rev"><div class="ldvp__stars" aria-hidden="true">{stars}</div><p>&ldquo;{t}&rdquo;</p>'
        f'<small><a href="https://www.google.com/maps/contrib/{cid}/reviews" target="_blank" rel="noopener nofollow">{n}</a> &middot; Google Review &middot; {d}</small></blockquote>'
        for n, d, cid, t in REVIEWS)
    faq_items = []
    for f in P["faq"]:
        if isinstance(f, str):
            q, a = FAQ_COMMON[f]
            q = q.format(topic=topic)
        else:
            q, a = f
        faq_items.append((q, a))
    faq_html = "\n".join(f"      <details><summary>{q}</summary>\n        <p>{a}</p></details>" for q, a in faq_items)

    def split(content, slot, photo_first):
        ph = photo(slot)
        if not ph:
            return content
        parts = (ph, f'<div class="ldvmedia__content">\n{content}\n        </div>') if photo_first else (f'<div class="ldvmedia__content">\n{content}\n        </div>', ph)
        return f'<div class="ldvmedia__split">\n        {parts[0]}\n        {parts[1]}\n      </div>'

    worry_content = f'        <div class="ldvp__cards">\n{worry_cards}\n        </div>'
    step1 = P.get("step1", ("Tell us what happened", "The crash, your injuries, your treatment so far. You don't need documents yet."))
    how_content = f"""        <ol class="ldvp__steps">
          <li><b>{step1[0]}</b>{step1[1]}</li>
          <li><b>We set up a free review of your case with an attorney</b>Free, with no obligation.</li>
          <li><b>The attorney explains what applies to you and what to avoid</b>Then you decide: hire the firm now, later, or not at all. No pressure.</li>
        </ol>
        <div class="ldvp__btns">
          {btn_form('how_form')}
          {btn_call('how_call')}
        </div>"""
    sit_note = P.get("situations_note", "Not sure which one fits? That is okay. Tell us what happened and an attorney will review it. Every case depends on its own facts, injuries, evidence, liability and insurance coverage.")
    sit_content = f"""        <ul class="ldvp__chips">
{sit_li}
        </ul>
        <p class="ldvp__note">{sit_note}</p>
        <div class="ldvp__btns">
          {btn_form('cases_form')}
        </div>"""
    final_content = f"""        <h2 class="ldvp__h2">{P['final_h2']}</h2>
        <p class="ldvp__lead">Call or leave your number. We'll set up a free review of your case with an attorney, who can tell you:</p>
        <ul class="ldvp__ticks">
          <li>what applies to YOUR case, not general advice</li>
          <li>what NOT to do so you don't lose compensation</li>
          <li>your next steps, in plain language</li>
          <li>where your case stands, based on what you tell us</li>
        </ul>
        <p class="ldvp__fee">No fee unless we win.</p>
        <div class="ldvp__btns">
          {btn_form('final_form')}
          {btn_call('final_call')}
        </div>
        <p class="ldvp__fine">Submitting a form does not by itself create an attorney-client relationship.</p>"""
    team_ph = PH["team"]
    res_note_p = f'<p class="ldvp__lead" style="margin-bottom:14px">{P["results_note"]}</p>' if P.get("results_note") else ""
    W2 = P.get("who")
    who_html = ""
    if W2:
        who_li = "\n".join(f"        <li>{x}</li>" for x in W2["items"])
        who_html = f"""  <section class="ldvp__sec ldvp__sec--cream" id="ldv-who">
    <div class="ldvp__in">
      <p class="ldvp__eyebrow">{W2['eyebrow']}</p>
      <h2 class="ldvp__h2">{W2['h2']}</h2>
      <ul class="ldvp__ticks">
{who_li}
      </ul>
      <p class="ldvp__note">{W2['note']}</p>
    </div>
  </section>

"""

    body = f"""<!-- Landver Law: страница «{P['h1']}», БЛОК 3: всё под формой (Tilda T123 «HTML»). Собрано build_topic_pages.py.
     Порядок: что говорят страховые, что делать и чего не делать, как проходит звонок, оплата, команда, ситуации, результаты, адвокат, отзывы, вопросы, финальный призыв.
     Все кнопки формы ведут на #ldv-form (якорь в блоке 1). Второй формы нет. -->
<style>
{brand(body_css)}
{EXTRA_CSS}
</style>

<div class="ldvp">

  <section class="ldvp__sec ldvp__sec--white" id="ldv-insurers">
    <div class="ldvp__in">
      <p class="ldvp__eyebrow">{W['eyebrow']}</p>
      <h2 class="ldvp__h2">{W['h2']}</h2>
      {split(worry_content, 'insurers', True)}
      <p class="ldvp__note" style="margin-top:16px">{W['note']}</p>
    </div>
  </section>

{who_html}  <section class="ldvp__sec ldvp__sec--white" id="ldv-checklist">
    <div class="ldvp__in">
      <p class="ldvp__eyebrow">{C['eyebrow']}</p>
      <h2 class="ldvp__h2">{C['h2']}</h2>
      <div class="ldvp__cols">
        <div class="ldvp__col">
          <h3>{C['do_title']}</h3>
          <ul class="ldvp__ticks">
{do_li}
          </ul>
        </div>
        <div class="ldvp__col">
          <h3>{C['hold_title']}</h3>
          <ul class="ldvp__nots">
{hold_li}
          </ul>
        </div>
      </div>
      <p class="ldvp__note">{C['note']}</p>
    </div>
  </section>

  <section class="ldvp__sec ldvp__sec--white" id="ldv-how">
    <div class="ldvp__in">
      <p class="ldvp__eyebrow">How it works</p>
      <h2 class="ldvp__h2">{P['steps_h2']}</h2>
      {split(how_content, 'how', False)}
    </div>
  </section>

  <section class="ldvp__sec ldvp__sec--cream" id="ldv-fee">
    <div class="ldvp__in">
      <p class="ldvp__eyebrow">How the fee works</p>
      <h2 class="ldvp__h2">Why is the first review free, and how does Landver Law get paid?</h2>
      <ul class="ldvp__ticks">
        <li>The first review is free. It is how you and the firm find out whether Landver Law can help with your case.</li>
        <li>If you hire the firm, you sign a written agreement first. It states the fee, and you can read it before you sign.</li>
        <li>The attorney fee is paid out of what is recovered. If nothing is recovered, you owe no attorney fee.</li>
        <li>There are no upfront costs.</li>
      </ul>
      <p class="ldvp__note">So the firm is paid only when you are. Exact financial terms are confirmed in the written attorney-client agreement before representation begins.</p>
      <div class="ldvp__hl"><strong>No Fee Unless We Win.</strong><p>Your first case review is free, with no obligation to hire the firm.</p></div>
      <div class="ldvp__btns">
        {btn_form('fee_form')}
        {btn_call('fee_call')}
      </div>
    </div>
  </section>

  <section class="ldv-team" id="ldv-team">
    <div class="ldv-team__inner">
      <p class="ldv-team__eyebrow">The people behind Landver Law</p>
      <h2 class="ldv-team__title">A Dedicated Team Behind Your Case</h2>
      <p class="ldv-team__description">When you work with Landver Law, you have a team committed to guiding you through the legal process, from your first consultation to the resolution of your case.</p>
      <figure class="ldv-team__photo"><img src="{team_ph[0]}" alt="{team_ph[1]}" width="1144" height="1299" loading="lazy" decoding="async"><figcaption class="ldv-team__caption">The Landver Law Team</figcaption></figure>
    </div>
  </section>

  <section class="ldvp__sec ldvp__sec--white" id="ldv-situations">
    <div class="ldvp__in">
      <p class="ldvp__eyebrow">{P.get('sit_eyebrow', 'Motorcycle accident cases')}</p>
      <h2 class="ldvp__h2">{P['situations_h2']}</h2>
      {split(sit_content, 'situations', True)}
    </div>
  </section>

  <section class="ldvp__sec ldvp__sec--cream" id="ldv-results">
    <div class="ldvp__in">
      <p class="ldvp__eyebrow">Results</p>
      <h2 class="ldvp__h2">Recent settlements and verdicts</h2>
      {res_note_p}
      <div class="ldvp__cards">
{res_cards}
      </div>
      <p class="ldvp__note">{RESULT_NOTE}</p>
    </div>
  </section>

  <section class="ldvp__sec ldvp__sec--dark" id="ldv-attorney">
    <div class="ldvp__in ldvp__atty">
      <img src="{SITE}/wp-content/uploads/2025/04/Landver0290.jpg" width="800" height="1200" loading="lazy" alt="{P['atty_alt']}">
      <div>
        <p class="ldvp__eyebrow">Your attorney</p>
        <h2 class="ldvp__h2">{P['atty_h2']}</h2>
        <ul class="ldvp__facts">
          <li>Managing Partner &middot; Trial Attorney</li>
          <li><b>California Bar</b> 231077</li>
          <li><b>Admitted</b> June 2004</li>
        </ul>
        <p class="ldvp__lead">Alina Landver has practiced personal injury law for over 20 years in State and Federal Court throughout California. She began her career on the defense side, representing corporate clients, which gives her direct insight into how insurers undervalue claims.</p>
        <ul class="ldvp__badges">
{badges_li}
        </ul>
        <p class="ldvp__src">Awards and memberships are as published by the firm. Attorney status and admission date are based on State Bar of California records. Statements about Landver Law's experience are based on information published by the firm. Prior experience and recognition do not guarantee a particular outcome in any individual matter.</p>
        <div class="ldvp__btns">
          {btn_form('attorney_form', 'Free case review')}
          {btn_call('attorney_call', with_24=False)}
        </div>
      </div>
    </div>
  </section>

  <section class="ldvp__sec ldvp__sec--cream" id="ldv-reviews">
    <div class="ldvp__in">
      <p class="ldvp__eyebrow">Client reviews</p>
      <h2 class="ldvp__h2">What people say after working with Landver Law</h2>
      <div class="ldvp__rate"><b>{RATING}</b><div><div class="ldvp__stars" aria-hidden="true">{stars}</div><span>out of 5 &middot; {RATING_COUNT} Google reviews</span></div></div>
      <div class="ldvp__revs">
{revs}
      </div>
      <p class="ldvp__revlinks"><a href="{GOOGLE_PROFILE}" target="_blank" rel="noopener nofollow">Read all reviews on Google</a></p>
      <p class="ldvp__note">A review is someone else's experience, not a promise about yours. Reviews shown are excerpts from publicly displayed Google reviews. Rating and review count can change over time. Testimonials do not constitute a guarantee, warranty or prediction regarding the outcome of any legal matter.</p>
      <div class="ldvp__btns">
        {btn_form('reviews_form')}
      </div>
    </div>
  </section>

  <section class="ldvp__sec ldvp__sec--white" id="ldv-faq">
    <div class="ldvp__in ldvp__faq">
      <p class="ldvp__eyebrow">Frequently asked questions</p>
      <h2 class="ldvp__h2">{P['faq_h2']}</h2>
{faq_html}
      <p class="ldvp__note" style="margin-top:16px">This FAQ provides general information and is not legal advice. Deadlines, liability, insurance obligations and available claims depend on the specific facts and applicable law. An attorney-client relationship is not created by viewing this page or submitting a request for an initial case review.</p>
    </div>
  </section>

  <section class="ldvp__sec ldvp__sec--dark" id="ldv-final">
    <div class="ldvp__in">
      <p class="ldvp__eyebrow">Free case review</p>
      {split(final_content, 'final', False)}
    </div>
  </section>

</div>
"""

    # ---------------- блок 4: подвал (общий для всех тематических страниц)
    footer = brand(footer_src).replace("Settlement page, подвал", f"тематические страницы, подвал ({key})")
    footer = footer.replace("including serious car and commercial-truck collisions", "including serious vehicle collisions and wrongful death")
    footer = footer.replace('<a href="mailto:info@landverpersonalinjury.com" style=',
                            '<a href="mailto:info@landverpersonalinjury.com" data-ldv-cta="footer_email" style=')
    assert "footer_email" in footer and "wrongful death" in footer

    for old in ("1_blok_top.txt", "2_blok_body.txt", "3_blok_footer.txt"):  # имена прошлой сборки (с формой B)
        (out / old).unlink(missing_ok=True)
    (out / "1_blok_top.txt").write_text(top, encoding="utf-8")
    (out / "2_blok_forma_podpis.txt").write_text(form_intro, encoding="utf-8")
    (out / "3_blok_body.txt").write_text(body, encoding="utf-8")
    (out / "4_blok_footer.txt").write_text(footer, encoding="utf-8")

    native_form = """<div class="ldv2-native" style="padding:0 16px 40px"><div class="t-form" style="max-width:520px;margin:0 auto"><form>
<div class="t-input-group"><label class="t-input-title">Your name</label><div class="t-input-block"><input class="t-input" type="text" name="name" placeholder="Enter your name"></div></div>
<div class="t-input-group t-input-group_ph"><label class="t-input-title">Phone number</label><div class="t-input-block"><input class="t-input" type="tel" name="phone" placeholder="+1(000)000-0000"></div></div>
<input type="hidden" name="quiz_summary" value="">
<button type="button" class="t-submit">Get My Free Case Review</button></form>
<p style="margin:12px 0 0;font:400 11px/1.65 Montserrat,Arial,sans-serif;color:#8c857a">Submitting this form does not by itself create an attorney-client relationship.</p></div></div>"""
    preview = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>PREVIEW: {key} (локальный макет, форма Tilda нарисована)</title>
<style>body{{margin:0;background:#fff}}html{{scroll-behavior:smooth}}</style></head><body>
{top}
{form_intro}
{native_form}
{body}
{footer}
</body></html>"""
    (out / "0_maket_prosmotr.html").write_text(preview, encoding="utf-8")

    # ---------------- инструкции
    kw = dict(folder=out, slug=P["slug"], title=P["title"], desc=P["desc"], h1=P["h1"], phone=PHONE, key=key)
    (out / "ИНСТРУКЦИЯ_сборка_в_Tilda.md").write_text(INSTR_MD.format(**kw), encoding="utf-8")
    (out / "ЧИТАЙ_МЕНЯ_инструкция.txt").write_text(INSTR_TXT.format(**kw), encoding="utf-8")

    # ---------------- проверки сборки
    allhtml = top + form_intro + body + footer
    for m in re.finditer(r'<a [^>]*href="tel:[^"]*"[^>]*>', allhtml):
        assert "ldvq-phone" in m.group(0) and "data-ldv-cta" in m.group(0), m.group(0)
    assert allhtml.count("<h1") == 1
    ids = re.findall(r' id="([^"]+)"', allhtml)
    dup = {i for i in ids if ids.count(i) > 1}
    assert not dup, dup
    for h in set(re.findall(r'href="#([^"]+)"', allhtml)):
        assert h in ids, f"мёртвый якорь #{h}"
    assert "ldv-form-2" not in allhtml
    for m in re.finditer(r"<img [^>]*>", allhtml):
        assert 'alt="' in m.group(0), m.group(0)
    print("OK", out, "| H1 1, ссылок tel: проверено, якорей без цели нет, alt у всех картинок")
    print("Title", len(P["title"]), "Description", len(P["desc"]))


INSTR_MD = """# Как собрать страницу «{h1}» в Tilda

Папка: `{folder}\\`

| Файл | Что это |
|---|---|
| `0_maket_prosmotr.html` | Макет всей страницы для просмотра (двойной щелчок, откроется в браузере). Форма в нём нарисованная. |
| `1_blok_top.txt` | Блок 1: шапка, первый экран (H1, доверие, кнопка звонка), нижняя плашка на телефоне. |
| `2_blok_forma_podpis.txt` | Блок 2: подпись над формой («Prefer we call you? Leave your number.») и оформление формы. Ставится прямо перед формой. |
| `3_blok_body.txt` | Блок 3: всё под формой (что говорят страховые, что делать и чего не делать, как проходит звонок, оплата, команда, ситуации, результаты, адвокат со значками, отзывы, вопросы, финальный призыв). |
| `4_blok_footer.txt` | Блок 4: подвал с дисклеймерами. |

Блоки сделаны как `.txt`, чтобы открывались в Блокноте двойным щелчком. Содержимое копируется (Ctrl+A, Ctrl+C) и вставляется в блок «HTML» в Tilda целиком, от первой до последней строки, без правок. Названия кнопок Tilda ниже написаны по памяти, интерфейс не проверял. Оформление такое же, как у готовой страницы california-car-accident-lawyer (цвета, шрифт, фото в блоках).

## Шаг 1. Новая страница

1. Дубликат готовой страницы california-car-accident-lawyer на сайте `landverpersonalinjury.tilda.ws` (или любой другой), все блоки удалить.
2. Адрес страницы: `{slug}`
3. Язык страницы: английский. После публикации в коде страницы (просмотр кода) в начале должно быть `<html lang="en">`; у прошлых страниц атрибута `lang` не было, его пришлось дописывать.
4. Вкладка SEO:
   - Title: `{title}`
   - Description: `{desc}`
   - Заголовки для соцсетей: те же.
5. Не ставить `noindex`.

## Шаг 2. Блоки по порядку

1. Блок HTML: `1_blok_top.txt`
2. Блок HTML: `2_blok_forma_podpis.txt`
3. **Обычная форма Tilda** (одна на всю страницу, см. шаг 3), **строго сразу под блоком 2**: скрипт блока 2 находит форму в следующем блоке и красит её.
4. Блок HTML: `3_blok_body.txt`
5. Блок HTML: `4_blok_footer.txt`

Форма одна, как на готовой Car. Все кнопки «Get my free case review» на странице ведут якорем `#ldv-form` (он уже внутри блока 1, сразу под первым экраном). Второй формы и всплывающего окна нет: якорь окно не открывает. Кнопки и ссылки в блоках не заменять блоками Tilda и не менять: у каждой ссылки на телефон есть класс `ldvq-phone` и метка `data-ldv-cta`, по ним работают подмена номера Ringostat и статистика.

## Шаг 3. Форма

- Поля: «Name» (обязательное) и «Phone» (обязательное, тип «Телефон», маска США). Имена переменных ровно `name` и `phone` (подписи над полями и текст кнопки блок 2 заменит сам).
- Скрытое поле: `quiz_summary` (квиза на странице нет, поле остаётся пустым, оставлено, чтобы заявки всех страниц имели одинаковый набор полей).
- Кнопка: `Get My Free Case Review`.
- Куда приходят заявки: те же почта и интеграции, что у остальных страниц.
- Под формой: `Submitting this form does not by itself create an attorney-client relationship.`
- Сообщение после отправки: `Thank you. We've received your request and will contact you to set up your free case review. Prefer to talk now? Call {phone} · 24/7.` (номер здесь текстом, не ссылкой).
- Фон блока формы: `#f7f2ea`. Отступы блока сверху и снизу около 20 px.

## Шаг 4. Публикация и проверка

1. Опубликовать, открыть на телефоне и на компьютере.
2. Первый экран: заголовок, кнопка звонка; нижняя плашка на телефоне не закрывает кнопки.
3. Нажать каждую кнопку «Get my free case review» (шапка, плашка, блоки): страница прокручивается к форме. Окон не открывается. Прокрутка не должна уходить в подвал.
4. Нажать ссылки с номером: открывается набор номера.
5. Форма: подписи полей «Your name» и «Phone number», кнопка «Get My Free Case Review», цвета как у остальных страниц.
6. Отправить тестовую заявку своим номером (имя «TEST»): в заявке поля `name`, `phone`.
7. Прислать ссылку на опубликованную страницу: подмену номера и события мы настраиваем и проверяем сами.

## Не делать до проверки

- Не менять адрес страницы в группах Google Ads, пока страница не проверена и нет «да».
- Не добавлять на страницу ссылки на номер внутри предложения и кнопки, которые создаются скриптом: подмена номера на них не работает.
- Не ссылаться на страницу с сайта клиента.

## Откуда брать правки

Исходник текста и сборки: `Кампании\\Search\\build_topic_pages.py` (тема `{key}`). После правок файлы в этой папке пересобираются, поэтому вставляйте в Tilda всегда файлы из папки.
"""

INSTR_TXT = """ЧИТАЙ МЕНЯ: как собрать страницу «{h1}» в Tilda
==========================================================

Что лежит в этой папке
----------------------
0_maket_prosmotr.html     - макет страницы (двойной щелчок, откроется в браузере). Форма в нём нарисованная.
1_blok_top.txt            - БЛОК 1: шапка, первый экран, кнопка звонка, нижняя плашка на телефоне.
2_blok_forma_podpis.txt   - БЛОК 2: подпись над формой и оформление формы. Ставится ПРЯМО ПЕРЕД формой.
3_blok_body.txt           - БЛОК 3: всё, что ниже формы.
4_blok_footer.txt         - БЛОК 4: подвал.
ИНСТРУКЦИЯ_сборка_в_Tilda.md - та же инструкция подробнее.

Оформление такое же, как у готовой страницы california-car-accident-lawyer.
Файлы блоков .txt открываются в Блокноте. Названия кнопок Tilda ниже написаны по памяти, у вас могут называться чуть иначе.
ВАЖНО: страницу публиковать как тестовую, рекламу на неё не переключать до проверки.

ШАГ 1. Новая страница
1. Сайт landverpersonalinjury.tilda.ws: дубликат готовой страницы, все блоки удалить.
2. Адрес страницы: {slug}
3. Язык страницы: английский. После публикации в коде страницы должно быть <html lang="en">.
4. Вкладка SEO:
   Title:        {title}
   Description:  {desc}
   Для соцсетей: те же Title и Description.
5. НЕ ставить noindex.

ШАГ 2. Блоки по порядку (сверху вниз)
1) Блок HTML: весь текст из 1_blok_top.txt (Ctrl+A, Ctrl+C в Блокноте, Ctrl+V в блоке).
2) Блок HTML: весь текст из 2_blok_forma_podpis.txt.
3) ОБЫЧНАЯ форма Tilda (одна на страницу) СТРОГО СРАЗУ ПОД блоком 2: скрипт блока 2 красит форму из следующего блока.
4) Блок HTML: весь текст из 3_blok_body.txt.
5) Блок HTML: весь текст из 4_blok_footer.txt.
Код вставлять целиком, ничего не менять. Все кнопки "Get my free case review" ведут якорем #ldv-form (он уже в блоке 1) к форме. Второй формы и окна нет: якорь окно не открывает.
Кнопки и ссылки на телефон не заменять блоками Tilda: по их классу и метке работает подмена номера.

ШАГ 3. Форма
- Поля: Name (обязательное), Phone (обязательное, тип "Телефон", маска США). Имена переменных ровно: name и phone.
- Скрытое поле: quiz_summary (останется пустым, нужно для одинакового набора полей на всех страницах).
- Кнопка: "Get My Free Case Review". Заявки идут на те же почту и интеграции, что у остальных страниц.
- Под формой: Submitting this form does not by itself create an attorney-client relationship.
- Сообщение после отправки: Thank you. We've received your request and will contact you to set up your free case review. Prefer to talk now? Call {phone} - 24/7. (номер текстом, не ссылкой)
- Фон блока формы #f7f2ea, отступы сверху и снизу около 20 px.

ШАГ 4. Проверка после публикации
1. Откройте на телефоне и на компьютере.
2. Нажмите каждую кнопку "Get my free case review": прокрутка к форме. Окон нет. В подвал прокручиваться не должно.
3. Нажмите ссылки с номером: открывается набор номера.
4. Форма: подписи "Your name" и "Phone number", кнопка "Get My Free Case Review", цвета как на остальных страницах.
5. Тестовая заявка своим номером (имя TEST): в заявке поля name и phone.
6. Пришлите ссылку: подмену номера и события настраиваем мы.

НЕ ДЕЛАТЬ: не переключать рекламу на страницу до проверки; не добавлять номер внутрь предложения и кнопки, создаваемые скриптом; не ставить noindex.
"""

def load_extra():
    for f in sorted((CLIENT / "Черновики_страниц").glob("*_PAGES.py")):
        exec(f.read_text(encoding="utf-8"), globals())


if __name__ == "__main__":
    load_extra()
    for k in (sys.argv[1:] or ["motorcycle"]):
        build(k)
