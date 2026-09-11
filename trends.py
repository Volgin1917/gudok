#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
trends.py — трекер тенденций информационной повестки издание «Гудок».

Читает data/store.jsonl и считает:
  * ежедневные ряды упоминаний по темам (topics) и рубрикам (categories)
    за последние sparkline_days дней;
  * статусы тем: «растёт» / «новая» / «стабильно» / «спадает»
    (сравнение последних 3 дней с предшествующей неделей);
  * топ Telegram-постов по просмотрам (вовлечённость аудитории);
  * сводные счётчики (24 ч / 7 дней / всего).

Выход: data/trends.json
Запуск: python3 trends.py
"""
import json
import os
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")
UTC4 = timezone(timedelta(hours=4))


def local_date(iso_utc):
    """UTC ISO -> дата по-ульяновски (UTC+4)."""
    dt = datetime.fromisoformat(iso_utc)
    return dt.astimezone(UTC4).date()


def main():
    with open(os.path.join(BASE, "config.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    spark_days = cfg["settings"].get("sparkline_days", 14)

    store_path = os.path.join(DATA, "store.jsonl")
    items = []
    if os.path.exists(store_path):
        with open(store_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        items.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass

    today = datetime.now(UTC4).date()
    days = [today - timedelta(days=i) for i in range(spark_days - 1, -1, -1)]
    day_index = {d: i for i, d in enumerate(days)}

    topics_cfg = {t["id"]: t["name"] for t in cfg["topics"]}
    cats_cfg = {c["id"]: c["name"] for c in cfg["categories"]}

    topic_series = {t: [0] * spark_days for t in topics_cfg}
    cat_series = {c: [0] * spark_days for c in cats_cfg}
    counts = {"total": len(items), "last24h": 0, "last7d": 0}
    tg_top = []

    cutoff24 = datetime.now(timezone.utc) - timedelta(hours=24)
    cutoff7 = datetime.now(timezone.utc) - timedelta(days=7)

    for it in items:
        pub = it.get("published")
        if not pub:
            continue
        try:
            pub_dt = datetime.fromisoformat(pub)
        except ValueError:
            continue
        if pub_dt >= cutoff24:
            counts["last24h"] += 1
        if pub_dt >= cutoff7:
            counts["last7d"] += 1
        d = local_date(pub)
        idx = day_index.get(d)
        if idx is None:
            continue
        for t in it.get("topics", []):
            if t in topic_series:
                topic_series[t][idx] += 1
        cat = it.get("category")
        if cat in cat_series:
            cat_series[cat][idx] += 1
        # топ Telegram по просмотрам (за 7 дней)
        if it.get("source_type") == "tg" and it.get("views") and pub_dt >= cutoff7:
            tg_top.append({
                "title": it["title"], "channel": it.get("channel"),
                "url": it.get("url"), "views": it["views"],
                "published": pub, "category": cat,
            })

    def status_of(series):
        """Последние 3 дня против предшествующей недели (пороги устойчивые к холодному старту)."""
        recent = sum(series[-3:])
        hist = series[:-3]
        prev = sum(hist[-7:]) / max(1, len(hist[-7:])) * 3  # ожидаемый 3-дневный объём по базе
        if recent > 0 and sum(hist) == 0:
            return "new"
        if recent == 0 and prev == 0:
            return "silent"
        if prev > 0 and recent >= prev * 2.0 and recent >= 4:
            return "rising"
        if prev >= 3 and recent * 2 <= prev:
            return "fading"
        return "stable"

    topics_out = {}
    for tid, name in topics_cfg.items():
        s = topic_series[tid]
        total = sum(s)
        topics_out[tid] = {
            "name": name,
            "series": s,
            "today": s[-1],
            "week": sum(s[-7:]),
            "total": total,
            "status": status_of(s),
        }
    cats_out = {
        cid: {"name": name, "series": cat_series[cid],
              "week": sum(cat_series[cid][-7:]), "today": cat_series[cid][-1]}
        for cid, name in cats_cfg.items()
    }

    tg_top.sort(key=lambda x: x["views"], reverse=True)
    result = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "generated_local": datetime.now(UTC4).strftime("%d.%m.%Y %H:%M"),
        "days": [d.isoformat() for d in days],
        "counts": counts,
        "topics": topics_out,
        "categories": cats_out,
        "tg_top": tg_top[:8],
    }
    os.makedirs(DATA, exist_ok=True)
    with open(os.path.join(DATA, "trends.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)

    rising = [t["name"] for t in topics_out.values() if t["status"] == "rising"]
    new = [t["name"] for t in topics_out.values() if t["status"] == "new"]
    fading = [t["name"] for t in topics_out.values() if t["status"] == "fading"]
    print(f"[trends] тем: {len(topics_out)} | растёт: {rising or '—'} | новые: {new or '—'} | спад: {fading or '—'}")
    print(f"[trends] 24ч: {counts['last24h']} | 7дн: {counts['last7d']} | всего: {counts['total']}")

    # Фаза 2: расширенная аналитика (афиша, кластеры, тональность, прогноз)
    try:
        import analytics
        r = analytics.build_all(items, result, cfg)
        print(f"[analytics] афиша: {len(r['calendar'])} | кластеры: {len(r['clusters'])} "
              f"(вне словаря: {sum(1 for c in r['clusters'] if c['gap'])}) | тон дня: {r['sentiment']['today_score']}")
    except Exception as e:  # noqa: BLE001
        print(f"[analytics] пропущено: {e}")


if __name__ == "__main__":
    main()
