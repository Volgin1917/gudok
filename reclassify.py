#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
reclassify.py — переклассификация накопленной базы после правки словарей config.json.

Меняете паттерны рубрик/тем в config.json -> запускаете этот скрипт ->
вся база data/store.jsonl переразмечается без повторного сбора.

Запуск: python3 reclassify.py [--dry-run] [--audit N]
  --audit N  — дополнительно напечатать N случайных записей для ручной проверки
"""
import argparse
import json
import os
import random
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from collector import classify, PROMO_TAIL_RE, EMOJI_STRIP_RE  # noqa: E402

BASE = os.path.dirname(os.path.abspath(__file__))
STORE = os.path.join(BASE, "data", "store.jsonl")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--audit", type=int, default=0)
    ap.add_argument("--seed", type=int, default=73)
    args = ap.parse_args()

    with open(os.path.join(BASE, "config.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    with open(STORE, encoding="utf-8") as f:
        items = [json.loads(l) for l in f if l.strip()]

    tier_by_ch = {c["username"]: c.get("tier", 2) for c in cfg.get("telegram_channels", [])}
    junk = cfg["settings"].get("junk_patterns", [])

    def is_junk(it):
        probe = EMOJI_STRIP_RE.sub("", f"{it.get('title','')} {(it.get('text') or '')[:120]}").strip().lower()
        return any(re.search(pat, probe, re.I) for pat in junk)

    before = len(items)
    items = [it for it in items if not is_junk(it)]
    removed = before - len(items)

    changed_cat = changed_top = changed_tier = 0
    for it in items:
        if it.get("text"):
            it["text"] = PROMO_TAIL_RE.sub("", it["text"]).strip()
        if it.get("source_type") == "tg" and it.get("channel") in tier_by_ch:
            t = tier_by_ch[it["channel"]]
            if it.get("tier") != t:
                it["tier"] = t
                changed_tier += 1
        cat, topics = classify(cfg, it.get("title", ""), it.get("text", ""))
        if cat != it.get("category"):
            changed_cat += 1
        if topics != it.get("topics"):
            changed_top += 1
        it["category"], it["topics"] = cat, topics

    if not args.dry_run:
        with open(STORE, "w", encoding="utf-8") as f:
            for it in items:
                f.write(json.dumps(it, ensure_ascii=False) + "\n")

    print(f"[reclassify] записей: {len(items)} (удалено мусора: {removed}) | сменено рубрик: {changed_cat} | тем: {changed_top} | tier: {changed_tier}"
          + (" (dry-run, база не изменена)" if args.dry_run else ""))

    if args.audit:
        random.seed(args.seed)
        pool = [i for i in items if not i.get("dup_of")]
        for n, it in enumerate(random.sample(pool, min(args.audit, len(pool))), 1):
            print(f"{n:>3} [{it['category']:<9}] {it['title'][:95]}")


if __name__ == "__main__":
    main()
