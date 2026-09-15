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
import json
import math
import os
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

BASE = os.path.dirname(os.path.abspath(__file__))
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
        src = it.get("channel") or it.get("source") or "?"
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
        if it.get("cluster") and it["cluster"] >= 2:
            setters[it.get("channel") or it.get("source") or "?"] += 1
            cascades.append({"size": it["cluster"], "title": it["title"][:100],
                             "source": it.get("channel") or it.get("source"),
                             "also": it.get("also_in", [])[:4], "url": it.get("url") or ""})
    cascades.sort(key=lambda c: -c["size"])

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
            src = it.get("channel") or it.get("source") or "?"
            srcs.add(src)
            if src in muni_src:
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
    src_counter_all = Counter(it.get("channel") or it.get("source") or "?" for it in week)
    top3 = sum(n for _, n in src_counter_all.most_common(3))
    concentration = round(top3 / len(week) * 100) if week else 0
    casc_sizes = [it["cluster"] for it in primaries if it.get("cluster") and it["cluster"] >= 2]
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
        cl = it.get("cluster") or 0
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
    zh_src = Counter((it.get("channel") or it.get("source") or "?") for it in zh_prim)
    out["zhkh"] = {"n": len(zh), "share": round(len(zh) / len(week), 3),
                   "tone": round(sum(zh_tones) / len(zh_tones), 3) if zh_tones else None,
                   "top_sources": zh_src.most_common(3)}

    # 10) федеральное эхо в разрезе источников (топ-8 по объёму первичных)
    src_prim = Counter()
    src_fed = Counter()
    for it in primaries:
        s = it.get("channel") or it.get("source") or "?"
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

    return out


def esc_(v):
    return str(v)



# ---------------------------------------------------------------- build all
def build_all(items, trends, cfg=None):
    now = datetime.now(UTC4)
    infospace = build_infospace(items, trends, cfg)
    try:
        infospace["w1"] = build_infospace_ext(items, trends, cfg)
    except Exception:
        infospace["w1"] = {}
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
