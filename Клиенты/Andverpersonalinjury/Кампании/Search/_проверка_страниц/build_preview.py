import pathlib
base = pathlib.Path(r"D:\GitHub\work-rb\Клиенты\Andverpersonalinjury\Кампании\Search")
b1=(base/"settlement_quiz_t123.html").read_text(encoding="utf-8")
b2=(base/"settlement_body_t123.html").read_text(encoding="utf-8")
b3=(base/"settlement_footer_t123.html").read_text(encoding="utf-8")
def form(i):
    return f"""<div style="background:#f6f2ea;padding:36px 16px;font-family:Manrope,Arial,sans-serif;color:#17242b"><div style="max-width:520px;margin:0 auto">
<h2 style="margin:0 0 8px;font-size:28px;font-weight:800">Get my free case review</h2>
<p style="margin:0 0 16px;font-size:16px;line-height:1.5;color:#4d5a60">Leave your name and phone. We'll contact you to set up your free review with an attorney.</p>
<form class="t-form" id="form{i}"><input type="text" name="name" placeholder="First name" style="box-sizing:border-box;width:100%;height:54px;margin:0 0 10px;padding:0 14px;font-size:16px;border:1px solid #ddd7ce;border-radius:10px">
<input type="tel" name="phone" placeholder="Phone number" style="box-sizing:border-box;width:100%;height:54px;margin:0 0 10px;padding:0 14px;font-size:16px;border:1px solid #ddd7ce;border-radius:10px">
<button type="button" style="box-sizing:border-box;width:100%;height:56px;border:0;border-radius:12px;background:#e8563f;color:#fff;font:800 17px Manrope,Arial,sans-serif">Get my free case review</button></form>
<p style="margin:12px 0 0;font-size:12.5px;line-height:1.5;color:#68747a">Free. No obligation. Submitting this form does not by itself create an attorney-client relationship.</p></div></div>"""
html=f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>PREVIEW: Settlement page (локальный макет, формы Tilda имитированы)</title>
<link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=Manrope:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>body{{margin:0;background:#0d151b}}html{{scroll-behavior:smooth}}</style></head><body>
<!-- БЛОК 1 --> {b1}
<!-- ФОРМА A (Tilda) --> {form('A')}
<!-- БЛОК 2 --> {b2}
<!-- ФОРМА B (Tilda) --> {form('B')}
<!-- БЛОК 3 --> {b3}
</body></html>"""
out=base/"settlement_page_preview.html"
out.write_text(html,encoding="utf-8"); print(out, len(html))
