#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
analytics.py — Фаза 2: интеллектуальная аналитика издание «Гудок».

Модули (всё — стандартная библиотека, без внешних зависимостей и API):
  1. extract_calendar()  — NLP-извлечение будущих событий из новостей
                           («13 сентября в 14:00…», диапазоны, площадки 📍) → автоафиша;
  2. cluster_stories()   — кластеризация сюжетов последних 72 ч методом лидера
                           по TF-IDF-косинусу, БЕЗ словаря тем; помечает сюжеты,
                           которые словарь config.json НЕ покрыл (кандидаты в новые темы);
  3. sentiment_score()   — лексиконная оценка тональности (грубая, помечена как оценочная):
                           тон дня, динамика 14 дней, разрез по рубрикам;
  4. source_credibility()— индекс источников: доля первичных сообщений vs перепечатки
                           (по данным дедупликации), медианные просмотры TG;
  5. forecast_topics()   — прогноз на завтра по темам: наклон + EMA, уровень уверенности.

Выход: data/analytics.json (пишется из trends.py или прямым запуском).
"""
import csv
import json
import math
import os
import re
import sys
from collections import Counter, OrderedDict, defaultdict
from datetime import datetime, timedelta, timezone

BASE = os.path.dirname(os.path.abspath(__file__))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

import outlets as _outlets  # канонические издания: каналы одной редакции = один источник

DATA = os.path.join(BASE, "data")
UTC4 = timezone(timedelta(hours=4))

MONTHS = {
    "январ": 1, "феврал": 2, "март": 3, "апрел": 4, "ма": 5, "июн": 6,
    "июл": 7, "август": 8, "сентябр": 9, "октябр": 10, "ноябр": 11, "декабр": 12,
}
MONTH_STEM = "|".join(MONTHS)

EVENT_HINTS = re.compile(
    r"откро|пройд|состо|заплан|приглаш|начн|начал|старт|будет|ожидает|намечен|"
    r"запуск|введ|планиру|примут|прожив|заверш|продлится|объявлен|введён|введен|"
    r"стартует|пропуст|приед|выступ|вручат|чествов|состоится|включ")
RE_DAY = re.compile(rf"(\d{{1,2}})\s*({MONTH_STEM})", re.I)
RE_RANGE_SAME = re.compile(rf"(\d{{1,2}})\s*[–—-]\s*(\d{{1,2}})\s*({MONTH_STEM})", re.I)
RE_RANGE_CROSS = re.compile(rf"(\d{{1,2}})\s*({MONTH_STEM})\w*\s*[–—-]\s*(\d{{1,2}})\s*({MONTH_STEM})", re.I)
RE_TIME = re.compile(r"\b(\d{1,2})[:.](\d{2})\b")
RE_VENUE = re.compile(r"📍\s*([^\n,]{3,70})")
WEATHER_RE = re.compile(r"гидромет|погод|облачн|заморозк|температур воздуха|ветер \d|осадк|метеопредупрежд", re.I)
HISTORY_RE = re.compile(r"\b1[5-9]\d{2}\b|историческ(их|ого|ие|ой) событий|в этот день \d{4}|в прошлом году", re.I)
PAST_RE = re.compile(r"начали укладывать|заасфальтировали|уложили|выиграл[аи]?\b|наводят чистоту|убрали|спасли|вручили|провели\b|состоял|прош[её]л|прошла|заверши|открыли\b|принял\b|сбил[аи]?\b", re.I)
PROMO_TAIL = re.compile(r"(?is)(плохо грузит|читай в max|подпишись в max|max\.ru/|наш канал в max|👍 [^|]{0,40}\| наш канал|телеграм-канал @\w+|t\.me/\w+).*$")

ETYPE_RULES = [
    ("kids",      r"детск|для детей|ребятам|малыш|школьник|кукольн|мультф|квест|мастер-класс|игров.*программ|семейн"),
    ("cinema",    r"кино|кинозал|фильм|кинопоказ|кинотеатр"),
    ("festival",  r"фестивал|праздник|празднован|день города|дня города|дню города|карнавал|гулянь|open\s?air|ярмарк"),
    ("theatre",   r"театр|спектакл|пьес|премьер|драм|постановк|балет|оперет"),
    ("concert",   r"концерт|филармони|оркестр|хор |хор\b|романс|песн|музык|джаз|рок|стендап|stand.?up|выступит|ансамбл|караоке|дискотек|вечеринк"),
    ("expo",      r"выставк|музей|экспозиц|вернисаж|галере|арт-объект|библиотек"),
    ("sport",     r"спорт|забег|матч|турнир|соревнован|зарядк|гто|кубок|чемпионат"),
]
DISTRICT_RE = re.compile(r"димитровград|барыш|инза|сенгилей|новоульяновск|ундоры|павловк|кузоватов|старая майна|чердакл|вешкайм|карсун|сурск|никольск|тереньга|радищев|майнк|большое нагаткино|район[аеу]?\b", re.I)


NOT_EVENT_RE = re.compile(
    r"иннопром|бизнес-делег|делегаци|отопительн|котельн|теплоснаб|\bмост\b|голосован|выбор", re.I)


def event_type(blob):
    low = blob.lower()
    if NOT_EVENT_RE.search(low):
        return "other"   # инфраструктура/деловые/политические — не афиша
    for et, pat in ETYPE_RULES:
        if re.search(pat, low):
            return et
    return "other"


NEG = ("авар", "катастроф", "пожар", "погиб", "ранен", "пострада", "травм", "удар",
       "атак", "обстрел", "опасность", "тревог", "сирен", "эвакуац", "взрыв",
       "задержан", "задержал", "арест", "приговор", "штраф", "взятк", "хищен",
       "краж", "мошенник", "преступл", "нарушен", "убыт", "банкрот", "безработ",
       "протест", "жалоб", "критик", "скандал", "коррупц", "дтп", "смерть",
       "умер", "убийств", "угроз", "паник", "кризис", "дефицит", "подорожан",
       "срыв", "задержк", "отмен", "снос", "мусор", "свалк", "разрушен", "износ",
       "прорыв", "отключ", "затоп", "обман", "фальсифик", "тупик", "проблем",
       "недоволен", "заболел", "инфекц", "эпидем", "долг", "неудач", "потер",
       "ухудшен", "загрязн", "вред", "опасен", "чрезвычайн")
POS = ("откр", "запуск", "запустил", "побед", "выигра", "рекорд", "достижен",
       "успех", "развит", "улучшен", "благоустр", "награжден", "наград", "преми",
       "грант", "поддержк", "инвестир", "рост", "превысил", "праздник", "фестивал",
       "концерт", "юбиле", "подарок", "помог", "спасл", "спасли", "решен",
       "модернизац", "обновлен", "чемпион", "кубок", "медаль", "золот", "лидер",
       "лучш", "вошел в топ", "благодар", "рад ", "гордимся", "готов", "ремонтир",
       "отремонт", "построят", "построен", "восстанов", "соглашение", "контракт",
       "сертификат", "первых", "передов", "качествен")


def cascade_sources(it):
    """Число НЕЗАВИСИМЫХ источников в каскаде перепечаток.
    После правок dedup.py (15.09, Волна 4) первичный материал несёт cluster_src —
    сколько разных источников сообщили о сюжете; повторы внутри собственного канала
    в каскад не засчитываются. Для старых записей без поля — общее число участников."""
    return it.get("cluster_src") or it.get("cluster") or 0


def _local_dt(iso):
    try:
        return datetime.fromisoformat(iso).astimezone(UTC4)
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------- 1. calendar
def extract_calendar(items, now=None, horizon_days=45):
    """Будущие события, упомянутые в новостях: дата(+диапазон), время, площадка."""
    now = now or datetime.now(UTC4)
    today = now.date()
    events, seen = [], set()

    def resolve(day, month):
        for year in (today.year, today.year + 1):
            try:
                d = datetime(year, month, day).date()
            except ValueError:
                continue
            delta = (d - today).days
            if 0 <= delta <= horizon_days:
                return d
        return None

    for it in items:
        if it.get("dup_of"):
            continue
        blob = f"{it.get('title','')} {it.get('text','')}"
        if not EVENT_HINTS.search(blob):
            continue
        title = it.get("title", "")
        if WEATHER_RE.search(title) or HISTORY_RE.search(title) or PAST_RE.search(title):
            continue
        # деловые поездки и события вне региона — не афиша
        if re.search(r"делегаци|бизнес-мисси|отправил|командиров", title, re.I):
            continue
        if re.search(r"\b(в|во|на)\s+(екатеринбург|москв|минск|сочи|казан|самар|саратов|пенз|уфу|пермь|нижн|волгоград|астрахан)", title, re.I) \
                and not re.search(r"ульяновск|симбирск", title, re.I):
            continue
        dt_pub = _local_dt(it.get("published"))
        if dt_pub and (now - dt_pub).days > 10:
            continue  # события из старых новостей обычно уже прошли
        dates = []
        m = RE_RANGE_CROSS.search(blob)
        if m:
            d1 = resolve(int(m.group(1)), MONTHS[m.group(2).lower()])
            d2 = resolve(int(m.group(3)), MONTHS[m.group(4).lower()])
            if d1 and d2 and d2 >= d1:
                dates = [d1, d2]
        if not dates:
            m = RE_RANGE_SAME.search(blob)
            if m:
                mon = MONTHS[m.group(3).lower()]
                d1 = resolve(int(m.group(1)), mon)
                d2 = resolve(int(m.group(2)), mon)
                if d1 and d2 and d2 >= d1 and (d2 - d1).days <= 10:
                    dates = [d1, d2]
        if not dates:
            for m in RE_DAY.finditer(blob):
                d = resolve(int(m.group(1)), MONTHS[m.group(2).lower()])
                if d:
                    dates.append(d)
                if len(dates) >= 2:
                    break
            dates = dates[:1]
        if not dates:
            continue
        tm = RE_TIME.search(blob)
        time_s = f"{int(tm.group(1)):02d}:{tm.group(2)}" if tm and int(tm.group(1)) < 24 else ""
        vm = RE_VENUE.search(blob)
        key = (dates[0].isoformat(), re.sub(r"\W+", "", it.get("title", "").lower())[:40])
        if key in seen:
            continue
        seen.add(key)
        etype = event_type(f"{it.get('title','')} {it.get('text','')}")
        is_culture = etype in ("kids", "cinema", "festival", "theatre", "concert", "expo") or it.get("category") == "culture"
        events.append({
            "etype": etype,
            "is_culture": is_culture,
            "district": bool(DISTRICT_RE.search(f"{it.get('title','')} {it.get('text','')}")),
            "date": dates[0].isoformat(),
            "date_end": dates[-1].isoformat() if len(dates) > 1 else None,
            "time": time_s,
            "title": it.get("title", "")[:150],
            "url": it.get("url") or "",
            "source": it.get("source", ""),
            "tier": it.get("tier"),
            "venue": (vm.group(1).strip()[:60] if vm else ""),
        })
    events.sort(key=lambda e: (e["date"], e["time"]))
    # не более 4 событий в день, приоритет официальным
    by_day = defaultdict(list)
    for e in events:
        by_day[e["date"]].append(e)
    out = []
    for d in sorted(by_day):
        day_evs = sorted(by_day[d], key=lambda e: (e["tier"] or 2, e["source"]))
        out.extend(day_evs[:4])
    return out[:40]


# ---------------------------------------------------------------- 2. clusters
WORD_RE = re.compile(r"[a-zа-яё]{4,}", re.I)
GENERIC = set("""
котор сегодня вчера завтра сентябр октябр ульяновск ульяновской ульяновска области
регион регионa городе город новость новости сообщил сообщает стало известно время
также может будут будет около после через между очень более самый своем своих этот
этого этой эти тех тот эта всего все весь всей людям люди человек людей
""".split())


def _tokens(text):
    text = PROMO_TAIL.sub(" ", text)
    return [w.lower() for w in WORD_RE.findall(text) if w.lower() not in GENERIC]


def cluster_stories(items, now=None, window_h=72, min_size=3, threshold=0.30, top_n=6):
    """TF-IDF кластеризация свежих сюжетов методом лидера (без словаря тем)."""
    now = now or datetime.now(UTC4)
    cutoff = now - timedelta(hours=window_h)

    corpus = []
    for it in items:
        if it.get("dup_of"):
            continue
        dt = _local_dt(it.get("published"))
        if not dt or dt < cutoff:
            continue
        toks = _tokens(f"{it.get('title','')} {it.get('title','')} {(it.get('text') or '')[:400]}")
        if len(toks) >= 6:
            corpus.append((it, Counter(toks)))
    if len(corpus) < min_size:
        return []

    n_docs = len(corpus)
    df = Counter()
    for _, tf in corpus:
        df.update(tf.keys())
    idf = {w: math.log((n_docs + 1) / (c + 1)) + 1 for w, c in df.items() if 2 <= c <= n_docs * 0.5}

    def vec(tf):
        v = {w: (c / len(tf)) * idf[w] for w, c in tf.items() if w in idf}
        top = sorted(v.items(), key=lambda x: -x[1])[:40]
        norm = math.sqrt(sum(x * x for _, x in top)) or 1.0
        return {w: x / norm for w, x in top}

    vectors = [(it, vec(tf)) for it, tf in corpus]
    leaders = []  # (centroid_vec, members)
    for it, v in vectors:
        best, best_sim = None, 0.0
        for li, (cv, members) in enumerate(leaders):
            sim = sum(x * cv.get(w, 0.0) for w, x in v.items())
            if sim > best_sim:
                best, best_sim = li, sim
        if best is not None and best_sim >= threshold:
            cv, members = leaders[best]
            members.append((it, v))
            k = len(members)
            leaders[best] = ({w: cv.get(w, 0) * ((k - 1) / k) + v.get(w, 0) / k for w in set(cv) | set(v)}, members)
        else:
            leaders.append((dict(v), [(it, v)]))

    clusters = []
    for cv, members in leaders:
        if len(members) < min_size:
            continue
        agg = Counter()
        for _, v in members:
            for w, x in v.items():
                agg[w] += x
        terms = [w for w, _ in agg.most_common(5)][:3]
        covered = sum(1 for it, _ in members if it.get("topics"))
        coverage = covered / len(members)
        samples = sorted(members, key=lambda m: (m[0].get("views") or 0), reverse=True)[:3]
        clusters.append({
            "name": " · ".join(terms),
            "terms": terms,
            "size": len(members),
            "coverage": round(coverage, 2),
            "gap": coverage < 0.5,   # словарь тем почти не покрывает сюжет
            "samples": [{"title": it["title"][:110], "url": it.get("url") or "",
                         "source": it.get("source", ""), "views": it.get("views")}
                        for it, _ in samples],
        })
    clusters.sort(key=lambda c: -c["size"])
    # сначала «слепые зоны» словаря, затем крупнейшие
    clusters.sort(key=lambda c: (not c["gap"], -c["size"]))
    return clusters[:top_n]


# ---------------------------------------------------------------- 3. sentiment


def sentiment_of(text):
    """Лексиконная тональность текста: (score -1..+1, pos, neg)."""
    low = (text or "").lower()
    neg = sum(1 for m in NEG if m in low)
    pos = sum(1 for m in POS if m in low)
    if not neg and not pos:
        return 0.0, pos, neg
    return (pos - neg) / (pos + neg), pos, neg




def sentiment_score(items, days=14, now=None):
    """Лексиконная тональность: оценка дня, ряд 14 дней, разрез рубрик."""
    now = now or datetime.now(UTC4)
    today = now.date()

    score_text = sentiment_of

    day_scores = defaultdict(list)
    cat_scores = defaultdict(list)
    tp = tn = tneu = 0
    for it in items:
        if it.get("dup_of"):
            continue
        dt = _local_dt(it.get("published"))
        if not dt:
            continue
        sc, pos, neg = score_text(f"{it.get('title','')} {(it.get('text') or '')[:300]}")
        tp += 1 if sc > 0.15 else 0
        tn += 1 if sc < -0.15 else 0
        tneu += 1 if -0.15 <= sc <= 0.15 else 0
        if dt.date() == today:
            day_scores["today"].append(sc)
            cat_scores[it.get("category", "?")].append(sc)
        delta = (today - dt.date()).days
        if 0 <= delta < days:
            day_scores[(today - timedelta(days=delta)).isoformat()].append(sc)

    series = []
    for i in range(days - 1, -1, -1):
        d = (today - timedelta(days=i)).isoformat()
        vals = day_scores.get(d)
        series.append({"date": d, "score": round(sum(vals) / len(vals), 3) if vals else None})
    tv = day_scores.get("today") or []
    return {
        "method": "лексиконная оценка (±): ориентировочно, не замена экспертной",
        "today_score": round(sum(tv) / len(tv), 3) if tv else None,
        "today_items": len(tv),
        "today_pos": tp, "today_neg": tn, "today_neu": tneu,
        "series": series,
        "by_category": {c: round(sum(v) / len(v), 3) for c, v in sorted(cat_scores.items()) if len(v) >= 2},
    }


# ---------------------------------------------------------------- 4. credibility
CLICKBAIT_RE = re.compile(r"шок|вы не поверите|все ахнули|жесть|смотри до конца|это нельзя пропустить|внимание!|⚡⚡", re.I)
EMOJI_CB_RE = re.compile("[\U0001F300-\U0001FAFF\U00002600-\U000027BF]")


def is_clickbait(title):
    """Грубая эвристика: 2+ признака из 4 (маркеры, восклицания, КАПС, эмодзи-спам)."""
    score = 0
    if CLICKBAIT_RE.search(title):
        score += 1
    if title.count("!") >= 3:
        score += 1
    if len(re.findall(r"\b[А-ЯЁA-Z]{5,}\b", title)) >= 2:
        score += 1
    if len(EMOJI_CB_RE.findall(title)) >= 4:
        score += 1
    return score >= 2


def source_credibility(items):
    """Доля первичных материалов vs перепечатки + медиана просмотров TG + кликбейт-индекс."""
    stats = defaultdict(lambda: {"total": 0, "primary": 0, "dup": 0, "views": [], "tier": None, "type": "", "cb": 0})
    for it in items:
        src = _outlet(it)   # одна редакция = одна строка, даже если у неё RSS и TG
        st = stats[src]
        st["total"] += 1
        if is_clickbait(it.get("title", "")):
            st["cb"] += 1
        st["type"] = it.get("source_type", "?")
        if it.get("tier") is not None:
            st["tier"] = it["tier"]
        if it.get("dup_of"):
            st["dup"] += 1
        else:
            st["primary"] += 1
            if it.get("views"):
                st["views"].append(it["views"])
    out = []
    for src, st in stats.items():
        if st["total"] < 5:
            continue
        rate = st["dup"] / st["total"]
        views_sorted = sorted(st["views"])
        median = views_sorted[len(views_sorted) // 2] if views_sorted else None
        label = ("первоисточник" if rate < 0.25 else "перепечатчик" if rate > 0.6 else "смешанный")
        out.append({"source": src, "tier": st["tier"], "type": st["type"], "total": st["total"],
                    "primary": st["primary"], "dup": st["dup"], "repost_rate": round(rate, 2),
                    "views_median": median, "label": label,
                    "clickbait_rate": round(st["cb"] / st["total"], 2)})
    out.sort(key=lambda x: (-x["total"]))
    return out


# ---------------------------------------------------------------- 5. forecast
def forecast_topics(trends):
    """Прогноз на завтра по темам: наклон (least squares) + EMA, уровень уверенности."""
    out = []
    for tid, t in (trends or {}).get("topics", {}).items():
        series = [float(x) for x in t.get("series", [])]
        if len(series) < 7:
            continue
        pts = series[-7:]
        n = len(pts)
        xs = list(range(n))
        mx, my = sum(xs) / n, sum(pts) / n
        den = sum((x - mx) ** 2 for x in xs) or 1
        slope = sum((xs[i] - mx) * (pts[i] - my) for i in range(n)) / den
        resid = [pts[i] - (my + slope * (xs[i] - mx)) for i in range(n)]
        var = math.sqrt(sum(r * r for r in resid) / n)
        ema = pts[-1]
        for p in pts[-3:]:
            ema = 0.5 * p + 0.5 * ema
        expected = max(0.0, ema + slope)
        if abs(slope) >= 1.0 and var <= abs(slope):
            conf = "высокая"
        elif abs(slope) >= 0.4:
            conf = "средняя"
        else:
            conf = "низкая"
        direction = "рост" if slope >= 0.4 else ("спад" if slope <= -0.4 else "плато")
        out.append({"topic": tid, "name": t["name"], "expected": round(expected, 1),
                    "slope": round(slope, 2), "direction": direction, "confidence": conf})
    out.sort(key=lambda x: -abs(x["slope"]))
    return out




# ---------------------------------------------------------------- 6. инфопространство
REGION_MARK = re.compile(r"ульяновск|димитровград|симбирск|\b73\b|област|русских|болдакин|\bуаз|волг|баратаевк|свияг", re.I)


def build_infospace(items, trends, cfg):
    """Сквозное исследование регионального информационного пространства."""
    now = datetime.now(UTC4)
    today = now.date()
    week_ago = now - timedelta(days=7)
    live = [it for it in items if _local_dt(it.get("published"))]
    week = [it for it in live if _local_dt(it["published"]) >= week_ago]
    primaries = [it for it in week if not it.get("dup_of")]
    dups = [it for it in week if it.get("dup_of")]

    # --- структура потока
    by_type = Counter(it.get("source_type", "?") for it in week)
    by_tier = Counter(f"T{it['tier']}" if it.get("tier") else "СМИ/подборка" for it in week)

    # --- сеттеры повестки: кто первичен в кластерах перепечаток
    setters = Counter()
    cascades = []
    for it in primaries:
        if cascade_sources(it) >= 2:
            setters[_outlet(it)] += 1
            cascades.append({"size": it["cluster"], "sources": cascade_sources(it),
                             "title": it["title"][:100],
                             "source": _outlet(it),
                             "also": it.get("also_in", [])[:4], "url": it.get("url") or ""})
    cascades.sort(key=lambda c: (-c.get("sources", c["size"]), -c["size"]))

    # --- оригинальность по уровням
    orig_by_tier = {}
    for tier_key in ["T1", "T2", "T3", "СМИ/подборка"]:
        tot = sum(1 for it in week if (f"T{it['tier']}" if it.get("tier") else "СМИ/подборка") == tier_key)
        dup = sum(1 for it in week if it.get("dup_of") and (f"T{it['tier']}" if it.get("tier") else "СМИ/подборка") == tier_key)
        if tot:
            orig_by_tier[tier_key] = {"total": tot, "original": round((tot - dup) / tot, 2)}

    # --- тональность по уровням и рубрикам
    tone_by_tier = {}
    for tier_key in ["T1", "T2", "T3", "СМИ/подборка"]:
        sc = [sentiment_of(f"{it.get('title','')} {(it.get('text') or '')[:300]}")[0]
              for it in primaries
              if (f"T{it['tier']}" if it.get("tier") else "СМИ/подборка") == tier_key]
        if sc:
            tone_by_tier[tier_key] = round(sum(sc) / len(sc), 3)

    # --- федеральное эхо vs своя повестка
    fed = sum(1 for it in primaries if not REGION_MARK.search(f"{it.get('title','')} {(it.get('text') or '')[:300]}"))
    fed_share = round(fed / len(primaries), 2) if primaries else 0

    # --- покрытие муниципалитетов
    muni = {}
    for name, pat in (cfg.get("municipalities") or {}).items():
        rx = re.compile(pat, re.I)
        n = sum(1 for it in week if rx.search(f"{it.get('title','')} {(it.get('text') or '')[:400]}"))
        muni[name] = n
    silent = [m for m, n in muni.items() if n == 0]
    low = [m for m, n in muni.items() if 0 < n <= 2]

    # --- дневной объём повестки (все темы)
    days = (trends or {}).get("days", [])
    daily = [0] * len(days)
    if days:
        idx = {d: i for i, d in enumerate(days)}
        for it in week:
            d = _local_dt(it["published"]).astimezone(UTC4).date().isoformat() if _local_dt(it["published"]) else None
            if d in idx:
                daily[idx[d]] += 1

    # --- динамика тона по дням (14 дней)
    tone_series = []
    for i in range(13, -1, -1):
        d0 = today - timedelta(days=i)
        day_items = [it for it in primaries
                     if _local_dt(it["published"]).astimezone(UTC4).date() == d0]
        sc = [sentiment_of(f"{it.get('title','')} {(it.get('text') or '')[:300]}")[0] for it in day_items]
        tone_series.append({"date": d0.isoformat(),
                            "score": round(sum(sc) / len(sc), 3) if sc else None,
                            "n": len(day_items)})

    # --- неделя к неделе
    this_week = len([it for it in week if _local_dt(it["published"]) >= now - timedelta(days=7)])
    prev_week = len([it for it in live
                     if now - timedelta(days=14) <= _local_dt(it["published"]) < now - timedelta(days=7)])
    wow = {"this": this_week, "prev": prev_week,
           "delta": round((this_week - prev_week) / prev_week * 100) if prev_week else None}

    topic_wow = []
    for tid, t in (trends or {}).get("topics", {}).items():
        ser = t.get("series", [])
        if len(ser) >= 14:
            tw, pw = sum(ser[-7:]), sum(ser[-14:-7])
            if tw or pw:
                topic_wow.append({"name": t["name"], "this": tw, "prev": pw,
                                  "delta": round((tw - pw) / pw * 100) if pw else None})
    topic_wow.sort(key=lambda x: -(x["this"]))

    # --- муниципальная повестка: свой и областной голос (метрика из очереди, 12.09)
    muni_src = set(cfg.get("municipal_sources") or [])
    # ключи изданий муниципальных источников (в config — имена каналов/лент)
    muni_src_keys = {_outlets.norm(_outlets.resolve_raw(x)) for x in muni_src}
    muni_agenda = []
    own_total = 0
    ment_total = 0
    for name, pat in (cfg.get("municipalities") or {}).items():
        rx = re.compile(pat, re.I)
        t_n = own_n = 0
        tones = []
        srcs = set()
        for it in week:
            title = it.get("title", "") or ""
            body = (it.get("text") or "")[:400]
            in_title = bool(rx.search(title))
            in_body = (not in_title) and bool(rx.search(body))
            if not (in_title or in_body):
                continue
            t_n += 1
            if in_title:
                ment_total += 1
            src = _outlet(it)
            srcs.add(src)
            if _outlet_key(it) in muni_src_keys:
                own_n += 1
                own_total += 1
            sc = sentiment_of(f"{title} {body[:250]}")[0]
            tones.append(sc)
        if t_n:
            muni_agenda.append({
                "name": name, "mentions": t_n,
                "subject": sum(1 for it in week if rx.search(it.get("title", "") or "")),
                "tone": round(sum(tones) / len(tones), 2) if tones else None,
                "sources": len(srcs), "own": own_n,
            })
    muni_agenda.sort(key=lambda x: -x["mentions"])
    muni_summary = {
        "own_share": round(own_total / ment_total * 100) if ment_total else 0,
        "voiced_own": [m["name"] for m in muni_agenda if m["own"] > 0],
        "silent_own": [m["name"] for m in muni_agenda if m["own"] == 0][:10],
        "muni_sources": sorted(muni_src),
    }

    # --- выводы
    concl = []
    if wow.get("delta") is not None and wow.get("prev", 0) >= 100:
        concl.append(f"Объём инфопотока неделя-к-неделе: {wow['this']} против {wow['prev']} ({wow['delta']:+d}%) — "
                     + ("интенсивность растёт." if wow["delta"] > 10 else
                        ("интенсивность падает." if wow["delta"] < -10 else "интенсивность стабильна.")))
    if topic_wow:
        risers = [t for t in topic_wow if (t["delta"] or 0) > 50][:3]
        if risers:
            concl.append("Резко усилились темы: " + ", ".join(f"«{t['name']}» ({t['delta']:+d}%)" for t in risers) + ".")
    if primaries:
        orig_share = round(len(primaries) / len(week), 2) if week else 0
        concl.append(f"За 7 дней поток составил {len(week)} сообщений, из них оригинальных (не перепечаток) — {int(orig_share*100)}%.")
    if setters:
        top_set = setters.most_common(3)
        concl.append("Повестку задают: " + ", ".join(f"{esc_(s_)} (первичен в {n} каскадах)" for s_, n in top_set) + ".")
    if cascades:
        c0 = cascades[0]
        concl.append(f"Крупнейший каскад недели — «{c0['title'][:70]}» (×{c0['size']} источников).")
    if tone_by_tier:
        t1 = tone_by_tier.get("T1"); t3 = tone_by_tier.get("T3")
        if t1 is not None and t3 is not None and abs(t1 - t3) > 0.1:
            concl.append(f"Тон различается по уровням: официальные каналы {t1:+.2f}, авторские/анонимные {t3:+.2f} — "
                         + ("официальная картина позитивнее." if t1 > t3 else "официальная картина тревожнее."))
    concl.append(f"Федеральное эхо: {int(fed_share*100)}% оригинальных сообщений не про регион напрямую.")
    if silent:
        concl.append(f"Зоны информационного молчания (0 упоминаний за 7 дней): {', '.join(silent[:8])}.")
    if low:
        concl.append(f"На грани видимости (1–2 упоминания): {', '.join(low[:8])}.")

    # --- отслеживаемые метрики инфопространства
    src_counter_all = Counter(_outlet(it) for it in week)
    top3 = sum(n for _, n in src_counter_all.most_common(3))
    concentration = round(top3 / len(week) * 100) if week else 0
    casc_sizes = [cascade_sources(it) for it in primaries if cascade_sources(it) >= 2]
    avg_cascade = round(sum(casc_sizes) / len(casc_sizes), 1) if casc_sizes else 0
    muni_total = len(cfg.get("municipalities") or {})
    muni_cov = round((muni_total - len(silent)) / muni_total * 100) if muni_total else 0
    scores = [t["score"] for t in tone_series if t["score"] is not None]
    if len(scores) > 1:
        mean = sum(scores) / len(scores)
        tone_vol = round((sum((x - mean) ** 2 for x in scores) / len(scores)) ** 0.5, 2)
    else:
        tone_vol = 0
    sec_n = sum(1 for it in week if it.get("category") == "security")
    # --- нацпроекты и госпрограммы в повестке (метрика из очереди, подключена 12.09)
    NP_RE = re.compile(r"нацпроект|национальн\w+\s+проект", re.I)
    NP_RULES = [
        ("Семья", r"семья"),
        ("Инфраструктура для жизни", r"инфраструктур"),
        ("Образование", r"образован"),
        ("Здравоохранение", r"здравоохран"),
        ("Экономика и производительность", r"экономик|производительн"),
        ("Экологическое благополучие", r"эколог"),
        ("Молодёжь России", r"молодеж"),
        ("Туризм", r"туризм"),
    ]
    np_items = [it for it in week if NP_RE.search(f"{it.get('title','')} {(it.get('text') or '')[:400]}")]
    np_by = Counter()
    for it in np_items:
        blob = f"{it.get('title','')} {(it.get('text') or '')[:400]}".lower()
        hit = [n for n, pat in NP_RULES if re.search(pat, blob)]
        if hit:
            for n in hit:
                np_by[n] += 1
        else:
            np_by["(проект не указан)"] += 1
    np_sc = [sentiment_of(f"{it.get('title','')} {(it.get('text') or '')[:250]}")[0] for it in np_items]
    natproj = {
        "total": len(np_items),
        "share": round(len(np_items) / len(week) * 100, 1) if week else 0,
        "by_project": np_by.most_common(8),
        "tone": round(sum(np_sc) / len(np_sc), 2) if np_sc else None,
    }

    metrics = {
        "original_share": round(len(primaries) / len(week) * 100) if week else 0,
        "concentration_top3": concentration,
        "avg_cascade": avg_cascade,
        "muni_coverage": muni_cov,
        "tone_volatility": tone_vol,
        "alert_share": round(sec_n / len(week) * 100) if week else 0,
    }

    return {
        "generated_local": now.strftime("%d.%m.%Y %H:%M"),
        "week_items": len(week), "week_primaries": len(primaries), "week_dups": len(dups),
        "metrics": metrics, "natproj": natproj,
        "muni_agenda": muni_agenda[:12], "muni_summary": muni_summary,
        "by_type": dict(by_type), "by_tier": dict(by_tier),
        "orig_by_tier": orig_by_tier,
        "setters": setters.most_common(8),
        "cascades": cascades[:6],
        "tone_by_tier": tone_by_tier,
        "federal_share": fed_share,
        "municipal": dict(sorted(muni.items(), key=lambda x: -x[1])),
        "silent": silent, "low": low,
        "daily": daily, "days": days,
        "tone_series": tone_series,
        "wow": wow, "topic_wow": topic_wow[:8],
        "conclusions": concl,
    }



# ─────────────────────────────────────────────────────────────────────
# Волна 1 предложения v0.9 (infospace-plan.html): метрики на текущих данных
# ─────────────────────────────────────────────────────────────────────
EMOJI_X_RE = re.compile("[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF\u2B50\u2705\u274C\u2764]")

LABOR_GROUPS = {
    "рабочие и инженеры": r"рабоч\w+|инженер\w+|завод\w+|\bуаз\b|авиастар\w*|моторн\w+ завод|станочник\w*|слесар\w*|токарь|сварщик\w*|монтажник\w*|строител\w+",
    "учителя": r"учител\w+|педагог\w+|преподавател\w+",
    "медики": r"врач\w*|медик\w+|медсестр\w+|фельдшер\w*|санитар\w+|хирург\w*",
    "водители и транспортники": r"водител\w+|шофёр|шофер|дальнобойщик\w*|кондуктор\w*|машинист\w+",
    "селяне и фермеры": r"селян\w+|крестьян\w+|фермер\w+|колхоз\w+|аграрий\w*",
    "студенты": r"студент\w+|курсант\w+|аспирант\w+",
}
SPEECH_X_RE = re.compile(
    r"рассказал\w*|сообщил\w*|говорит|говорят|пояснил\w*|заявил\w*|добавил\w*|поделился|"
    r"отметил\w*|написал\w*|прокомментировал\w*|жалуется|жалуются|обратился|обращаются|"
    r"просит|просят|требует|требуют|возмущается|возмущены|объяснил\w*|уточнил\w*", re.I)


BUROKRAT_MARKERS = [
    "оптимизац", "благоустройств", "временные неудобства", "в рабочем порядке",
    "на контроле", "держим на контроле", "модернизаци", "капитальный ремонт",
    "капремонт", "отчитал", "рабочая поездка", "рабочее совещание", "плановые работы",
    "нацпроект", "национальный проект", "региональный проект", "муниципальный контракт",
    "субсиди", "грант", "в приоритете", "по поручению", "инвестицион", "точка роста",
    "комфортная городская среда", "введение в эксплуатацию", "в штатном режиме",
]


# ─────────────────────────────────────────────────────────────────────
# Латентность освещения (ось «время» плана v0.9): время события из текста.
# Паспорт метрики: «Часы от события до первой публикации: насколько поле
# догоняет реальность и по каким темам догоняет медленнее».
# ─────────────────────────────────────────────────────────────────────
LAT_REL_DAYS = {"сегодня": 0, "вчера": 1, "накануне": 1, "позавчера": 2}
LAT_WEEKDAY = {"понедельник": 0, "вторник": 1, "среду": 2, "четверг": 3,
               "пятницу": 4, "субботу": 5, "воскресенье": 6}
LAT_TOD_HOURS = {"утром": 8, "днём": 14, "днем": 14, "вечером": 20, "ночью": 2}
LAT_DAY_X = re.compile(
    rf"(?<![\d.])(\d{{1,2}})\s*(?:({MONTH_STEM})|\.(\d{{1,2}})(?:\.(20\d{{2}}))?(?![\d.]))", re.I)
LAT_REL_X = re.compile(r"\b(сегодня|вчера|позавчера|накануне)\b", re.I)
LAT_MIND_X = re.compile(r"\b(?:минувш\w+|прошедш\w+)\s+(ночью|вечером|днём|днем|утром)\b", re.I)
LAT_WD_X = re.compile(r"\bв(?:о)?\s+(понедельник|вторник|среду|четверг|пятницу|субботу|воскресенье)\b", re.I)
LAT_TOD_X = re.compile(r"\b(утром|днём|днем|вечером|ночью|в\s*(\d{1,2})[:.](\d{2}))\b", re.I)
# охраны: анонс будущего события; диапазон/дедлайн перед датой
LAT_FUTURE_X = re.compile(
    r"пройд[её]т|пройдут|состо[ия]|ожида[ею]|запланир|начн[её]т|начнут|откро[ею]|откроют|"
    r"прибуд|приед|старту|намечен|будет|будут|готовит|завершит|продлит|планиру|объявят|вручат", re.I)
LAT_PREP_X = re.compile(r"(?:до|с|к|по|после|через|за|спустя|на|около)\s+$", re.I)
# пост-анонс («завлекаловка») не измеряется: событие ещё не случилось
LAT_ANNOUNCE_X = re.compile(
    r"приглаша\w+|жд[её]м (?:вас|тебя|всех)|приходи\w*|придите|не пропусти\w*|успей\w*|"
    r"розыгрыш\w*|вход свободный|регистрац\w+|ты погрузишься|погружайся|"
    r"могут (?:выбрать|проголосовать|принять участие|подать|записаться)", re.I)
# день недели («в среду») неоднозначен — прошлая или следующая? принимаем только
# при подтверждении глаголом прошедшего времени в окне вокруг маркера
LAT_PAST_X = re.compile(
    r"произош\w+|случило\w+|прош[её]л|прошла|прошли|состоял\w+|открыли|открылс\w+|запустили|стартовал\w+|"
    r"сбил[аи]?\b|задержан\w*|задержал\w*|поврежд\w+|возник\w*|начал\w*|обрушил\w+|загорел\w+|упал\w*|"
    r"приб\w+|приехал\w*|выехал\w*|выявил\w+|зафиксирован\w*|обнаруже\w+|введ[её]н\w*|отключ\w+|включ\w+|"
    r"подписал\w*|вручил\w*|наградил\w*|завершил\w+|провели|пров[её]л|поступил\w+|скончал\w+|погиб\w*", re.I)


def extract_event_time(text, pub):
    """Время события из текста (datetime в UTC4) или None.

    Маркеры: явные даты («14 сентября», «14.09», «14.09.2026»), относительные
    («сегодня/вчера/позавчера/накануне»), день недели («в среду» — ближайший
    прошедший, только при глаголе прошлого времени рядом); уточнение времени
    суток («вечером»≈20, «в 18:30» — точно) в пределах 40 знаков после маркера.
    Дата без времени — полдень (конвенция). Охраны: будущее событие (анонс),
    диапазон («до 20 сентября»), явный год не года публикации (историческая
    справка), посты-анонсы («приглашаем/ждём вас/розыгрыш…») целиком.
    Берётся первый по тексту валидный маркер — лид-предложение обычно о событии.

    Возвращает (datetime, kind) или None; kind: "time" — точное «в 18:30»,
    "tod" — время суток, "day" — только дата. «day» + сегодняшняя дата =
    «освещено в тот же день» — агрегатор метрики считает такие отдельно."""
    if not pub or not text:
        return None
    blob = text[:900]
    if LAT_ANNOUNCE_X.search(blob):          # анонс-«завлекаловка»: события ещё не было
        return None

    def _guarded(m):
        pre = blob[max(0, m.start() - 14):m.start()]
        if LAT_PREP_X.search(pre):
            return True
        ctx = blob[max(0, m.start() - 90):m.end() + 130]
        return bool(LAT_FUTURE_X.search(ctx))

    def _tod_after(pos):
        m = LAT_TOD_X.search(blob[pos:pos + 40])
        if not m:
            return None                       # время не уточнено — решение за вызывающим
        if m.group(2):
            h = int(m.group(2))
            return (h if 0 <= h <= 23 else 12), int(m.group(3)), "time"
        return LAT_TOD_HOURS.get(m.group(1).lower(), 12), 0, "tod"

    def _mk(d, tod):
        """(datetime, точность): time — «в 18:30», tod — «вечером»≈20, day — только дата.
        Дата без времени — полдень (конвенция); точность day у сегодняшней даты означает
        «освещено в тот же день» — внутридневное запаздывание текст не восстанавливает."""
        if tod:
            return datetime(d.year, d.month, d.day, tod[0], tod[1], tzinfo=UTC4), tod[2]
        return datetime(d.year, d.month, d.day, 12, 0, tzinfo=UTC4), "day"

    def _add(pos, mk):
        cands.append((pos, mk[0], mk[1]))

    cands = []
    for m in LAT_DAY_X.finditer(blob):
        if _guarded(m):
            continue
        day = int(m.group(1))
        if m.group(2):                       # «14 сентября»
            mon = MONTHS.get(m.group(2).lower())
            year = pub.year
            ym = re.match(r"\w*\s*((?:19|20)\d{2})", blob[m.end():m.end() + 14])
            if ym and int(ym.group(1)) != pub.year:
                continue                     # историческая справка с иным годом
        else:                                # «14.09[.2026]»
            mon = int(m.group(3)) if m.group(3) else None
            if not mon or mon > 12 or day > 31:
                continue
            year = int(m.group(4)) if m.group(4) else pub.year
            if year != pub.year:             # историческая справка/далёкий анонс
                continue
        if not mon or not (1 <= day <= 31):
            continue
        try:
            d = datetime(year, mon, day, tzinfo=UTC4).date()
        except ValueError:
            continue
        if d > pub.date() + timedelta(days=1):   # будущая дата — анонс
            continue
        _add(m.start(), _mk(d, _tod_after(m.end())))
    for m in LAT_REL_X.finditer(blob):
        if _guarded(m):
            continue
        d = pub.date() - timedelta(days=LAT_REL_DAYS[m.group(1).lower()])
        _add(m.start(), _mk(d, _tod_after(m.end())))
    for m in LAT_MIND_X.finditer(blob):      # «минувшей ночью» ≈ «вчера ночью»
        if _guarded(m):
            continue
        d = pub.date() - timedelta(days=1)
        _add(m.start(), _mk(d, (LAT_TOD_HOURS.get(m.group(1).lower(), 12), 0, "tod")))
    for m in LAT_WD_X.finditer(blob):
        if _guarded(m):
            continue
        wctx = blob[max(0, m.start() - 130):m.end() + 170]
        if not LAT_PAST_X.search(wctx):      # «в среду» без глагола прошлого — пропуск
            continue
        back = (pub.weekday() - LAT_WEEKDAY[m.group(1).lower()]) % 7
        d = pub.date() - timedelta(days=back)
        _add(m.start(), _mk(d, _tod_after(m.end())))
    if not cands:
        return None
    cands.sort(key=lambda x: x[0])
    return cands[0][1], cands[0][2]


def build_infospace_ext(items, trends, cfg):
    """Волна 1 предложения v0.9: матрица территория×рубрика, ритм суток,
    динамика каскадов (полка жизни и скорость), индекс присутствия труда (TLI),
    эмодзи-профиль по уровням, доля бюджетного голоса. Только store.jsonl."""
    now = datetime.now(UTC4)
    week_ago = now - timedelta(days=7)
    live = [it for it in items if _local_dt(it.get("published"))]
    week = [it for it in live if _local_dt(it["published"]) >= week_ago]
    primaries = [it for it in week if not it.get("dup_of")]
    out = {"generated_local": now.strftime("%d.%m.%Y %H:%M"), "week_items": len(week)}
    if not week:
        return out

    # 1) матрица территория × рубрика (топ-10 территорий по объёму)
    cats = cfg.get("categories") or []
    rows = []
    for name, pat in (cfg.get("municipalities") or {}).items():
        rx = re.compile(pat, re.I)
        hits = {c["id"]: 0 for c in cats}
        tot = 0
        for it in week:
            if rx.search(f"{it.get('title', '')} {(it.get('text') or '')[:400]}"):
                tot += 1
                cid = it.get("category") or "society"
                if cid in hits:
                    hits[cid] += 1
        rows.append({"muni": name, "total": tot, "cats": hits})
    rows.sort(key=lambda r: -r["total"])
    out["matrix"] = {"cats": [{"id": c["id"], "name": c.get("name", c["id"])} for c in cats],
                     "rows": rows[:10]}

    # 2) ритм суток: будни/выходные по часам + ночная доля
    wd = [0] * 24
    we = [0] * 24
    for it in week:
        dt = _local_dt(it["published"])
        (we if dt.weekday() >= 5 else wd)[dt.hour] += 1
    tot_w = sum(wd) + sum(we)
    out["rhythm"] = {"weekday": wd, "weekend": we,
                     "night_share": round((sum(wd[:6]) + sum(we[:6])) / tot_w, 3) if tot_w else None,
                     "weekend_share": round(sum(we) / tot_w, 3) if tot_w else None}

    # 3) динамика каскадов: полка жизни сюжета и скорость подхватов
    by_id = {it.get("id"): it for it in week}
    spans = []
    for it in primaries:
        cl = cascade_sources(it)
        if cl < 2:
            continue
        times = []
        t0 = _local_dt(it.get("published"))
        if t0:
            times.append(t0)
        for d in week:
            if d.get("dup_of") == it.get("id"):
                td = _local_dt(d.get("published"))
                if td:
                    times.append(td)
        if len(times) >= 2:
            span_h = (max(times) - min(times)).total_seconds() / 3600.0
            spans.append({"title": (it.get("title") or "")[:90], "size": cl,
                          "span_h": round(span_h, 1),
                          "speed": round(cl / span_h, 1) if span_h > 0.05 else None,
                          "url": it.get("url") or ""})
    med = None
    if spans:
        s = sorted(x["span_h"] for x in spans)
        med = round(s[len(s) // 2], 1)
    spans.sort(key=lambda x: -(x["speed"] or 0))
    out["cascade_time"] = {"n": len(spans), "median_span_h": med, "fastest": spans[:5]}

    # 4) TLI — индекс присутствия труда (эвристика: маркер группы + глагол речи рядом)
    groups = {}
    tot_m = tot_s = 0
    for gname, gpat in LABOR_GROUPS.items():
        grx = re.compile(gpat, re.I)
        mentioned = speaks = 0
        for it in week:
            blob = f"{it.get('title', '')} {(it.get('text') or '')[:500]}"
            m = grx.search(blob)
            if not m:
                continue
            mentioned += 1
            ctx = blob[max(0, m.start() - 160):m.end() + 200]
            if SPEECH_X_RE.search(ctx):
                speaks += 1
        groups[gname] = {"mentioned": mentioned, "speaks": speaks,
                         "share": round(speaks / mentioned, 3) if mentioned else None}
        tot_m += mentioned
        tot_s += speaks
    tli = round(tot_s / tot_m, 3) if tot_m else None
    verdict = ("—" if tli is None else
               "труд невидим" if tli < 0.10 else
               "труд упоминаем" if tli < 0.30 else "труд говорит")
    out["tli"] = {"groups": groups, "mentioned": tot_m, "speaks": tot_s,
                  "index": tli, "verdict": verdict}

    # 5) эмодзи-профиль по уровням источников
    emo = {}
    for key in ("T1", "T2", "T3", "СМИ/подборка"):
        sel = [it for it in week
               if (f"T{it['tier']}" if it.get("tier") else "СМИ/подборка") == key]
        if not sel:
            continue
        e = sum(1 for it in sel
                if EMOJI_X_RE.search((it.get("title") or "") + (it.get("text") or "")[:300]))
        emo[key] = {"total": len(sel), "with_emoji": round(e / len(sel), 3)}
    out["emoji"] = emo

    # 6) доля бюджетного голоса: T1 в потоке, T1 среди первичных, эхо T1 в перепечатках
    t1_flow = sum(1 for it in week if it.get("tier") == 1)
    t1_prim = sum(1 for it in primaries if it.get("tier") == 1)
    dups_n = echo_n = 0
    for it in week:
        if it.get("dup_of"):
            dups_n += 1
            pr = by_id.get(it["dup_of"])
            if pr is not None and pr.get("tier") == 1:
                echo_n += 1
    out["budget_voice"] = {
        "t1_share_flow": round(t1_flow / len(week), 3),
        "t1_share_primaries": round(t1_prim / len(primaries), 3) if primaries else None,
        "echo_of_t1": round(echo_n / dups_n, 3) if dups_n else None,
        "echo_n": echo_n, "dups_n": dups_n}

    # 7) словарь власти: канцелярит и эвфемизмы по уровням источников
    tier_keys = ("T1", "T2", "T3", "СМИ/подборка")
    def _tier_key(it):
        return f"T{it['tier']}" if it.get("tier") else "СМИ/подборка"
    buro = {k: {"total": 0, "with_marker": 0} for k in tier_keys}
    marker_hits = Counter()
    for it in week:
        blob = (it.get("title") or "") + " " + (it.get("text") or "")[:400]
        low = blob.lower()
        k = _tier_key(it)
        buro[k]["total"] += 1
        found = [m for m in BUROKRAT_MARKERS if m in low]
        if found:
            buro[k]["with_marker"] += 1
            marker_hits[found[0]] += 1
    for k in list(buro):
        t = buro[k]["total"]
        buro[k]["share"] = round(buro[k]["with_marker"] / t, 3) if t else None
        if not t:
            del buro[k]
    out["bureaucratese"] = {"by_tier": buro,
                            "top_markers": marker_hits.most_common(6)}

    # 8) индекс тревожности: дневная доля security/uav + вердикт
    anx_series = []
    for i in range(6, -1, -1):
        d0 = (now - timedelta(days=i)).astimezone(UTC4).date()
        day_items = [it for it in week if _local_dt(it["published"]).astimezone(UTC4).date() == d0]
        sec = sum(1 for it in day_items
                  if it.get("category") == "security" or "uav" in (it.get("topics") or []))
        anx_series.append({"date": d0.isoformat(),
                           "share": round(sec / len(day_items), 3) if day_items else None,
                           "n": len(day_items), "sec": sec})
    vals = [x["share"] for x in anx_series if x["share"] is not None]
    anx_avg = round(sum(vals) / len(vals), 3) if vals else None
    out["anxiety"] = {"series": anx_series, "avg": anx_avg,
                      "verdict": ("—" if anx_avg is None else
                                  "спокойный фон" if anx_avg < 0.08 else
                                  "повышенный фон" if anx_avg < 0.20 else "высокая тревожность")}

    # 9) ЖКХ и тарифы: доля и тон
    zh = [it for it in week if "zhkh" in (it.get("topics") or [])]
    zh_prim = [it for it in zh if not it.get("dup_of")]
    zh_tones = [sentiment_of(f"{it.get('title','')} {(it.get('text') or '')[:300]}")[0] for it in zh_prim]
    zh_src = Counter(_outlet(it) for it in zh_prim)
    out["zhkh"] = {"n": len(zh), "share": round(len(zh) / len(week), 3),
                   "tone": round(sum(zh_tones) / len(zh_tones), 3) if zh_tones else None,
                   "top_sources": zh_src.most_common(3)}

    # 10) федеральное эхо в разрезе источников (топ-8 по объёму первичных)
    src_prim = Counter()
    src_fed = Counter()
    for it in primaries:
        s = _outlet(it)
        src_prim[s] += 1
        if not REGION_MARK.search(f"{it.get('title','')} {(it.get('text') or '')[:300]}"):
            src_fed[s] += 1
    fed_by_src = []
    for s, n in src_prim.most_common(8):
        fed_by_src.append({"source": str(s), "n": n,
                           "fed_share": round(src_fed.get(s, 0) / n, 2)})
    out["federal_by_source"] = fed_by_src

    # 11) индекс присутствия села: доля районов в повестке против доли в населении
    pops = cfg.get("muni_population") or {}
    meta_p = pops.get("_meta") or {}
    oblast_total = meta_p.get("oblast_total") or 0
    city_keys = {"Димитровград", "Новоульяновск"}
    districts = {k: v for k, v in pops.items() if not k.startswith("_") and k not in city_keys}
    rural = {}
    if districts and oblast_total:
        rx_map = {name: re.compile((cfg.get("municipalities") or {}).get(name, ""), re.I)
                  for name in districts if (cfg.get("municipalities") or {}).get(name)}
        pop_sum = sum(v for k, v in districts.items() if k in rx_map)
        hits = 0
        per = Counter()
        for it in week:
            blob = f"{it.get('title','')} {(it.get('text') or '')[:400]}"
            for name, rx in rx_map.items():
                if rx.search(blob):
                    hits += 1
                    per[name] += 1
                    break
        agenda_share = round(hits / len(week), 3)
        pop_share = round(pop_sum / oblast_total, 3)
        idx = round(agenda_share / pop_share, 2) if pop_share else None
        rural = {"agenda_share": agenda_share, "pop_share": pop_share, "index": idx,
                 "hits": hits, "pop_sum": pop_sum,
                 "rural_pop_share": round((meta_p.get("oblast_rural") or 0) / oblast_total, 3),
                 "verdict": ("—" if idx is None else
                             "паритет" if idx >= 0.8 else
                             "недопредставлены" if idx >= 0.4 else "символическое исключение"),
                 "top": per.most_common(5),
                 "source": meta_p.get("source", "")}
    out["rural_index"] = rural

    # 12) латентность освещения: часы от события до первой публикации (ось «время»)
    lat_hours = []
    lat_topics = defaultdict(list)
    lat_tiers = defaultdict(list)
    lat_samples = []
    sameday_n = 0
    for it in primaries:
        pub = _local_dt(it.get("published"))
        if not pub:
            continue
        got = extract_event_time((it.get("title") or "") + ". " + (it.get("text") or ""), pub)
        if got is None:
            continue
        ev, kind = got
        if kind == "day" and ev.date() == pub.date():
            sameday_n += 1             # освещено в тот же день: <24 ч, точное значение текст не даёт
            continue
        raw_h = (pub - ev).total_seconds() / 3600.0
        if raw_h < -2 or raw_h > 336:  # артефакты разбора и исторические справки — не латентность
            continue
        h = max(0.0, raw_h)            # отрицательные — артефакт допущения «полдень/время суток»
        lat_hours.append(h)
        lat_topics[it.get("category") or "?"].append(h)
        lat_tiers[f"T{it['tier']}" if it.get("tier") else "СМИ/подборка"].append(h)
        lat_samples.append({"h": round(h, 1), "title": (it.get("title") or "")[:90],
                            "url": it.get("url") or "#"})

    def _med(xs):
        xs = sorted(xs)
        return round(xs[len(xs) // 2], 1) if xs else None

    latency = {}
    if lat_hours or sameday_n:
        meas_n = len(lat_hours)
        tot_n = meas_n + sameday_n
        cat_names = {c.get("id"): c.get("name") or c.get("id")
                     for c in (cfg.get("categories") or [])}
        topics = [(cat_names.get(k, k), _med(v), len(v))
                  for k, v in lat_topics.items() if len(v) >= 5]
        topics.sort(key=lambda x: -(x[1] or 0))
        buckets = {
            "<6ч": round(sum(1 for h in lat_hours if h < 6) / meas_n, 3) if meas_n else 0,
            "6-24ч": round(sum(1 for h in lat_hours if 6 <= h < 24) / meas_n, 3) if meas_n else 0,
            "24-48ч": round(sum(1 for h in lat_hours if 24 <= h < 48) / meas_n, 3) if meas_n else 0,
            ">48ч": round(sum(1 for h in lat_hours if h >= 48) / meas_n, 3) if meas_n else 0,
        }
        latency = {
            "n": meas_n,
            "sameday_n": sameday_n,
            "sameday_share": round(sameday_n / tot_n, 3) if tot_n else None,
            "coverage": round(tot_n / len(primaries), 3) if primaries else None,
            "median_h": _med(lat_hours),
            "buckets": buckets,
            "slow_topics": topics[:5],
            "fast_topics": topics[-3:][::-1] if len(topics) > 5 else [],
            "by_tier": {k: {"median_h": _med(v), "n": len(v)}
                        for k, v in sorted(lat_tiers.items())},
            "slowest": sorted(lat_samples, key=lambda x: -x["h"])[:3],
        }
    out["latency"] = latency

    return out



# ─────────────────────────────────────────────────────────────────────
# Волна 2 (предложение v0.9): кто пишет и кто читает — на базе
# sources_registry.json и уже собираемых просмотров
# ─────────────────────────────────────────────────────────────────────
QUOTE_X_RE = re.compile(r"«[^»]{15,300}»")
OFFICIAL_X_RE = re.compile(
    r"губернатор|министр|глава\b|мэр|депутат|администрац|пресс-служб|правительств|"
    r"руководител|директор|начальник|сенатор|мэрия|министерств", re.I)
CITIZEN_X_RE = re.compile(
    r"жител|горожан|селян|рабоч\w+|пенсионер|учител|врач|медик|студент|водитель|"
    r"многодетн|очевидц|местн\w+ жител", re.I)
# Рекламная нагрузка — калибровка по реальной базе 15.09.2026 (вместо грубого PROMO_AD_X_RE).
# Два независимых класса:
# 1) Коммерческая реклама: (а) легальная маркировка по 38-ФЗ — erid, «Реклама.» + ИНН,
#    «на правах рекламы», «рекламная интеграция»; (б) офертные рамки — промокод с кодом,
#    «успей купить по … цене», цена «от N ₽», «скидкой N%», рассрочка в ₽, рекламные
#    сокращатели ссылок (clck.ru/bit.ly/vk.cc). Сигнал «посев» исключён: сталкивается
#    с сельскохозяйственной лексикой («совка уничтожает посевы»).
# 2) Кросс-промо: приписки канала, уводящие в MAX/на второй канал («плохо грузит? читай в MAX»,
#    «мы в МАКС», «наш канал в MAX»). Коллектор срезает такие хвосты из текста — сигнал
#    сохраняется флагом xtail на записи (collector.normalize_item).
# Известные границы: сторителл-нативка без маркировки ловится частично (сигнал «в канале «…»»
# с оговоркой на цитирование) — оценка рекламной нагрузки является нижней границей.
AD_MARK_X_RE = re.compile(
    r"erid[:=\s]|на правах рекламы|рекламн\w+ интеграц|реклама\s*[.·]|инн[:\s]*\d{6,}", re.I)
AD_OFFER_X_RE = re.compile(
    r"по промокод\w+|промокод\w*\s*[—–:\-]?\s*[A-Za-z0-9]{4,}|"
    r"clck\.ru|bit\.ly|vk\.cc/|"
    r"успей\w*\s+(?:купить|забрать|заказать|оформить|подключить|перейти)|"
    r"по (?:специальной|старой|выгодной|минимальной|низкой) цене|по минимальн\w+ цена\w+|"
    r"всего (?:за|с|от)\s*\d+[\d\s.,]*(?:₽|руб)|от\s*\d[\d\s]{4,}(?:₽|руб)|"
    r"рассрочк\w*\s*\d[\d\s]*(?:₽|руб)|скидкой\s*\d+\s*%|скидк\w+ по промо", re.I)
AD_CROSSPROMO_X_RE = re.compile(
    r"плохо грузит|max\.ru/\w+|"
    r"(?:читай|читайте|подпишись|подписывайся|мы)\s*(?:нас\s*)?(?:теперь\s*)?в\s*(?:max|макс)\b|"
    r"наш канал в\s*(?:max|макс)", re.I)
# Нативный «посев»: перенаправление «в канале «Brand»» без журналистского цитирования.
AD_CHANNEL_X_RE = re.compile(r"в\s+(?:телеграм[- ]?)?канале\s*«?\s*([A-Za-z@А-Яа-яЁё][\w \-]{1,40})")
AD_CITED_X_RE = re.compile(
    r"жалу\w+|сообщ\w+|написал\w*|рассказал\w*|появилось|опубликовал\w*|заявил\w*|"
    r"говорят|обсужда\w+|читаем|увидели|узнали|по данным|опрос|объявил\w+|уточнил\w+", re.I)


def ad_channel_promo(blob):
    """Нативная реклама-перенаправление: «она берёт … в канале «BaggyBags»».
    Не считается, если перед упоминанием канала — глагол цитирования («жалуются в канале …»)."""
    for m in AD_CHANNEL_X_RE.finditer(blob):
        ctx = blob[max(0, m.start() - 60):m.start()]
        if not AD_CITED_X_RE.search(ctx):
            return True
    return False
SOCIAL_GROUPS_EXT = dict(LABOR_GROUPS)
SOCIAL_GROUPS_EXT.update({
    "пенсионеры": r"пенсионер\w+",
    "мигранты": r"мигрант\w+|переселен\w+",
    "люди с инвалидностью": r"инвалид\w+|ограниченн\w+ возможност\w+",
})


def load_registry(base=None):
    path = os.path.join(base or BASE, "sources_registry.json")
    reg = {}
    try:
        data = json.load(open(path, encoding="utf-8"))
        for e in data.get("sources", []):
            reg[e.get("id")] = e
    except Exception:
        pass
    return reg


def _gini(values):
    xs = sorted(v for v in values if v and v > 0)
    n = len(xs)
    if n < 2:
        return None
    total = sum(xs)
    if not total:
        return None
    cum = sum((2 * i - n - 1) * x for i, x in enumerate(xs, 1))
    return round(cum / (n * total), 3)


def build_infospace_w2(items, trends, cfg, registry=None):
    """Волна 2: тип производителя («кто пишет»), концентрация внимания (Gini
    просмотров), прямая речь чиновников и жителей, рекламная нагрузка,
    немые социальные группы. Данные: store.jsonl + sources_registry.json."""
    now = datetime.now(UTC4)
    week_ago = now - timedelta(days=7)
    live = [it for it in items if _local_dt(it.get("published"))]
    week = [it for it in live if _local_dt(it["published"]) >= week_ago]
    reg = load_registry() if registry is None else registry
    out = {"generated_local": now.strftime("%d.%m.%Y %H:%M"), "week_items": len(week),
           "registry_sources": len(reg)}
    if not week:
        return out

    # издание → первая запись реестра (для подборок seed_data и «чужих» подписей:
    # «Алексей Русских (Telegram)», «Sollers / УАЗ», «Правительство Ульяновской области»)
    by_outlet = {}
    for sid, e in reg.items():
        by_outlet.setdefault(_outlets.norm(e.get("outlet") or e.get("name") or sid), e)

    def reg_entry(it):
        st = it.get("source_type")
        if st == "tg":
            hit = reg.get(f"tg:{it.get('channel')}")
            if hit:
                return hit
        if st == "vk":
            hit = reg.get(f"vk:{it.get('channel')}")
            if hit:
                return hit
        if st == "web":
            hit = reg.get(f"web:{it.get('source')}")
            if hit:
                return hit
        for sid, e in reg.items():
            if sid.startswith("rss:") and sid[4:].lower() == str(it.get("source", "")).lower():
                return e
        return by_outlet.get(_outlet_key(it))

    def ptype(it):
        e = reg_entry(it)
        if e and e.get("producer_type"):
            return e["producer_type"]
        if it.get("source_type") == "web":
            return "пресс-служба"      # сайт органа власти — всегда пресс-служба
        return "редакция" if it.get("source_type") == "rss" else "не атрибутирован"

    # 1) кто пишет: состав потока по типам производителя (неделя + 7 дней)
    week_mix = Counter(ptype(it) for it in week)
    days = [(now - timedelta(days=i)).astimezone(UTC4).date() for i in range(6, -1, -1)]
    daily = []
    for d in days:
        d_items = [it for it in week if _local_dt(it["published"]).astimezone(UTC4).date() == d]
        mix = Counter(ptype(it) for it in d_items)
        daily.append({"date": d.isoformat(), "n": len(d_items),
                      "mix": {k: round(v / len(d_items), 3) for k, v in mix.items()} if d_items else {}})
    out["producer_mix"] = {"week": dict(week_mix.most_common()),
                           "week_n": len(week),
                           "daily": daily}

    # 2) внимание как ресурс: просмотры TG по источникам, Gini, доля топ-3
    views_by_src = Counter()
    for it in week:
        if it.get("views") and it.get("source_type") == "tg":
            views_by_src[_outlet(it)] += it["views"]
    total_views = sum(views_by_src.values())
    top5 = views_by_src.most_common(5)
    out["attention"] = {
        "total_views": total_views,
        "gini": _gini(list(views_by_src.values())),
        "top3_share": round(sum(v for _, v in views_by_src.most_common(3)) / total_views, 3) if total_views else None,
        "top": [{"source": str(s), "views": v,
                 "share": round(v / total_views, 3) if total_views else 0} for s, v in top5],
        "n_sources": len(views_by_src),
    }

    # 3) прямая речь: цитаты чиновников против цитат жителей
    official = citizen = 0
    for it in week:
        if it.get("dup_of"):
            continue
        text = (it.get("text") or "")[:2200]
        for m in QUOTE_X_RE.finditer(text):
            ctx = text[max(0, m.start() - 150):m.end() + 150]
            if CITIZEN_X_RE.search(ctx):
                citizen += 1
            elif OFFICIAL_X_RE.search(ctx):
                official += 1
    out["speech"] = {"official": official, "citizen": citizen,
                     "ratio": round(citizen / official, 2) if official else None}

    # 4) рекламная нагрузка: коммерческая реклама против кросс-промо (калибровка 15.09)
    com_n = cross_n = marked_n = total_n = 0
    com_by_tier = Counter()
    cross_by_tier = Counter()
    total_by_tier = Counter()
    cross_by_src = Counter()
    for it in week:
        blob = (it.get("title") or "") + " " + (it.get("text") or "")[:1200]
        tier = f"T{it['tier']}" if it.get("tier") else "СМИ/подборка"
        # marked_as_ads от VK — та же легальная маркировка, что erid/«Реклама.» в тексте
        marked = bool(AD_MARK_X_RE.search(blob)) or bool(it.get("vk_ads"))
        commercial = marked or bool(AD_OFFER_X_RE.search(blob)) or ad_channel_promo(blob)
        cross = bool(it.get("xtail")) or bool(AD_CROSSPROMO_X_RE.search(blob))
        if commercial:
            com_n += 1
            com_by_tier[tier] += 1
            marked_n += marked
        if cross:
            cross_n += 1
            cross_by_tier[tier] += 1
            cross_by_src[_outlet(it)] += 1
        if commercial or cross:
            total_n += 1
            total_by_tier[tier] += 1
    out["promo_load"] = {
        "n": total_n, "share": round(total_n / len(week), 4),
        "by_tier": dict(total_by_tier),
        "commercial": {"n": com_n, "share": round(com_n / len(week), 4),
                       "marked": marked_n, "by_tier": dict(com_by_tier)},
        "crosspromo": {"n": cross_n, "share": round(cross_n / len(week), 4),
                       "by_tier": dict(cross_by_tier),
                       "by_source": dict(cross_by_src.most_common(5))},
    }

    # 5) немые группы: кого за неделю ни разу не процитировали
    silent = []
    for gname, gpat in SOCIAL_GROUPS_EXT.items():
        grx = re.compile(gpat, re.I)
        mentioned = speaks = 0
        for it in week:
            blob = f"{it.get('title', '')} {(it.get('text') or '')[:500]}"
            m = grx.search(blob)
            if not m:
                continue
            mentioned += 1
            ctx = blob[max(0, m.start() - 160):m.end() + 200]
            if SPEECH_X_RE.search(ctx):
                speaks += 1
        if speaks == 0:
            silent.append({"group": gname, "mentioned": mentioned})
    out["silent_groups"] = silent
    return out


def esc_(v):
    return str(v)



# ---------------------------------------------------------------- build all

# ─────────────────────────────────────────────────────────────────────
# Волна 3 (предложение v0.9): деньги и собственность — концентрация
# владения (HHI по учредителям) на базе sources_registry.json и ЕИС-выгрузки
# ─────────────────────────────────────────────────────────────────────
OWNER_STATE_X = re.compile(r"ОГАУ|ОАУ|ОГБУ|ПАО «ОАК»|УлГТУ|государствен", re.I)
OWNER_OFFICIAL_X = re.compile(r"Губернатор|Правительств|Администрац|Депутат|Глава|глава|мэрия", re.I)
OWNER_PRIVATE_X = re.compile(r"ООО|ИП |ПАО «УАЗ»|Соллерс|АО «", re.I)
OWNER_INN_X = re.compile(r"ИНН[:\s]*(\d{10}|\d{12})")


def owner_form_of(e):
    """Форма владения из реестра (owner_form) или по юрлицу — для старых/тестовых записей."""
    f = (e or {}).get("owner_form")
    if f:
        return f
    o = (e or {}).get("owner") or ""
    if not o:
        return "не установлен" if (e or {}).get("producer_type") == "редакция" else "аноним"
    if OWNER_STATE_X.search(o):
        return "государство"
    if OWNER_OFFICIAL_X.search(o):
        return "официальные"
    if OWNER_PRIVATE_X.search(o):
        return "частный бизнес"
    return "не установлен"


def build_infospace_w3(items, cfg, registry=None):
    """Концентрация собственности: HHI по учредителям, взвешенный недельным потоком.
    Паспорт метрики (план v0.9, ось «деньги»): «Насколько поле принадлежит узкой группе
    владельцев: индекс Херфиндаля по учредителям источников».
    Метод: владелец = юрлицо (слияние по ИНН) или должностное лицо; источник без
    раскрытого владельца считается отдельным неизвестным владельцем (концентрация
    занижается). HHI_confirmed — только по подтверждённым владельцам (перенормировка).
    Шкала 0–10000: <1500 низкая, 1500–2500 умеренная, >2500 высокая (пороги DOJ)."""
    now = datetime.now(UTC4)
    week_ago = now - timedelta(days=7)
    reg = load_registry() if registry is None else registry
    out = {"generated_local": now.strftime("%d.%m.%Y %H:%M"), "registry_sources": len(reg)}
    live = [it for it in items if _local_dt(it.get("published"))]
    week = [it for it in live if _local_dt(it["published"]) >= week_ago]
    if not reg or not week:
        return out

    def src_id(it):
        st = it.get("source_type")
        if st == "tg":
            return f"tg:{it.get('channel')}"
        if st == "vk":
            return f"vk:{it.get('channel')}"
        if st == "web":
            return f"web:{it.get('source')}"
        return f"rss:{it.get('source')}"

    flow = Counter(src_id(it) for it in week)
    total = sum(flow.values())
    if not total:
        return out

    owners = {}
    for sid, n in flow.items():
        e = reg.get(sid)
        if e and e.get("owner"):
            m = OWNER_INN_X.search(e["owner"])
            key = m.group(1) if m else e["owner"]
            name = e["owner"]
            confirmed = e.get("owner_status") == "подтверждён"
        else:
            form0 = owner_form_of(e) if e else "не установлен"
            key = f"?{sid}"                      # каждый нераскрытый — отдельный неизвестный
            name = (e or {}).get("name") or sid
            confirmed = False
        o = owners.setdefault(key, {"name": name, "flow": 0, "sources": [],
                                    "form": owner_form_of(e) if e else "не установлен",
                                    "confirmed": confirmed})
        o["flow"] += n
        o["sources"].append(sid)

    def _hhi(pairs, base):
        return round(sum((v / base) ** 2 for _, v in pairs) * 10000) if base else None

    all_pairs = [(k, o["flow"]) for k, o in owners.items()]
    conf_pairs = [(k, o["flow"]) for k, o in owners.items() if o["confirmed"]]
    conf_total = sum(v for _, v in conf_pairs)
    hhi = _hhi(all_pairs, total)
    hhi_conf = _hhi(conf_pairs, conf_total)

    groups = defaultdict(lambda: {"flow": 0, "n": 0})
    for sid, n in flow.items():
        e = reg.get(sid)
        if e is None or not e.get("owner"):
            form = "вне реестра" if e is None else owner_form_of(e)
        else:
            form = owner_form_of(e)
        groups[form]["flow"] += n
        groups[form]["n"] += 1
    groups_out = {g: {"flow": v["flow"], "share": round(v["flow"] / total, 4), "n": v["n"]}
                  for g, v in sorted(groups.items(), key=lambda kv: -kv[1]["flow"])}

    top = sorted(owners.values(), key=lambda o: -o["flow"])[:6]
    affiliates = [{"id": sid, "group": e.get("affiliate")} for sid, e in reg.items()
                  if e.get("affiliate") and flow.get(sid)]

    state_official = round(sum(v["flow"] for g, v in groups.items()
                               if g in ("государство", "официальные")) / total, 4)
    anon = round(sum(v["flow"] for g, v in groups.items()
                     if g in ("аноним", "вне реестра")) / total, 4)

    def _verdict(x):
        return ("—" if x is None else
                "высокая концентрация" if x > 2500 else
                "умеренная концентрация" if x >= 1500 else "низкая концентрация")

    out.update({
        "week_items": total,
        "hhi": hhi, "hhi_confirmed": hhi_conf,
        "confirmed_flow_share": round(conf_total / total, 4),
        "verdict": _verdict(hhi_conf),          # вердикт — по атрибутируемой части (честнее)
        "verdict_all": _verdict(hhi),           # с анонимами как отдельными владельцами — занижен
        "groups": groups_out,
        "state_official_share": state_official,
        "anon_share": anon,
        "top_owners": [{"name": o["name"], "form": o["form"], "n_sources": len(o["sources"]),
                        "share": round(o["flow"] / total, 4)} for o in top],
        "affiliates": affiliates,
    })
    return out


# ── ЕИС «Госзакупки»: метрики по ручной выгрузке data/goszakupki_eis.csv ──
EIS_COLUMNS = ("date", "customer", "method", "nmck", "supplier", "price")


def load_eis_csv(path=None):
    """Выгрузка ЕИС (44-ФЗ/223-ФЗ): date,customer,method,nmck[,supplier[,price]].
    Форматы дат: YYYY-MM-DD или DD.MM.YYYY. Числа допускают пробелы и запятую-разделитель.
    Возвращает список dict с нормализованными _dt/_nmck/_price или None (нет файла/пуст)."""
    path = path or os.path.join(DATA, "goszakupki_eis.csv")
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8-sig", newline="") as f:
            raw = list(csv.DictReader(f))
    except OSError:
        return None
    rows = []
    for r in raw:
        if not r.get("customer"):
            continue
        d = (r.get("date") or "").strip()
        dt = None
        for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
            try:
                dt = datetime.strptime(d, fmt).replace(tzinfo=UTC4)
                break
            except ValueError:
                continue

        def _num(x):
            try:
                return float(str(x).replace("\xa0", "").replace(" ", "").replace(",", "."))
            except (TypeError, ValueError):
                return None
        rows.append({"date": d, "_dt": dt, "customer": r["customer"].strip(),
                     "method": (r.get("method") or "").strip(),
                     "nmck": _num(r.get("nmck")) or 0.0,
                     "supplier": (r.get("supplier") or "").strip(),
                     "price": _num(r.get("price"))})
    return rows or None


def compute_eis_metrics(rows, now=None):
    """Метрики паспорта проекта «Госзакупки»: извещения за неделю/месяц, суммы НМЦК,
    доля единственного поставщика, среднее снижение, топ заказчиков/поставщиков, HHI поставщиков."""
    now = now or datetime.now(UTC4)
    dated = [r for r in rows if r["_dt"]]
    week = [r for r in dated if timedelta(0) <= now - r["_dt"] <= timedelta(days=7)]
    month = [r for r in dated if timedelta(0) <= now - r["_dt"] <= timedelta(days=30)]

    def _sole(r):
        return "единств" in r["method"].lower()

    sole = [r for r in rows if _sole(r)]
    comp = [r for r in rows if not _sole(r) and r.get("price") and r["nmck"] > 0]
    savings = [ (r["nmck"] - r["price"]) / r["nmck"] for r in comp if r["price"] <= r["nmck"]]
    cust = defaultdict(float)
    for r in rows:
        cust[r["customer"]] += r["nmck"]
    sup = defaultdict(float)
    for r in rows:
        if r.get("supplier"):
            sup[r["supplier"]] += (r.get("price") if r.get("price") is not None else r["nmck"])
    sup_total = sum(sup.values())
    sup_hhi = round(sum((v / sup_total) ** 2 for v in sup.values()) * 10000) if sup_total else None
    total_nmck = sum(r["nmck"] for r in rows)
    total_sole = sum(r["nmck"] for r in sole)
    return {
        "n_rows": len(rows),
        "week_n": len(week), "month_n": len(month),
        "total_nmck": round(total_nmck, 2),
        "total_price": round(sum(r["price"] for r in rows if r.get("price") is not None), 2),
        "sole_share_n": round(len(sole) / len(rows), 4) if rows else None,
        "sole_share_sum": round(total_sole / total_nmck, 4) if total_nmck else None,
        "avg_savings": round(sum(savings) / len(savings), 4) if savings else None,
        "top_customers": [{"name": k, "sum": round(v, 2)} for k, v in
                          sorted(cust.items(), key=lambda kv: -kv[1])[:10]],
        "top_suppliers": [{"name": k, "sum": round(v, 2)} for k, v in
                          sorted(sup.items(), key=lambda kv: -kv[1])[:10]],
        "supplier_hhi": sup_hhi,
    }


# ─────────────────────────────────────────────────────────────────────
# Волна 4 (план v0.9): язык, труд и методика — четыре метрики на уже
# собранной базе store.jsonl, без новых источников:
#   1) agency_index()    — индекс агентности (ось «язык»): кому поле отдаёт действие;
#   2) frame_map()       — фрейм-карта события (ось «язык»): как один сюжет назван
#                          в разных каналах и где фреймы расходятся;
#   3) ai_trace()        — ИИ-след (ось «труд»): признаки шаблонного/машинного
#                          производства текста и дословные повторы между источниками;
#   4) dedup_stability() — устойчивость дедупликации (ось «методика»): чувствительность
#                          оригинальности к порогу Жаккара и сомнительные склейки.
# Принцип автономности соблюдён: синтаксический парсер (natasha/syntax) отклонён как
# внешняя зависимость — вместо него регулярные эвристики, границы которых зафиксированы
# в паспортах метрик и в выводах блоков.
# ─────────────────────────────────────────────────────────────────────
AGENCY_PREP_X = re.compile(
    r"(?:^|[^\wа-яё])(?:в|во|на|у|к|из|от|до|с|со|по|при|о|об|про|для|после|перед|пред|"
    r"за|над|под|между|благодаря|несмотря\s+на|около|возле|мимо|против|ради|без|из-за|из-под)\s+"
    r"(?:[\w-]+\s+){0,2}$", re.I)
# Последний предлог перед актором — для «мягких» падежных окончаний.
AGENCY_PREP_LAST_X = re.compile(
    r"(?:^|[^\wа-яё])(?:в|во|на|у|к|из|от|до|с|со|по|при|о|об|про|для|после|перед|пред|за|над|под|"
    r"между|благодаря|около|возле|мимо|против|ради|без|из-за|из-под)\b", re.I)
# Косвенные падежи по окончанию: твёрдые («журналистку», «школам», «россиян», «художником»)
# работают без предлога; мягкие («школе», «полиции») — только рядом с предлогом.
AGENCY_OBLIQUE_HARD_X = re.compile(r"(?:у|ю|ом|ем|ам|ям|ов|ев|ей|ами|ями|ах|ях|ан|ян|их|ых)$", re.I)
AGENCY_OBLIQUE_SOFT_X = re.compile(r"(?:е|и|а|я|ий|ы)$", re.I)
# Переходные глаголы перед актором: существительное после них — прямой объект
# («посетил завод», «направило школам рекомендации»), а не субъект.
AGENCY_TRANSITIVE_X = re.compile(
    r"\b(?:посетил\w*|осмотрел\w*|открыл\w*|открыли|запустил\w*|направил\w*|направили|направило|"
    r"запретил\w*|запретили|обязал\w*|обязали|обвинил\w*|обвиняют|задержал\w*|задержали|"
    r"наказал\w*|оштрафовал\w*|проверил\w*|проверили|наградил\w*|наградили|поздравил\w*|поздравили|"
    r"вручил\w*|вручили|спас\w*|спасли|госпитализировал\w*|эвакуировал\w*|подключил\w*|"
    r"отключил\w*|приостановил\w*|предостерег\w*|уведомил\w*|выиграл\w*|выиграли|завоевал\w*|"
    r"купил\w*|купили|приобр[её]л\w*|арендовал\w*|украл\w*|похитил\w*)\s+(?:[\w«».,-]+\s+){0,3}$", re.I)
# Глаголы речи допускают инверсию («заявил губернатор») — они гасят понижение роли.
AGENCY_SPEECH_X = re.compile(
    r"\b(?:сообщил\w*|заявил\w*|рассказал\w*|отметил\w*|пояснил\w*|добавил\w*|уточнил\w*|"
    r"подчеркнул\w*|напомнил\w*|объяснил\w*|прокомментировал\w*|рассказали|сообщили|заявили|"
    r"отметили|пояснили)\b", re.I)
# Атрибуция источника («по информации главы города», «по данным прокуратуры») — не пассив:
# названное лицо остаётся субъектом речи, а не объектом действия.
AGENCY_ATTRIB_X = re.compile(r"по информации|по данным|по словам|со ссылкой|по сообщению", re.I)
AGENCY_CLAUSE_SEP_X = re.compile(r"[,;:]|\s—\s|\s-\s")

# Классы социальных акторов (паспорт: «кто подлежащее в сообщении»). Порядок = приоритет
# при равенстве позиций. \b обязателен: без него «лице» ловилось внутри «улице».
AGENCY_CLASSES = OrderedDict([
    ("власть", r"губернатор(?!ск)\w*|министр\w*|мэр\w*|мэри[ия]\w*|правительств\w*|администрац\w*|"
               r"министерств\w*|департамент\w*|управлен\w+|комитет\w*|депутат\w*|сенатор\w*|"
               r"чиновник\w*|ведомств\w*|пресс-служб\w*|зампред\w*|гордум\w*|облдум\w*|"
               r"директор\w*|руководител\w*|начальник\w*|заведующ\w*|главврач\w*|"
               r"глав[аыуеи]\s+(?:администрац|город|район|регион|област|муниципал|сельск|"
               r"поселен|ульяновск|димитровград)\w*"),
    ("контроль", r"полици\w*|полицейск\w*|госавтоинспекц\w*|\bгибдд\b|\bмчс\b|прокуратур\w*|"
                 r"прокурор\w*|\bследстви[еяюи]\b|\bследователь\w*|\bфсб\b|росгварди\w*|\bсуд(?:ы|а|у|ом|е)?\b|"
                 r"роспотребнадзор\w*|инспекц\w*|\bнадзор\w*|пристав\w*|\буфсин\b"),
    ("жители", r"жител\w*|горожан\w*|ульяновц\w*|димитровградц\w*|сельчан\w*|селян\w*|"
               r"родител\w*|пенсионер\w*|пассажир\w*|пешеход\w*|очевидц\w*|собственник\w*|"
               r"арендатор\w*|автомобилист\w*|велосипедист\w*|мотоциклист\w*|дачник\w*|"
               r"садовод\w*|местны\w+\s+жител\w*|волонт[её]р\w*|\bлюд[иь]\b|\bнарод\w*|"
               r"школьник\w*|ученик\w*|земляк\w*|многодетн\w*|инвалид\w*|\bсемь[ия]\b|\bсемьи\b|\bсемей\b|"
               r"подростк\w*|\bдет[иь]\b|\bдети\b|\bреб[её]нок\b|\bреб[её]нк\w*|мальчик\w*|"
               r"девочк\w*|женщин\w*|мужчин\w*|девушк\w*|юнош\w*|человек\w*|человека|"
               r"россиян\w*|\bграждан\w*|ветеран\w*|беженц\w*|переселенц\w*|призывник\w*"),
    ("работники", r"\bрабоч(?:ие|их|ими|им|ий|его|ему|ей|ую|ая)\b(?!\s+(?:визит|поездк|совещан|"
                  r"встреч|недел|групп|режим|порядок|мест|дн\w*|верси|документ|материал|стол|"
                  r"инструмент|одежд|тетрад|сил\w*))|"
                  r"работник\w*|инженер\w*|врач\w*|медик\w*|медсестр\w*|фельдшер\w*|хирург\w*|"
                  r"терапевт\w*|педиатр\w*|невролог\w*|стоматолог\w*|учител\w*|педагог\w*|"
                  r"преподавател\w*|водител\w*|кондуктор\w*|диспетчер\w*|фермер\w*|аграр\w*|"
                  r"\bстроител\w*|дорожник\w*|слесар\w*|сварщик\w*|электрик\w*|сантехник\w*|"
                  r"коммунальщик\w*|энергетик\w*|дворник\w*|продавец\w*|кассир\w*|повар\w*|"
                  r"официант\w*|курьер\w*|таксист\w*|тракторист\w*|комбайн[её]р\w*|шахт[её]р\w*|"
                  r"\bперсонал(?:ы|а|у|ом|е|ов|ам|ами|ах)?\b|специалист\w*|бригад\w*|машинист\w*|механизатор\w*|спортсмен\w*|"
                  r"тренер\w*|акт[её]р\w*|артист\w*|музыкант\w*|художник\w*|журналист\w*|"
                  r"библиотекар\w*|почтальон\w*|бухгалтер\w*|юрист\w*|программист\w*|"
                  r"\bуч[её]ны[ейхм]\b|\bуч[её]ный\b|академик\w*|научн\w+\s+сотрудник\w*|студент\w*|"
                  r"курсант\w*|спасател\w*|\bпожарн(?:ые|ым|ыми|ых|ый)\b|охранник\w*|\bпилот\w*|"
                  r"профессор\w*|доцент\w*"),
    ("военные", r"военнослужащ\w*|\bбоец\b|\bбойц\w*|солдат\w*|офицер\w*|защитник\w*|"
                r"мобилизован\w*|контрактник\w*|военкор\w*|десантник\w*|штурман\w*|\bгварде\w*|"
                r"участник\w+\s+сво|военн\w+\s+(?:част|подразделен|округ)"),
    ("бизнес", r"\bооо\b|\bао\b|\bпао\b|\bип\b|компан\w*|фирм\w*|предпят\w*|\bзавод(?!ск)\w*|банк\w*|"
               r"застройщик\w*|подрядчик\w*|холдинг\w*|\bоператор\w*|торгов\w+\s+цент\w*|\bуаз\b|"
               r"соллерс\w*|авиастар\w*|бизнес\w*|предпринимател\w*|магазин\w*|аптек\w*|\bазс\b|"
               r"перевозчик\w*|авиакомпан\w*|торгов\w+\s+сет\w*|\bржд\b|фермерск\w+\s+хозяйств\w*"),
    ("учреждения", r"\bшкол\w*|гимнази\w*|\bлице(?:й|я|ю|е|и)\w*|больниц\w*|поликлиник\w*|клиник\w*|"
                   r"госпитал\w*|\bмузе\w*|театр\w*|университет\w*|\bулгу\b|\bулгту\b|\bулгпу\b|"
                   r"институт\w*|библиотек\w*|дом\w*\s+культур\w*|\bдк\b|аэропорт\w*|вокзал\w*|"
                   r"стадион\w*|филармон\w*|детск\w+\s+сад\w*|колледж\w*|техникум\w*|училищ\w*|"
                   r"\bакадеми[яию]\w*|\bвуз\w*|\bмфц\b|управляющ\w+\s+компани\w*|\bтсж\b|\bпочт(?!и\b)\w*|"
                   r"\bзагс\b|храм\w*|церков\w*|мечет\w*|монастыр\w*|\bфк\b|\bкоманд\w*|\bклуб\w*"),
    ("неизвестные", r"неизвестн(?!о\b)\w*|злоумышленник\w*|нарушител\w*|вандал\w*|мошенник\w*|"
                    r"неустановленн\w*|аферист\w*|преступник\w*|хулиган\w*|грабител\w*|"
                    r"диверсант\w*|\bвор\b|\bворы\b"),
])
AGENCY_ORDER = list(AGENCY_CLASSES)
AGENCY_X = [(k, re.compile(v, re.I)) for k, v in AGENCY_CLASSES.items()]
# «сотрудник» двузначен: сотрудники полиции/МЧС — контроль, остальные — работники.
AGENCY_SOTR_X = re.compile(r"сотрудник\w*|сотрудница\w*", re.I)
AGENCY_SOTR_CTL_X = re.compile(r"полици|мчс|прокуратур|фсб|госавтоинспекц|гибдд|следствен|"
                               r"росгвард|налог|тамож", re.I)

# Агентивные глаголы (прошедшее, настоящее и будущее время, 3-е лицо).
AGENCY_ACTION_X = re.compile(
    r"\b(?:заявил\w*|сообщил\w*|рассказал\w*|отметил\w*|подчеркнул\w*|поручил\w*|напомнил\w*|"
    r"говорил\w*|сказал\w*|писал\w*|написал\w*|объяснил\w*|объяснял\w*|отмечал\w*|заявлял\w*|"
    r"сообщал\w*|рассказывал\w*|добавил\w*|добавлял\w*|подчеркивал\w*|обещал\w*|пообещал\w*|"
    r"озвучил\w*|огласил\w*|анонсировал\w*|презентовал\w*|представил\w*|обнародовал\w*|"
    r"пров[её]л\w*|открыл\w*|запустил\w*|проверил\w*|объявил\w*|вв[её]л\w*|потребовал\w*|"
    r"предложил\w*|призвал\w*|обвинил\w*|раскритиковал\w*|назвал\w*|оценил\w*|посетил\w*|"
    r"вручил\w*|подписал\w*|доложил\w*|отчитал\w*|приехал\w*|встретил\w*|обратил\w*|"
    r"пожаловал\w*|возмутил\w*|сделал\w*|построил\w*|отремонтировал\w*|выделил\w*|"
    r"направил\w*|принял\w*|утвердил\w*|задержал\w*|спас\w*|остановил\w*|начал\w*|"
    r"завершил\w*|продолжа\w*|планиру\w*|намерен\w*|договорил\w*|согласовал\w*|осмотрел\w*|"
    r"поздравил\w*|наградил\w*|похвалил\w*|отреагировал\w*|приостановил\w*|ограничил\w*|"
    r"запретил\w*|разрешил\w*|предупредил\w*|уточнил\w*|поделил\w*|осудил\w*|поддержал\w*|"
    r"одобрил\w*|выиграл\w*|победил\w*|завоевал\w*|установил\w*|получил\w*|выступил\w*|"
    r"признал\w*|опроверг\w*|раскрыл\w*|наш[её]л\w*|ответил\w*|выразил\w*|извинил\w*|"
    r"пригласил\w*|поблагодарил\w*|рассмотрел\w*|распорядил\w*|проинспектир\w*|"
    r"проконтролир\w*|решил\w*|договорились|встретились|обратились|пожаловались|"
    r"требуют\w*|жалуются|жалуется|жаловались|говорят|говорит|пишут|пишет|вышли|вышел|"
    r"собрались|собрался|пришли|приш[её]л|голосуют|обсуждают|работают|работает|живут|"
    r"жив[её]т|получили|остались|остался|вынуждены|вынужден|просят|просит|просили|хотят|"
    r"хочет|хотели|боятся|боится|обращаются|обращается|возмущаются|возмущается|возмущены|"
    r"недовольны|готовы|готов\b|начали|открывают|строят|ремонтируют|запускают|вводят|"
    r"закрыли|отменили|перенесли|подписали|отвечает|отвечают|сету\w*|выиграли|победили|"
    r"завоевали|установили|получат|получит|смогут|сможет|смогли|могут\b|может\b|добил\w*|"
    r"добьют\w*|констатир\w*|будут|собираются|готовятся|намерены|планируют|надеются|"
    r"рассчитывают|настаива\w*|добива\w*|доказал\w*|устроил\w*|устроили|совершил\w*|"
    r"совершили|организовал\w*|допустил\w*|уступил\w*|уступили|протаранил\w*|снес\w*|"
    r"возобновил\w*|возобновили|"
    r"проведут|откроют|построят|"
    r"отремонтируют|запустят|введут|закроют|отменят|перенесут|поднимут|обратятся|"
    r"выступят|расскажут|объяснят|потребуют|предложат|выберут|проголосуют|придут|выйдут|"
    r"приедут|примут|сообщат|заявят|сообщают|сообщает|рассказывают|рассказывает|"
    r"объясняют|уверяют|подтверждают|напоминают|предупреждают|отчитались|доложили|"
    r"посетили|вручили|поздравили|наградили|осмотрели|проверили|объявили|ввели|открыли|"
    r"запустили|нашли|предложили|обещали|предупредили|напомнили|извинились|выразили)", re.I)

# Пассив, безличность и виктимность: действие совершено над кем-то или «вообще».
AGENCY_PASSIVE_X = re.compile(
    r"\bсообщается\b|\bстало известно\b|по информации|по данным|\bотмечается\b|"
    r"появилась информация|было принято|\bзафиксирован\w*|\bпроизошл\w*|\bслучил\w*|"
    r"\bвводится\b|\bввед[её]н[аоы]\b|\bввед[её]ны\b|\bпроводится\b|\bпроводятся\b|\bпланируется\b|"
    r"\bрассматривается\b|\bожидается\b|\bнамечен\w*|ведутся работы|ид[её]т работа|"
    r"\bосуществля\w*|\bпроизвед[её]н\w*|\bвыполнен\w*|\bобеспечен\w*|\bорганизован\w*|"
    r"в штатном режиме|в рабочем порядке|\bотключен[аоы]\b|\bотключены\b|\bограничен[аоы]\b|"
    r"\bограничены\b|\bзакрыт[аоы]\b|\bзакрыты\b|\bвозобновлен[аоы]\b|"
    r"\bприостановлен[аоы]\b|\bприостановлены\b|\bразрешен[аоы]\b|\bразрешены\b|"
    r"\bзапрещен[аоы]\b|\bзапрещены\b|\bпострада\w*|\bпогиб\w*|\bпогибш\w*|"
    r"\bтравмирован\w*|\bгоспитализирован\w*|\bэвакуирован\w*|\bзадержан\w*|найдено тело|"
    r"\bоштрафован\w*|\bосужд[её]н\w*|\bобвиня\w*|\bлиши\w*|\bостал\w*\s+без|"
    r"\bобесточен\w*|\bранен\w*|\bобокрал\w*|\bограбл\w*|"
    r"\bоповещен\w*|\bрекомендуют\b|\bрекомендуется\b|нашли тело|обнаружен\w+\s+тело|"
    r"тело\s+\w+\s+обнаружен", re.I)

# Служебные формуляры исключаются из расчёта агентности: в них нет субъекта по определению.
SERVICE_ALERT_X = re.compile(
    r"(ракетн\w*|беспилотн\w*|бпла)\W{0,40}опасност|опасност\W{0,40}(бпла|беспилотн\w*|ракетн\w*)|"
    r"план\s*«?ковер|при[ёе]м и выпуск\W{0,30}ограничен|ограничени\w*\W{0,40}(аэропорт|при[ёе]м)|"
    r"аэропорт\w*\W{0,40}ограничен|\bсирены\b|воздушн\w+\s+тревог", re.I)
SERVICE_CASUALTY_X = re.compile(r"погиб|пострада|ранен|убит|разруш|поврежд|сбит|упал|обломк", re.I)
SERVICE_WEATHER_X = re.compile(r"гидромет|прогноз\s+погод|погод\w+\s+на|заморозк|температур воздуха", re.I)
AGENCY_SENT_X = re.compile(r"(?<=[.!?…])\s+|\n+")
AGENCY_PROX = 55          # окно близости «актор ↔ глагол», знаков
AGENCY_FIRST_PERSON_X = re.compile(r"\b(?:я|мы|мой|моя|мо[её]|мои|наш|наша|наше|наши|мной|нами)\b", re.I)
# Адресатные глаголы: если такой глагол стоит ПЕРЕД актором, актор — объект обращения,
# а не субъект действия («жителей призвали быть бдительными»). Единственный доступный
# без парсера способ учесть направление действия.
AGENCY_ADDRESS_X = re.compile(
    r"\b(?:призвал\w*|призвали|призывают|попросил\w*|попросили|просят|просит|просили|"
    r"рекомендовал\w*|рекомендовали|рекомендуют|предупредил\w*|предупредили|предупреждают|"
    r"посоветовал\w*|обязал\w*|обязали|напомнил\w*|напомнили|пригласил\w*|пригласили|"
    r"убедил\w*|проинструктировал\w*|научил\w*|попросила|призвала)\b", re.I)

PEOPLE_CLASSES = ("жители", "работники", "военные")
POWER_CLASSES = ("власть", "контроль")


def service_kind(it):
    """«погода»/«оповещение» — служебный формуляр без социального актора (иначе — None).
    Правило то же, что в generate.is_alert(): сообщение о последствиях — новость, не уведомление."""
    blob = (it.get("title") or "") + " " + (it.get("text") or "")[:200]
    if SERVICE_WEATHER_X.search(blob):
        return "погода"
    if SERVICE_ALERT_X.search(blob) and not SERVICE_CASUALTY_X.search(blob):
        return "оповещение"
    return None


def agency_sentences(it, limit=3):
    """Первые предложения лида: заголовок + начало текста (TG-заголовки — обрезанные посты)."""
    out = []
    for chunk in ((it.get("title") or "").strip(), (it.get("text") or "")[:500].strip()):
        for s in AGENCY_SENT_X.split(chunk):
            s = s.strip()
            if len(s) >= 20:
                out.append(s)
            if len(out) >= limit:
                return out
    return out


def agency_roles(sentence):
    """Список (класс, роль, слово, косвенный_падеж) для одного предложения.
    Роль: «субъект» — актор в именительном (нет предлога) и рядом агентивный глагол;
    «объект» — рядом пассив/виктимный маркер; иначе «упоминание»."""
    res, seen, cands = [], set(), []
    for name, rx in AGENCY_X:
        m = rx.search(sentence)
        if m:
            cands.append((name, m))
    m = AGENCY_SOTR_X.search(sentence)
    if m:
        w0 = sentence[max(0, m.start() - AGENCY_PROX):m.end() + AGENCY_PROX]
        cands.append(("контроль" if AGENCY_SOTR_CTL_X.search(w0) else "работники", m))
    for name, m in cands:
        if name in seen:
            continue
        win = sentence[max(0, m.start() - AGENCY_PROX):m.end() + AGENCY_PROX]
        # узкое окно вокруг самого актора: пассив/виктимность рядом сильнее агентивного
        # глагола в широком окне («нашли тело мужчины» — мужчина объект, а не субъект)
        near = sentence[max(0, m.start() - 45):m.end() + 45]
        before = sentence[max(0, m.start() - 45):m.start()]
        prefix = sentence[:m.start()]
        word = re.sub(r"[^\wа-яё-]", "", m.group(0).lower())
        # косвенный падеж: твёрдое окончание работает само, мягкое — только рядом с предлогом
        last_prep = None
        for pm in AGENCY_PREP_LAST_X.finditer(prefix):
            last_prep = pm
        near_prep = bool(last_prep and len(prefix[last_prep.end():].split()) <= 3
                         and not AGENCY_ACTION_X.search(prefix[last_prep.end():]))
        oblique = bool(AGENCY_OBLIQUE_HARD_X.search(word)
                       or (near_prep and AGENCY_OBLIQUE_SOFT_X.search(word)))
        addressed = bool(AGENCY_ADDRESS_X.search(before))
        # адресатный глагол может стоять и после актора: «Жителей призвали быть бдительными»
        addressed_post = bool(AGENCY_ADDRESS_X.search(sentence[m.end():m.end() + 45]))
        # переходный глагол перед актором — но только в том же придаточном:
        # «"Волга" арендовала Дзиова. Наш клуб договорился…» — клуб субъект, а не объект
        tm = AGENCY_TRANSITIVE_X.search(before)
        transitive = bool(tm and not AGENCY_CLAUSE_SEP_X.search(before[tm.end():]))
        # атрибуция источника («по словам сенатора», «по данным полиции») — не участник действия
        attributed = bool(AGENCY_ATTRIB_X.search(prefix[-45:]))
        # пассив рядом понижает роль, но не через глагол речи: «пострадали, сообщил глава
        # города» — глава субъект речи, а не объект действия
        off = max(0, m.start() - 45)
        passive_near = False
        pm2 = AGENCY_PASSIVE_X.search(near)
        if pm2:
            rel_a, rel_b = m.start() - off, m.end() - off
            if pm2.end() <= rel_a:
                gap = near[pm2.end():rel_a]
            elif pm2.start() >= rel_b:
                gap = near[rel_b:pm2.start()]
            else:
                gap = ""
            passive_near = not (AGENCY_SPEECH_X.search(gap)
                                or AGENCY_CLAUSE_SEP_X.search(gap)
                                or AGENCY_ATTRIB_X.search(pm2.group(0)))
        if attributed:
            role = "упоминание"
        elif passive_near or addressed or transitive:
            role = "объект"
        elif oblique:
            # косвенный падеж в субъекты не берём; объект — при пассиве или адресатном глаголе
            role = "объект" if (AGENCY_PASSIVE_X.search(win) or addressed_post) else "упоминание"
        elif AGENCY_ACTION_X.search(win):
            role = "субъект"
        elif AGENCY_PASSIVE_X.search(win):
            role = "объект"
        else:
            role = "упоминание"
        res.append((name, role, m.group(0), oblique, m.start()))
        seen.add(name)
    # приоритет: сначала субъекты (кто действует), затем по позиции в предложении
    role_rank = {"субъект": 0, "объект": 1, "упоминание": 2}
    res.sort(key=lambda x: (role_rank.get(x[1], 3), x[4]))
    return res


def agency_of(it):
    """Разметка одного сообщения: роль актора и класс."""
    sents = agency_sentences(it)
    if not sents:
        return {"role": "нет текста"}
    impersonal = False
    for s in sents:
        rs = agency_roles(s)
        if rs:
            subj = [x for x in rs if x[1] == "субъект"]
            obj = [x for x in rs if x[1] == "объект"]
            if subj:
                return {"role": "субъект", "actor": subj[0][0], "word": subj[0][2],
                        "sentence": s[:140], "objects": [x[0] for x in obj]}
            if obj:
                return {"role": "объект", "object": obj[0][0], "word": obj[0][2], "sentence": s[:140]}
            return {"role": "упоминание", "class": rs[0][0], "word": rs[0][2], "sentence": s[:140]}
        if AGENCY_PASSIVE_X.search(s):
            impersonal = True
    return {"role": "безличный"} if impersonal else {"role": "без актора"}


def agency_index(items):
    """Паспорт метрики «Индекс агентности» (ось «язык», план v0.9).
    Гипотеза: кому поле отдаёт действие — чиновнику, «жителям», «силовикам», «неизвестным».
    Метод: эвристика без морфологии — класс актора + агентивный глагол в окне ±55 знаков
    внутри предложения лида; актор после предлога считается косвенным падежом и в субъекты
    не попадает. Служебные формуляры (погода, оповещения о режимах) исключены: в них
    субъекта нет по определению. Границы: омонимия падежей без парсера снимается частично,
    поэтому роли «субъект/объект» — нижняя оценка агентности людей и верхняя у институций."""
    now = datetime.now(UTC4)
    week_ago = now - timedelta(days=7)
    live = [it for it in items if _local_dt(it.get("published"))]
    week = [it for it in live if _local_dt(it["published"]) >= week_ago]
    out = {"week_items": len(week)}
    excluded = Counter()
    work = []
    for it in week:
        k = service_kind(it)
        if k:
            excluded[k] += 1
        else:
            work.append(it)
    out["excluded_service"] = dict(excluded)
    out["n"] = len(work)
    if not work:
        return out

    roles, actors, objects = Counter(), Counter(), Counter()
    by_tier = {}
    people_s = people_o = 0
    first_person = 0
    fp_by_tier = Counter()
    tier_n = Counter()
    examples = {}
    for it in work:
        r = agency_of(it)
        tier = f"T{it['tier']}" if it.get("tier") else "СМИ/подборка"
        roles[r["role"]] += 1
        tier_n[tier] += 1
        t = by_tier.setdefault(tier, {"n": 0, "roles": Counter(), "actors": Counter(), "objects": Counter()})
        t["n"] += 1
        t["roles"][r["role"]] += 1
        lead = f"{it.get('title', '')} {(it.get('text') or '')[:120]}"
        if AGENCY_FIRST_PERSON_X.search(lead):
            first_person += 1
            fp_by_tier[tier] += 1
        if r["role"] == "субъект":
            actors[r["actor"]] += 1
            t["actors"][r["actor"]] += 1
            if r["actor"] in PEOPLE_CLASSES:
                people_s += 1
            if any(o in PEOPLE_CLASSES for o in r.get("objects") or []):
                people_o += 1
            if len(examples.setdefault(r["actor"], [])) < 3:
                examples[r["actor"]].append({
                    "source": str(it.get("channel") or it.get("source") or "?"),
                    "title": (it.get("title") or "")[:110], "word": r.get("word"),
                    "url": it.get("url") or ""})
        elif r["role"] == "объект":
            objects[r["object"]] += 1
            t["objects"][r["object"]] += 1
            if r["object"] in PEOPLE_CLASSES:
                people_o += 1

    n = len(work)
    named = roles["субъект"] + roles["объект"] + roles["упоминание"]
    people_a = sum(actors[c] for c in PEOPLE_CLASSES)
    power_a = sum(actors[c] for c in POWER_CLASSES)
    inst_a = actors["учреждения"] + actors["бизнес"]
    idx = round(people_a / power_a, 2) if power_a else None
    verdict = ("—" if idx is None else
               "действие у людей" if idx >= 1.5 else
               "паритет людей и власти" if idx >= 0.8 else
               "действие у власти" if idx >= 0.4 else "действие полностью у власти")
    out.update({
        "roles": dict(roles.most_common()),
        "role_shares": {k: round(v / n, 4) for k, v in roles.items()},
        "actor_mix": dict(actors.most_common()),
        "actor_shares": {k: round(v / sum(actors.values()), 4) for k, v in actors.items()} if actors else {},
        "object_mix": dict(objects.most_common()),
        "agency_index": idx,
        "verdict": verdict,
        "people_subjects": people_a, "power_subjects": power_a, "institutions_subjects": inst_a,
        "people_objects": people_o,
        "objectification": round(people_o / (people_a + people_o), 3) if (people_a + people_o) else None,
        "actor_density": round(named / n, 4),
        "subject_share": round(roles["субъект"] / n, 4),
        "impersonal_share": round((roles["безличный"] + roles["без актора"]) / n, 4),
        "first_person_share": round(first_person / n, 4),
        "first_person_by_tier": {k: round(fp_by_tier[k] / tier_n[k], 3) for k in tier_n if tier_n[k]},
        "by_tier": {k: {"n": v["n"],
                        "subject_share": round(v["roles"]["субъект"] / v["n"], 4),
                        "people_subjects": sum(v["actors"][c] for c in PEOPLE_CLASSES),
                        "power_subjects": sum(v["actors"][c] for c in POWER_CLASSES),
                        "people_objects": sum(v["objects"][c] for c in PEOPLE_CLASSES),
                        "impersonal_share": round((v["roles"]["безличный"] + v["roles"]["без актора"]) / v["n"], 4)}
                    for k, v in by_tier.items() if v["n"]},
        "examples": examples,
    })
    return out


# ── Фрейм-карта события (ось «язык»): как один сюжет назван в разных каналах ──
FRAME_RULES = [
    ("тревога", r"ракетн\w*|беспилотн\w*|\bбпла\b|опасност\w*|сирен\w*|эвакуац\w*|обстрел\w*|"
                r"атак\w*|план\s*«?ковер|\bпво\b|воздушн\w+\s+тревог|подозрительн\w+\s+предмет"),
    ("ЧП", r"\bдтп\b|авари\w*|пожар\w*|гор[еи]т|взрыв\w*|обрушен\w*|погиб\w*|пострада\w*|"
           r"травм\w*|утечк\w*|отравлен\w*|избиен\w*|ножев\w*|стрельб\w*|происшеств\w*|"
           r"криминал\w*|убийств\w*|утону\w*|сбил\w*|нашли тело|обнаружен\w+\s+тело|драка|кража|"
           r"граб[её]ж|мошенник\w*|столкнул\w*|съеха\w+ в кювет|перевернул\w*|влетел\w*|"
           r"врезал\w*|наехал\w*|опрокинул\w*|загорел\w*|горел\w*|вспыхнул\w*|рухнул\w*|"
           r"упал\w*|порыв\w*|прорыв\w*|замкнуло|громит\w*|избил\w*|напал\w*|проткнул\w*|"
           r"запер\w*|неадекват\w*|поножовщ\w*|госпитализирован\w*|\bтруп\w*"),
    ("жалоба", r"жалоб\w*|жалуются|возмущ\w*|недоволен\w*|недовольств\w*|проблем\w*|срыв\w*|"
               r"затоп\w*|подтопл\w*|мусор\w*|свалк\w*|\bям[аыу]\b|разруш\w*|износ\w*|"
               r"аварийн\w*|протека\w*|плесень|крыс\w*|не работает|коллапс|хаос|безобраз\w*|"
               r"скандал\w*|конфликт\w*|долг\w*|задолжен\w*|не выплачен\w*|обман\w*|"
               r"холод\w*|без воды|без света|отключ\w*|не могу|не могут добиться|бьют тревогу|"
               r"загадил\w*|разбит\w*|грязь|антисанитар"),
    ("надзор", r"прокуратур\w*|проверк\w*|надзор\w*|предписан\w*|расследован\w*|возбужден\w*|"
               r"уголовн\w*|административн\w*|инспекц\w*|нарушен\w*|виновн\w*|ответствен\w*|"
               r"штраф\w*|приговор\w*|\bсуд(?:ы|а|у|ом|е)?\b|судебн\w*|\bиск\b|задержан\w*|"
               r"лицензи\w*|контрол\w*|предписан"),
    ("работы", r"планов\w*|ремонт\w*|благоустройств\w*|модернизаци\w*|капремонт\w*|"
               r"работ[ыае]|укладк\w*|асфальт\w*|строительств\w*|реконструкц\w*|обновлен\w*|"
               r"замен\w*|в штатном|в рабочем порядке|перекрыт\w*|ограничение движени\w*|"
               r"отопительн\w*|подготовк\w+ к зиме|подключен\w*|дорожник\w*"),
    ("достижение", r"побед\w*|выиграл\w*|чемпион\w*|кубок\w*|медал\w*|рекорд\w*|награжден\w*|"
                   r"преми\w*|грант\w*|открыл\w*|открыт\w*|запустил\w*|ввели|первое место|"
                   r"лучш\w*|лидер\w*|рейтинг\w*|успех\w*|достижен\w*|реализован\w*|"
                   r"завершил\w*|досрочно|гордимся|поздравляем|вперв\w*|уникальн\w*"),
    ("ритуал", r"посетил\w*|визит\w*|встретил\w*|совещан\w*|\bштаб\b|заседан\w*|поздравил\w*|"
               r"вручил\w*|церемон\w*|возложил\w*|памят\w*|праздник\w*|день города|митинг\w*|"
               r"брифинг\w*|пресс-конференц\w*|соглашение|рабочая поездка|осмотрел\w*|"
               r"проинспектир\w*|почтил\w*|награждение|подписал\w*|делегац\w*"),
    ("услуга", r"как получить|инструкц\w*|совет\w*|напомин\w*|разъясн\w*|можно\b|госуслуг\w*|"
               r"запис\w*|расписан\w*|график\w*|тариф\w*|оплат\w*|льгот\w*|выплат\w*|"
               r"субсид\w*|пенс\w*|пособи\w*|справк\w*|документ\w*|оформить|подать заявлен\w*|"
               r"рекоменду\w*|памятка"),
    ("статистика", r"средняя зарплат\w*|статистик\w*|по данным|опрос\w*|социолог\w*|\bитоги\b|"
                   r"отчёт\w*|отчет\w*|рейтинг\w*|показател\w*|\bдоля\b|\bпроцент\w*|"
                   r"\bцифр\w*|подсчита\w*|выяснил\w*|исследован\w*|мониторинг\w*|\bданны[ех]\b"),
    ("интерактив", r"ночной чат|открываем чат|поиграем|предлагаем поиграть|игр\w+ в слова|"
                   r"пишит\w+ в комментар|в комментарии|делитесь в|а вы как|голосован\w+ в|"
                   r"ставьт\w+ реакц|\bлайк\w*|реакци\w+ на пост|викторин\w*|розыгрыш\w*|"
                   r"подписывайт\w*|конкурс репостов"),
    ("лайв", r"\b\d{1,3}[’']\s|пост будет обновляться|прям\w+\s+(?:эфир|трансляц)|трансляц\w*|"
             r"обновля\w+|вед[её]м онлайн|с места событий|сейчас на месте|онлайн"),
    ("погода", r"гидромет\w*|синоптик\w*|погод\w*|заморозк\w*|температур\w*|\bветер\b|"
               r"осадк\w*|\bдождь\b|облачн\w*|метео\w*|прогноз\w*|переменн\w+\s+облачн|гололёд|гололед"),
]
FRAME_X = [(name, re.compile(pat, re.I)) for name, pat in FRAME_RULES]
FRAME_DEFAULT = "прочее"


def frame_of(it, limit=260):
    """Доминирующий фрейм сообщения: считаем совпадения маркеров в заголовке и лиде.
    Возвращает (фрейм, счёт, топ-2) — второй фрейм нужен для оценки расхождения."""
    blob = f"{it.get('title', '')} {(it.get('text') or '')[:limit]}"
    scores = []
    for name, rx in FRAME_X:
        n = len(rx.findall(blob))
        if n:
            scores.append((n, name))
    if not scores:
        return FRAME_DEFAULT, 0, [FRAME_DEFAULT]
    scores.sort(key=lambda x: (-x[0], [f for f, _ in FRAME_RULES].index(x[1])))
    top = [s[1] for s in scores[:2]]
    return scores[0][1], scores[0][0], top


def frame_map(items):
    """Паспорт метрики «Фрейм-карта события» (ось «язык», план v0.9).
    Гипотеза: один и тот же сюжет разные каналы называют по-разному («ЧП», «плановые работы»,
    «провокация»); расхождение фреймов внутри каскада — видимый след конфликта интересов.
    Метод: лексикон из 8 фреймов + «прочее», доминанта по числу маркеров в заголовке и лиде;
    кластеры — уже посчитанная дедупликацией связность перепечаток (dup_of/cluster)."""
    now = datetime.now(UTC4)
    week_ago = now - timedelta(days=7)
    live = [it for it in items if _local_dt(it.get("published"))]
    week = [it for it in live if _local_dt(it["published"]) >= week_ago]
    out = {"week_items": len(week)}
    if not week:
        return out
    by_id = {it.get("id"): it for it in week}

    frames_all = Counter()
    frames_prim = Counter()
    tier_frame = {}
    for it in week:
        fr, _, _ = frame_of(it)
        frames_all[fr] += 1
        if not it.get("dup_of"):
            frames_prim[fr] += 1
            tier = f"T{it['tier']}" if it.get("tier") else "СМИ/подборка"
            tier_frame.setdefault(tier, Counter())[fr] += 1

    clusters = []
    for it in week:
        if cascade_sources(it) < 2 or it.get("dup_of"):
            continue
        members = [it] + [d for d in week if d.get("dup_of") == it.get("id")]
        if len(members) < 2:
            continue
        fr_list = []
        for m in members:
            fr, sc, top2 = frame_of(m)
            fr_list.append({"source": _outlet(m), "channel": _src_key(m),
                            "tier": m.get("tier"), "frame": fr, "score": sc,
                            "title": (m.get("title") or "")[:110], "url": m.get("url") or ""})
        uniq = sorted({x["frame"] for x in fr_list})
        # конфликт уровней: официальный канал (T1) и агрегатор (T2) назвали сюжет по-разному
        t1f = {x["frame"] for x in fr_list if x["tier"] == 1}
        t2f = {x["frame"] for x in fr_list if x["tier"] == 2}
        tier_conflict = bool(t1f and t2f and not (t1f & t2f))
        clusters.append({"size": len(members), "title": (it.get("title") or "")[:110],
                         "url": it.get("url") or "", "frames": uniq, "divergent": len(uniq) > 1,
                         "tier_conflict": tier_conflict, "members": fr_list,
                         "chp_vs_works": ({"ЧП", "работы"} <= set(uniq))})

    n_cl = len(clusters)
    div = [c for c in clusters if c["divergent"]]
    div.sort(key=lambda c: (not c["tier_conflict"], -len(c["frames"]), -c["size"]))
    tier_matrix = {}
    for tier, c in tier_frame.items():
        tot = sum(c.values())
        tier_matrix[tier] = {"n": tot,
                             "frames": {f: round(v / tot, 3) for f, v in c.most_common()}}
    out.update({
        "frame_mix": dict(frames_all.most_common()),
        "frame_shares": {k: round(v / len(week), 4) for k, v in frames_all.items()},
        "frame_mix_primaries": dict(frames_prim.most_common()),
        "tier_matrix": tier_matrix,
        "clusters": n_cl,
        "divergent": len(div),
        "divergence_share": round(len(div) / n_cl, 3) if n_cl else None,
        "chp_vs_works": sum(1 for c in clusters if c["chp_vs_works"]),
        "tier_conflicts": sum(1 for c in clusters if c["tier_conflict"]),
        "examples": [{"size": c["size"], "title": c["title"], "url": c["url"],
                      "frames": c["frames"], "tier_conflict": c["tier_conflict"],
                      "members": c["members"][:6]} for c in div[:4]],
    })
    return out


# ── ИИ-след (ось «труд»): признаки шаблонного и машинного производства текста ──
AI_TAIL_X = re.compile(
    r"мы в (?:телеграм|max|макс)\b|наш канал в (?:телеграм|max|макс)\b|читай(?:те)? в (?:max|макс)\b|"
    r"плохо грузит|подписаться \||прислать новость|все новости (?:на|в) |читайте нас в|смотрите в нашем|"
    r"t\.me/\w+|max\.ru/\w+|телеграм-канал @\w+|\bподпишись\b|\bподписывайт\w*|👉", re.I)
AI_CLICHE_X = re.compile(
    r"важно отметить|стоит отметить|следует отметить|хочется отметить|нельзя не отметить|"
    r"в современном мире|на сегодняшний день|играет важную роль|является неотъемлемой|"
    r"не остался в стороне|не осталась в стороне|в заключение|таким образом|как известно|"
    r"по словам экспертов|по мнению экспертов|безусловно|в первую очередь|"
    r"ни для кого не секрет|в наши дни|современные технологи|ид[её]т в ногу со временем|"
    r"ярким примером|в полной мере|несомненно|примечательно, что", re.I)
AI_CAPS_X = re.compile(r"(?:^|\n)\s*[А-ЯЁA-Z][А-ЯЁA-Z\s!?—–:,\-]{14,}")
# Переводы строк в базе схлопнуты коллектором (clean_text), поэтому список-шаблон
# ищем по повторяющимся маркерам внутри строки, а не по началам строк.
AI_BULLET_X = re.compile("[🔹🔸🔺🔻•▪●‣➤→►🔵🟢🟡🟠🔴⚪✔✓☑]")
AI_EMOJI_X = re.compile("[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF"
                        "\u2B50\u2705\u274C\u2764\u26A0\u26A1\u2757\u270D]")


def _norm_sentence(s):
    return re.sub(r"[^a-zа-яё0-9]", "", s.lower())


def ai_trace(items, min_shared_len=40):
    """Паспорт метрики «ИИ-след» (ось «труд», план v0.9).
    Гипотеза: доля текстов с признаками машинной генерации — шаблонные концовки
    («Мы в Telegram | Мы в MAX»), однородные эмодзи-блоки, клише машинного текста,
    дословные повторы между источниками.
    Метод: 6 независимых признаков, сообщение считается «со следом» при ≥1 признаке
    и «с выраженным следом» при ≥2. Дословные повторы ищутся по индексу нормализованных
    предложений (≥40 знаков) внутри недели — это ловит и копипаст пресс-релизов,
    и синдицированный рерайт ниже порога дедупликации.
    Границы: это НЕ детектор авторства ИИ, а измерение шаблонности; признаки одинаково
    ловят машинную генерацию, потогонный рерайт и копипаст пресс-релизов. Требуется
    сверка с редакциями (пункт паспорта)."""
    now = datetime.now(UTC4)
    week_ago = now - timedelta(days=7)
    live = [it for it in items if _local_dt(it.get("published"))]
    week = [it for it in live if _local_dt(it["published"]) >= week_ago]
    out = {"week_items": len(week)}
    if not week:
        return out

    # индекс дословных повторов: предложение → {(source_key, id)}
    sent_index = {}
    item_sents = {}
    for it in week:
        key = _outlet_key(it)   # общий текст RSS и TG одной редакции — не заимствование
        text = (it.get("text") or "")[:1500]
        ss = set()
        for s in AGENCY_SENT_X.split(text):
            ns = _norm_sentence(s)
            if len(ns) >= min_shared_len:
                ss.add(ns)
                sent_index.setdefault(ns, set()).add((key, it.get("id")))
        item_sents[it.get("id")] = (key, ss)

    shared_items = Counter()          # id → число предложений, общих с ДРУГИМ источником
    shared_groups = set()
    shared_examples = []
    for ns, owners in sent_index.items():
        srcs = {k for k, _ in owners}
        if len(srcs) < 2:
            continue
        shared_groups.add(ns)
        for key, iid in owners:
            others = {k for k, _ in owners if k != key}
            if others:
                shared_items[iid] += 1
                if len(shared_examples) < 6 and len(ns) > 70:
                    shared_examples.append({"ids": sorted({i for _, i in owners}),
                                            "sources": sorted(srcs)[:4],
                                            "snippet": ns[:120]})

    signals = Counter()
    by_tier = {}
    by_source = {}
    n_any = n_strong = 0
    examples = []
    for it in week:
        title = it.get("title") or ""
        text = it.get("text") or ""
        head = f"{title} {text[:600]}"
        tier = f"T{it['tier']}" if it.get("tier") else "СМИ/подборка"
        src = _outlet(it)
        found = []
        if AI_TAIL_X.search(head):
            found.append("шаблонная концовка")
        clich = AI_CLICHE_X.findall(head)
        if clich:
            found.append("клише машинного текста")
        emoji_head = AI_EMOJI_X.findall(f"{title} {text[:200]}")
        same_emoji = max(Counter(emoji_head).values()) if emoji_head else 0
        if len(emoji_head) >= 5 or same_emoji >= 3:
            found.append("эмодзи-блок")
        if AI_CAPS_X.search(title) or AI_CAPS_X.search(text[:200]):
            found.append("капс-заголовок")
        if len(AI_BULLET_X.findall(text[:600])) >= 3:
            found.append("список-шаблон")
        if shared_items.get(it.get("id"), 0) >= 2:
            found.append("дословный повтор")
        t = by_tier.setdefault(tier, {"n": 0, "any": 0, "strong": 0})
        s = by_source.setdefault(src, {"n": 0, "any": 0})
        t["n"] += 1
        s["n"] += 1
        if found:
            n_any += 1
            t["any"] += 1
            s["any"] += 1
            signals.update(found)
            if len(found) >= 2:
                n_strong += 1
                t["strong"] += 1
            if len(examples) < 8 and len(found) >= 2:
                examples.append({"source": src, "title": title[:110],
                                 "signals": found, "url": it.get("url") or ""})
    n = len(week)
    out.update({
        "n": n,
        "any_n": n_any, "any_share": round(n_any / n, 4),
        "strong_n": n_strong, "strong_share": round(n_strong / n, 4),
        "signals": dict(signals.most_common()),
        "by_tier": {k: {"n": v["n"], "any_share": round(v["any"] / v["n"], 3),
                        "strong_share": round(v["strong"] / v["n"], 3)}
                    for k, v in by_tier.items() if v["n"]},
        "by_source": sorted([{"source": k, "n": v["n"], "share": round(v["any"] / v["n"], 3)}
                             for k, v in by_source.items() if v["n"] >= 12],
                            key=lambda x: (-x["share"], -x["n"]))[:8],
        "verbatim_items": sum(1 for v in shared_items.values() if v >= 2),
        "verbatim_groups": len(shared_groups),
        "verbatim_examples": shared_examples[:4],
        "share_any_verdict": ("—" if not n else
                              "поле почти не шаблонно" if n_any / n < 0.10 else
                              "заметная шаблонность" if n_any / n < 0.30 else
                              "шаблонное производство"),
        "examples": examples[:5],
    })
    return out


# ── Устойчивость дедупликации (ось «методика»): пороговые эксперименты ──
DEDUP_THRESHOLDS = (0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60)
# Антагонистические формуляры: «режим введён» и «режим снят» — разные сообщения,
# но токены почти совпадают, поэтому дедупликация их склеивает.
DEDUP_ONSET_X = re.compile(
    r"введ[её]н\w*|объявлен\w*|включ[её]н\w*|режим\s*«?(?:ракетн|беспилотн)|опасность|"
    r"ограничения на при[ёе]м|закрыт\w*|приостановлен\w*|отключен\w*|прекращен\w*|эвакуац\w*", re.I)
DEDUP_CANCEL_X = re.compile(
    r"снят\s+режим|режим\s+снят|сняты|снято|снята\b|отменен\w*|отменён\w*|восстановлен\w*|"
    r"возобновлен\w*|возобновл[её]н\w*|заверш[её]н\w*|опасности нет|угроза миновала|открыт\w*\s+после", re.I)


def _src_key(it):
    """Ключ КАНАЛА (TG/VK/лента) — для подписей и трассировки примеров."""
    return str(it.get("channel") or it.get("source") or "?")


def _outlet(it):
    """Каноническое издание записи: RSS ulpressa.ru и TG @ulpressa — одна «Улпресса».

    Все метрики независимости (сеттеры повестки, каскады, cluster_src, концентрация
    внимания, дословные повторы между источниками) считаются по изданиям, а не по
    каналам: перепечатка своего материала в свой канал — не независимое подтверждение
    (outlets.py + поле outlet в sources_registry.json, решение редакции 15.09.2026)."""
    return _outlets.outlet(it)


def _outlet_key(it):
    """Нормализованный ключ издания — для сравнений «один и тот же источник»."""
    return _outlets.outlet_key(it)


def span_h(a, b):
    """Расстояние между публикациями в часах — делегируем dedup.py (единые правила)."""
    import dedup as _dedup
    return _dedup.span_h(a, b)


def _antagonistic(a, b):
    """True, если одно сообщение вводит режим/ограничение, а второе его снимает.
    Текст отмены сам содержит слово «опасность», поэтому признак ввода гасится
    признаком отмены — иначе снятие режима совпадёт само с собой."""
    def blob(it):
        return f"{it.get('title') or ''} {(it.get('text') or '')[:200]}"

    def is_cancel(t):
        return bool(DEDUP_CANCEL_X.search(t))

    def is_onset(t):
        return bool(DEDUP_ONSET_X.search(t)) and not is_cancel(t)
    ta, tb = blob(a), blob(b)
    return bool((is_onset(ta) and is_cancel(tb)) or (is_onset(tb) and is_cancel(ta)))


def dedup_stability(items, cfg=None, days=7, min_jaccard=0.28):
    """Паспорт метрики «Устойчивость дедупликации» (ось «методика», план v0.9).
    Гипотеза: доля ложных склеек и пропусков — «82% оригинальности» может быть завышен
    или занижен. Метод: пороговый эксперимент — одни и те же пары недели пересчитываются
    при порогах Жаккара 0.30…0.60, фиксируется размах доли оригинальности; плюс два
    класса сомнительных склеек: (а) кластеры, растянутые более чем на 24 ч (склеены разные
    эпизоды одного формуляра — оповещения, погода), (б) пограничные пары (|Жаккар − порог| ≤ 0.07),
    которые отдаются на ручную проверку. Скорректированная оригинальность — без дублей
    из кластеров-«эпизодов». Границы: ручная верификация всей выборки не выполнялась,
    оценка ложных склеек — по времени жизни кластера, это прокси, а не истина."""
    import dedup as _dedup
    now = datetime.now(UTC4)
    since = now - timedelta(days=days)
    live = [it for it in items if _local_dt(it.get("published"))]
    week = [it for it in live if _local_dt(it["published"]) >= since]
    settings = (cfg or {}).get("settings") or {}
    dcfg = dict(_dedup.DEFAULTS)
    dcfg.update({k: settings[k] for k in _dedup.DEFAULTS if k in settings})
    thr_cfg = dcfg["dedup_threshold"]
    out = {"n_items": len(week), "threshold": thr_cfg, "days": days,
           "policy": {k: dcfg[k] for k in ("dedup_max_span_h", "dedup_service_span_h",
                                           "dedup_verbatim_jaccard")}}
    if len(week) < 5:
        return out

    feats = []
    for it in week:
        toks, _raw = _dedup.tokens(it)
        feats.append((toks, None, _dedup.title_core(it)))
    n = len(week)
    edges = []            # (i, j, jaccard, разрешено_охранными_правилами)
    blocked = Counter()
    for i in range(n):
        ti = feats[i][0]
        if not ti:
            continue
        for j in range(i + 1, n):
            tj = feats[j][0]
            if not tj:
                continue
            inter = len(ti & tj)
            if not inter:
                continue
            jacc = inter / len(ti | tj)
            if jacc < min_jaccard:
                continue
            ok, why = _dedup.mergeable(feats[i], feats[j], week[i], week[j],
                                       min_jaccard, dcfg)
            if not ok and why:
                blocked[why] += 1
            edges.append((i, j, jacc, ok or not why))

    def clusters_at(thr, guards=True):
        dsu = _dedup.DSU(n)
        for i, j, jacc, allowed in edges:
            if jacc >= thr and (allowed or not guards):
                dsu.union(i, j)
        groups = {}
        for i in range(n):
            groups.setdefault(dsu.find(i), []).append(i)
        return [g for g in groups.values() if len(g) > 1]

    sweep = []
    for thr in DEDUP_THRESHOLDS:
        groups = clusters_at(thr)
        dup_n = sum(len(g) - 1 for g in groups)
        raw = clusters_at(thr, guards=False)
        raw_n = sum(len(g) - 1 for g in raw)
        sweep.append({"threshold": thr, "clusters": len(groups), "dups": dup_n,
                      "dup_share": round(dup_n / n, 4),
                      "original_share": round((n - dup_n) / n, 4),
                      "original_share_noguards": round((n - raw_n) / n, 4),
                      "max_size": max((len(g) for g in groups), default=0)})
    cur = next((s for s in sweep if abs(s["threshold"] - thr_cfg) < 1e-9), sweep[len(sweep) // 2])
    lo = min(s["original_share"] for s in sweep)
    hi = max(s["original_share"] for s in sweep)

    # сомнительные склейки при текущем пороге — три независимых признака:
    # (а) кластер-«эпизод»: разброс публикаций > 24 ч — склеены разные события формуляра;
    # (б) антагонизм: «режим введён» склеен с «режим снят» — противоположные сообщения;
    # (в) один источник: повтор внутри канала, а не перепечатка (каскада нет).
    groups = clusters_at(thr_cfg)
    episode_clusters = episode_dups = service_dups = 0
    episode_verbatim = 0
    antagonistic_dups = same_source_dups = 0
    suspicious = 0
    spans = []
    ant_examples = []
    same_source_flagged = 0
    for g in groups:
        times = [_local_dt(week[i]["published"]) for i in g if _local_dt(week[i].get("published"))]
        span_hours = (max(times) - min(times)).total_seconds() / 3600.0 if len(times) >= 2 else 0.0
        spans.append(round(span_hours, 1))
        svc = sum(1 for i in g if service_kind(week[i]))
        long_span = span_hours > 24
        if long_span:
            episode_clusters += 1
            episode_dups += len(g) - 1
        if svc >= max(2, int(len(g) * 0.8)):
            service_dups += len(g) - 1
        order = sorted(g, key=lambda i: _dedup.primary_score(week[i]), reverse=True)
        head = order[0]
        h_key = _outlet_key(week[head])   # издание, а не канал: RSS + TG одной редакции
        verbatim = dcfg["dedup_verbatim_jaccard"]
        pair_j = {(min(a, b), max(a, b)): j for a, b, j, _ok in edges}
        for i in order[1:]:
            # длинный кластер после включения охран возможен только через разрешение
            # «дословного повтора» — это не брак, а тот же текст сутки спустя
            j_head = pair_j.get((min(head, i), max(head, i)))
            flag_episode = long_span and not (j_head is not None and j_head >= verbatim)
            if long_span:
                episode_verbatim += 1 if not flag_episode else 0
            flag_same = week[i].get("same_source") or _outlet_key(week[i]) == h_key
            flag_ant = _antagonistic(week[head], week[i])
            if flag_same:
                same_source_dups += 1
            if flag_ant:
                antagonistic_dups += 1
                if len(ant_examples) < 4:
                    ant_examples.append({
                        "a": {"source": _outlet(week[head]), "channel": _src_key(week[head]),
                              "title": (week[head].get("title") or "")[:110]},
                        "b": {"source": _outlet(week[i]), "channel": _src_key(week[i]),
                              "title": (week[i].get("title") or "")[:110]},
                        "jaccard": round(max((j for a, b, j in edges
                                              if {a, b} == {head, i}), default=0.0), 3)})
            if flag_same:
                same_source_flagged += 1
            if flag_episode or flag_ant:
                suspicious += 1
    orig_now = cur["original_share"]
    corrected = round((n - cur["dups"] + suspicious) / n, 4) if n else None

    # контрольная выборка пограничных пар — на ручную верификацию редакцией
    border = [(i, j, jacc) for i, j, jacc, _a in edges if abs(jacc - thr_cfg) <= 0.07]
    border.sort(key=lambda e: (abs(e[2] - thr_cfg), week[e[0]].get("title") or ""))
    sample = []
    for i, j, jacc in border[:12]:
        a, b = week[i], week[j]
        sample.append({"jaccard": round(jacc, 3),
                       "would_merge": jacc >= thr_cfg,
                       "same_source": _outlet_key(a) == _outlet_key(b),
                       "same_channel": _src_key(a) == _src_key(b),
                       "antagonistic": _antagonistic(a, b),
                       "service": bool(service_kind(a) or service_kind(b)),
                       "span_h": (round(_dedup.span_h(a, b), 1)
                                  if _dedup.span_h(a, b) is not None else None),
                       "a": {"source": _outlet(a), "channel": _src_key(a),
                             "title": (a.get("title") or "")[:110]},
                       "b": {"source": _outlet(b), "channel": _src_key(b),
                             "title": (b.get("title") or "")[:110]}})
    spans.sort()
    out.update({
        "sweep": sweep,
        "original_share": orig_now,
        "original_range": [lo, hi],
        "spread_pp": round((hi - lo) * 100, 1),
        "pairs": len(edges),
        "clusters": cur["clusters"],
        "episode_clusters": episode_clusters,
        "episode_dups": episode_dups,
        "episode_verbatim_dups": episode_verbatim,
        "service_dups": service_dups,
        "antagonistic_dups": antagonistic_dups,
        "same_source_dups": same_source_dups,
        "same_source_flagged": same_source_flagged,
        "blocked_by_guards": dict(blocked.most_common()),
        "antagonistic_examples": ant_examples,
        "suspicious_dups": suspicious,
        "suspicious_share": round(suspicious / cur["dups"], 3) if cur["dups"] else None,
        "corrected_original_share": corrected,
        "median_span_h": spans[len(spans) // 2] if spans else None,
        "borderline_pairs": len(border),
        "sample": sample,
        "guards_effect_pp": round((sum(s["original_share"] - s["original_share_noguards"]
                                       for s in sweep) / len(sweep)) * 100, 1) if sweep else None,
        "verdict": (f"оригинальность {round(orig_now * 100, 1)}% при пороге {thr_cfg}; "
                    f"размах на порогах {DEDUP_THRESHOLDS[0]}–{DEDUP_THRESHOLDS[-1]} — "
                    f"{round(lo * 100, 1)}…{round(hi * 100, 1)}% (±{round((hi - lo) * 50, 1)} п.п.); "
                    f"охранные правила dedup.py заблокировали {sum(blocked.values())} склеек "
                    f"({', '.join(f'{k} {v}' for k, v in blocked.most_common()) or '—'}); "
                    f"остаточных дефектов {suspicious} из {cur['dups']} дублей"),
    })
    return out


def build_infospace_w4(items, cfg=None):
    """Волна 4: язык (агентность, фреймы), труд (ИИ-след), методика (устойчивость дедупликации)."""
    now = datetime.now(UTC4)
    out = {"generated_local": now.strftime("%d.%m.%Y %H:%M")}
    for key, fn in (("agency", agency_index), ("frames", frame_map),
                    ("ai_trace", ai_trace)):
        try:
            out[key] = fn(items)
        except Exception:
            out[key] = {}
    try:
        out["dedup"] = dedup_stability(items, cfg)
    except Exception:
        out["dedup"] = {}
    return out


def build_all(items, trends, cfg=None):
    now = datetime.now(UTC4)
    infospace = build_infospace(items, trends, cfg)
    try:
        infospace["w1"] = build_infospace_ext(items, trends, cfg)
    except Exception:
        infospace["w1"] = {}
    try:
        infospace["w2"] = build_infospace_w2(items, trends, cfg)
    except Exception:
        infospace["w2"] = {}
    try:
        infospace["w3"] = build_infospace_w3(items, cfg)
    except Exception:
        infospace["w3"] = {}
    try:
        infospace["w4"] = build_infospace_w4(items, cfg)
    except Exception:
        infospace["w4"] = {}
    os.makedirs(DATA, exist_ok=True)
    with open(os.path.join(DATA, "infospace.json"), "w", encoding="utf-8") as f:
        json.dump(infospace, f, ensure_ascii=False, indent=1)

    result = {
        "generated_local": now.strftime("%d.%m.%Y %H:%M"),
        "calendar": extract_calendar(items, now),
        "clusters": cluster_stories(items, now),
        "sentiment": sentiment_score(items, now=now),
        "credibility": source_credibility(items),
        "forecast": forecast_topics(trends),
    }
    os.makedirs(DATA, exist_ok=True)
    with open(os.path.join(DATA, "analytics.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    return result


def main():
    with open(os.path.join(BASE, "config.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    with open(os.path.join(DATA, "trends.json"), encoding="utf-8") as f:
        trends = json.load(f)
    items = []
    with open(os.path.join(DATA, "store.jsonl"), encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    items.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    r = build_all(items, trends, cfg)
    print(f"[analytics] календарь: {len(r['calendar'])} событий | кластеров: {len(r['clusters'])} "
          f"(слепых зон словаря: {sum(1 for c in r['clusters'] if c['gap'])})")
    s = r["sentiment"]
    print(f"[analytics] тон дня: {s['today_score']} (+{s['today_pos']}/-{s['today_neg']}/±{s['today_neu']})")
    cred = r["credibility"]
    print(f"[analytics] источников в индексе: {len(cred)}")
    fc = r["forecast"][:5]
    for f_ in fc:
        print(f"   прогноз: {f_['name']:<26} {f_['direction']} (ожид. {f_['expected']}, {f_['confidence']})")


if __name__ == "__main__":
    main()
