#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import ast, re

p = 'generate.py'
s = open(p, encoding='utf-8').read()

# ---------- 1. гамбургер + поиск в render_nav ----------
old = '''    return f'<nav class="nav"><div class="nav-inner">{"".join(html_items)}</div></nav>' + subnav'''
new = '''    search_box = ""
    if getattr(render_nav, "search_manifest", None) and current in ("index", "digest"):
        search_box = (f'<div class="nav-search" style="position:relative;"><input id="q" type="search" '
                      f'placeholder="Поиск по выпуску…" aria-label="Поиск по выпуску" '
                      f'oninput="qSearch(this.value)" onfocus="qSearch(this.value)">'
                      f'<div class="search-drop" id="qdrop"></div></div>'
                      f'<script>var QMAN={render_nav.search_manifest};'
                      'function qSearch(v){var d=document.getElementById("qdrop");v=v.trim().toLowerCase();'
                      'if(v.length<3){d.classList.remove("on");return;}'
                      'var r=QMAN.filter(function(x){return x.t.toLowerCase().indexOf(v)>=0;}).slice(0,8);'
                      'd.innerHTML=r.map(function(x){return \'<a href="\'+x.u+\'">\'+x.t+\'<span>\'+x.d+\' · \'+x.c+\'</span></a>\';}).join("")'
                      '||\'<a href="#">Ничего не найдено</a>\';d.classList.add("on");}'
                      'document.addEventListener("click",function(e){if(!e.target.closest(".nav-search"))document.getElementById("qdrop").classList.remove("on");});'
                      '</script>')
    toggle = ('<button class="nav-toggle" aria-label="Открыть разделы" '
              'onclick="document.body.classList.toggle(\'nav-open\')">☰ Разделы</button>')
    return (f'<nav class="nav">{toggle}{search_box}<div class="nav-inner">{"".join(html_items)}</div></nav>'
            + subnav)'''
assert old in s
s = s.replace(old, new, 1)

# ---------- 2. main-обёртка + article/time в themed() ----------
old = '''    def themed(html):
        html = html.replace("</head>", THEME_HEAD + "</head>", 1)
        return html.replace("</body>", THEME_FOOT + "</body>", 1)'''
new = '''    def themed(html):
        html = html.replace("</head>", THEME_HEAD + "</head>", 1)
        html = re.sub(r'(</nav>(?:<div class="subnav">.*?</div></div>)?)', r'\\1<main id="main">',
                      html, count=1, flags=re.S)
        html = html.replace('<footer class="footer">', '</main>\\n<footer class="footer">', 1)
        return html.replace("</body>", THEME_FOOT + "</body>", 1)'''
assert old in s
s = s.replace(old, new, 1)

# ---------- 3. news-item -> article + <time> ----------
s = s.replace('''                items_html.append(f"""<div class="news-item">
{thumb}<h4><a href="{link}" target="_blank" rel="noopener">{esc(it['title'])}</a></h4>''',
'''                items_html.append(f"""<article class="news-item">
{thumb}<h4><a href="{link}" target="_blank" rel="noopener">{esc(it['title'])}</a></h4>''', 1)
s = s.replace('''<div class="meta">{dt.strftime('%d.%m %H:%M') if dt else ''} · {esc(it.get('source',''))}{tg_badge}</div>
{chips}</div>""")''',
'''<div class="meta"><time datetime="{dt.isoformat() if dt else ''}">{dt.strftime('%d.%m %H:%M') if dt else ''}</time> · {esc(it.get('source',''))}{tg_badge}</div>
{chips}</article>""")''', 1)

# lead-карточки -> article
s = s.replace('''        lead_html = f"""<div class="lead-main" style="border-top-color:{cat.get('color','var(--gold)')};">''',
'''        lead_html = f"""<article class="lead-main">''', 1)
s = s.replace('''<div class="lead-meta">{meta} · <a href="{url}" target="_blank" rel="noopener">читать полностью →</a></div></div>""")''',
'''<div class="lead-meta">{meta} · <a href="{url}" target="_blank" rel="noopener">читать полностью →</a></div></article>""")''', 1)
s = s.replace('''            side += f"""<div class="lead-card" style="border-top-color:{cat.get('color','var(--blue)')};">''',
'''            side += f"""<article class="lead-card">''', 1)
s = s.replace('''<div class="lead-meta">{meta}</div></div>"""
        lead_html += f'<div class="lead-side">{side}</div>' ''',
'''<div class="lead-meta">{meta}</div></article>"""
        lead_html += f'<div class="lead-side">{side}</div>' ''', 1)

# ---------- 4. index: третья колонка «сейчас» — по-человечески, без тона ----------
old = '''<div class="now-col">
<div class="now-h">📊 Картина момента</div>
<div class="now-num">{n24} <small>публикаций за 24 ч</small></div>
<div class="now-line">тема часа: <b>{esc(top_topic[1]['name']) if top_topic else '—'}</b> ({top_topic[1]['today'] if top_topic else 0} упом.)</div>
<div class="now-line">тон повестки: <b>{tone:+.2f}</b> — {tone_txt}</div>
<div class="now-line">до дня голосования: <b>{d_vote} дн.</b></div>
<div class="now-line">погода: {esc(weather) if weather else '—'}</div>
</div>'''
new = '''<div class="now-col">
<div class="now-h">Сегодня в номере</div>
<p style="font-family:var(--serif);font-size:15.5px;line-height:1.55;color:var(--ink2);">
В выпуске <b>{n24} материала</b> за сутки, из них {len(leads)} главных на полосе.
На сегодня в афише <b>{len(today_events)}</b> события. До дня голосования — <b>{d_vote} дн.</b>
Погода: {esc(weather) if weather else '—'}. Тон повестки и все метрики инфополя —
в разделе <a href="infospace.html">«Инфопространство»</a>.</p>
</div>'''
assert old in s
s = s.replace(old, new, 1)

# ---------- 5. инлайн-золото -> классы ----------
s = s.replace('style="color:#ffd47e;"', 'class="flink"')
s = s.replace('style="color:#ffe9b8;"', 'class="chip-link"')
s = s.replace('.chip a,.chip-link{color:var(--ink2);text-decoration:none;}',
              '.chip a,.chip-link,.flink{color:var(--ink2);text-decoration:none;}')

# ---------- 6. манифест поиска из main ----------
old = '''    def with_utilbar(html, prefix=""):'''
new = '''    manifest = []
    for it in sorted([x for x in store if x.get("published")], key=lambda x: x["published"], reverse=True)[:120]:
        dt = local_dt(it["published"])
        manifest.append({"t": it["title"][:110], "u": it.get("url") or "#",
                         "d": dt.strftime("%d.%m") if dt else "",
                         "c": (cats_all.get(it.get("category"), {}) or {}).get("name", "") if False else str(it.get("source", ""))[:18]})
    import json as _json
    render_nav.search_manifest = _json.dumps(manifest, ensure_ascii=False)

    def with_utilbar(html, prefix=""):'''
assert old in s
s = s.replace(old, new, 1)

open(p, 'w', encoding='utf-8').write(s)
ast.parse(s)
print("шаблоны: семантика, поиск, гамбургер, человеческая колонка")
