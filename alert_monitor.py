#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
alert_monitor.py — Фаза 3 (MVP из спринта): мгновенные алерты об угрозах.

Опрашивает веб-превью tier-1 каналов белого списка (t.me/s/<канал>) и ищет
сообщения о ракетной/беспилотной опасности, сиренах, атаках БПЛА по словарю
config.json -> alerting.patterns. Отмена угрозы распознаётся отдельными
паттернами (cancel_patterns) и закрывает активный алерт.

Режимы:
  python3 alert_monitor.py --once           # одна проверка (для cron: * * * * *)
  python3 alert_monitor.py --loop           # непрерывно, интервал alerting.interval_sec
  python3 alert_monitor.py --status         # показать активные/закрытые алерты

Уведомления (MVP, локальные):
  * консоль + звонок терминала (\a)
  * data/alerts.log  (журнал)
  * data/alerts.json (состояние — читается генератором дайджеста: красный баннер)
  * notify-send / osascript, если доступны (Linux desktop / macOS)

Первый запуск инициализирует состояние БЕЗ ретро-алертов (помечает текущие
посты как прочитанные). Алерт срабатывает только на новых сообщениях.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from collector import http_get, parse_tg_page  # noqa: E402

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")
STATE = os.path.join(DATA, "alert_state.json")
ALERTS = os.path.join(DATA, "alerts.json")
LOG = os.path.join(DATA, "alerts.log")
UTC4 = timezone(timedelta(hours=4))


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def load(path, default):
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            pass
    return default


def save(path, obj):
    os.makedirs(DATA, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


def desktop_notify(title, body):
    """notify-send (Linux) / osascript (macOS) — если есть; ошибки глушим."""
    try:
        if shutil.which("notify-send"):
            subprocess.run(["notify-send", "-u", "critical", title, body], timeout=5, check=False)
        elif shutil.which("osascript"):
            subprocess.run(["osascript", "-e",
                            f'display notification "{body[:120]}" with title "{title}" sound name "Glass"'],
                           timeout=5, check=False)
    except Exception:  # noqa: BLE001
        pass


def log_line(line):
    os.makedirs(DATA, exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def matches(text, patterns):
    low = text.lower()
    for pat in patterns:
        if re.search(pat, low):
            return pat
    return None


def check_once(cfg, quiet=False):
    acfg = cfg.get("alerting", {})
    if not acfg.get("enabled", True):
        return []
    patterns = acfg.get("patterns", [])
    cancels = acfg.get("cancel_patterns", [])
    whitelist = acfg.get("whitelist", [])

    state = load(STATE, {"seen": {}, "initialized": {}})
    alerts = load(ALERTS, {"active": [], "resolved": []})
    fired = []
    first_run = not state.get("seen")

    for username in whitelist:
        try:
            page = http_get(f"https://t.me/s/{username}", cfg)
        except Exception as e:  # noqa: BLE001
            if not quiet:
                print(f"  [alert] @{username}: недоступен ({str(e)[:50]})")
            time.sleep(cfg["settings"]["http_delay_sec"])
            continue
        posts = parse_tg_page(page, username)
        seen = set(state["seen"].get(username, []))
        new_ids = []
        for p in posts:
            new_ids.append(p["id"])
            if p["id"] in seen:
                continue
            blob = f"{p['title']} {p['text']}"
            if not first_run:
                cancel_first = matches(blob, cancels)
                hit = None if cancel_first else matches(blob, patterns)
                if cancel_first and alerts["active"]:
                    for a in alerts["active"]:
                        if a["status"] == "active":
                            a["status"] = "resolved"
                            a["resolved_by"] = p["url"]
                            a["resolved_at"] = now_iso()
                            a["resolved_title"] = p["title"][:140]
                            alerts["resolved"].append(a)
                    alerts["active"] = [a for a in alerts["active"] if a["status"] == "active"]
                    line = f"[{datetime.now(UTC4):%d.%m.%Y %H:%M:%S}] ОТБОЙ @{username}: {p['title'][:120]}"
                    log_line(line)
                    print("\a" + line)
                    desktop_notify("✅ Отбой угрозы", p["title"][:150])
                elif hit:
                    alert = {
                        "id": f"{username}/{p['id']}", "channel": username, "url": p["url"],
                        "title": p["title"][:200], "text": p["text"][:400],
                        "published": p["published"], "matched": hit,
                        "detected_at": now_iso(), "status": "active",
                    }
                    alerts["active"].append(alert)
                    fired.append(alert)
                    line = f"[{datetime.now(UTC4):%d.%m.%Y %H:%M:%S}] АЛЕРТ @{username}: {p['title'][:120]} | {p['url']}"
                    log_line(line)
                    print("\a" + line)
                    desktop_notify("🚨 издание «Гудок»: воздушная угроза", p["title"][:150])

        # храним последние 300 id канала
        state["seen"][username] = (list(seen) + new_ids)[-300:]
        time.sleep(cfg["settings"]["http_delay_sec"])

    state["last_check"] = now_iso()
    state["last_check_local"] = datetime.now(UTC4).strftime("%d.%m.%Y %H:%M:%S")
    save(STATE, state)
    save(ALERTS, alerts)
    if first_run:
        log_line(f"[{datetime.now(UTC4):%d.%m.%Y %H:%M:%S}] Инициализация мониторинга: {len(whitelist)} каналов, ретро-алерты подавлены")
        if not quiet:
            print(f"[alert] инициализация: {len(whitelist)} каналов в белом списке, ретро-алерты подавлены")
    return fired


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--loop", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    with open(os.path.join(BASE, "config.json"), encoding="utf-8") as f:
        cfg = json.load(f)

    if args.status:
        alerts = load(ALERTS, {"active": [], "resolved": []})
        state = load(STATE, {})
        print(f"последняя проверка: {state.get('last_check_local', '—')}")
        print(f"активных алертов: {len(alerts['active'])}")
        for a in alerts["active"]:
            print(f"  🚨 {a['title'][:100]} (@{a['channel']}, {a['url']})")
        print(f"закрыто: {len(alerts['resolved'])}")
        for a in alerts["resolved"][-5:]:
            print(f"  ✅ {a['title'][:100]} -> {a.get('resolved_title','')[:60]}")
        return

    if args.loop:
        interval = cfg.get("alerting", {}).get("interval_sec", 60)
        print(f"[alert] непрерывный мониторинг, интервал {interval} с (Ctrl-C для остановки)")
        while True:
            check_once(cfg, args.quiet)
            time.sleep(interval)
    else:
        check_once(cfg, args.quiet)


if __name__ == "__main__":
    main()
