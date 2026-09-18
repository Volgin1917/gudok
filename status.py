#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
status.py — status-page конвейера издание Гудок (status.html).

Показывает: здоровье пайплайна (когда последний сбор/тренды/бэкап),
доступность каждого источника, состояние алерт-монитора, статистику базы.
Генерируется после каждого прогона (встроен в run.sh); автообновление страницы 60 с.

Запуск: python3 status.py
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

BASE = os.path.dirname(os.path.abspath(__file__))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

import outlets  # канонические издания: какие каналы считаются одним источником
import footer  # единый подвал всех страниц
DATA = os.path.join(BASE, "data")
UTC4 = timezone(timedelta(hours=4))


def jload(path, default=None):
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            pass
    return default


def age_str(iso):
    if not iso:
        return "—"
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return "—"
    delta = datetime.now(timezone.utc) - dt
    mins = int(delta.total_seconds() // 60)
    if mins < 60:
        return f"{mins} мин назад"
    hours = mins // 60
    if hours < 48:
        return f"{hours} ч назад"
    return f"{hours // 24} дн назад"


def esc_(v):
    import html as _h
    return _h.escape(str(v)) if v is not None else "—"


def quality_block(passport):
    """Спринт 3, п.5: блок «Качество выборки афиши» для страницы статуса.
    Пустой HTML, если паспорт афиши не собран."""
    if not isinstance(passport, dict) or not passport.get("run_local"):
        return ""
    q = passport
    kpis = [
        ("прошло порог", q.get("accepted", q.get("total", 0))),
        ("дат найдено в текстах", q.get("found_dates", "—")),
        ("отсеяно", q.get("rejected", "—")),
        ("без времени", q.get("no_time", "—")),
        ("без площадки", q.get("no_venue", "—")),
        ("«Прочее»", (str(q.get("other_share")) + "%") if q.get("other_share") is not None else "—"),
        ("с др. анонсами", q.get("also_n", "—")),
        ("новых площадок к словарю", q.get("venues_new_n", len(q.get("venues_new", {}) or {}))),
        ("средний балл уверенности", q.get("score_avg", "—")),
    ]
    cells = "".join(
        f'<div class="stat"><b>{esc_(v)}</b><span>{esc_(k)}</span></div>' for k, v in kpis)
    thr = q.get("threshold", 0)
    stats = (q.get("stats") or {})
    return f"""<h2>🎯 Качество выборки афиши</h2>
<div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(130px,1fr));">{cells}</div>
<div class="note">Порог входа: {thr}. Афиша собрана {esc_(q.get('run_local'))}. {esc_(q.get('verdict') or '')}
Прогоны сквозь <code>extract_calendar_full</code>; словарь площадок — <code>data/venues.json</code>; метки «отменено/перенесено» — по свежим постам (reschedule_flags, горизонт 48 ч).</div>
"""


def main():
    cfg = jload(os.path.join(BASE, "config.json"), {})
    status = jload(os.path.join(DATA, "fetch_status.json"), {})
    alerts = jload(os.path.join(DATA, "alerts.json"), {"active": [], "resolved": []})
    astate = jload(os.path.join(DATA, "alert_state.json"), {})
    trends = jload(os.path.join(DATA, "trends.json"), {})
    meta = status.get("_meta", {})

    n_items = 0
    store_path = os.path.join(DATA, "store.jsonl")
    if os.path.exists(store_path):
        with open(store_path, encoding="utf-8") as f:
            n_items = sum(1 for l in f if l.strip())

    backups = []
    bdir = os.path.join(DATA, "backups")
    if os.path.isdir(bdir):
        backups = sorted(d for d in os.listdir(bdir) if len(d) == 10)
    last_backup = backups[-1] if backups else None

    now = datetime.now(UTC4)
    run_age_h = None
    if meta.get("last_run_utc"):
        try:
            run_age_h = (datetime.now(timezone.utc) - datetime.fromisoformat(meta["last_run_utc"])).total_seconds() / 3600
        except ValueError:
            pass
    health_ok = run_age_h is not None and run_age_h < 30
    health = ("🟢 в норме" if health_ok else
              ("🟡 давно не собирали" if run_age_h is not None else "🔴 сбор не запускался"))

    # таблица источников; каналы одной редакции помечаются общим изданием (outlets.py)
    merged = {sid: (canon, len(ids))
              for canon, ids in outlets.merged_groups().items() for sid in ids}

    def outlet_note(sid):
        """Пометка «этот канал — часть одного издания с другим каналом»."""
        hit = merged.get(sid)
        if not hit:
            return ""
        canon, n = hit
        ch = "канала" if 2 <= n <= 4 else "каналов"
        return (f' <span style="color:var(--muted);font-size:11px;">→ издание «{esc_(canon)}»: '
                f'{n} {ch} = один источник</span>')

    rows = []
    for src in cfg.get("rss_sources", []):
        if not src.get("enabled", True):
            continue
        st = status.get(f"rss:{src['name']}", {})
        rows.append(("RSS", src["name"], src.get("url", ""), st,
                     outlet_note(f"rss:{src['name']}")))
    for ch in sorted(cfg.get("telegram_channels", []), key=lambda c: (c.get("tier", 2), -(c.get("subs") or 0))):
        if not ch.get("enabled", True):
            continue
        st = status.get(f"tg:{ch['username']}", {})
        rows.append((f"TG T{ch.get('tier', '?')}", ch["username"], f"https://t.me/{ch['username']}", st,
                     outlet_note(f"tg:{ch['username']}")))
    for cm in cfg.get("vk_communities", []) or []:
        if not cm.get("enabled", True):
            continue
        st = status.get(f"vk:{cm['domain']}", {})
        rows.append((f"VK T{cm.get('tier', '?')}", cm.get("title") or cm["domain"],
                     f"https://vk.ru/{cm['domain']}", st, outlet_note(f"vk:{cm['domain']}")))
    for ws in cfg.get("web_sources", []) or []:
        if not ws.get("enabled", True):
            continue
        st = status.get(f"web:{ws['name']}", {})
        rows.append((f"САЙТ T{ws.get('tier', '?')}", ws["name"], ws.get("url", ""), st,
                     outlet_note(f"web:{ws['name']}")))

    ok_n = sum(1 for r in rows if r[3].get("ok"))
    tr_html = "".join(
        f"""<tr><td><span class="badge-t">{kind}</span></td>
<td><a href="{url}" target="_blank" rel="noopener">{name}</a>{note}</td>
<td>{'<span class="ok">в сети</span>' if st.get('ok') else '<span class="fail">ошибка: ' + esc_((st.get('error') or 'нет данных')[:60]) + '</span>'}</td>
<td>{st.get('items', '—')}</td></tr>"""
        for kind, name, url, st, note in rows)

    active_html = "".join(
        f'<div class="alert-line red">🚨 {a["title"][:110]} <span>(@{a["channel"]}, <a href="{a["url"]}">ссылка</a>)</span></div>'
        for a in alerts.get("active", [])) or '<div class="alert-line green">✅ Активных угроз нет</div>'
    resolved_html = "".join(
        f'<div class="alert-line">✔️ {r["title"][:90]} <span>(закрыт {age_str(r.get("resolved_at"))})</span></div>'
        for r in alerts.get("resolved", [])[-5:][::-1]) or '<div class="alert-line">Отбоев не зафиксировано</div>'

    counts = trends.get("counts", {})
    afisha_report = quality_block(jload(os.path.join(DATA, "analytics.json"), {}).get("calendar_passport") or {})
    import glob as _glob
    _dig = sorted(_glob.glob(os.path.join(BASE, "digests", "digest_*.html")))
    latest_digest_href = f"digests/{os.path.basename(_dig[-1])}" if _dig else "index.html"
    _dstr = os.path.basename(_dig[-1]).replace("digest_", "") if _dig else ""
    _ex = os.path.join(BASE, "digests", f"exec_{_dstr}")
    latest_exec_href = f"digests/exec_{_dstr}" if os.path.exists(_ex) else "index.html"
    html = f"""<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="refresh" content="60">
<link rel="icon" type="image/png" href="assets/logo_gudok.png">
<title>Status — {cfg.get('brand','издание Гудок')}</title>
<style>
:root{{--paper:#FAF7F2;--paper-2:#F3EFE7;--ink:#0B0B0B;--ink-2:#2A2620;--muted:#6B655C;--rule:#E3DED4;--rule-strong:#0B0B0B;--accent:#D63F1F;--on-ink:#C9C2B6;--maxw:1180px;--gutter:20px;
--serif-display:"Fraunces","Source Serif 4",Georgia,serif;--serif-body:"Source Serif 4",Georgia,serif;--sans:"Inter",system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;--rubleny:Impact,"Arial Black","Franklin Gothic Bold",sans-serif;}}
:root[data-theme="dark"]{{--paper:#101214;--paper-2:#17191c;--ink:#ECE7DE;--ink-2:#D5CFC4;--muted:#9A948A;--rule:#2A2D31;--rule-strong:#ECE7DE;--accent:#FF6A4D;--on-ink:#2A2620;}}
body{{background:var(--paper);color:var(--ink);font-family:var(--serif-body);font-size:16.5px;line-height:1.55;}}
a{{color:inherit;text-decoration:none;}} a:hover{{color:var(--accent);}}
.brand-title{{font-family:var(--rubleny);font-weight:900;text-transform:uppercase;letter-spacing:.04em;color:var(--ink);}}
.brand-title span{{color:var(--accent);}}

:root{{--navy:#0d2137;--navy3:#1d4066;--blue:#2f80ed;--gold:#f2b134;--red:#e5484d;--green:#2ea36b;
--bg:#eef2f7;--card:#fff;--line:#dbe4ee;--txt:#1c2733;--muted:#5b6b7c;}}
:root[data-theme="dark"]{{--bg:#0b1622;--card:#12202f;--line:#24384e;--txt:#dfe9f4;--muted:#93a7bc;--navy:#dce9f8;}}
*{{margin:0;padding:0;box-sizing:border-box;}}
body{{font-family:"Segoe UI",Roboto,Arial,sans-serif;background:var(--bg);color:var(--txt);font-size:14px;line-height:1.5;}}
a{{color:var(--blue);text-decoration:none;}}
.page-title{{font-family:var(--serif-display);font-weight:600;font-size:26px;letter-spacing:-.02em;margin:8px 0 18px;color:var(--ink);}}
.theme-btn{{border:1px solid rgba(255,255,255,.22);font-size:13px;padding:5px 11px;border-radius:8px;cursor:pointer;background:rgba(255,255,255,.12);color:#ffe9b8;font-weight:800;}}
.page{{max-width:1000px;margin:0 auto;padding:20px 16px 40px;}}
.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:20px;}}
.stat{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:13px 15px;}}
.stat b{{display:block;font-size:20px;color:var(--navy);}}
.stat span{{font-size:11.5px;color:var(--muted);}}
h2{{font-size:16px;color:var(--navy);margin:22px 0 10px;}}
table{{width:100%;border-collapse:collapse;background:var(--card);border-radius:12px;overflow:hidden;font-size:12.8px;}}
th{{background:var(--navy3);color:#fff;text-align:left;padding:8px 12px;font-size:11px;text-transform:uppercase;letter-spacing:.5px;}}
:root[data-theme="dark"] th{{background:#16283c;}}
td{{padding:7px 12px;border-bottom:1px solid var(--line);}}
.ok{{color:var(--green);font-weight:800;}} .fail{{color:var(--red);font-weight:700;}}
.badge-t{{display:inline-block;background:var(--bg);border:1px solid var(--line);border-radius:6px;padding:1px 7px;font-size:10.5px;font-weight:800;color:var(--muted);}}
.alert-line{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:9px 13px;margin-bottom:7px;font-size:13px;}}
.alert-line.red{{border-left:4px solid var(--red);font-weight:700;}}
.alert-line.green{{border-left:4px solid var(--green);}}
.alert-line span{{color:var(--muted);font-weight:400;font-size:11.5px;}}
.nav{{background:#0d2137;border-top:1px solid rgba(255,255,255,.12);}}
:root[data-theme="dark"] .nav{{background:#0a1826;}}
.nav-inner{{max-width:1000px;margin:0 auto;display:flex;gap:2px;overflow-x:auto;padding:0 14px;}}
.nav a{{color:#c9d8e8;font-size:13px;font-weight:600;padding:10px 13px;white-space:nowrap;border-bottom:3px solid transparent;text-decoration:none;}}
.nav a:hover{{color:#fff;background:rgba(255,255,255,.06);}}
.nav a.active{{color:#fff;border-bottom-color:#f2b134;}}
.nav a.nav-util{{color:#8fa9c4;}}
.nav a.nav-util-first{{margin-left:auto;}}
.util-bar-wrap{{max-width:1000px;margin:0 auto;padding:16px 18px 0;}}
.util-bar{{display:flex;gap:22px;align-items:center;flex-wrap:wrap;border-top:1px dashed var(--line);padding-top:12px;}}
.util-bar a{{color:var(--muted);font-size:12.3px;font-weight:700;text-decoration:none;}}
.util-bar a:hover{{color:#f2b134;}}
.util-lbl{{font-size:10px;font-weight:800;letter-spacing:1.2px;text-transform:uppercase;color:var(--muted);}}
.note{{font-size:11.5px;color:var(--muted);margin-top:8px;}}

/* мастхэд в формате первой полосы */
.masthead{{background:var(--paper);}}
.masthead::after{{content:"";display:block;max-width:1200px;margin:14px auto 0;border-bottom:1px solid var(--rule-strong);}}
.mast-inner{{display:grid;grid-template-columns:1fr auto 1fr;align-items:center;gap:24px;max-width:1200px;margin:0 auto;padding:26px 22px 20px;}}
.mast-side{{font-family:var(--sans);font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);line-height:1.7;}}
.mast-side--right{{text-align:right;}}
.mast-title{{font-family:var(--rubleny);font-weight:900;text-transform:uppercase;letter-spacing:.06em;line-height:.95;font-size:clamp(44px,8vw,76px);color:var(--ink);}}
.mast-title span{{color:var(--accent);}}
.mast-actions{{display:flex;gap:14px;justify-content:flex-end;align-items:center;margin-top:10px;}}
@media (max-width:900px){{.mast-inner{{grid-template-columns:1fr;text-align:center;gap:10px;}}.mast-side,.mast-side--right{{text-align:center;}}.mast-actions{{justify-content:center;}}}}
.top-meta{{margin:8px auto 0;justify-content:center;display:flex;flex-wrap:wrap;gap:0;}}
.chip{{background:none;border:none;border-radius:0;padding:0 10px;font-size:11.5px;color:var(--muted,#57616c);position:relative;}}
.chip+.chip::before{{content:"·";position:absolute;left:-3px;color:var(--rule,#ddd8ce);}}
.chip b{{color:var(--ink2,#39424c);}}
.chip a{{color:var(--muted,#57616c);text-decoration:none;}}
.theme-btn,.print-btn{{border:none;background:none;color:var(--muted,#57616c);font-size:11.5px;text-decoration:underline;cursor:pointer;}}
.logo,.mast-logo,.mast-right{{display:none;}}
.ticker{{animation:none;}}
{footer.FOOTER_CSS}
</style>
<script>
(function(){{try{{var t=localStorage.getItem("gudok-theme");
if(!t){{t=window.matchMedia&&matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light";}}
document.documentElement.setAttribute("data-theme",t);}}catch(e){{}}}})();
function toggleTheme(){{var c=document.documentElement.getAttribute("data-theme")==="dark"?"light":"dark";
document.documentElement.setAttribute("data-theme",c);try{{localStorage.setItem("gudok-theme",c);}}catch(e){{}}
var b=document.getElementById("themeBtn");if(b)b.textContent=c==="dark"?"\\u2600\\ufe0f":"\\U0001F319";}}
</script></head><body>
<header class="masthead"><div class="flagline"><span id="fl"></span><span>Ульяновск · служебная страница</span><span>обновляется каждые 60 с</span></div><div class="mast-inner">
<div class="mast-side">Информационно-аналитическое издание<br>марксистской группы «Победа»</div>
<div class="mast-title">ГУДОК<span>.</span></div>
<div class="mast-side mast-side--right">Статус конвейера<br>источники · база · алерты
<div class="mast-actions"><button class="theme-btn" id="themeBtn" onclick="toggleTheme()" title="Светлая/тёмная тема">🌙</button></div></div>
</div></header>
<nav class="nav"><div class="nav-inner">
<a href="index.html">Первая полоса</a>
<a href="digests/today.html">Сегодня</a>
<a href="weekly.html">Неделя</a>
<a href="monthly.html">Месяц</a>
<a href="afisha.html">Афиша</a>
<a href="projects.html">Проекты</a>
<a href="archive.html">Архив</a>
<a href="{latest_exec_href}">Руководителю</a>
</div></nav>
<main id="main"><div class="page">
<h1 class="page-title">🩺 Status — конвейер издания Гудок</h1>

<div class="grid">
<div class="stat"><b>{health}</b><span>последний сбор: {age_str(meta.get('last_run_utc'))}</span></div>
<div class="stat"><b>{ok_n}/{len(rows)}</b><span>источников доступно</span></div>
<div class="stat"><b>{n_items}</b><span>записей в базе · {counts.get('last24h','—')} за 24 ч</span></div>
<div class="stat"><b>{last_backup or '—'}</b><span>последний бэкап</span></div>
</div>

<h2>⚡ Алерт-монитор</h2>
{active_html}
{resolved_html}
<div class="note">Последняя проверка монитора: {esc_(astate.get('last_check_local'))} · белый список: {', '.join(cfg.get('alerting',{}).get('whitelist',[]))}</div>

{afisha_report}

<h2>📡 Источники</h2>
<table><tr><th>Тип</th><th>Источник</th><th>Статус</th><th>Собрано</th></tr>{tr_html}</table>
<div class="note">«Собрано» — записей с источника за последний успешный запрос. Кэш отказов доменов (403/429/401) хранится в data/enrich_failures.json и сбрасывается ежедневно.</div>

<h2>🧮 Конвейер</h2>
<table><tr><th>Шаг</th><th>Результат</th></tr>
<tr><td>collector → store.jsonl</td><td>{meta.get('fetched','—')} получено, {meta.get('new','—')} новых ({esc_(meta.get('last_run_local'))})</td></tr>
<tr><td>trends → trends.json</td><td>{esc_(trends.get('generated_local','—'))} · тем: {len(trends.get('topics',{}))}</td></tr>
<tr><td>analytics → analytics.json</td><td>{esc_((jload(os.path.join(DATA,'analytics.json'),{}) or {}).get('generated_local','—'))}</td></tr>
<tr><td>backup → data/backups/</td><td>{len(backups)} копий, хранение {backups and '14'} дн.</td></tr>
<tr><td>тесты</td><td>python3 -m unittest discover -s tests (38 тестов)</td></tr>
</table>

</div><div class="util-bar-wrap"><div class="util-bar">
<span class="util-lbl">Служебное</span>
<a href="roadmap.html">План развития</a>
<a href="status.html">Статус системы</a>
<a href="https://github.com/Volgin1917/gudok" target="_blank" rel="noopener"> GitHub: исходники, выпуски и конвейер</a>
</div></div>
</main>
{footer.render_footer('')}
<script>var d=new Date();var M=["января","февраля","марта","апреля","мая","июня","июля","августа","сентября","октября","ноября","декабря"];var W=["воскресенье","понедельник","вторник","среда","четверг","пятница","суббота"];var e=document.getElementById("fl");if(e)e.textContent=W[d.getDay()]+", "+d.getDate()+" "+M[d.getMonth()]+" "+d.getFullYear()+" г.";</script></body></html>"""

    with open(os.path.join(BASE, "status.html"), "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[status] status.html: {health}, источников {ok_n}/{len(rows)}, записей {n_items}")


if __name__ == "__main__":
    main()
