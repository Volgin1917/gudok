#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dedup.py — Фаза 1 спринта: дедупликация перепечаток.

Одно событие, опубликованное несколькими источниками (СМИ + Telegram-каналы),
сворачивается в кластер: в дайджесте показывается «первичный» материал
(самый полный текст), остальные помечаются dup_of и выводятся как
«Также сообщили: …» — список источников.

Метод: токены (заголовок + начало текста) без стоп-слов, косинус/Жаккар
+ проверка вложенности заголовков; связность — union-find.
Трекер трендов намеренно считает ВСЕ записи (каскад перепечаток —
сам по себе сигнал важности темы), дедупликация влияет только на ленту.

Запуск: python3 dedup.py [--threshold 0.45]
"""
import argparse
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

import outlets as _outlets  # канонические издания: каналы одной редакции = один источник

STORE = os.path.join(BASE, "data", "store.jsonl")

STOP = set("""
и в во не что он на я с со как а то все она так его но да ты к у же вы за бы по
только ее мне было вот от меня еще нет о из ему теперь когда даже ну вдруг ли если
уже или ни быть был него до вас нибудь опять уж вам сказал сказала тоже себя ничего
ей может они тут где есть надо ней для мы тебя их чем была сам чтоб без будто чего
раз тоже себе под будет ж тогда кто этот того потому этого какой совсем ним
здесь этом один почти мой тем чтобы нее сейчас были куда зачем всех никогда можно
при наконец два об другой хоть после над больше тот через эти нас про всего них
какая много разве три эту моя впрочем хорошо свою этой перед иногда лучше чуть
том нельзя такой им более всегда конечно всю между это эти этот эта этих мочь
свой своем своём весь года году году лет дня день неделю сегодня вчера завтра
сейчас время регион области область ульяновск ульяновской ульяновска
""".split())

WORD_RE = re.compile(r"[a-zа-яё0-9]+", re.I)
EMOJI_RE = re.compile(
    "[" 
    "\U0001F300-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U0001F000-\U0001F0FF"
    "️⚡❗‼⭐✨⚠☝✍❤"
    "]+", flags=re.UNICODE)


def tokens(item):
    raw = f"{item.get('title','')} {item.get('text','')[:220]}".lower()
    raw = EMOJI_RE.sub(" ", raw)
    toks = [w for w in WORD_RE.findall(raw) if len(w) > 2 and w not in STOP]
    return set(toks), raw


def title_core(item):
    raw = EMOJI_RE.sub(" ", item.get("title", "").lower())
    return set(w for w in WORD_RE.findall(raw) if len(w) > 2 and w not in STOP)




# ─────────────────────────────────────────────────────────────────────────────
# Охранные правила склейки (Волна 4 «Инфопространства», пункт 7 спринта, 15.09).
# Метрика «устойчивость дедупликации» нашла 91 сомнительную склейку (36% дублей
# недели): разные эпизоды одного формуляра («Ракетная опасность» ↔ «Снят режим»),
# разные сутки прогнозов погоды, повторы внутри одного канала. Три правила:
#   1) антагонистичные формуляры («режим введён» ↔ «режим снят») не склеиваются
#      никогда — это противоположные сообщения, а не перепечатки;
#   2) служебные формуляры (оповещения о режимах, погода) склеиваются только
#      в пределах dedup_service_span_h (6 ч): текст у них идентичен сутки за сутками;
#   3) обычные материалы — в пределах dedup_max_span_h (24 ч), кроме дословных
#      повторов (Жаккар ≥ dedup_verbatim_jaccard, 0.85): медианная жизнь каскада
#      1,6 ч, перепечатка через двое суток — это уже другое событие или промо-повтор.
# Повтор внутри одного источника остаётся склеенным (чистота ленты), но помечается
# same_source=True и не попадает ни в «также сообщили», ни в каскады перепечаток.
# «Источник» здесь — ИЗДАНИЕ, а не канал (outlets.py, 15.09.2026): RSS ulpressa.ru
# и Telegram @ulpressa — одна редакция ООО «Симбирск-Паблисити», @ulgovru и
# @Russkih_Aleksey — одна пресс-служба исполнительной власти области. Повтор своего
# же материала в свой же канал независимым подтверждением не считается, поэтому
# cluster_src и «также сообщили» строятся по каноническим изданиям.
# Регулярки намеренно продублированы из analytics.py: dedup не импортирует аналитику
# (обратная зависимость), а совпадение словарей покрыто тестом.
# ─────────────────────────────────────────────────────────────────────────────
SERVICE_ALERT_RE = re.compile(
    r"(ракетн\w*|беспилотн\w*|бпла)\W{0,40}опасност|опасност\W{0,40}(бпла|беспилотн\w*|ракетн\w*)|"
    r"план\s*«?ковер|при[ёе]м и выпуск\W{0,30}ограничен|ограничени\w*\W{0,40}(аэропорт|при[ёе]м)|"
    r"аэропорт\w*\W{0,40}ограничен|\bсирены\b|воздушн\w+\s+тревог", re.I)
SERVICE_WEATHER_RE = re.compile(
    r"гидромет|прогноз\s+погод|погод\w+\s+на|заморозк|температур воздуха", re.I)
CASUALTY_RE = re.compile(r"погиб|пострада|ранен|убит|разруш|поврежд|сбит|упал|обломк", re.I)
ONSET_RE = re.compile(
    r"введ[её]н\w*|объявлен\w*|включ[её]н\w*|режим\s*«?(?:ракетн|беспилотн)|опасность|"
    r"ограничения на при[ёе]м|закрыт\w*|приостановлен\w*|отключен\w*|прекращен\w*|эвакуац\w*", re.I)
CANCEL_RE = re.compile(
    r"снят\s+режим|режим\s+снят|сняты|снято|снята\b|отменен\w*|отменён\w*|восстановлен\w*|"
    r"возобновлен\w*|возобновл[её]н\w*|заверш[её]н\w*|опасности нет|угроза миновала|"
    r"открыт\w*\s+после", re.I)

DEFAULTS = {"dedup_threshold": 0.45, "dedup_max_span_h": 24,
            "dedup_service_span_h": 6, "dedup_verbatim_jaccard": 0.85}


def src_key(it):
    """Ключ КАНАЛА: канал TG/VK или имя RSS-источника (для подписей карточек)."""
    return str(it.get("channel") or it.get("source") or "?")


def outlet_key(it):
    """Ключ ИЗДАНИЯ: каналы одной редакции (RSS + TG + сайт) дают один ключ.

    Именно он определяет независимость источника в метриках: cluster_src,
    «также сообщили», каскады перепечаток (outlets.py, sources_registry.json)."""
    return _outlets.outlet_key(it)


def outlet_name(it):
    """Подпись издания («Улпресса», а не «t.me/ulpressa»); для канала вне реестра —
    прежнее «t.me/канал», чтобы список «также сообщили» не терял тип источника."""
    return _outlets.outlet_label(it)


def service_kind(it):
    """«погода»/«оповещение» — служебный формуляр (иначе None). Зеркалит
    analytics.service_kind(): сообщение о последствиях — новость, а не уведомление."""
    blob = (it.get("title") or "") + " " + (it.get("text") or "")[:200]
    if SERVICE_WEATHER_RE.search(blob):
        return "погода"
    if SERVICE_ALERT_RE.search(blob) and not CASUALTY_RE.search(blob):
        return "оповещение"
    return None


def antagonistic(a, b):
    """Одно сообщение вводит режим/ограничение, второе его снимает. Текст отмены сам
    содержит слово «опасность», поэтому признак ввода гасится признаком отмены."""
    def blob(it):
        return f"{it.get('title') or ''} {(it.get('text') or '')[:200]}"

    def is_cancel(t):
        return bool(CANCEL_RE.search(t))

    def is_onset(t):
        return bool(ONSET_RE.search(t)) and not is_cancel(t)
    ta, tb = blob(a), blob(b)
    return bool((is_onset(ta) and is_cancel(tb)) or (is_onset(tb) and is_cancel(ta)))


def pub_dt(it):
    """Дата публикации в UTC (для измерения разброса внутри кластера)."""
    v = it.get("published")
    if not v:
        return None
    try:
        return datetime.fromisoformat(v)
    except (ValueError, TypeError):
        return None


def span_h(a, b):
    """Расстояние между публикациями в часах (None, если дату не прочитать)."""
    da, db = pub_dt(a), pub_dt(b)
    if not da or not db:
        return None
    return abs((da - db).total_seconds()) / 3600.0


def pair_jaccard(a, b):
    """Жаккар по токенам (без проверки вложенности заголовков) — для охраны «дословности»."""
    ta, tb = a[0], b[0]
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def mergeable(fa, fb, ia, ib, threshold, cfg):
    """Можно ли склеить пару. Возвращает (bool, причина_блокировки)."""
    if not similar(fa, fb, threshold):
        return False, ""
    if antagonistic(ia, ib):
        return False, "антагонизм формуляра"
    h = span_h(ia, ib)
    if h is not None:
        service = bool(service_kind(ia)) or bool(service_kind(ib))
        limit = cfg.get("dedup_service_span_h") if service else cfg.get("dedup_max_span_h")
        if h > limit:
            if service or pair_jaccard(fa, fb) < cfg.get("dedup_verbatim_jaccard"):
                return False, ("служебный формуляр вне окна" if service else "вне окна перепечаток")
    return True, ""
def similar(a, b, threshold):
    ta, tb = a[0], b[0]
    if not ta or not tb:
        return False
    inter = len(ta & tb)
    jacc = inter / len(ta | tb)
    if jacc >= threshold:
        return True
    # вложенность заголовков: один почти полностью содержится в другом
    ca, cb = a[2], b[2]
    if ca and cb:
        cont = len(ca & cb) / min(len(ca), len(cb))
        if cont >= 0.85 and jacc >= threshold * 0.6:
            return True
    return False


class DSU:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra


def primary_score(it):
    """Первичным считаем самый полный и ранний материал."""
    s = len(it.get("text") or "")
    pub = it.get("published")
    if pub:
        try:
            # более ранние получают бонус до +200
            dt = datetime.fromisoformat(pub)
            s += max(0, 200 - int((datetime.now(dt.tzinfo) - dt).total_seconds() / 3600))
        except ValueError:
            pass
    if it.get("source_type") == "tg":
        s -= 60  # посты короче и разговорнее — приоритет полноценным статьям
    if it.get("views"):
        s += min(it["views"] / 1000.0, 40)  # самую читаемую копию — в первичные
    tier = it.get("tier")
    if tier == 1:
        s += 240  # официальные/верифицированные — предпочитаемый первичный источник
    elif tier == 3:
        s -= 120  # анонимы и сатира — в конце очереди
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--threshold", type=float, default=None)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    with open(os.path.join(BASE, "config.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    settings = cfg.get("settings") or {}
    dcfg = dict(DEFAULTS)
    dcfg.update({k: settings[k] for k in DEFAULTS if k in settings})
    if args.threshold:
        dcfg["dedup_threshold"] = args.threshold
    threshold = dcfg["dedup_threshold"]

    with open(STORE, encoding="utf-8") as f:
        items = [json.loads(l) for l in f if l.strip()]

    # сброс предыдущей разметки
    for it in items:
        it.pop("dup_of", None)
        it.pop("also_in", None)
        it.pop("cluster", None)
        it.pop("cluster_src", None)
        it.pop("same_source", None)

    feats = []
    for it in items:
        toks, raw = tokens(it)
        feats.append((toks, raw, title_core(it)))

    n = len(items)
    dsu = DSU(n)
    blocked = Counter()
    # предварительный фильтр: пары дальше 14 суток не сравниваем вовсе (окно перепечаток)
    hard_span = max(dcfg["dedup_max_span_h"], dcfg["dedup_service_span_h"]) * 14
    for i in range(n):
        for j in range(i + 1, n):
            h = span_h(items[i], items[j])
            if h is not None and h > hard_span:
                continue
            ok, why = mergeable(feats[i], feats[j], items[i], items[j], threshold, dcfg)
            if ok:
                dsu.union(i, j)
            elif why:
                blocked[why] += 1

    clusters = {}
    for i in range(n):
        clusters.setdefault(dsu.find(i), []).append(i)

    n_dup = n_same = 0
    for members in clusters.values():
        if len(members) < 2:
            continue
        members.sort(key=lambda i: primary_score(items[i]), reverse=True)
        head = members[0]
        head_out = outlet_key(items[head])
        items[head]["cluster"] = len(members)
        # «также сообщили» — только ДРУГИЕ ИЗДАНИЯ: повтор своего же материала
        # (в своём канале или в TG той же редакции) перепечаткой не считается
        others = {outlet_key(items[m]) for m in members[1:]} - {head_out}
        # подписи — канонические имена изданий («Улпресса», «Репортёр73»), а не
        # «t.me/канал»: одна редакция в списке «также сообщили» — одна строка
        items[head]["also_in"] = sorted({outlet_name(items[m]) for m in members[1:]
                                         if outlet_key(items[m]) != head_out})
        items[head]["cluster_src"] = len(others) + 1
        for m in members[1:]:
            items[m]["dup_of"] = items[head]["id"]
            items[m]["same_source"] = outlet_key(items[m]) == head_out
            n_dup += 1
            n_same += items[m]["same_source"]

    with open(STORE, "w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")

    if not args.quiet:
        mult = [c for c in clusters.values() if len(c) > 1]
        print(f"[dedup] кластеров перепечаток: {len(mult)}, скрыто дублей: {n_dup} из {n} "
              f"(порог {threshold}, окно {dcfg['dedup_max_span_h']} ч, "
              f"служебные {dcfg['dedup_service_span_h']} ч, дословные {dcfg['dedup_verbatim_jaccard']})")
        print(f"[dedup] из дублей повторов своего же издания (канал той же редакции): {n_same} — в каскады не засчитаны")
        if blocked:
            print("[dedup] заблокировано склеек: "
                  + ", ".join(f"{k} — {v}" for k, v in blocked.most_common()))
        for c in sorted(mult, key=len, reverse=True)[:5]:
            head = max(c, key=lambda i: primary_score(items[i]))
            print(f"  • ×{len(c)}: {items[head]['title'][:70]}")


if __name__ == "__main__":
    main()
