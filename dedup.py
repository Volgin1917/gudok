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
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
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
    threshold = args.threshold or cfg["settings"].get("dedup_threshold", 0.45)

    with open(STORE, encoding="utf-8") as f:
        items = [json.loads(l) for l in f if l.strip()]

    # сброс предыдущей разметки
    for it in items:
        it.pop("dup_of", None)
        it.pop("also_in", None)
        it.pop("cluster", None)

    feats = []
    for it in items:
        toks, raw = tokens(it)
        feats.append((toks, raw, title_core(it)))

    n = len(items)
    dsu = DSU(n)
    # сравниваем только пары в пределах ±3 суток (окно перепечаток)
    def day(it):
        return (it.get("published") or "")[:10]
    for i in range(n):
        di = day(items[i])
        for j in range(i + 1, n):
            dj = day(items[j])
            if di and dj:
                diff = abs(int(dj.replace("-", "")) - int(di.replace("-", "")))
                if diff > 100:  # грубый фильтр по номеру даты (в пределах месяца+)
                    continue
            if similar(feats[i], feats[j], threshold):
                dsu.union(i, j)

    clusters = {}
    for i in range(n):
        clusters.setdefault(dsu.find(i), []).append(i)

    n_dup = 0
    for members in clusters.values():
        if len(members) < 2:
            continue
        members.sort(key=lambda i: primary_score(items[i]), reverse=True)
        head = members[0]
        items[head]["cluster"] = len(members)
        also = sorted({items[m].get("source", "?") for m in members[1:]})
        items[head]["also_in"] = also
        for m in members[1:]:
            items[m]["dup_of"] = items[head]["id"]
            n_dup += 1

    with open(STORE, "w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")

    if not args.quiet:
        mult = [c for c in clusters.values() if len(c) > 1]
        print(f"[dedup] кластеров перепечаток: {len(mult)}, скрыто дублей: {n_dup} из {n}")
        for c in sorted(mult, key=len, reverse=True)[:5]:
            head = max(c, key=lambda i: primary_score(items[i]))
            print(f"  • ×{len(c)}: {items[head]['title'][:70]}")


if __name__ == "__main__":
    main()
