#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
status.py — status-page конвейера издание «Гудок» (status.html).

Показывает: здоровье пайплайна (когда последний сбор/тренды/бэкап),
доступность каждого источника, состояние алерт-монитора, статистику базы.
Генерируется после каждого прогона (встроен в run.sh); автообновление страницы 60 с.

Запуск: python3 status.py
"""
import json
import os
from datetime import datetime, timedelta, timezone

BASE = os.path.dirname(os.path.abspath(__file__))
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

    # таблица источников
    rows = []
    for src in cfg.get("rss_sources", []):
        if not src.get("enabled", True):
            continue
        st = status.get(f"rss:{src['name']}", {})
        rows.append(("RSS", src["name"], src.get("url", ""), st))
    for ch in sorted(cfg.get("telegram_channels", []), key=lambda c: (c.get("tier", 2), -(c.get("subs") or 0))):
        if not ch.get("enabled", True):
            continue
        st = status.get(f"tg:{ch['username']}", {})
        rows.append((f"TG T{ch.get('tier', '?')}", ch["username"], f"https://t.me/{ch['username']}", st))

    ok_n = sum(1 for r in rows if r[3].get("ok"))
    tr_html = "".join(
        f"""<tr><td><span class="badge-t">{kind}</span></td>
<td><a href="{url}" target="_blank" rel="noopener">{name}</a></td>
<td>{'<span class="ok">в сети</span>' if st.get('ok') else '<span class="fail">ошибка: ' + esc_((st.get('error') or 'нет данных')[:60]) + '</span>'}</td>
<td>{st.get('items', '—')}</td></tr>"""
        for kind, name, url, st in rows)

    active_html = "".join(
        f'<div class="alert-line red">🚨 {a["title"][:110]} <span>(@{a["channel"]}, <a href="{a["url"]}">ссылка</a>)</span></div>'
        for a in alerts.get("active", [])) or '<div class="alert-line green">✅ Активных угроз нет</div>'
    resolved_html = "".join(
        f'<div class="alert-line">✔️ {r["title"][:90]} <span>(закрыт {age_str(r.get("resolved_at"))})</span></div>'
        for r in alerts.get("resolved", [])[-5:][::-1]) or '<div class="alert-line">Отбоев не зафиксировано</div>'

    counts = trends.get("counts", {})
    import glob as _glob
    _dig = sorted(_glob.glob(os.path.join(BASE, "digests", "digest_*.html")))
    latest_digest_href = f"digests/{os.path.basename(_dig[-1])}" if _dig else "index.html"
    _dstr = os.path.basename(_dig[-1]).replace("digest_", "") if _dig else ""
    _ex = os.path.join(BASE, "digests", f"exec_{_dstr}")
    latest_exec_href = f"digests/exec_{_dstr}" if os.path.exists(_ex) else "index.html"
    html = f"""<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="refresh" content="60">
<title>Status — {cfg.get('brand','издание «Гудок»')}</title>
<style>
:root{{--navy:#0d2137;--navy3:#1d4066;--blue:#2f80ed;--gold:#f2b134;--red:#e5484d;--green:#2ea36b;
--bg:#eef2f7;--card:#fff;--line:#dbe4ee;--txt:#1c2733;--muted:#5b6b7c;}}
:root[data-theme="dark"]{{--bg:#0b1622;--card:#12202f;--line:#24384e;--txt:#dfe9f4;--muted:#93a7bc;--navy:#dce9f8;}}
*{{margin:0;padding:0;box-sizing:border-box;}}
body{{font-family:"Segoe UI",Roboto,Arial,sans-serif;background:var(--bg);color:var(--txt);font-size:14px;line-height:1.5;}}
a{{color:var(--blue);text-decoration:none;}}
.topbar{{background:linear-gradient(135deg,var(--navy),#14314f);color:#fff;padding:13px 22px;display:flex;align-items:center;gap:14px;flex-wrap:wrap;}}
:root[data-theme="dark"] .topbar{{background:linear-gradient(135deg,#0a1826,#0f2033);}}
.topbar h1{{font-size:17px;font-weight:800;}}
.topbar .sub{{font-size:11.5px;color:#a9c1d9;}}
.topbar a{{margin-left:auto;color:#ffd47e;font-size:13px;font-weight:700;}}
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
.note{{font-size:11.5px;color:var(--muted);margin-top:8px;}}
</style>
<script>
(function(){{try{{var t=localStorage.getItem("gudok-theme");
if(!t){{t=window.matchMedia&&matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light";}}
document.documentElement.setAttribute("data-theme",t);}}catch(e){{}}}})();
function toggleTheme(){{var c=document.documentElement.getAttribute("data-theme")==="dark"?"light":"dark";
document.documentElement.setAttribute("data-theme",c);try{{localStorage.setItem("gudok-theme",c);}}catch(e){{}}
var b=document.getElementById("themeBtn");if(b)b.textContent=c==="dark"?"\\u2600\\ufe0f":"\\U0001F319";}}
</script></head><body>
<div class="topbar">
<div><h1>🩺 Status — конвейер издания «Гудок»</h1><div class="sub">автообновление каждые 60 с · {now:%d.%m.%Y %H:%M} UTC+4</div></div>
<button class="theme-btn" id="themeBtn" onclick="toggleTheme()">🌙</button>

</div>
<nav class="nav"><div class="nav-inner">
<a href="index.html">🏠 Первая полоса</a>
<a href="{latest_digest_href}">📰 Выпуск</a>
<a href="{latest_exec_href}">📋 Руководителю</a>
<a href="afisha.html">🎭 Афиша</a>
<a href="special/elections_2026.html">🗳 Выборы-2026</a>
<a href="index.html#archive">🗄 Архив</a>
<a class="nav-util nav-util-first" href="special/analytics_2026-09-11.html">Аналитика недели</a>
<a class="nav-util" href="roadmap.html">🧭 Роадмап</a>
<a class="nav-util active" href="status.html">🩺 Статус</a>
</div></nav>
<div class="page">

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

</div></body></html>"""

    with open(os.path.join(BASE, "status.html"), "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[status] status.html: {health}, источников {ok_n}/{len(rows)}, записей {n_items}")


if __name__ == "__main__":
    main()
