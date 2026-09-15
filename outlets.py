#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
outlets.py — канонические издания: алиасы источников одной редакции.

Зачем. Одна редакция публикуется в нескольких каналах сразу: RSS-лента сайта,
Telegram-канал, группа ВКонтакте, сайт ОМСУ на Госвебе. «Улпресса» (RSS
ulpressa.ru) и @ulpressa (Telegram) — это не два источника, а одна редакция
ООО «Симбирск-Паблисити»; @ulgovru и @Russkih_Aleksey — одна пресс-служба
исполнительной власти области. Если считать каналы независимыми источниками,
перепечатка собственного релиза в собственный канал выглядит как «каскад из
двух редакций» и завышает и сеттеров повестки, и тиражирование, и оригинальность.

Что делает. Строит карту «сырой ключ записи → каноническое издание» из
sources_registry.json (поля outlet и aka у записи реестра) и отдаёт:
  outlet(it)      — каноническое имя издания для записи store.jsonl (для подписей);
  outlet_key(it)  — нормализованный ключ издания (для сравнений «один и тот же»);
  resolve_raw(s)  — каноническое имя для сырой строки (config.municipal_sources и т.п.);
  groups()        — издание → список id реестра (для справок, статусной страницы, тестов).

Правила решения редакции (15.09.2026): объединяются только каналы одного
производителя — одного юрлица/редакции (подтверждено ЕГРЮЛ/imprint) или одной
пресс-службы. Конкурирующие каналы одного города (например «Типичный
Димитровград» и «Информационный Димитровград» — разные админы и разные группы
ВК) остаются разными источниками: их повторы и есть настоящая перепечатка.

Только стандартная библиотека. Карта кэшируется по mtime реестра.
"""
import json
import os
import re
from urllib.parse import urlparse

BASE = os.path.dirname(os.path.abspath(__file__))

# хосты, из пути которых берётся имя канала/сообщества
_CHANNEL_HOSTS = ("t.me", "telegram.me", "vk.com", "vk.ru", "ok.ru", "max.ru")

_cache = {"stamp": None, "map": {}, "explicit": set(), "groups": {}}


# татарская кириллица в названиях районных СМИ («Кумәк көч») — при сверке
# написаний складываем специальные буквы в русские, иначе алиас не совпадёт
_TATAR_FOLD = str.maketrans({"ә": "а", "ө": "о", "ү": "у"})


def norm(raw):
    """Нормализация сырой строки источника: регистр, ё/татарские буквы, префиксы."""
    s = str(raw or "").strip().lower()
    s = s.replace("ё", "е").translate(_TATAR_FOLD)
    s = re.sub(r"^(https?://)?(www\.|m\.)?", "", s)
    s = re.sub(r"^t\.me/", "", s)
    s = s.lstrip("@").rstrip("/")
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def _default_canon(entry):
    """Имя издания по умолчанию: у TG/VK — имя канала без «@», у лент и сайтов — имя."""
    name = str(entry.get("name") or entry.get("id") or "").strip()
    kind = entry.get("kind") or str(entry.get("id") or "").split(":", 1)[0]
    if kind in ("tg", "vk") and name.startswith("@"):
        name = name[1:]
    return name


def _entries(base=None):
    """Записи реестра источников (пустой список, если файла нет/битый)."""
    path = os.path.join(base or BASE, "sources_registry.json")
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("sources", []) if isinstance(data, dict) else data
    except Exception:
        return []


def _load(base=None):
    """Карта norm(сырой ключ) → каноническое имя издания (+ обратный индекс)."""
    path = os.path.join(base or BASE, "sources_registry.json")
    stamp = None
    try:
        stamp = (os.path.getmtime(path), os.path.getsize(path))
    except OSError:
        pass
    if base is None and _cache["stamp"] == stamp and _cache["map"]:
        return _cache["map"]

    amap, groups, explicit = {}, {}, set()
    entries = _entries(base or BASE)

    for e in entries:
        sid = str(e.get("id") or "")
        if not sid:
            continue
        canon = str(e.get("outlet") or _default_canon(e) or sid.split(":", 1)[-1])
        if e.get("outlet"):
            explicit.add(canon)   # имя задано редакцией, а не взято из имени канала
        kind = e.get("kind") or sid.split(":", 1)[0]
        short = sid.split(":", 1)[-1]
        keys = {sid, short, canon}
        name = str(e.get("name") or "")
        if name:
            keys |= {name, name.lstrip("@")}
        if kind == "tg" and short:
            keys.add(f"t.me/{short}")
        for a in (e.get("aka") or []):
            if a:
                keys.add(str(a))
        for k in keys:
            nk = norm(k)
            if nk and nk not in amap:
                amap[nk] = canon
        groups.setdefault(canon, []).append(sid)

    if base is None:
        _cache.update({"stamp": stamp, "map": amap, "groups": groups, "explicit": explicit})
    return amap


def _explicit(base=None):
    """Издания, чьё каноническое имя задано редакцией (поле outlet в реестре)."""
    if base is None:
        _load(base)
        return _cache["explicit"]
    return {str(e.get("outlet")) for e in _entries(base) if e.get("outlet")}


def _groups(base=None):
    if base is None and _cache["groups"]:
        _load(base)
        return _cache["groups"]
    _load(base)
    # пересобираем индекс (для произвольного base)
    groups = {}
    for e in _entries(base):
        sid = str(e.get("id") or "")
        if not sid:
            continue
        canon = str(e.get("outlet") or _default_canon(e) or sid.split(":", 1)[-1])
        groups.setdefault(canon, []).append(sid)
    return groups


def resolve_raw(raw, base=None):
    """Каноническое издание для сырой строки («Улпресса», «t.me/ulpressa», «ulpressa.ru»)."""
    s = str(raw or "").strip()
    if not s:
        return ""
    amap = _load(base)
    return amap.get(norm(s), s)


def _item_keys(it):
    """Все сырые ключи записи store, по которым ищем издание (по убыванию точности)."""
    keys = []
    st = it.get("source_type")
    ch, src = it.get("channel"), it.get("source")
    if st and ch:
        keys.append(f"{st}:{ch}")
    if ch:
        keys.append(str(ch))
    if st and src:
        keys.append(f"{st}:{src}")
    if src:
        keys.append(str(src))
    url = str(it.get("url") or "")
    if url:
        try:
            p = urlparse(url if "//" in url else "http://" + url)
            host = (p.netloc or "").lower()
            host = re.sub(r"^(www\.|m\.)", "", host)
            seg = [s for s in (p.path or "").split("/") if s]
            if host:
                keys.append(host)
                if host in _CHANNEL_HOSTS and seg and not seg[0].isdigit():
                    keys.append(seg[0])
        except ValueError:
            pass
    return keys


def _resolve(it, base=None):
    """Каноническое имя издания или None, если запись не найдена в реестре."""
    if not isinstance(it, dict):
        return resolve_raw(it, base) or None
    amap = _load(base)
    for k in _item_keys(it):
        hit = amap.get(norm(k))
        if hit:
            return hit
    return None


def outlet(it, base=None):
    """Каноническое имя издания для метрик и подписей («Улпресса», «tresh_ulyan»)."""
    return _resolve(it, base) or str(it.get("channel") or it.get("source") or "?") \
        if isinstance(it, dict) else resolve_raw(it, base)


def outlet_label(it, base=None):
    """Подпись в списках источников («также сообщили», каскады).

    Если издание объединяет каналы и его имя задано редакцией — показываем
    каноническое имя («Улпресса», «Репортёр73»); иначе сохраняем прежний вид
    подписи канала («t.me/tresh_ulyan»), чтобы читатель видел тип источника."""
    canon = _resolve(it, base)
    if canon and canon in _explicit(base):
        return canon
    if isinstance(it, dict):
        return str(it.get("source") or it.get("channel") or "?")
    return canon or str(it or "?")


def outlet_key(it, base=None):
    """Нормализованный ключ издания: равен для всех каналов одной редакции."""
    return norm(outlet(it, base))


def channel_key(it):
    """Ключ конкретного канала (как раньше src_key в dedup) — для подписей карточек."""
    return str(it.get("channel") or it.get("source") or "?")


def groups(base=None):
    """Издание → [id реестра]. Издания из 2+ каналов — объединённые алиасы."""
    return _groups(base)


def merged_groups(base=None):
    """Только издания, объединяющие несколько каналов реестра (для справок/тестов)."""
    return {k: v for k, v in groups(base).items() if len(v) > 1}


def same_outlet(a, b, base=None):
    """Одна и та же редакция (включая разные её каналы)?"""
    return outlet_key(a, base) == outlet_key(b, base)


def invalidate_cache():
    _cache.update({"stamp": None, "map": {}, "explicit": set(), "groups": {}})
