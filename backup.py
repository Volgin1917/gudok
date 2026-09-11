#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backup.py — ежедневный бэкап данных издание «Гудок».

Копирует data/store.jsonl, trends.json, analytics.json, alerts.json,
fetch_status.json в data/backups/YYYY-MM-DD/ и чистит копии старше
RETENTION дней. Идемпотентен: повторный запуск в тот же день перезаписывает.

Запуск: python3 backup.py [--retention 14]
"""
import argparse
import os
import shutil
from datetime import datetime, timedelta, timezone

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")
BACKUPS = os.path.join(DATA, "backups")
UTC4 = timezone(timedelta(hours=4))
FILES = ["store.jsonl", "trends.json", "analytics.json", "alerts.json",
         "fetch_status.json", "alert_state.json"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--retention", type=int, default=14, help="сколько дней хранить")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    today = datetime.now(UTC4).strftime("%Y-%m-%d")
    dest = os.path.join(BACKUPS, today)
    os.makedirs(dest, exist_ok=True)

    copied = 0
    for name in FILES:
        src = os.path.join(DATA, name)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(dest, name))
            copied += 1

    # ротация
    cutoff = datetime.now(UTC4).date() - timedelta(days=args.retention)
    removed = 0
    if os.path.isdir(BACKUPS):
        for d in os.listdir(BACKUPS):
            try:
                dd = datetime.strptime(d, "%Y-%m-%d").date()
            except ValueError:
                continue
            if dd < cutoff:
                shutil.rmtree(os.path.join(BACKUPS, d), ignore_errors=True)
                removed += 1

    size = sum(os.path.getsize(os.path.join(dest, f)) for f in os.listdir(dest))
    if not args.quiet:
        print(f"[backup] {today}: файлов {copied}, {size/1024:.0f} КБ | удалено старых: {removed}")


if __name__ == "__main__":
    main()
