#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
photos.py — скачивание фотографий из Telegram-превью в локальный assets/photos.

Telegram-CDN (cdn4.telesco.pe) у части читателей недоступен, поэтому фото
зеркалируются в репозиторий и отдаются с нашего домена. Для свежих записей,
у которых фото ещё не привязано, страница канала читается повторно и
строится карта message_id -> photo.

Запуск: python3 photos.py [--days 5] [--max 80] [--quiet]
"""
import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from collector import http_get, parse_tg_page  # noqa: E402

BASE = os.path.dirname(os.path.abspath(__file__))
PH = os.path.join(BASE, "assets", "photos")
UTC4 = timezone(timedelta(hours=4))


def safe_url(url):
    """Процент-кодирование не-ASCII в URL: у районных СМИ встречаются кириллические
    имена файлов фото (kumiakk.ru/…/Без-названия-4), на них urllib падал с
    «'ascii' codec can't encode characters»."""
    try:
        url.encode("ascii")
        return url
    except UnicodeEncodeError:
        p = urllib.parse.urlsplit(url)
        return urllib.parse.urlunsplit((
            p.scheme, p.netloc,
            urllib.parse.quote(p.path, safe="/%~"),
            urllib.parse.quote(p.query, safe="=&%"),
            urllib.parse.quote(p.fragment)))


def magic_ext(b):
    if b[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if b[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if b[:4] == b"RIFF":
        return ".webp"
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=10)
    ap.add_argument("--max", type=int, default=80)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    cfg = json.load(open(os.path.join(BASE, "config.json"), encoding="utf-8"))
    items = [json.loads(l) for l in open(os.path.join(BASE, "data", "store.jsonl"), encoding="utf-8") if l.strip()]
    os.makedirs(PH, exist_ok=True)
    now = datetime.now(UTC4)
    cutoff = now - timedelta(days=args.days)

    def pdate(it):
        p = it.get("published")
        try:
            return datetime.fromisoformat(p).astimezone(UTC4)
        except (TypeError, ValueError):
            return None

    # 1) добор photo для свежих записей без photo: перечитываем страницы каналов
    need = [it for it in items if it.get("source_type") == "tg" and not it.get("photo")
            and pdate(it) and pdate(it) >= cutoff]
    by_ch = {}
    for it in need:
        by_ch.setdefault(it.get("channel"), []).append(it)
    for ch, lst in by_ch.items():
        if not ch:
            continue
        try:
            page = http_get(f"https://t.me/s/{ch}", cfg)
            pm = {p["id"]: p.get("photo") for p in parse_tg_page(page, ch)}
            for it in lst:
                mid = (it.get("url") or "").rsplit("/", 1)[-1]
                if pm.get(mid):
                    it["photo"] = pm[mid]
        except Exception as e:  # noqa: BLE001
            if not args.quiet:
                print(f"  [photos] @{ch}: {str(e)[:60]}")
        time.sleep(cfg["settings"]["http_delay_sec"])

    # 1b) добивка photo из RSS-фидов (enclosure / media:content) для записей без photo
    import xml.etree.ElementTree as ET
    rss_items = [it for it in items if it.get("source_type") == "rss" and not it.get("photo")
                 and pdate(it) and pdate(it) >= cutoff]
    if rss_items:
        feeds = {s_["url"]: s_["name"] for s_ in cfg.get("rss_sources", []) if s_.get("enabled", True)}
        link2ph = {}
        for furl in feeds:
            try:
                raw = http_get(furl, cfg)
                root = ET.fromstring(raw)
                for el in root.iter():
                    ln = el.tag.rsplit("}", 1)[-1].lower()
                    if ln == "item":
                        link = photo = None
                        for ch_ in el:
                            cln = ch_.tag.rsplit("}", 1)[-1].lower()
                            if cln == "link":
                                link = (ch_.text or "").strip()
                            elif cln == "enclosure" and ch_.attrib.get("url"):
                                photo = photo or ch_.attrib["url"]
                            elif cln == "content" and ch_.attrib.get("url") and "media" in ch_.tag:
                                photo = photo or ch_.attrib["url"]
                        if link and photo:
                            link2ph[link] = photo
            except Exception as e:  # noqa: BLE001
                if not args.quiet:
                    print(f"  [photos] feed {furl}: {str(e)[:60]}")
            time.sleep(cfg["settings"]["http_delay_sec"])
        n_fb = 0
        for it in rss_items:
            ph = link2ph.get(it.get("url"))
            if ph:
                it["photo"] = ph
                n_fb += 1
        if not args.quiet:
            print(f"[photos] добивка из фидов: {n_fb}")

    # 1c) самоочистка: photo_local без файла на диске — ссылка в никуда (404 на Pages).
    # Сбрасываем её, чтобы кадр можно было перекачать, а генератор вернулся к удалённому URL.
    stale = 0
    for it in items:
        pl = it.get("photo_local")
        if pl and not os.path.exists(os.path.join(BASE, pl)):
            it["photo_local"] = ""
            stale += 1
    if stale and not args.quiet:
        print(f"  [photos] сброшено битых ссылок на зеркала: {stale}")

    # 2) скачивание fehlende фото
    downloaded = 0
    for it in items:
        if downloaded >= args.max:
            break
        ph = it.get("photo")
        if not ph or it.get("photo_local"):
            continue
        if not (pdate(it) and pdate(it) >= cutoff):
            continue
        url = safe_url(ph if ph.startswith("http") else "https:" + ph)
        if not url.startswith("http"):
            continue
        try:
            req = urllib.request.Request(url, headers={"User-Agent": cfg["settings"]["user_agent"]})
            with urllib.request.urlopen(req, timeout=20) as r:
                b = r.read()
            ext = magic_ext(b)
            if not ext or len(b) < 4000 or len(b) > 3_000_000:
                it["photo_local"] = ""
                continue
            fn = f"{it['id']}{ext}"
            with open(os.path.join(PH, fn), "wb") as f:
                f.write(b)
            it["photo_local"] = f"assets/photos/{fn}"
            downloaded += 1
            time.sleep(0.4)
        except Exception as e:  # noqa: BLE001
            if not args.quiet:
                print(f"  [photos] {url[:60]}: {str(e)[:60]}")

    with open(os.path.join(BASE, "data", "store.jsonl"), "w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    if not args.quiet:
        have = sum(1 for it in items if it.get("photo_local"))
        print(f"[photos] скачано: {downloaded} | всего с фото: {have}")


if __name__ == "__main__":
    main()
