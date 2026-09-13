#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
collector.py — сбор новостей для издания «Гудок».
Источники:
  1) RSS-ленты региональных СМИ (config.json -> rss_sources)
  2) Публичные веб-превью Telegram-каналов: https://t.me/s/<username>
     (домен te.me превью НЕ отдаёт — только t.me; авторизация не нужна,
      пагинация — параметр ?before=<message_id>, ~20 сообщений на страницу)

Только стандартная библиотека Python. Вежливый режим: задержка между
запросами, один ретрай, User-Agent с указанием бота.

Запуск:  python3 collector.py [--tg-pages N] [--rss-only] [--tg-only]
Выход:   data/store.jsonl (база новостей), data/fetch_status.json (статусы)
"""
import argparse
import gzip
import hashlib
import html as htmlmod
import io
import json
import os
import re
import socket
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")
STORE = os.path.join(DATA, "store.jsonl")
STATUS = os.path.join(DATA, "fetch_status.json")
UTC4 = timezone(timedelta(hours=4))  # Ульяновск


# ---------------------------------------------------------------- utilities
def http_get(url, cfg, timeout=None):
    """GET с User-Agent, одним ретраем и поддержкой gzip."""
    timeout = timeout or cfg["settings"]["http_timeout_sec"]
    headers = {
        "User-Agent": cfg["settings"]["user_agent"],
        "Accept-Encoding": "gzip, identity",
        "Accept-Language": "ru,en;q=0.8",
    }
    last_err = None
    for attempt in (1, 2):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read()
                if r.headers.get("Content-Encoding") == "gzip" or raw[:2] == b"\x1f\x8b":
                    raw = gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
                return raw.decode("utf-8", "ignore")
        except Exception as e:  # noqa: BLE001
            last_err = e
            if attempt == 1:
                time.sleep(cfg["settings"]["http_delay_sec"])
    raise last_err


TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")
CHANNEL_TAIL_X = ""
PROMO_TAIL_RE = re.compile(r"(?is)\s*(плохо грузит|читай в max|подпишись в max|max\.ru/|наш канал в max|👍 [^|]{0,40}\| наш канал).*$")
EMOJI_STRIP_RE = re.compile("[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF\uFE0F\u200D\u203C\u2049\u2B50\u2705\u274C\u2764]+")


SENT_SPLIT_RE = re.compile(r"(?<=[.!?…])\s+")


def clip_sentences(s, maxlen):
    s = (s or "").strip()
    parts = SENT_SPLIT.split(s)
    tail_cut = False
    if parts and not re.search(r'[.!?…»]"?$', parts[-1].strip()):
        if len(parts) > 1:
            parts = parts[:-1]
            tail_cut = True
        else:
            cut = s[:maxlen].rsplit(" ", 1)[0]
            return cut.rstrip(" ,;:—-") + "…"
    full = " ".join(parts)
    if len(full) <= maxlen:
        return full + ("…" if tail_cut else "")
    out = ""
    for p in parts:
        if not out:
            out = p
            continue
        if len(out) + 1 + len(p) <= maxlen:
            out += " " + p
        else:
            break
    return out + "…"


def norm_sq(s):
    return re.sub(r"[^a-zа-яё0-9]", "", (s or "").lower())


def strip_title_lead(text, title):
    t = (text or "").strip()
    ti = norm_sq(title)
    if not ti or not t:
        return t
    parts = SENT_SPLIT_RE.split(t)
    while parts:
        p0 = norm_sq(parts[0])
        if not p0:
            parts.pop(0)
            continue
        if p0 == ti or p0 in ti or ti in p0:
            parts.pop(0)
            continue
        break
    return " ".join(parts) if parts else t


def clean_text(s, maxlen=600):
    if not s:
        return ""
    s = htmlmod.unescape(s)
    s = TAG_RE.sub(" ", s)
    s = PROMO_TAIL_RE.sub("", s)
    s = re.sub(r"(?is)\s*(подписаться\s*\|\s*прислать|прислать новость|мы в макс|читайте нас в макс|подпишись).*$", "", s)
    s = WS_RE.sub(" ", s).strip()
    if len(s) > maxlen:
        s = clip_sentences(s, maxlen)
    return s


def to_utc_iso(value):
    """Любой понятный формат даты -> ISO 8601 в UTC."""
    if not value:
        return None
    value = str(value).strip()
    # unix timestamp
    if re.fullmatch(r"\d{9,11}", value):
        return datetime.fromtimestamp(int(value), tz=timezone.utc).isoformat()
    # ISO
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except ValueError:
        pass
    # RFC 822 (RSS)
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError):
        return None


def classify(cfg, title, text):
    """Категория — скоринг: побеждает рубрика с наибольшим числом совпавших
    паттернов (при равенстве — раньше в списке config). Темы — все совпадения."""
    blob = f"{title} {text}".lower()
    best_id, best_score = None, 0
    for pos, cat in enumerate(cfg["categories"]):
        score = sum(1 for pat in cat["patterns"] if re.search(pat, blob))
        if score > best_score:
            best_id, best_score = cat["id"], score
    topics = []
    for tp in cfg["topics"]:
        for pat in tp["patterns"]:
            if re.search(pat, blob):
                topics.append(tp["id"])
                break
    return best_id or "society", topics


def normalize_item(cfg, raw):
    """Сырая запись -> нормализованный элемент базы (или None, если это мусор)."""
    title = clean_text(raw.get("title", ""), 220) or "(без заголовка)"
    text = clean_text(raw.get("text", ""), cfg["settings"]["max_text_len"])
    text = strip_title_lead(text, title)
    # фильтр служебного/мусорного контента (эмодзи/символы вначале не должны мешать ^-паттернам)
    probe = EMOJI_STRIP_RE.sub("", f"{title} {text[:120]}").strip().lower()
    for pat in cfg["settings"].get("junk_patterns", []):
        if re.search(pat, probe, re.I):
            return None
    url = raw.get("url")
    pub = to_utc_iso(raw.get("published"))
    key = url if url else f"{title}|{pub}"
    item_id = hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]
    category, topics = classify(cfg, title, text)
    return {
        "id": item_id,
        "source_type": raw.get("source_type", "rss"),   # rss | tg | seed
        "source": raw.get("source", "?"),
        "channel": raw.get("channel"),                   # только для tg
        "url": url,
        "title": title,
        "text": text,
        "published": pub,
        "fetched": datetime.now(timezone.utc).isoformat(),
        "views": raw.get("views"),
        "category": category,
        "topics": topics,
        "tier": raw.get("tier"),
        "photo": raw.get("photo"),
    }


# ---------------------------------------------------------------- store
def load_store_ids(base=BASE):
    ids = set()
    path = os.path.join(base, "data", "store.jsonl")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    ids.add(json.loads(line)["id"])
                except (json.JSONDecodeError, KeyError):
                    continue
    return ids


def append_items(base, items):
    if not items:
        return 0
    os.makedirs(os.path.join(base, "data"), exist_ok=True)
    with open(os.path.join(base, "data", "store.jsonl"), "a", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    return len(items)


# ---------------------------------------------------------------- RSS
def parse_rss(xml_text):
    """Универсальный парсер RSS 2.0 / Atom (локальные имена тегов)."""
    out = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        raise ValueError(f"RSS parse error: {e}") from e

    def localname(tag):
        return tag.rsplit("}", 1)[-1].lower()

    entries = [el for el in root.iter() if localname(el.tag) in ("item", "entry")]
    for el in entries:
        fields = {}
        for child in el:
            ln = localname(child.tag)
            val = (child.text or "").strip()
            if ln == "link":
                if val:
                    fields["link"] = val
                elif child.attrib.get("href"):
                    fields["link"] = child.attrib["href"]
            elif ln == "enclosure" and child.attrib.get("url"):
                fields.setdefault("photo", child.attrib["url"])
            elif ln == "content" and child.attrib.get("url") and "media" in child.tag:
                fields.setdefault("photo", child.attrib["url"])
            elif ln in ("title", "description", "summary", "encoded"):
                fields.setdefault(ln, val)
            elif ln in ("pubdate", "published", "updated", "date"):
                fields.setdefault("date", val)
        if not fields.get("title") and not fields.get("description"):
            continue
        out.append({
            "title": fields.get("title") or clean_text(fields.get("description", ""), 120),
            "text": fields.get("description") or fields.get("encoded") or "",
            "url": fields.get("link"),
            "published": fields.get("date"),
            "photo": fields.get("photo"),
        })
    return out


def collect_rss(cfg, status, quiet=False):
    added = []
    for src in cfg["rss_sources"]:
        if not src.get("enabled", True):
            continue
        key = f"rss:{src['name']}"
        try:
            text = http_get(src["url"], cfg)
            entries = parse_rss(text)
            for e in entries:
                item = normalize_item(cfg, {
                    "source_type": "rss", "source": src["name"],
                    "url": e["url"], "title": e["title"], "text": e["text"],
                    "published": e["published"], "views": None, "channel": None,
                })
                if item:
                    added.append(item)
            status[key] = {"ok": True, "items": len(entries), "error": None}
            if not quiet:
                print(f"  [rss] {src['name']}: {len(entries)} записей")
            time.sleep(cfg["settings"]["http_delay_sec"])
        except Exception as e:  # noqa: BLE001
            status[key] = {"ok": False, "items": 0, "error": str(e)[:160]}
            if not quiet:
                print(f"  [rss] {src['name']}: ОШИБКА {e}")
    return added


# ---------------------------------------------------------------- Telegram
def parse_views(s):
    if not s:
        return None
    s = s.strip().replace("\u2009", "").replace(" ", "")
    m = re.fullmatch(r"([\d.,]+)([KM]?)", s, re.I)
    if not m:
        return None
    num = float(m.group(1).replace(",", "."))
    mult = {"K": 1000, "M": 1000000}.get(m.group(2).upper(), 1)
    return int(num * mult)


MSG_SPLIT = "tgme_widget_message_wrap"


def parse_tg_page(page_html, username):
    """Разбор веб-превью канала. Возвращает список dict(id, text, datetime, views, url)."""
    posts = []
    chunks = page_html.split(MSG_SPLIT)[1:]
    for chunk in chunks:
        m_id = re.search(r'data-post="([\w\-]+/(\d+))"', chunk)
        if not m_id:
            continue
        msg_id = m_id.group(2)
        m_txt = re.search(r'class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', chunk, re.S)
        if not m_txt:
            continue  # сервисные сообщения ("Channel created" и т.п.)
        raw_txt = m_txt.group(1)
        raw_txt = re.sub(r"<br\s*/?>", "\n", raw_txt)
        m_dt = re.search(r'tgme_widget_message_date[^>]*>\s*<time[^>]*datetime="([^"]+)"', chunk) \
            or re.search(r'<time[^>]*datetime="([^"]+)"', chunk)
        m_views = re.search(r'tgme_widget_message_views[^>]*>([^<]+)<', chunk)
        m_ph = re.search(r"background-image:url\('(https?://[^']*telesco\.pe[^']*)'\)", chunk)
        text = clean_text(raw_txt, 700)
        # «заголовок» — первая строка/предложение поста
        first_line = text.split("\n")[0].strip()
        title = first_line[:110] + ("…" if len(first_line) > 110 else "")
        posts.append({
            "id": msg_id,
            "url": f"https://t.me/{username}/{msg_id}",
            "title": title,
            "text": text,
            "published": m_dt.group(1) if m_dt else None,
            "views": parse_views(m_views.group(1) if m_views else None),
            "photo": (m_ph.group(1) if m_ph else None),
        })
    return posts


def collect_telegram(cfg, status, pages=None, quiet=False):
    added = []
    delay = cfg["settings"]["http_delay_sec"]
    for ch in cfg["telegram_channels"]:
        if not ch.get("enabled", True):
            continue
        username = ch["username"]
        key = f"tg:{username}"
        n_pages = pages or ch.get("pages") or cfg["settings"].get("tg_history_pages", 1)
        try:
            url = f"https://t.me/s/{username}"   # ВАЖНО: te.me/s/... -> 404, превью живёт на t.me
            html_text = http_get(url, cfg)
            posts = parse_tg_page(html_text, username)
            seen_ids = {p["id"] for p in posts}
            # пагинация вглубь истории: ?before=<min_id>
            for _ in range(max(0, n_pages - 1)):
                if not posts:
                    break
                min_id = min(int(p["id"]) for p in posts)
                time.sleep(delay)
                try:
                    older = parse_tg_page(http_get(f"{url}?before={min_id}", cfg), username)
                except Exception:  # noqa: BLE001
                    break
                new = [p for p in older if p["id"] not in seen_ids]
                if not new:
                    break
                posts.extend(new)
                seen_ids.update(p["id"] for p in new)
            for p in posts:
                item = normalize_item(cfg, {
                    "source_type": "tg", "source": f"t.me/{username}",
                    "channel": username, "url": p["url"], "title": p["title"],
                    "text": p["text"], "published": p["published"], "views": p["views"],
                    "tier": ch.get("tier", 2),
                })
                if item:
                    added.append(item)
            status[key] = {"ok": True, "items": len(posts), "error": None,
                           "title": ch.get("title", username)}
            if not quiet:
                print(f"  [tg]  @{username}: {len(posts)} сообщений")
            time.sleep(delay)
        except Exception as e:  # noqa: BLE001
            status[key] = {"ok": False, "items": 0, "error": str(e)[:160],
                           "title": ch.get("title", username)}
            if not quiet:
                print(f"  [tg]  @{username}: ОШИБКА {e}")
    return added


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="Сбор новостей издание «Гудок»")
    ap.add_argument("--tg-pages", type=int, default=None,
                    help="сколько страниц истории читать с каждого Telegram-канала (1 = ~20 сообщений)")
    ap.add_argument("--rss-only", action="store_true")
    ap.add_argument("--tg-only", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    socket.setdefaulttimeout(25)
    os.makedirs(DATA, exist_ok=True)
    with open(os.path.join(BASE, "config.json"), encoding="utf-8") as f:
        cfg = json.load(f)

    started = datetime.now(timezone.utc)
    if not args.quiet:
        print(f"=== издание «Гудок»: сбор {started.astimezone(UTC4):%d.%m.%Y %H:%M} (UTC+4) ===")

    status = {}
    raw_items = []
    if not args.tg_only:
        raw_items += collect_rss(cfg, status, args.quiet)
    if not args.rss_only:
        raw_items += collect_telegram(cfg, status, args.tg_pages, args.quiet)

    # дедупликация: с базой и внутри пакета
    existing = load_store_ids(BASE)
    fresh, seen = [], set(existing)
    for it in raw_items:
        if it["id"] in seen:
            continue
        seen.add(it["id"])
        fresh.append(it)

    append_items(BASE, fresh)

    # статусы источников
    status["_meta"] = {
        "last_run_utc": started.isoformat(),
        "last_run_local": started.astimezone(UTC4).strftime("%d.%m.%Y %H:%M"),
        "fetched": len(raw_items),
        "new": len(fresh),
        "total_store": len(seen),
    }
    old_status = {}
    if os.path.exists(STATUS):
        try:
            with open(STATUS, encoding="utf-8") as f:
                old_status = json.load(f)
        except json.JSONDecodeError:
            old_status = {}
    for k, v in old_status.items():
        if k not in status and k != "_meta":
            status[k] = v
    with open(STATUS, "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, indent=1)

    if not args.quiet:
        print(f"--- получено {len(raw_items)}, новых {len(fresh)}, всего в базе {len(seen)}")


if __name__ == "__main__":
    main()
