#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
footer.py — единый подвал для всех страниц издания Гудок.

Один источник разметки и стилей: <footer class="footer"> с колонками
footer__inner (бренд + Периодичности + Проекты + Служебное) и нижней
полосой footer__bottom. Префикс ссылок задаётся по глубине страницы.

Подключается из generate.py и status.py; в рукописных страницах
(roadmap.html, infospace-plan.html) разметка вставляется правкой файла,
стили — из FOOTER_CSS.
"""
import glob
import os
from datetime import datetime, timedelta, timezone

UTC4 = timezone(timedelta(hours=4))
BASE = os.path.dirname(os.path.abspath(__file__))


def exec_href(prefix, today):
    """Ссылка на «Версию руководителю» с проверкой существования файла.

    Регрессия 29.09: подвал весь день ссылался на exec_<сегодня>.html, которого нет
    до ежедневного прогона, — тот же дефект, что починен 17.09 для датированного
    выпуска (digest_link). Свежего файла нет — ссылаемся на последний существующий;
    нет ни одного — возвращаем пустую строку (пункт подвала опускается).
    """
    name = f"exec_{today}.html"
    if not os.path.exists(os.path.join(BASE, "digests", name)):
        ex = sorted(glob.glob(os.path.join(BASE, "digests", "exec_*.html")))
        name = os.path.basename(ex[-1]) if ex else ""
    return f"{prefix}digests/{name}" if name else ""

FOOTER_CSS = """/* подвал — единый */
.footer{background:var(--ink);color:var(--on-ink);margin-top:52px;padding:30px 0 18px;}
.footer h3{color:var(--paper);}
.footer h3{font-family:var(--sans);font-size:10.5px;font-weight:700;letter-spacing:.14em;text-transform:uppercase;margin:0 0 8px;}
.footer a{color:var(--on-ink);}
.footer a:hover{color:var(--accent);}
.footer__inner{max-width:var(--maxw);margin:0 auto;padding:0 var(--gutter);display:grid;grid-template-columns:1.5fr repeat(3,1fr);gap:20px 36px;}
.footer p{font-family:var(--serif-body);font-size:12.5px;line-height:1.55;max-width:430px;margin:0 0 6px;}
.footer ul{list-style:none;padding:0;margin:0;font-family:var(--serif-body);font-size:12.5px;line-height:1.55;}
.footer li{margin:4px 0;}
.footer__brand{font-family:var(--rubleny);font-weight:900;font-size:22px;letter-spacing:.04em;text-transform:uppercase;color:var(--paper);line-height:1;margin-bottom:8px;}
.footer__brand span{color:var(--accent);}
.footer__bottom{max-width:var(--maxw);margin:20px auto 0;padding:10px var(--gutter) 0;border-top:1px solid rgba(250,247,242,.14);font-family:var(--sans);font-size:11.5px;color:var(--on-ink);display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;}
:root[data-theme="dark"] .footer__bottom{border-top-color:rgba(11,11,11,.2);}
@media (max-width:1100px){.footer__inner{grid-template-columns:1fr 1fr;gap:26px;}}
@media (max-width:720px){.footer__inner{grid-template-columns:1fr;gap:22px;}.footer__bottom{flex-direction:column;}}
"""


def render_footer(prefix=""):
    """Разметка единого подвала. prefix — относительный путь к корню сайта."""
    now = datetime.now(UTC4)
    today = now.strftime("%Y-%m-%d")
    year = now.year
    ex_href = exec_href(prefix, today)
    exec_li = f'<li><a href="{ex_href}">Версия руководителю</a></li>' if ex_href else ""
    try:
        import methods as _mreg
        m_label = f"Методы · реестр v{_mreg.VERSION}"
    except Exception:
        m_label = "Методы"
    return f"""<footer class="footer"><div class="footer__inner">
<div><div class="footer__brand">ГУДОК<span>.</span></div>
<p>Информационно-аналитическое издание марксистской группы «Победа» по Ульяновской области. Выходит с 11 сентября 2026 года. Материалы принадлежат их изданиям; издание носит информационно-аналитический характер и не является агитацией.</p></div>
<div><h3>Периодичности</h3><ul style="list-style:none;padding:0;">
<li><a href="{prefix}digests/today.html">День · выпуск сегодня</a></li>
<li><a href="{prefix}weekly.html">Неделя · дуги сюжетов</a></li>
<li><a href="{prefix}monthly.html">Месяц · метрики</a></li>
<li><a href="{prefix}archive.html">Архив-матрица</a></li></ul></div>
<div><h3>Проекты</h3><ul style="list-style:none;padding:0;">
<li><a href="{prefix}projects/elections.html">Выборы</a></li>
<li><a href="{prefix}projects/goszakupki.html">Госзакупки</a></li>
<li><a href="{prefix}projects/gorodskoy_sovet.html">Городской совет</a></li>
<li><a href="{prefix}infospace.html">Инфопространство</a></li>
<li><a href="{prefix}methods.html">{m_label}</a></li>
<li><a href="{prefix}projects/dossier.html">Досье · прототип</a></li>
<li><a href="{prefix}projects/pressa.html">Архив прессы</a></li>
<li><a href="{prefix}afisha.html">Афиша</a></li></ul></div>
<div><h3>Служебное</h3><ul style="list-style:none;padding:0;">
<li><a href="{prefix}status.html">Статус системы</a></li>
<li><a href="{prefix}projects/plans.html">Планы</a></li>
{exec_li}
<li><a href="https://github.com/Volgin1917/gudok" target="_blank" rel="noopener">GitHub</a></li></ul></div>
</div>
<div class="footer__bottom"><span>© {year} Гудок · Ульяновск</span><span>Сделано с уважением к читателю</span></div>
</footer>"""