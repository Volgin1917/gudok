#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
enrich.py — Фаза 1 спринта: экстракция полных текстов статей.

Для каждой записи базы (кроме Telegram — там текст уже полный) скачивает
страницу источника и извлекает:
  * og:description / og:image / article:published_time;
  * тело статьи — через JSON-LD "articleBody" либо скоринг параграфов <p>:
    отсев меню/футеров по плотности ссылок, длине и маркерам мусора.

Вежливость: задержка между запросами, один ретрай, кэш отказов домена
(403/429/401/timeout — домен пропускается до следующего дня).

Запуск: python3 enrich.py [--max N] [--force]
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from collector import http_get, clean_text, to_utc_iso  # noqa: E402

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")
STORE = os.path.join(DATA, "store.jsonl")
FAILS = os.path.join(DATA, "enrich_failures.json")
UTC4 = timezone(timedelta(hours=4))

BOILERPLATE = [
    "версия для слабовидящих", "подписывайтесь", "подпишитесь", "наш канал",
    "читайте нас", "рассылк", "реклам", "фото:", "источник:", "ctrl+enter",
    "нашли ошибку", "поделиться", "комменти", "смотрите также", "читайте также",
    "предыдущая новость", "следующая новость", "все новости", "главное за",
    "мы в соц", "vk.com", "ок.ру", "whatsapp", "©", "все права защищены",
    "обсудить", "просмотров:", "новости дня", "рубрик", "политика конфиденциальности",
    "cookie", "куки", "зарегистрировано", "информационное агентство", "18+", "0+",
    "роскомнадзор", "свидетельство о регистрации",
]

P_RE = re.compile(r"<p[^>]*>(.*?)</p>", re.S | re.I)
A_RE = re.compile(r"<a\b[^>]*>.*?</a>", re.S | re.I)


def paragraph_is_junk(raw_p):
    """Меню/футеры/плашки: много ссылок, мало текста, маркеры мусора."""
    text = clean_text(raw_p, 5000)
    if len(text) < 40:
        return True, ""
    low = text.lower()
    for marker in BOILERPLATE:
        if marker in low:
            return True, ""
    stripped = A_RE.sub(" ", raw_p)
    link_chars = sum(len(clean_text(m.group(0), 500)) for m in A_RE.finditer(raw_p))
    total = len(clean_text(stripped, 5000)) or 1
    if link_chars / max(total, link_chars) > 0.55:
        return True, ""
    return False, text


def truncate_at_boilerplate(text):
    """Обрезаем хвост-футер, если маркер мусора встретился после основного текста."""
    if not text:
        return text
    low = text.lower()
    cut = len(text)
    for marker in BOILERPLATE:
        idx = low.find(marker)
        if idx > 200 and idx < cut:
            cut = idx
    return text[:cut].rstrip() if cut < len(text) else text


def extract_body(page):
    """Тело статьи: JSON-LD articleBody -> скоринг параграфов."""
    # 1) JSON-LD
    m = re.search(r'"articleBody"\s*:\s*"((?:[^"\\]|\\.)+)"', page)
    if m:
        try:
            body = json.loads('"' + m.group(1) + '"')
            body = clean_text(body.replace("\n", " "), 6000)
            if len(body) > 200:
                return body
        except (json.JSONDecodeError, ValueError):
            pass
    # 2) параграфы
    good = []
    for pm in P_RE.finditer(page):
        junk, text = paragraph_is_junk(pm.group(1))
        if not junk:
            good.append(text)
    return " ".join(good)


def meta_tag(page, prop):
    for order in (
        rf'<meta[^>]+(?:property|name)=["\']{prop}["\'][^>]+content=["\']([^"\']+)["\']',
        rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\']{prop}["\']',
    ):
        m = re.search(order, page, re.I)
        if m:
            return m.group(1).strip()
    return ""


def load_fails():
    if os.path.exists(FAILS):
        try:
            with open(FAILS, encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            pass
    return {}


def save_fails(fails):
    with open(FAILS, "w", encoding="utf-8") as f:
        json.dump(fails, f, ensure_ascii=False, indent=1)


def domain_blocked(fails, domain):
    rec = fails.get(domain)
    if not rec:
        return False
    if rec.get("date") != datetime.now(UTC4).strftime("%Y-%m-%d"):
        return False  # кэш отказов живёт сутки
    return rec.get("code") in (401, 403, 429, "timeout", "blocked")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=40, help="сколько страниц скачать за запуск")
    ap.add_argument("--force", action="store_true", help="игнорировать кэш отказов доменов")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    with open(os.path.join(BASE, "config.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    delay = cfg["settings"]["http_delay_sec"]
    maxlen = cfg["settings"].get("max_full_text_len", 1800)

    with open(STORE, encoding="utf-8") as f:
        items = [json.loads(l) for l in f if l.strip()]

    fails = load_fails()
    todo = []
    for it in items:
        url = it.get("url") or ""
        if it.get("source_type") == "tg" or not url or url.startswith("https://t.me"):
            continue
        if it.get("enriched") or len(it.get("text") or "") >= maxlen * 0.8:
            continue
        dom = urllib.parse.urlparse(url).netloc
        if not args.force and domain_blocked(fails, dom):
            continue
        todo.append((it, dom))
    todo = todo[: args.max]

    if not args.quiet:
        print(f"[enrich] кандидатов: {len(todo)} (лимит {args.max})")

    updated = 0
    for it, dom in todo:
        try:
            page = http_get(it["url"], cfg)
        except Exception as e:  # noqa: BLE001
            code = getattr(e, "code", None) or ("timeout" if "timed out" in str(e).lower() else "blocked")
            fails[dom] = {"code": code, "date": datetime.now(UTC4).strftime("%Y-%m-%d"),
                          "error": str(e)[:100]}
            if not args.quiet:
                print(f"  ✗ {dom}: {code} — домен пропущен до завтра")
            time.sleep(delay)
            continue

        fails.pop(dom, None)
        body = extract_body(page)
        og_desc = clean_text(meta_tag(page, "og:description"), maxlen)
        og_img = meta_tag(page, "og:image")
        pub = to_utc_iso(meta_tag(page, "article:published_time"))

        best = truncate_at_boilerplate(max([body, og_desc], key=len))
        if best and len(best) > len(it.get("text") or "") + 40:
            it["text"] = best[:maxlen]
            updated += 1
        if og_img:
            it["image"] = urllib.parse.urljoin(it["url"], og_img)
        if pub and not it.get("published"):
            it["published"] = pub
        it["enriched"] = True
        it["enriched_at"] = datetime.now(timezone.utc).isoformat()
        if not args.quiet:
            gain = len(it.get("text") or "")
            print(f"  ✓ {dom}: текст {gain} симв." + (" +img" if og_img else ""))
        time.sleep(delay)

    with open(STORE, "w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    save_fails(fails)
    if not args.quiet:
        print(f"[enrich] обработано {len(todo)}, улучшено текстов: {updated}")


if __name__ == "__main__":
    main()
