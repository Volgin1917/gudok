#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
seed_sources_registry.py — построение/обновление реестра источников sources_registry.json.

Реестр — справочник для метрик «Инфопространства» (Волна 2): уровень T1–T3, тип
производителя, территория, владелец, признак «своего голоса», флаг платного освещения.
Канонический список каналов/лент — config.json; реестр не заменяет его, а дополняет
атрибутами, которые не знает конвейер.

Запуск:
  python3 seed_sources_registry.py            # создать/обновить (ручные поля сохраняются)
Принцип слияния: скрипт обновляет структурные поля (tier, enabled, kind) из config.json,
ручные поля (owner, producer_type, territory, notes…) сохраняются, если уже заполнены;
для нового источника подставляет значения из встроенного справочника KNOWN ниже.
"""
import json
import os
from datetime import datetime, timedelta, timezone

BASE = os.path.dirname(os.path.abspath(__file__))
UTC4 = timezone(timedelta(hours=4))

# producer_type: пресс-служба | редакция | агрегатор | авторский канал | промо/коммерция
# owner_status: подтверждён | уточнить (ручная верификация по ЕГРЮЛ/реестру СМИ — Волна 3)
KNOWN = {
    # ── tier 1: официальные и СМИ ──
    "tg:Russkih_Aleksey":   ("пресс-служба", "область",      "Губернатор А. Русских (пресс-служба)", "подтверждён", ""),
    "tg:ulgovru":           ("пресс-служба", "область",      "Правительство Ульяновской области", "подтверждён", ""),
    "tg:A_Boldakin":        ("пресс-служба", "Ульяновск",    "Глава г. Ульяновска А. Болдакин", "подтверждён", ""),
    "tg:ulmeria":           ("пресс-служба", "Ульяновск",    "Администрация г. Ульяновска", "подтверждён", "отключён как источник"),
    "tg:ulpressa":          ("редакция",     "область",      "ООО «Симбирск-Паблисити» (ИНН 7325027230)", "подтверждён", "TG редакции ulpressa.ru; верифицировано 15.09.2026 (imprint + ЕГРЮЛ) — owner_verification.md"),
    "tg:ulpravda":          ("редакция",     "область",      "ОГАУ ИД «Ульяновская правда» (ИНН 7325043842)", "подтверждён", "госучреждение области (ОГРН 1037300995082, 391 чел.); не одно юрлицо с ООО «Симбирск-Паблисити» (ulpressa.ru) — аффилированность по персоналиям уточнить"),
    "tg:reporter73":        ("редакция",     "область",      "ООО «Репортер 73» (ИНН 7325140155)", "подтверждён", "региональный телеканал (21-я кнопка); ОГРН 1157325006486, с 10.2015; верифицировано 15.09.2026 (imprint reporter73.tv + ЕГРЮЛ)"),
    "tg:sergeymorozov73":   ("пресс-служба", "область",      "Депутат Госдумы С. Морозов", "подтверждён", ""),
    "tg:vmkononov":         ("пресс-служба", "область",      "Депутат Госдумы В. Кононов", "подтверждён", ""),
    "tg:UAZ_Today":         ("пресс-служба", "Ульяновск",    "ПАО «УАЗ» (Соллерс)", "подтверждён", ""),
    "tg:uac_ru":            ("пресс-служба", "Ульяновск",    "ПАО «ОАК» (ИНН 7708619320)", "подтверждён", "«Авиастар-СП» — площадка в структуре ПАО «ОАК»; ОГРН 1067759884598; верифицировано 15.09.2026"),
    "tg:fcvolga":           ("пресс-служба", "Ульяновск",    "ФК «Волга» (Ульяновск)", "подтверждён", ""),
    "tg:ulstu73":           ("пресс-служба", "Ульяновск",    "УлГТУ", "подтверждён", "отключён как источник"),
    # ── tier 2: агрегаторы ──
    "tg:tresh_ulyan":       ("агрегатор",    "Ульяновск",    None, "уточнить", "крупнейший агрегатор (~145K)"),
    "tg:insaid173":         ("агрегатор",    "Ульяновск",    None, "уточнить", "~139K"),
    "tg:chpulsk":           ("агрегатор",    "Ульяновск",    None, "уточнить", "ЧП-тематика, ~83K"),
    "tg:chpul":             ("агрегатор",    "Ульяновск",    None, "уточнить", "ЧП-тематика"),
    "tg:dimitrovgradonline":("агрегатор",    "Димитровград", None, "уточнить", "муниципальный фокус"),
    "tg:dimitrovgradd":     ("агрегатор",    "Димитровград", None, "уточнить", "муниципальный фокус"),
    "tg:dimgrad24":         ("агрегатор",    "Димитровград", None, "уточнить", "отключён как источник"),
    "tg:topor_ul":          ("агрегатор",    "Ульяновск",    None, "уточнить", ""),
    "tg:ulkoroche":         ("агрегатор",    "Ульяновск",    None, "уточнить", ""),
    "tg:ulyanovsk_smi":     ("агрегатор",    "область",      None, "уточнить", "подборки по СМИ"),
    "tg:ulsk_on":           ("агрегатор",    "Ульяновск",    None, "уточнить", ""),
    "tg:ulsk_73online":     ("агрегатор",    "Ульяновск",    None, "уточнить", ""),
    # ── VK: «второй этаж» (публичные сообщества; wall.get через сервисный ключ) ──
    "vk:cherdaklinskyrayon": ("пресс-служба", "Чердаклинский р-н",
                              "Администрация Чердаклинского района (проверить)", "уточнить",
                              "пилот VK «второго этажа»; тип сообщества и владельца подтвердить после первого сбора"),
    "tg:ulsk_driver73":     ("агрегатор",    "Ульяновск",    None, "уточнить", "автомобильная тематика"),
    "tg:ulyanovsknews":     ("агрегатор",    "Ульяновск",    None, "уточнить", "отключён как источник"),
    "tg:ulyanovsk_ktt":     ("агрегатор",    "Ульяновск",    None, "уточнить", "общественный транспорт"),
    "tg:ulyanovskfirst":    ("агрегатор",    "Ульяновск",    None, "уточнить", "отключён как источник"),
    "tg:youlsk":            ("агрегатор",    "Ульяновск",    None, "уточнить", "отключён как источник"),
    "tg:ulcity_media":      ("агрегатор",    "Ульяновск",    None, "уточнить", "отключён как источник"),
    "tg:ProNovosty73":      ("агрегатор",    "область",      None, "уточнить", "событийный канал (афиша)"),
    "tg:brsh73":            ("агрегатор",    "область",      None, "уточнить", ""),
    # ── tier 3: авторские и промо ──
    "tg:ulpatriot":         ("авторский канал", "область",   None, "уточнить", "авторская аналитика"),
    "tg:shugozhor73":       ("авторский канал", "Ульяновск", None, "уточнить", "сатира"),
    "tg:terr73":            ("авторский канал", "область",   None, "уточнить", ""),
    "tg:volkodav73":        ("авторский канал", "область",   None, "уточнить", ""),
    "tg:ulkompr":           ("авторский канал", "Ульяновск", None, "уточнить", "критика городской власти"),
    "tg:culturnik":         ("авторский канал", "Ульяновск", None, "уточнить", "культура"),
    "tg:ulpromo":           ("промо/коммерция", "Ульяновск", None, "уточнить", "анонсы и промо"),
    # ── RSS ──
    "rss:Ulnovosti.ru":     ("редакция",     "область",      None, "уточнить", "гл. ред. И. Казакова (imprint сайта); юрлицо-учредитель не раскрывается: на сайте не указано, в реестре РКН поиском не найдено (15.09.2026)"),
    "rss:Улпресса":         ("редакция",     "область",      "ООО «Симбирск-Паблисити» (ИНН 7325027230)", "подтверждён", "сетевое издание ulpressa.ru: ИА № ФС77-84971 (17.04.2023); директор/гл. ред. О.С. Турковская; верифицировано 15.09.2026"),
    "rss:Улград":           ("редакция",     "Ульяновск",    None, "уточнить", "исключён: превратился в краеведческий проект; реестр СМИ РКН (id=333881): регистрация 11.06.2010, свидетельство прекращено 15.02.2023 по решению учредителей; юрлицо не установлено"),
    "rss:Media73":          ("редакция",     "область",      "ОАУ Корпорация «Медиа 73» (ИНН 7326033815)", "подтверждён", "отключён; TG-юзернейм @media73 занят посторонним каналом; госкорпорация СМИ области (с 2009), директор А.В. Шишов; верифицировано 15.09.2026 (ulgov.gosuslugi.ru + ЕГРЮЛ)"),
}

# территории «своего голоса» (муниципальные источники вне облцентра)
VOICE_OF = {"tg:dimitrovgradonline": "Димитровград", "tg:dimitrovgradd": "Димитровград",
            "tg:dimgrad24": "Димитровград",
            "vk:cherdaklinskyrayon": "Чердаклинский р-н"}

# форма владения (верификация 15.09.2026 — owner_verification.md):
# государство | официальные | частный бизнес | аноним | не установлен
OWNER_FORM = {
    "tg:Russkih_Aleksey": "официальные", "tg:ulgovru": "официальные",
    "tg:A_Boldakin": "официальные", "tg:ulmeria": "официальные",
    "tg:sergeymorozov73": "официальные", "tg:vmkononov": "официальные",
    "vk:cherdaklinskyrayon": "официальные",
    "tg:ulpravda": "государство", "rss:Media73": "государство",
    "tg:ulstu73": "государство", "tg:uac_ru": "государство",
    "tg:ulpressa": "частный бизнес", "rss:Улпресса": "частный бизнес",
    "tg:reporter73": "частный бизнес", "tg:UAZ_Today": "частный бизнес",
    "rss:Ulnovosti.ru": "не установлен", "rss:Улград": "не установлен",
}

# гипотезы аффилированности (не юрфакт — для разреза HHI и ручного разбора)
AFFILIATE = {
    "tg:ulpravda": "гос-медиа кластер «Ульяновская правда»",
    "rss:Media73": "гос-медиа кластер «Ульяновская правда» (email директора ОАУ «Медиа 73» — @ulpravda.ru)",
}


def main():
    cfg = json.load(open(os.path.join(BASE, "config.json"), encoding="utf-8"))
    path = os.path.join(BASE, "sources_registry.json")
    existing = {}
    if os.path.exists(path):
        try:
            old = json.load(open(path, encoding="utf-8"))
            existing = {e["id"]: e for e in old.get("sources", [])}
        except Exception:
            existing = {}

    entries = []
    for ch in cfg.get("telegram_channels") or []:
        sid = f"tg:{ch['username']}"
        entries.append(_entry(sid, "tg", f"@{ch['username']}", ch.get("tier"),
                              ch.get("enabled", True), existing.get(sid)))
    for s in cfg.get("rss_sources") or []:
        sid = f"rss:{s['name']}"
        entries.append(_entry(sid, "rss", s["name"], None,
                              s.get("enabled", True), existing.get(sid)))
    for c in cfg.get("vk_communities") or []:
        sid = f"vk:{c['domain']}"
        entries.append(_entry(sid, "vk", c.get("title") or f"vk.ru/{c['domain']}",
                              c.get("tier"), c.get("enabled", True), existing.get(sid)))

    registry = {
        "_meta": {
            "purpose": "Реестр источников издания «Гудок»: атрибуты для метрик «Инфопространства» "
                       "(тип производителя, территория, владелец, свой голос, платное освещение). "
                       "Канонический список и tier — config.json; реестр дополняет его.",
            "created": "15.09.2026",
            "updated": datetime.now(UTC4).strftime("%d.%m.%Y %H:%M"),
            "maintenance": "python3 seed_sources_registry.py (структурные поля из config, ручные сохраняются); "
                           "верификация владельцев по ЕГРЮЛ/реестру СМИ РКН — Волна 3",
            "sources_total": len(entries),
            "sources_enabled": sum(1 for e in entries if e["enabled"]),
            "owners_confirmed": sum(1 for e in entries if e.get("owner_status") == "подтверждён"),
        },
        "sources": entries,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(registry, f, ensure_ascii=False, indent=1)
    n_known = sum(1 for e in entries if e.get("producer_type"))
    n_owner = sum(1 for e in entries if e.get("owner"))
    print(f"[registry] {path}: источников {len(entries)} (включено {registry['_meta']['sources_enabled']}), "
          f"с типом производителя {n_known}, с владельцем {n_owner}")


def _entry(sid, kind, name, tier, enabled, old):
    prod, terr, owner, ostatus, notes = KNOWN.get(sid, (None, "область", None, "уточнить", ""))
    e = {
        "id": sid,
        "kind": kind,
        "name": name,
        "tier": tier,
        "enabled": enabled,
        # структурные поля — всегда из config; атрибутивные — из старого файла, иначе из KNOWN
        "producer_type": (old or {}).get("producer_type") or prod,
        "territory": (old or {}).get("territory") or terr,
        "owner": (old or {}).get("owner") or owner,
        "owner_status": (old or {}).get("owner_status") or ostatus,
        "voice_of": (old or {}).get("voice_of") or VOICE_OF.get(sid),
        "owner_form": (old or {}).get("owner_form") or OWNER_FORM.get(sid)
                      or ("аноним" if not ((old or {}).get("owner") or owner) else "не установлен"),
        "affiliate": (old or {}).get("affiliate") or AFFILIATE.get(sid),
        "paid_coverage": (old or {}).get("paid_coverage"),
        "notes": (old or {}).get("notes") if old else notes,
    }
    return e


if __name__ == "__main__":
    main()
