#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
reclassify.py — переклассификация накопленной базы после правки словарей config.json.

Меняете паттерны рубрик/тем в config.json -> запускаете этот скрипт ->
вся база data/store.jsonl переразмечается без повторного сбора.

Производные поля (SQL-готовые, хранятся в store):
  sub_category — подрубрика (для category=society из config.subcategories)
  material_type — алерт|анонс|хроника|мнение|аналитика|новость
  geo_tag — строка муниципалитета из config.municipalities
  trust_status — факт|по данным|не подтверждено|анонс|мнение

Запуск: python3 reclassify.py [--dry-run] [--audit N]
  --audit N  — дополнительно напечатать N случайных записей для ручной проверки
"""
import argparse
import json
import math
import os
import random
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from collector import classify, PROMO_TAIL_RE, EMOJI_STRIP_RE  # noqa: E402

BASE = os.path.dirname(os.path.abspath(__file__))
STORE = os.path.join(BASE, "data", "store.jsonl")

# -------------------------------------------------------------------
# Дублирование regex-ов из generate.py — единый источник истинны generate.
# При синхронизации правок в Alert/Promo/Casualty — обновлять оба файла.
# -------------------------------------------------------------------
_ALERT_RE = re.compile(
    r"(ракетн\w*|беспилотн\w*|бпла)\W{0,40}опасност"
    r"|опасност\W{0,40}(бпла|беспилотн\w*|ракетн\w*)"
    r"|план\s*«?ковер"
    r"|при[ёе]м и выпуск\W{0,30}ограничен"
    r"|ограничени\w*\W{0,40}(аэропорт|при[ёе]м)"
    r"|аэропорт\w*\W{0,40}ограничен", re.I)
_CASUALTY_RE = re.compile(r"погиб|пострада|ранен|убит|разруш|поврежд|сбит|упал|обломк", re.I)
_PROMO_RE = re.compile(
    r"(приглашаем|жд[её]м вас|приходите|в программе\s*[:—]|анонс|открытие сезона"
    r"|розыгрыш\w*\s+(?:билет\w*|приз\w*|подарк\w*|мест\w*))", re.I)
_CHRONO_KEYS = ("ракетная опасность", "беспилотная опасность", "бпла", "беспилот",
                "воздушная тревога", "пво", "атак", "аэропорт", "баратаевка", "сбит")


def _is_alert(it):
    """Локальная копия generate.is_alert — избегаем тяжёлого импорта generate."""
    blob = (it.get("title") or "") + " " + (it.get("text") or "")[:200]
    if not _ALERT_RE.search(blob):
        return False
    return not _CASUALTY_RE.search(blob)


def _is_promo(it):
    blob = (it.get("title") or "") + " " + (it.get("text") or "")[:150]
    return bool(_PROMO_RE.search(blob))


def _is_chrono(it):
    blob = (it.get("title") or "") + " " + (it.get("text") or "")[:200]
    return any(k in blob.lower() for k in _CHRONO_KEYS)


# -------------------------------------------------------------------
# Производные поля: compute_* — чистые функции (record, cfg) -> value
# -------------------------------------------------------------------
def compute_subcategory(title, text, category, cfg):
    """Подрубрика для category=='society' по паттернам config.subcategories."""
    if category != "society":
        return None
    blob = f"{title} {text}".lower()
    best_id, best_score = None, 0
    for sub in cfg.get("subcategories", []):
        if sub.get("parent") != "society":
            continue
        score = sum(1 for p in sub["patterns"] if re.search(p, blob))
        if score > best_score:
            best_id, best_score = sub["id"], score
    return best_id


def compute_material_type(it):
    """Тип материала: алерт|анонс|хроника|мнение|аналитика|новость."""
    if _is_alert(it):
        return "alert"
    if _is_promo(it):
        return "announce"
    if _is_chrono(it):
        return "chronicle"
    if it.get("tier") == 3:
        return "opinion"
    # аналитика = длинный текст (≥300 слов) + много тем (≥2)
    text_len = len((it.get("text") or "").split())
    topics_n = len(it.get("topics") or [])
    if text_len >= 300 and topics_n >= 2:
        return "analytics"
    return "news"


def compute_geo_tag(title, text, cfg):
    """Муниципалитет из config.municipalities (первое совпадение)."""
    blob = f"{title} {text}".lower()
    for name, pattern in cfg.get("municipalities", {}).items():
        if name.startswith("_"):
            continue
        if re.search(pattern, blob, re.I):
            return name
    return None


def compute_trust_status(tier, cluster_src, material_type):
    """Статус достоверности (SQL-готовое поле)."""
    if material_type == "alert":
        return "fact"
    if material_type == "announce":
        return "announce"
    if material_type == "opinion":
        return "unconfirmed"
    if (cluster_src or 0) >= 2:
        return "fact"
    if tier == 1:
        return "fact"
    if tier == 2:
        return "source_reported"
    if tier == 3:
        return "unconfirmed"
    return "source_reported"


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
    changed_sub = changed_mat = changed_geo = changed_trust = 0
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

        # --- производные поля v4 ---
        new_sub = compute_subcategory(it.get("title", ""), it.get("text", ""), cat, cfg)
        new_mat = compute_material_type(it)
        new_geo = compute_geo_tag(it.get("title", ""), it.get("text", ""), cfg)
        new_trust = compute_trust_status(it.get("tier"), it.get("cluster_src"), new_mat)

        if new_sub != it.get("sub_category"):
            changed_sub += 1
        if new_mat != it.get("material_type"):
            changed_mat += 1
        if new_geo != it.get("geo_tag"):
            changed_geo += 1
        if new_trust != it.get("trust_status"):
            changed_trust += 1

        if new_sub:
            it["sub_category"] = new_sub
        elif "sub_category" in it:
            del it["sub_category"]
        it["material_type"] = new_mat
        if new_geo:
            it["geo_tag"] = new_geo
        elif "geo_tag" in it:
            del it["geo_tag"]
        it["trust_status"] = new_trust

    if not args.dry_run:
        with open(STORE, "w", encoding="utf-8") as f:
            for it in items:
                f.write(json.dumps(it, ensure_ascii=False) + "\n")

    print(f"[reclassify] записей: {len(items)} (удалено мусора: {removed})")
    print(f"  сменено: рубрик {changed_cat} | тем {changed_top} | tier {changed_tier}")
    print(f"  v4: sub_category {changed_sub} | material_type {changed_mat} | geo_tag {changed_geo} | trust_status {changed_trust}"
          + (" (dry-run, база не изменена)" if args.dry_run else ""))

    if args.audit:
        random.seed(args.seed)
        pool = [i for i in items if not i.get("dup_of")]
        for n, it in enumerate(random.sample(pool, min(args.audit, len(pool))), 1):
            mt = it.get("material_type", "")
            sub = it.get("sub_category", "")
            geo = it.get("geo_tag", "")
            tr = it.get("trust_status", "")
            tags = " | ".join(x for x in [mt, sub, geo, tr] if x)
            title = it["title"][:60].encode("cp1251", errors="replace").decode("cp1251")
            print(f"{n:>3} [{it['category']:<9}] [{tags:<40}] {title}")


if __name__ == "__main__":
    main()
