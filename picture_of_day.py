#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
picture_of_day.py — модуль «Гудок. Картина дня».

Ежедневная генерация ИЗОБРАЖЕНИЯ (художественно-аналитической «картины дня»)
через Yandex ART из структурированного брифа дня: кластеры событий,
противоречия (gap-кластеры), силы и агентность (w4), сеттеры, тон, каскады.

Философия модуля (см. документ «Картина дня»):
  - содержание одно (события дня), форма каждый раз иная — визуальный стиль
    выбирается из пресетов (конструктивизм / соцплакат / инфографика /
    карикатура / абстрактная метафора);
  - система эволюционирует: веса стилей пересчитываются по отклику аудитории
    (data/picture_weights.json), петля обратной связи работает офлайн.

Генерация — внешний сетевой вызов к Yandex ART (Foundation Models async API).
Это исключение из правила «только stdlib» (AGENTS.md): разрешены внешние
зависимости/сетевые вызовы для модулей генерации; секрет — только через
env GUDOK_ART_API_KEY или файл data/art_token (.gitignore). Без ключа модуль
мягко пропускает генерацию (как tg_publish без токена) — сборка и тесты не падают.

Вывод: публикация фото в Telegram-канал (config.telegram.channel) через
tg_publish.send_photo. Публичной страницы-архива в v1 нет — история хранится
в data/pictures_of_day.jsonl.

Режимы:
  python3 picture_of_day.py --publish            # собрать бриф, сгенерировать, опубликовать
  python3 picture_of_day.py --date 2026-09-30    # за конкретную дату
  python3 picture_of_day.py --style caricature   # принудительно задать стиль
  python3 picture_of_day.py --dry-run            # показать бриф+prompt, без вызова API и без отправки
  python3 picture_of_day.py --evolve             # пересчитать веса стилей по накопленному отклику
  python3 picture_of_day.py --show-brief         # только вывести бриф дня
"""

import argparse
import base64
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

BASE = os.path.dirname(os.path.abspath(__file__))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

import generate  # noqa: E402  (load_json / load_store — те же источники, что у конвейера)
import tg_publish  # noqa: E402  (send_photo, state_mark, state_has — публикация в канал)

DATA = os.path.join(BASE, "data")
UTC4 = timezone(timedelta(hours=4))

# ------------------------------------------------------------------ настройки
PICTURES_DIR = os.path.join(DATA, "pictures")
JSONL = os.path.join(DATA, "pictures_of_day.jsonl")
WEIGHTS = os.path.join(DATA, "picture_weights.json")
ART_TOKEN_FILE = os.path.join(DATA, "art_token")

ART_MODEL = os.environ.get("GUDOK_ART_MODEL") or "art://b1gqcuqmnbmajes3scqi/yandex-art-2.0"
# Канонический хост Foundation Models API (резолвится). Указанный в брифе
# foundation-models.serverless.yandexcloud.net не существует (DNS NXDOMAIN) —
# при необходимости переопределить через GUDOK_ART_ENDPOINT.
ART_ENDPOINT = (os.environ.get("GUDOK_ART_ENDPOINT")
                or "https://llm.api.cloud.yandex.net/foundationModels/v1/imageGenerationAsync")
ART_OPS_BASE = (os.environ.get("GUDOK_ART_OPS_URL")
                or "https://operation.api.cloud.yandex.net/operations/")
ART_TIMEOUT = int(os.environ.get("GUDOK_ART_TIMEOUT", "180"))   # сек на генерацию
ART_POLL = int(os.environ.get("GUDOK_ART_POLL", "5"))           # сек между опросами
GEN_W = int(os.environ.get("GUDOK_ART_W", "1024"))
GEN_H = int(os.environ.get("GUDOK_ART_H", "1024"))

SYSTEM_FRAMING = (
    "Критический взгляд: за событиями — структуры власти, интересы и противоречия. "
    "Без текста на изображении, только символы и композиция."
)


# ------------------------------------------------------------------ визуальные пресеты
# Каждый стиль = визуальное описание для промпта + «линза» (что подчеркнуть из брифа).
STYLES = {
    "constructivism": {
        "name_ru": "конструктивизм 1920-х",
        "visual": "стиль конструктивизма 1920-х: геометрия, диагональные композиции, "
                  "красный и чёрный, лозунговая графика, плакатная типографика форм",
        "lens": "динамика и столкновение сил, ритм масс",
    },
    "social_poster": {
        "name_ru": "советский социальный плакат",
        "visual": "советский социальный плакат: крупная обобщённая фигура, "
                  "монументальный жест, тёплый охристо-красный колорит, призывная метафора",
        "lens": "народ/трудящиеся против абстрактной власти",
    },
    "infographic": {
        "name_ru": "аналитическая инфографика",
        "visual": "аналитическая инфографика: схема потоков и связей, чистые цветовые блоки, "
                  "условные значки, минималистичная диаграмма",
        "lens": "структура информационного поля и связи событий",
    },
    "caricature": {
        "name_ru": "политическая карикатура",
        "visual": "политическая карикатура: гротескные фигуры, символы власти, денег и "
                  "бюрократии, экспрессивный штрих, сатирическая гипербола",
        "lens": "вскрыть лицемерие и интересы тех, кто за событиями",
    },
    "abstract_metaphor": {
        "name_ru": "абстрактная метафора",
        "visual": "абстрактная метафора: стихия, свет и тень, символические формы, "
                  "экспрессионистская фактура, мрачноватая атмосфера",
        "lens": "настроение и тон дня, скрытые тревоги",
    },
}
DEFAULT_STYLE = "constructivism"


# ------------------------------------------------------------------ секрет
def art_token():
    """Api-Key Yandex ART: env GUDOK_ART_API_KEY или файл data/art_token (.gitignore)."""
    tok = (os.environ.get("GUDOK_ART_API_KEY") or "").strip()
    if tok:
        return tok
    try:
        with open(ART_TOKEN_FILE, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


# ------------------------------------------------------------------ сборка брифа
def _ru_month(d):
    mr = ["января", "февраля", "марта", "апреля", "мая", "июня",
          "июля", "августа", "сентября", "октября", "ноября", "декабря"]
    return f"{d.day} {mr[d.month - 1]} {d.year} г."


def build_brief(date_str=None):
    """Структурированный «бриф дня» из уже посчитанных analytics.json / infospace.json.

    Возвращает dict с читаемыми полями: кластеры (и противоречия),
    тон, фреймы w4, роли агентности, сеттеры, каскады, выводы.
    """
    now = datetime.now(UTC4)
    day = _parse_day(date_str) if date_str else now.date()
    an = generate.load_json(os.path.join(DATA, "analytics.json")) or {}
    info = generate.load_json(os.path.join(DATA, "infospace.json")) or {}

    clusters = []
    for c in (an.get("clusters") or []):
        clusters.append({
            "name": c.get("name", ""),
            "size": c.get("size", 0),
            "coverage": c.get("coverage", 0.0),
            "gap": bool(c.get("gap")),
            "terms": c.get("terms", [])[:5],
            "top": (c.get("samples") or [{}])[0].get("title", "") if c.get("samples") else "",
        })
    clusters.sort(key=lambda x: (x["size"], x["coverage"]), reverse=True)

    sentiment = an.get("sentiment") or {}
    tone_score = sentiment.get("today_score")
    tone_by_cat = sentiment.get("by_category") or {}

    w4 = (info.get("w4") or {})
    frames = ((w4.get("frames") or {}).get("frame_mix") or {})
    agency_roles = ((w4.get("agency") or {}).get("roles") or {})

    setters = [{"name": s[0], "count": s[1]} for s in (info.get("setters") or [])][:6]
    cascades = [{"title": c.get("title", ""), "size": c.get("size", 0),
                 "sources": c.get("sources", 0)} for c in (info.get("cascades") or [])][:5]
    conclusions = info.get("conclusions") or []
    if isinstance(conclusions, str):
        conclusions = [conclusions]

    contradictions = [c["name"] for c in clusters if c["gap"]]

    return {
        "date_iso": day.isoformat(),
        "date_ru": _ru_month(day),
        "clusters": clusters,
        "contradictions": contradictions,
        "tone_score": tone_score,
        "tone_by_cat": tone_by_cat,
        "frames": frames,
        "agency_roles": agency_roles,
        "setters": setters,
        "cascades": cascades,
        "conclusions": conclusions,
    }


def _frame_phrase(frames):
    if not frames:
        return "информационное поле разнородно"
    top = sorted(frames.items(), key=lambda kv: kv[1], reverse=True)[:3]
    names = {
        "тревога": "тревога", "ЧП": "чрезвычайные происшествия",
        "работы": "дела повседневные", "надзор": "надзор и проверки",
        "услуга": "услуги", "достижение": "достижения", "ритуал": "ритуалы",
        "статистика": "статистика", "жалоба": "жалобы", "погода": "погода",
        "лайв": "прямые эфиры", "интерактив": "интерактив", "прочее": "прочее",
    }
    return ", ".join(names.get(k, k) for k, _ in top)


def _agency_phrase(roles):
    if not roles:
        return ""
    subj = roles.get("субъект", 0)
    obj = roles.get("объект", 0)
    no_actor = roles.get("без актора", 0)
    if no_actor and no_actor >= max(subj, obj, 1):
        return "главные действующие лица часто скрыты — события без актора"
    if subj >= obj:
        return "действующие субъекты заявляют о себе прямо"
    return "акцент на объектах воздействия, а не на тех, кто действует"


# ------------------------------------------------------------------ промпт
def brief_to_prompt(brief, style):
    """Перевод структурированного брифа + визуального стиля в русскоязычный prompt Yandex ART."""
    st = STYLES.get(style, STYLES[DEFAULT_STYLE])
    parts = []

    if brief["clusters"]:
        top = brief["clusters"][0]
        terms = ", ".join(top["terms"]) if top["terms"] else top["name"]
        parts.append(f"Центр дня — «{top['name']}» (ключевое: {terms})")
    if brief["contradictions"]:
        parts.append("заметны противоречия: " + "; ".join(brief["contradictions"][:3]))
    fp = _frame_phrase(brief["frames"])
    parts.append(f"в инфополе преобладают: {fp}")
    ap = _agency_phrase(brief["agency_roles"])
    if ap:
        parts.append(ap)
    if brief["cascades"]:
        parts.append(f"крупный инфо-каскад: «{brief['cascades'][0]['title']}»")
    tone = brief["tone_score"]
    if tone is not None:
        mood = "тревожный" if tone < -0.1 else ("спокойный" if tone > 0.1 else "нейтральный")
        parts.append(f"общий тон дня — {mood} (индекс {tone})")

    subject = ". ".join(parts).strip()
    if subject:
        subject = subject[0].upper() + subject[1:]
    else:
        subject = "информационная картина дня региона"

    prompt = (
        f"{st['visual']}. "
        f"Сюжет: {subject}. "
        f"Композиционный акцент — {st['lens']}. "
        f"{SYSTEM_FRAMING}"
    )
    return prompt


def caption_for(brief, style):
    """Короткая подпись-интерпретация (без LLM), самодостаточная для Telegram."""
    st = STYLES.get(style, STYLES[DEFAULT_STYLE])
    lines = [f"🖼 Картина дня · {brief['date_ru']}", f"Стиль: {st['name_ru']}"]
    if brief["clusters"]:
        lines.append(f"Главное: {brief['clusters'][0]['name']}")
    if brief["contradictions"]:
        lines.append(f"Противоречие: {brief['contradictions'][0]}")
    if brief["cascades"]:
        lines.append(f"Каскад: {brief['cascades'][0]['title']}")
    lines.append("#Гудок #КартинаДня")
    return "\n".join(lines)


# ------------------------------------------------------------------ выбор стиля
def load_weights():
    try:
        with open(WEIGHTS, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def choose_style(override=None, seed=None, weights=None):
    """Выбор стиля: либо принудительно (override), либо взвешенно по эволюционирующим весам.

    weights — dict {style: {"weight": float}}; при отсутствии — равномерно.
    seed — для детерминизма в тестах.
    """
    if override and override in STYLES:
        return override
    rng = random.Random(seed)
    wmap = weights or load_weights()
    items = []
    for s in STYLES:
        ws = (wmap.get(s) or {}).get("weight")
        if ws is None:
            ws = 1.0
        if ws <= 0:
            ws = 0.0001
        items.append((s, ws))
    total = sum(w for _, w in items)
    r = rng.random() * total
    cum = 0.0
    for s, w in items:
        cum += w
        if r <= cum:
            return s
    return items[-1][0]


# ------------------------------------------------------------------ генерация (Yandex ART)
def _http_json(url, payload, headers, timeout):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            return {"error": f"HTTP {e.code}"}
    except urllib.error.URLError as e:
        return {"error": str(e.reason)}


def _http_get_json(url, headers, timeout):
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            return {"error": f"HTTP {e.code}"}
    except urllib.error.URLError as e:
        return {"error": str(e.reason)}


def _extract_op_id(resp):
    for k in ("id", "operationId", "operation_id", "operation"):
        v = resp.get(k)
        if v:
            v = str(v)
            if v.startswith("operations/"):
                v = v[len("operations/"):]
            if v.startswith("operations\\"):
                v = v[len("operations\\"):]
            return v
    return None


def _extract_image(resp):
    """Толерантный разбор финального ответа операции (вариативный формат)."""
    if not isinstance(resp, dict):
        return None
    r = resp.get("response") or resp
    # вариант 1: response.image (base64)
    if isinstance(r, dict) and r.get("image"):
        return r["image"]
    # вариант 2: response.images[0]
    if isinstance(r, dict) and isinstance(r.get("images"), list) and r["images"]:
        return r["images"][0]
    # вариант 3: верхнеуровневый image / result
    if resp.get("image"):
        return resp["image"]
    if resp.get("result"):
        return resp["result"]
    return None


def _is_transient(marker):
    """Транзиентные/инфраструктурные сбои Yandex ART, при которых ретрай безопасен."""
    if marker is None:
        return False
    s = str(marker).lower()
    return ("failed to execute calls to all endpoints" in s
            or "unavailable" in s or "internal" in s or "code 13" in s
            or "timeout" in s or "429" in s or "rate" in s)


def _gen_once(prompt, model, headers, timeout, poll):
    """Один проход генерации: init + опрос операции. Возвращает bytes или поднимает RuntimeError."""
    body = {
        "modelUri": model,
        "messages": [{"role": "user", "text": prompt}],
        "image": {"width": GEN_W, "height": GEN_H},
    }
    resp = _http_json(ART_ENDPOINT, body, headers, timeout)
    if resp.get("error"):
        raise RuntimeError(f"Yandex ART init error: {resp['error']}")
    op_id = _extract_op_id(resp)
    if not op_id:
        raise RuntimeError(f"Yandex ART: не найден id операции в ответе: {resp}")
    ops_url = ART_OPS_BASE.rstrip("/") + "/" + op_id
    deadline = time.time() + timeout
    while True:
        time.sleep(poll)
        r = _http_get_json(ops_url, headers, timeout)
        if r.get("error"):
            raise RuntimeError(f"Yandex ART poll error: {r['error']}")
        if r.get("done") or r.get("status") == "DONE" or r.get("finished"):
            b64 = _extract_image(r)
            if not b64:
                raise RuntimeError(f"Yandex ART: изображение не найдено в ответе: {r}")
            try:
                return base64.b64decode(b64)
            except Exception as e:
                raise RuntimeError(f"Yandex ART: неверный base64: {e}")
        if time.time() > deadline:
            raise RuntimeError("Yandex ART: превышен таймаут генерации")


def generate_image(prompt, model=None, timeout=ART_TIMEOUT, poll=ART_POLL,
                   retries=None, backoff=None, quiet=False):
    """Асинхронная генерация через Yandex ART с ретраем транзиентных сбоев.

    Yandex ART работает асинхронно; ошибка исполнения code 13
    («failed to execute calls to all endpoints») обычно транзиентна и лечится
    повтором. retries/backoff — через env GUDOK_ART_RETRIES / GUDOK_ART_BACKOFF
    (по умолчанию 3 и 8с, экспоненциально). Возвращает bytes PNG.
    """
    tok = art_token()
    if not tok:
        raise RuntimeError("GUDOK_ART_API_KEY / data/art_token не задан — генерация невозможна")
    model = model or ART_MODEL
    headers = {"Authorization": f"Api-Key {tok}", "Content-Type": "application/json"}
    if retries is None:
        retries = int(os.environ.get("GUDOK_ART_RETRIES", "3"))
    if backoff is None:
        backoff = int(os.environ.get("GUDOK_ART_BACKOFF", "8"))
    last = None
    for attempt in range(1, retries + 2):  # первая попытка + retries повторов
        try:
            return _gen_once(prompt, model, headers, timeout, poll)
        except RuntimeError as e:
            last = e
            if not _is_transient(e):
                raise  # не транзиентно (например, нет ключа/нет модели) — не ретраим
            if attempt > retries:
                break
            wait = backoff * (2 ** (attempt - 1))
            if not quiet:
                print(f"[picture] Yandex ART: транзиентный сбой ({e}); повтор через {wait}с "
                      f"(попытка {attempt}/{retries})")
            time.sleep(wait)
    raise last or RuntimeError("Yandex ART: неизвестная ошибка")


def save_image(data_bytes, date_str, style):
    os.makedirs(PICTURES_DIR, exist_ok=True)
    safe = re.sub(r"[^0-9a-zA-Z_]", "", f"{date_str}_{style}")
    path = os.path.join(PICTURES_DIR, f"picture_{safe}.png")
    with open(path, "wb") as f:
        f.write(data_bytes)
    return path


# ------------------------------------------------------------------ запись истории
def record(rec):
    os.makedirs(DATA, exist_ok=True)
    with open(JSONL, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def load_records():
    out = []
    if os.path.exists(JSONL):
        with open(JSONL, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    return out


# ------------------------------------------------------------------ эволюция весов
def compute_score(rec):
    """Сигнал качества стиля по отклику. Без метрик — нейтральная единица."""
    views = rec.get("views") or 0
    forwards = rec.get("forwards") or 0
    reactions = rec.get("reactions") or 0
    if not (views or forwards or reactions):
        return 1.0
    # простая нормировка: репосты и реакции весят выше просмотров
    return 1.0 + min(views, 5000) / 5000.0 + 2.0 * (forwards > 0) + 1.5 * (reactions > 0)


def update_weights(records=None):
    """Пересчёт весов стилей по накопленному отклику -> data/picture_weights.json."""
    records = records if records is not None else load_records()
    stats = {s: {"count": 0, "sum": 0.0} for s in STYLES}
    for rec in records:
        s = rec.get("style")
        if s not in stats:
            continue
        sc = compute_score(rec)
        stats[s]["count"] += 1
        stats[s]["sum"] += sc
    # усреднённый балл со сглаживанием (лапласово: +1 к count), затем softmax
    avgs = {}
    for s, st in stats.items():
        if st["count"] == 0:
            avgs[s] = 0.0
        else:
            avgs[s] = st["sum"] / st["count"]
    # softmax по (avg + log(count+1)) — баланс между качеством и частотой
    raw = {s: avgs[s] + 0.3 * (stats[s]["count"] ** 0.5) for s in avgs}
    mx = max(raw.values())
    exps = {s: __import__("math").exp(raw[s] - mx) for s in raw}
    tot = sum(exps.values())
    out = {}
    for s in STYLES:
        out[s] = {
            "count": stats[s]["count"],
            "avg_score": round(avgs[s], 4),
            "weight": round(exps[s] / tot, 4),
        }
    os.makedirs(DATA, exist_ok=True)
    with open(WEIGHTS, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    return out


# ------------------------------------------------------------------ публикация
def publish(date_str, style, image_path, caption, cfg, chat=None, dry_run=False,
            record_state=True, force=False, quiet=False):
    tg = cfg.get("telegram") or {}
    chat = chat or tg.get("channel") or ""
    if dry_run:
        if not quiet:
            print(f"[picture] dry-run: публикация в «{chat or '<канал не задан>'}' пропущена")
        return True
    if not chat:
        if not quiet:
            print("[picture] канал не задан (telegram.channel или --chat) — пропуск")
        return False
    key = f"picture:{date_str}:{chat}"
    if record_state and tg_publish.state_has(key) and not force:
        if not quiet:
            print(f"[picture] картина {date_str} уже публиковалась в {chat} — пропуск")
        return False
    ok = tg_publish.send_photo(chat, image_path, caption, quiet=quiet)
    if ok and record_state:
        tg_publish.state_mark(key)
    if ok and not quiet:
        print(f"[picture] картина {date_str} ({style}) опубликована в {chat}")
    return bool(ok)


# ------------------------------------------------------------------ оркестрация
def run(date_str=None, style=None, chat=None, dry_run=False, publish=False,
        force=False, quiet=False, cfg=None):
    cfg = cfg or generate.load_json(os.path.join(BASE, "config.json")) or {}
    brief = build_brief(date_str)
    weights = load_weights()
    chosen = choose_style(override=style, weights=weights)
    prompt = brief_to_prompt(brief, chosen)
    caption = caption_for(brief, chosen)

    if dry_run or not publish:
        if not quiet:
            print("═" * 60)
            print(f"Дата:     {brief['date_ru']}  ({brief['date_iso']})")
            print(f"Стиль:    {STYLES[chosen]['name_ru']}  [{chosen}]")
            print(f"Кластеры: {len(brief['clusters'])}  | противоречия: {len(brief['contradictions'])}")
            if brief["clusters"]:
                print(f"  главный: {brief['clusters'][0]['name']}")
            if brief["contradictions"]:
                print(f"  против:  {brief['contradictions'][0]}")
            print("─" * 60)
            print("PROMPT:")
            print(prompt)
            print("─" * 60)
            print("CAPTION:")
            print(caption)
            if publish and not dry_run:
                pass
        if not publish:
            # просто показали бриф/промпт (--dry-run или без --publish)
            return {"brief": brief, "style": chosen, "prompt": prompt, "caption": caption}

    # публикация / генерация
    try:
        img = generate_image(prompt)
    except RuntimeError as e:
        if not quiet:
            print(f"[picture] генерация пропущена: {e}")
        return {"brief": brief, "style": chosen, "prompt": prompt, "caption": caption,
                "error": str(e)}
    image_path = save_image(img, brief["date_iso"], chosen)
    rec = {
        "date": brief["date_iso"],
        "style": chosen,
        "prompt": prompt,
        "image": os.path.relpath(image_path, BASE),
        "caption": caption,
        "views": 0, "forwards": 0, "reactions": 0,
    }
    record(rec)
    result = {"brief": brief, "style": chosen, "prompt": prompt,
              "caption": caption, "image": image_path}
    if publish:
        ok = publish(date_str=brief["date_iso"], style=chosen, image_path=image_path,
                     caption=caption, cfg=cfg, chat=chat, dry_run=dry_run,
                     force=force, quiet=quiet)
        result["published"] = ok
    else:
        if not quiet:
            print(f"[picture] изображение сохранено: {image_path}")
    return result


def _parse_day(s):
    return datetime.strptime(s, "%Y-%m-%d").date()


# ------------------------------------------------------------------ CLI
def _fix_stdout():
    """Безопасный UTF-8 вывод (Windows-консоль иначе падает на нетипографике)."""
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (OSError, ValueError):
        pass


def main():
    _fix_stdout()
    ap = argparse.ArgumentParser(description="Гудок. Картина дня (Yandex ART)")
    ap.add_argument("--date", help="дата YYYY-MM-DD (по умолчанию — сегодня)")
    ap.add_argument("--style", help="принудительный стиль: " + ", ".join(STYLES))
    ap.add_argument("--chat", help="чат/канал для публикации (перекрывает config)")
    ap.add_argument("--publish", action="store_true", help="сгенерировать и опубликовать в Telegram")
    ap.add_argument("--dry-run", action="store_true", help="только бриф+prompt, без API и отправки")
    ap.add_argument("--show-brief", action="store_true", help="вывести только бриф дня")
    ap.add_argument("--evolve", action="store_true", help="пересчитать веса стилей по отклику")
    ap.add_argument("--force", action="store_true", help="не пропускать по состоянию публикаций")
    ap.add_argument("--quiet", action="store_true", help="минимум вывода")
    args = ap.parse_args()

    if args.evolve:
        w = update_weights()
        if not args.quiet:
            print("[picture] пересчёт весов стилей:")
            for s, v in sorted(w.items(), key=lambda kv: -kv[1]["weight"]):
                print(f"  {s:18s} weight={v['weight']:.3f} count={v['count']} avg={v['avg_score']:.2f}")
        return

    if args.show_brief:
        b = build_brief(args.date)
        print(json.dumps(b, ensure_ascii=False, indent=1, default=str))
        return

    run(date_str=args.date, style=args.style, chat=args.chat,
        dry_run=args.dry_run, publish=args.publish, force=args.force,
        quiet=args.quiet)


if __name__ == "__main__":
    main()
