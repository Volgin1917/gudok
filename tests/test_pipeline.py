#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_pipeline.py — unit-тесты парсеров и ядра издание «Гудок».

Запуск:  python3 -m unittest discover -s tests -v   (или:  python3 tests/test_pipeline.py)
Только стандартная библиотека. Фикстуры — реальные страницы источников
(tests/fixtures/), сохранены 11.09.2026.
"""
import json
import os
import sys
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

import collector  # noqa: E402
import dedup  # noqa: E402
import analytics  # noqa: E402

FIX = os.path.join(BASE, "tests", "fixtures")
CFG = json.load(open(os.path.join(BASE, "config.json"), encoding="utf-8"))


def read_fixture(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return f.read()


class TestTextCleaning(unittest.TestCase):
    def test_strip_tags_and_unescape(self):
        out = collector.clean_text("<p>Привет &amp; <b>мир</b> &#8212; светло!</p>", 200)
        self.assertEqual(out, "Привет & мир — светло!")

    def test_promo_tail_cut(self):
        out = collector.clean_text("Новость дня. Плохо грузит? Читай в MAX max.ru/chpulsk", 200)
        self.assertNotIn("max.ru", out)
        self.assertTrue(out.startswith("Новость дня."))

    def test_truncation(self):
        out = collector.clean_text("слово " * 300, 100)
        self.assertLessEqual(len(out), 101)
        self.assertTrue(out.endswith("…"))


class TestDates(unittest.TestCase):
    def test_iso_with_tz(self):
        self.assertEqual(collector.to_utc_iso("2026-09-11T05:34:30+00:00"),
                         "2026-09-11T05:34:30+00:00")

    def test_iso_offset_converted(self):
        out = collector.to_utc_iso("2026-09-11T10:00:00+04:00")
        self.assertTrue(out.startswith("2026-09-11T06:00:00"))

    def test_rfc822(self):
        out = collector.to_utc_iso("Thu, 11 Sep 2026 06:00:00 +0300")
        self.assertTrue(out.startswith("2026-09-11T03:00:00"))

    def test_unix(self):
        out = collector.to_utc_iso("1789000000")
        self.assertIn("2026", out)

    def test_garbage(self):
        self.assertIsNone(collector.to_utc_iso("не дата"))


class TestViews(unittest.TestCase):
    def test_k_m_plain(self):
        self.assertEqual(collector.parse_views("12.3K"), 12300)
        self.assertEqual(collector.parse_views("1.2M"), 1200000)
        self.assertEqual(collector.parse_views("845"), 845)
        self.assertIsNone(collector.parse_views(""))


class TestTelegramParser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.posts = collector.parse_tg_page(read_fixture("tg_page.html"), "vmkononov")

    def test_posts_found(self):
        self.assertGreaterEqual(len(self.posts), 3)

    def test_post_fields(self):
        for p in self.posts:
            self.assertTrue(p["id"].isdigit())
            self.assertEqual(p["url"], f"https://t.me/vmkononov/{p['id']}")
            self.assertTrue(p["title"])
            self.assertTrue(p["published"].startswith("20"))

    def test_no_service_messages(self):
        # «Channel created» и подобные не должны попадать (у них нет message_text)
        for p in self.posts:
            self.assertNotIn("Channel created", p["title"])


class TestRssParser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entries = collector.parse_rss(read_fixture("rss.xml"))

    def test_entries_found(self):
        self.assertGreaterEqual(len(self.entries), 5)

    def test_entry_fields(self):
        for e in self.entries:
            self.assertTrue(e["title"])
            self.assertTrue(e["url"].startswith("http"))
            self.assertIsNotNone(collector.to_utc_iso(e["published"]))


class TestClassification(unittest.TestCase):
    def cat(self, title, text=""):
        c, _ = collector.classify(CFG, title, text)
        return c

    def test_security(self):
        self.assertEqual(self.cat("Суд оставил в силе приговор по делу о взятке"), "security")
        self.assertEqual(self.cat("Ночью сбиты БПЛА над регионом, работала ПВО"), "security")
        self.assertEqual(self.cat("В Ульяновске задержали подозреваемого в краже"), "security")

    def test_sport_not_security(self):
        # регресс: «судья» не должно триггерить «суд»
        self.assertEqual(self.cat("Судья добавил две минуты, матч завершился пенальти"), "sport")

    def test_culture_beats_security_on_concert(self):
        # регресс: ансамбль Росгвардии на концерте — культура
        self.assertEqual(self.cat("Ансамбль песни и пляски Росгвардии и группа «Рондо» выступят "
                                  "на концерте в День города, фестиваль и колокольный звон"), "culture")

    def test_sport_live(self):
        self.assertEqual(self.cat("Трансляция заработала: вратарь потащил пенальти"), "sport")

    def test_agro(self):
        self.assertEqual(self.cat("Урожай зерна превысил план, уборочная продолжается"), "agro")

    def test_health(self):
        self.assertEqual(self.cat("Скорая помощь получила два реанимобиля"), "health")

    def test_topics_multitag(self):
        _, topics = collector.classify(CFG, "Ракетная опасность объявлена, сирены звучат", "")
        self.assertIn("uav", topics)

    def test_transport_topic_covers_closures(self):
        _, topics = collector.classify(CFG, "Центр перекроют из-за праздника", "")
        self.assertIn("transport", topics)


class TestJunkFilter(unittest.TestCase):
    def item(self, title, text=""):
        return collector.normalize_item(CFG, {
            "source_type": "tg", "source": "t", "channel": "x", "url": f"https://t.me/x/{hash(title)}",
            "title": title, "text": text, "published": "2026-09-11T05:00:00+00:00", "views": None,
        })

    def test_morning_greeting_rejected(self):
        self.assertIsNone(self.item("Доброе утро, друзья! С пятницей!"))

    def test_service_message_rejected(self):
        self.assertIsNone(self.item("Channel name was changed to «GS»"))

    def test_emoji_prefixed_greeting_rejected(self):
        # регресс: эмодзи перед «как сейчас обстановка» не должно спасать от фильтра
        self.assertIsNone(self.item("\u26a1\ufe0f Как сейчас обстановка в городе и области? \U0001F44d — Тишина"))

    def test_normal_news_passes(self):
        it = self.item("В области открыли новый сквер")
        self.assertIsNotNone(it)
        self.assertEqual(it["category"], "society")
        self.assertEqual(it["id"], self.item("В области открыли новый сквер")["id"])  # стабильный id


class TestDedup(unittest.TestCase):
    def make(self, title, text, **kw):
        base = {"source_type": "tg", "source": "t", "channel": "x", "url": None,
                "title": title, "text": text, "published": "2026-09-11T05:00:00+00:00",
                "views": None, "tier": 2}
        base.update(kw)
        return collector.normalize_item(CFG, base)

    def test_reprint_detected(self):
        a = self.make("Ракетная опасность объявлена в Ульяновской области",
                      "Нельзя оставаться на открытой местности, зайдите в помещение")
        b = self.make("⚡️ В Ульяновской области объявлен режим «Ракетная опасность»",
                      "Нельзя оставаться на открытой местности. Зайдите в ближайшее помещение")
        self.assertTrue(dedup.similar(
            (dedup.tokens(a)[0], dedup.tokens(a)[1], dedup.title_core(a)),
            (dedup.tokens(b)[0], dedup.tokens(b)[1], dedup.title_core(b)), 0.45))

    def test_different_news_not_similar(self):
        a = self.make("Открыт новый сквер в Засвияжье", "Благоустройство по нацпроекту")
        b = self.make("Урожай зерна превысил миллион тонн", "Уборочная кампания продолжается")
        self.assertFalse(dedup.similar(
            (dedup.tokens(a)[0], dedup.tokens(a)[1], dedup.title_core(a)),
            (dedup.tokens(b)[0], dedup.tokens(b)[1], dedup.title_core(b)), 0.45))

    def test_primary_prefers_tier1_and_views(self):
        low = self.make("Новость", "текст " * 40, tier=2, views=100)
        high = self.make("Новость", "текст " * 40, tier=1, views=20000)
        self.assertGreater(dedup.primary_score(high), dedup.primary_score(low))


class TestCalendar(unittest.TestCase):
    def test_event_extraction(self):
        item = {"title": "Фестиваль пройдёт 25 сентября", 
                "text": "Фестиваль состоится 25 сентября в 15:00 📍 Площадь Ленина. Приглашаем всех.",
                "published": "2026-09-11T05:00:00+00:00", "source": "test"}
        evs = analytics.extract_calendar([item],
                                         now=analytics.datetime(2026, 9, 11, tzinfo=analytics.UTC4))
        self.assertEqual(len(evs), 1)
        self.assertEqual(evs[0]["date"], "2026-09-25")
        self.assertEqual(evs[0]["time"], "15:00")
        self.assertIn("Площадь Ленина", evs[0]["venue"])

    def test_weather_filtered(self):
        item = {"title": "❗️ Ночью ожидаются заморозки, сообщает гидрометцентр",
                "text": "12 сентября температура опустится, прогноз погоды",
                "published": "2026-09-11T05:00:00+00:00", "source": "test"}
        evs = analytics.extract_calendar([item],
                                         now=analytics.datetime(2026, 9, 11, tzinfo=analytics.UTC4))
        self.assertEqual(len(evs), 0)

    def test_past_tense_filtered(self):
        item = {"title": "Волга выиграла матч 9 сентября",
                "text": "Победа состоялась 9 сентября",
                "published": "2026-09-10T05:00:00+00:00", "source": "test"}
        evs = analytics.extract_calendar([item],
                                         now=analytics.datetime(2026, 9, 11, tzinfo=analytics.UTC4))
        self.assertEqual(len(evs), 0)


class TestSentiment(unittest.TestCase):
    def score(self, text):
        items = [{"title": text, "text": "", "published": "2026-09-11T05:00:00+00:00",
                  "category": "society"}]
        r = analytics.sentiment_score(items, now=analytics.datetime(2026, 9, 11, 12, tzinfo=analytics.UTC4))
        return r["today_score"]

    def test_negative(self):
        self.assertLess(self.score("Трагедия: пожар унёс жизнь, пострадали люди, угроза"), -0.3)

    def test_positive(self):
        self.assertGreater(self.score("Победа! Открытие фестиваля, успех и праздник, награда"), 0.3)


class TestEndToEndOnStore(unittest.TestCase):
    """Санитарные проверки на реальной базе (если собрана)."""

    @classmethod
    def setUpClass(cls):
        cls.items = []
        path = os.path.join(BASE, "data", "store.jsonl")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                cls.items = [json.loads(l) for l in f if l.strip()]

    def test_store_not_empty(self):
        self.assertGreater(len(self.items), 100, "база пуста — сначала запустите run.sh")

    def test_ids_unique(self):
        ids = [i["id"] for i in self.items]
        self.assertEqual(len(ids), len(set(ids)))

    def test_required_fields(self):
        for i in self.items:
            self.assertTrue(i.get("title"))
            self.assertTrue(i.get("category"))
            self.assertIsNotNone(i.get("published"))

    def test_dups_reference_existing(self):
        ids = {i["id"] for i in self.items}
        for i in self.items:
            if i.get("dup_of"):
                self.assertIn(i["dup_of"], ids)

    def test_no_promo_tails(self):
        bad = [i for i in self.items if "max.ru/" in (i.get("text") or "").lower()]
        self.assertEqual(len(bad), 0, f"промо-хвосты остались в {len(bad)} записях")


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestInfospaceW1(unittest.TestCase):
    """Метрики Волны 1 (build_infospace_ext): матрица, ритм, каскады, TLI, бюджетный голос."""

    CFG_W1 = {"municipalities": {"Тестград": r"тестград"},
              "categories": [{"id": "society", "name": "Общество"},
                             {"id": "security", "name": "Безопасность и происшествия"}]}

    def _it(self, id, hours_ago, title="Заголовок", text="", category="society",
            tier=None, dup_of=None, cluster=0, source_type="tg", channel="test"):
        from datetime import datetime, timedelta, timezone
        UTC4 = timezone(timedelta(hours=4))
        dt = datetime.now(UTC4) - timedelta(hours=hours_ago)
        return {"id": id, "title": title, "text": text, "published": dt.isoformat(),
                "category": category, "tier": tier, "dup_of": dup_of, "cluster": cluster,
                "source_type": source_type, "channel": channel, "source": channel}

    def test_empty_store(self):
        r = analytics.build_infospace_ext([], None, self.CFG_W1)
        self.assertNotIn("matrix", r)
        self.assertEqual(r.get("week_items"), 0)

    def test_matrix_counts(self):
        items = [self._it("a", 5, "В Тестграде открыли парк", category="society"),
                 self._it("b", 6, "Тестград: ДТП на трассе", category="security"),
                 self._it("c", 7, "Новости без географии")]
        r = analytics.build_infospace_ext(items, None, self.CFG_W1)
        row = r["matrix"]["rows"][0]
        self.assertEqual(row["muni"], "Тестград")
        self.assertEqual(row["total"], 2)
        self.assertEqual(row["cats"]["society"], 1)
        self.assertEqual(row["cats"]["security"], 1)

    def test_rhythm_totals(self):
        items = [self._it("a", 1), self._it("b", 2)]
        r = analytics.build_infospace_ext(items, None, self.CFG_W1)
        self.assertEqual(len(r["rhythm"]["weekday"]), 24)
        self.assertEqual(sum(r["rhythm"]["weekday"]) + sum(r["rhythm"]["weekend"]), 2)
        self.assertIsNotNone(r["rhythm"]["night_share"])

    def test_tli_speech(self):
        items = [self._it("a", 3, "Рабочие УАЗа рассказали о простое",
                          text="«Нам не объяснили», — говорят рабочие УАЗа."),
                 self._it("b", 4, "На заводе сократили инженеров",
                          text="Уволены инженеры цеха №2.")]
        r = analytics.build_infospace_ext(items, None, self.CFG_W1)
        g = r["tli"]["groups"]["рабочие и инженеры"]
        self.assertEqual(g["mentioned"], 2)
        self.assertGreaterEqual(g["speaks"], 1)

    def test_budget_echo(self):
        items = [self._it("p", 5, "Официально о ремонте", tier=1, cluster=2),
                 self._it("d", 4, "Официально о ремонте (копия)", tier=2, dup_of="p")]
        r = analytics.build_infospace_ext(items, None, self.CFG_W1)
        bv = r["budget_voice"]
        self.assertEqual(bv["echo_of_t1"], 1.0)
        self.assertEqual(bv["echo_n"], 1)

    def test_cascade_span(self):
        items = [self._it("p", 6, "Сюжет о дороге", cluster=2),
                 self._it("d", 4, "Сюжет о дороге подхват", dup_of="p")]
        r = analytics.build_infospace_ext(items, None, self.CFG_W1)
        ct = r["cascade_time"]
        self.assertEqual(ct["n"], 1)
        self.assertAlmostEqual(ct["fastest"][0]["span_h"], 2.0, delta=0.3)


class TestInfospaceW1Part2(unittest.TestCase):
    """Волна 1, вторая пачка: канцелярит, тревожность, ЖКХ, фед-эхо, индекс села."""

    CFG_W1 = {"municipalities": {"Тестград": r"тестград"},
              "categories": [{"id": "society", "name": "Общество"},
                             {"id": "security", "name": "Безопасность и происшествия"}]}

    def _it(self, id, hours_ago, title="Заголовок", text="", category="society",
            tier=None, topics=None):
        from datetime import datetime, timedelta, timezone
        UTC4 = timezone(timedelta(hours=4))
        dt = datetime.now(UTC4) - timedelta(hours=hours_ago)
        return {"id": id, "title": title, "text": text, "published": dt.isoformat(),
                "category": category, "tier": tier, "topics": topics or [],
                "source_type": "tg", "channel": f"ch_{id}", "source": f"ch_{id}"}

    def test_bureaucratese_by_tier(self):
        items = [self._it("a", 2, "Благоустройство парка завершено по поручению губернатора", tier=1),
                 self._it("b", 3, "Во дворе отремонтировали качели", tier=2)]
        r = analytics.build_infospace_ext(items, None, self.CFG_W1)
        b = r["bureaucratese"]["by_tier"]
        self.assertEqual(b["T1"]["share"], 1.0)
        self.assertEqual(b["T2"]["share"], 0.0)
        self.assertTrue(r["bureaucratese"]["top_markers"])

    def test_anxiety_series(self):
        items = [self._it("a", 2, "ДТП на трассе", category="security"),
                 self._it("b", 3, "Праздник в парке")]
        r = analytics.build_infospace_ext(items, None, self.CFG_W1)
        self.assertEqual(len(r["anxiety"]["series"]), 7)
        self.assertIsNotNone(r["anxiety"]["avg"])
        self.assertIn(r["anxiety"]["verdict"], ("спокойный фон", "повышенный фон", "высокая тревожность"))

    def test_zhkh_share_and_tone(self):
        items = [self._it("a", 2, "Тарифы на тепло вырастут", topics=["zhkh"]),
                 self._it("b", 3, "Фестиваль прошёл")]
        r = analytics.build_infospace_ext(items, None, self.CFG_W1)
        self.assertEqual(r["zhkh"]["n"], 1)
        self.assertAlmostEqual(r["zhkh"]["share"], 0.5, places=2)

    def test_federal_by_source(self):
        items = [self._it("a", 2, "В Москве открыли выставку достижений"),
                 self._it("b", 3, "В Ульяновске отремонтировали дорогу")]
        r = analytics.build_infospace_ext(items, None, self.CFG_W1)
        fed = {x["source"]: x["fed_share"] for x in r["federal_by_source"]}
        self.assertEqual(fed.get("ch_a"), 1.0)
        self.assertEqual(fed.get("ch_b"), 0.0)

    def test_rural_index(self):
        cfg = dict(self.CFG_W1)
        cfg["muni_population"] = {"_meta": {"oblast_total": 1000, "oblast_rural": 300,
                                            "source": "тест"},
                                  "Тестград": 300}
        items = [self._it("a", 2, "В Тестграде открыли клуб"),
                 self._it("b", 3, "Новости областного центра")]
        r = analytics.build_infospace_ext(items, None, cfg)
        ri = r["rural_index"]
        self.assertAlmostEqual(ri["agenda_share"], 0.5, places=2)
        self.assertAlmostEqual(ri["pop_share"], 0.3, places=2)
        self.assertEqual(ri["verdict"], "паритет")

    def test_rural_index_no_population(self):
        r = analytics.build_infospace_ext([self._it("a", 2, "В Тестграде праздник")],
                                          None, self.CFG_W1)
        self.assertEqual(r["rural_index"], {})


class TestInfospaceW2(unittest.TestCase):
    """Волна 2: кто пишет, внимание, прямая речь, промо, немые группы."""

    CFG_W2 = {"municipalities": {}, "categories": [{"id": "society", "name": "Общество"}]}
    REG_W2 = {"tg:press": {"id": "tg:press", "producer_type": "пресс-служба"},
              "tg:agg": {"id": "tg:agg", "producer_type": "агрегатор"}}

    def _it(self, id, hours_ago, title="Новость", text="", channel="press",
            source_type="tg", views=None):
        from datetime import datetime, timedelta, timezone
        UTC4 = timezone(timedelta(hours=4))
        dt = datetime.now(UTC4) - timedelta(hours=hours_ago)
        it = {"id": id, "title": title, "text": text, "published": dt.isoformat(),
              "category": "society", "source_type": source_type,
              "channel": channel, "source": channel if source_type == "tg" else "Ulnovosti.ru"}
        if views is not None:
            it["views"] = views
        return it

    def test_producer_mix(self):
        items = [self._it("a", 2, channel="press"), self._it("b", 3, channel="agg"),
                 self._it("c", 4, channel="agg"), self._it("d", 5, source_type="rss")]
        r = analytics.build_infospace_w2(items, None, self.CFG_W2, registry=self.REG_W2)
        mix = r["producer_mix"]["week"]
        self.assertEqual(mix["пресс-служба"], 1)
        self.assertEqual(mix["агрегатор"], 2)
        self.assertEqual(mix["редакция"], 1)
        self.assertEqual(len(r["producer_mix"]["daily"]), 7)

    def test_attention_gini(self):
        items = [self._it("a", 2, views=100), self._it("b", 3, channel="agg", views=100)]
        r = analytics.build_infospace_w2(items, None, self.CFG_W2, registry=self.REG_W2)
        at = r["attention"]
        self.assertEqual(at["gini"], 0.0)
        self.assertEqual(at["top3_share"], 1.0)
        self.assertEqual(at["total_views"], 200)

    def test_speech_attribution(self):
        t1 = "«Мы держим ситуацию на контроле», — сообщил губернатор области."
        t2 = "«Дорогу не чинили десять лет», — рассказали жители переулка."
        items = [self._it("a", 2, text=t1), self._it("b", 3, text=t2)]
        r = analytics.build_infospace_w2(items, None, self.CFG_W2, registry=self.REG_W2)
        self.assertEqual(r["speech"]["official"], 1)
        self.assertEqual(r["speech"]["citizen"], 1)

    def test_promo_load(self):
        items = [self._it("a", 2, text="Скидка по промокоду ГУДОК до конца недели"),
                 self._it("b", 3, text="Обычная новость без коммерции")]
        r = analytics.build_infospace_w2(items, None, self.CFG_W2, registry=self.REG_W2)
        pl = r["promo_load"]
        self.assertEqual(pl["n"], 1)
        self.assertAlmostEqual(pl["share"], 0.5, places=2)
        self.assertEqual(pl["commercial"]["n"], 1)
        self.assertEqual(pl["crosspromo"]["n"], 0)

    def test_promo_legal_marking(self):
        # erid и раскрытие «Реклама.» + ИНН — безусловный коммерческий сигнал (маркировка по 38-ФЗ)
        items = [self._it("a", 2, text="В городе открыли экстрим-парк. erid: 2VfnxwLt8Yp"),
                 self._it("b", 3, text="Роллы топ. Реклама. ООО «Меркурий». ИНН: 9729109919.")]
        r = analytics.build_infospace_w2(items, None, self.CFG_W2, registry=self.REG_W2)
        plc = r["promo_load"]["commercial"]
        self.assertEqual(plc["n"], 2)
        self.assertEqual(plc["marked"], 2)

    def test_promo_offer_frame(self):
        # офертная рамка без легальной маркировки: «успей купить … от N ₽»
        items = [self._it("a", 2, text="Только в сентябре успей купить по специальной цене от 3 290 000 ₽!")]
        r = analytics.build_infospace_w2(items, None, self.CFG_W2, registry=self.REG_W2)
        plc = r["promo_load"]["commercial"]
        self.assertEqual(plc["n"], 1)
        self.assertEqual(plc["marked"], 0)

    def test_promo_false_positives_gone(self):
        # калибровка 15.09: сельхоз-«посевы» и новостной «персональный промокод» — не реклама
        items = [self._it("a", 2, text="Хлопковая совка уничтожает посевы: до 20 гусениц на растение"),
                 self._it("b", 3, text="Маркетплейс позволит запросить скидку до 35%: клиенту придёт "
                                       "персональный промокод, который будет действовать 24 часа")]
        r = analytics.build_infospace_w2(items, None, self.CFG_W2, registry=self.REG_W2)
        self.assertEqual(r["promo_load"]["n"], 0)

    def test_promo_crosspromo_separate(self):
        # приписка канала про MAX — кросс-промо, а не коммерческая интеграция
        items = [self._it("a", 2, title="Звуки сирены в Ульяновске Плохо грузит? Читай в MAX max.ru/chpulsk")]
        r = analytics.build_infospace_w2(items, None, self.CFG_W2, registry=self.REG_W2)
        pl = r["promo_load"]
        self.assertEqual(pl["commercial"]["n"], 0)
        self.assertEqual(pl["crosspromo"]["n"], 1)
        self.assertEqual(pl["n"], 1)

    def test_promo_xtail_flag(self):
        # коллектор срезал приписку из текста — флаг xtail на записи сохраняет сигнал
        it = self._it("a", 2, text="Чистый текст новости без хвоста")
        it["xtail"] = True
        r = analytics.build_infospace_w2([it], None, self.CFG_W2, registry=self.REG_W2)
        pl = r["promo_load"]
        self.assertEqual(pl["crosspromo"]["n"], 1)
        self.assertEqual(pl["crosspromo"]["by_source"], {"press": 1})

    def test_promo_native_channel_redirect(self):
        # сторителл-нативка «берёт … в канале «BaggyBags»» — реклама;
        # цитирование канала («жалуются…», «как сообщают пассажиры…») — новость
        items = [self._it("a", 2, text="Оказалось, она берёт премиальные копии в канале «BaggyBags». Шьют из той же кожи."),
                 self._it("b", 3, title="Ульяновцы массово жалуются на транспорт в канале «Инсайд Ульяновска»",
                          text="После 20:00 транспорта практически нет."),
                 self._it("c", 4, title="Водители, как сообщают пассажиры в канале «Инсайд Ульян…», хамят",
                          text="Пассажиры недовольны.")]
        r = analytics.build_infospace_w2(items, None, self.CFG_W2, registry=self.REG_W2)
        self.assertEqual(r["promo_load"]["commercial"]["n"], 1)

    def test_silent_groups(self):
        items = [self._it("a", 2, text="Врачи поликлиники №4 получили новое оборудование."),
                 self._it("b", 3, text="«Условия тяжёлые», — рассказали рабочие завода.")]
        r = analytics.build_infospace_w2(items, None, self.CFG_W2, registry=self.REG_W2)
        names = [g["group"] for g in r["silent_groups"]]
        self.assertIn("медики", names)          # упомянуты, но не процитированы
        self.assertNotIn("рабочие и инженеры", names)  # получили прямую речь


class TestPromoTailFlag(unittest.TestCase):
    """Коллектор: флаг xtail сохраняет сигнал кросс-промо после срезания приписок."""

    def _raw(self, **kw):
        base = {"title": "Новость дня", "text": "В городе открыли новый парк.",
                "url": "https://example.com/1", "published": "2026-09-14T10:00:00+00:00"}
        base.update(kw)
        return base

    def test_xtail_passthrough_from_tg(self):
        it = collector.normalize_item(CFG, self._raw(xtail=True))
        self.assertTrue(it["xtail"])

    def test_xtail_detected_in_rss_raw(self):
        it = collector.normalize_item(CFG, self._raw(
            text="В городе открыли новый парк. Читайте нас в МАКС max.ru/news73"))
        self.assertTrue(it.get("xtail"))
        self.assertNotIn("макс", it["text"].lower())   # хвост срезан
        self.assertNotIn("max.ru", it["text"].lower())

    def test_no_xtail_for_clean_item(self):
        it = collector.normalize_item(CFG, self._raw())
        self.assertNotIn("xtail", it)


class TestPromoFilter(unittest.TestCase):
    """Редакторский фильтр is_promo(): калибровка «в программе» и розыгрышей."""

    def setUp(self):
        import generate
        self.generate = generate

    def test_announce_with_colon_is_promo(self):
        self.assertTrue(self.generate.is_promo(
            {"title": "Открытие осеннего сезона в «Квартале»", "text": "В программе: в 16:00 — живая музыка"}))

    def test_news_with_program_space_is_not_promo(self):
        for t in ("Бизнес-делегация региона отправится в Беларусь. В программе посещение промышленных объектов Минска",
                  "Начался рабочий визит Президента в Индию, в программе – беседа с Премьер-министром",
                  "Двор выбрали по Программе поддержки местных инициатив-2027",
                  "Мэр ответил на вопросы ульяновцев в программе «Первые лица» на ГТРК «Волга»"):
            self.assertFalse(self.generate.is_promo({"title": t, "text": ""}), msg=t)

    def test_ticket_raffle_is_promo(self):
        self.assertTrue(self.generate.is_promo(
            {"title": "РОЗЫГРЫШ БИЛЕТА на концерт Мураками в Ульяновске", "text": ""}))

    def test_invitation_is_promo(self):
        self.assertTrue(self.generate.is_promo(
            {"title": "Приглашаем на выставку-продажу саженцев", "text": ""}))


class TestVkCollector(unittest.TestCase):
    """VK «второй этаж»: wall.get через сервисный ключ, только агрегаты."""

    def setUp(self):
        with open(os.path.join(FIX, "vk_wall_sample.json"), encoding="utf-8") as f:
            self.data = json.load(f)

    def test_parse_vk_wall(self):
        posts = collector.parse_vk_wall(self.data, "cherdaklinskyrayon")
        self.assertEqual(len(posts), 4)
        p = posts[0]
        self.assertEqual(p["url"], "https://vk.ru/cherdaklinskyrayon?w=wall-62043407_5001")
        self.assertEqual(p["views"], 1200)
        self.assertEqual(p["comments"], 7)
        self.assertTrue(p["published"].startswith("2026-09-10"))
        self.assertIsNone(p["vk_ads"])
        self.assertIn("котельной", p["text"])
        self.assertNotIn("<br>", p["text"])

    def test_parse_vk_ads_flag_and_repost(self):
        posts = collector.parse_vk_wall(self.data, "cherdaklinskyrayon")
        self.assertEqual(posts[1]["vk_ads"], 1)                      # marked_as_ads
        self.assertTrue(posts[2]["text"].startswith("[репост: wall-99999123_777]"))

    def test_parse_vk_bad_response(self):
        self.assertEqual(collector.parse_vk_wall({"error": {"error_code": 15}}, "x"), [])
        self.assertEqual(collector.parse_vk_wall(None, "x"), [])

    def test_normalize_vk_item(self):
        raw = {"source_type": "vk", "source": "vk.ru/cherdaklinskyrayon",
               "channel": "cherdaklinskyrayon",
               "url": "https://vk.ru/cherdaklinskyrayon?w=wall-62043407_5000",
               "title": "Ремонт кровли под ключ", "text": "Ремонт кровли под ключ. Скидкой 15%",
               "published": "2026-09-10T10:00:00+00:00", "views": 800, "tier": 1,
               "vk_ads": 1, "comments": 3, "likes": 2}
        it = collector.normalize_item(CFG, raw)
        self.assertEqual(it["source_type"], "vk")
        self.assertEqual(it["vk_ads"], 1)
        self.assertEqual(it["comments"], 3)
        self.assertEqual(it["views"], 800)

    def test_collect_vk_skips_without_token(self):
        os.environ.pop("GUDOK_VK_TOKEN", None)
        token_path = os.path.join(BASE, "data", "vk_token")
        self.assertFalse(os.path.exists(token_path))   # файл ключа не должен попадать в репозиторий
        cfg = {"settings": CFG["settings"], "vk_communities": [{"domain": "test_dom", "tier": 1}]}
        status = {}
        self.assertEqual(collector.collect_vk(cfg, status, quiet=True), [])
        self.assertFalse(status["vk:test_dom"]["ok"])
        self.assertIn("сервисного ключа", status["vk:test_dom"]["error"])

    def test_collect_vk_no_communities(self):
        self.assertEqual(collector.collect_vk({"settings": CFG["settings"]}, {}, quiet=True), [])


class TestInfospaceW2Vk(unittest.TestCase):
    """Волна 2 на VK-записях: атрибуция по реестру и платформенная маркировка рекламы."""

    CFG_W2 = TestInfospaceW2.CFG_W2
    REG_W2 = {"vk:raion": {"id": "vk:raion", "producer_type": "пресс-служба",
                           "territory": "Чердаклинский р-н"}}

    def _it(self, id, text="Новость района", **kw):
        it = TestInfospaceW2._it(self, id, 2, text=text, channel="raion", source_type="vk")
        it.update(kw)
        return it

    def test_vk_producer_type_from_registry(self):
        r = analytics.build_infospace_w2([self._it("a")], None, self.CFG_W2, registry=self.REG_W2)
        self.assertEqual(r["producer_mix"]["week"]["пресс-служба"], 1)

    def test_vk_marked_as_ads_counts(self):
        # vk_ads=1 — платформенная маркировка: коммерческий класс + зачёт в «с маркировкой»
        items = [self._it("a", text="Обычный пост без промо-признаков", vk_ads=1),
                 self._it("b", text="Пост главы района о совещании")]
        r = analytics.build_infospace_w2(items, None, self.CFG_W2, registry=self.REG_W2)
        pl = r["promo_load"]
        self.assertEqual(pl["commercial"]["n"], 1)
        self.assertEqual(pl["commercial"]["marked"], 1)
        self.assertEqual(pl["crosspromo"]["n"], 0)


class TestEventLatency(unittest.TestCase):
    """Латентность «событие → публикация»: извлечение времени события из текста."""

    from datetime import datetime as _dt, timedelta as _td, timezone as _tz
    UTC4 = _tz(_td(hours=4))
    PUB = _dt(2026, 9, 15, 9, 0, tzinfo=UTC4)   # вторник

    def ev(self, text):
        got = analytics.extract_event_time(text, self.PUB)
        return got[0] if got else None

    def test_yesterday_with_evening(self):
        ev = self.ev("Вчера вечером на проспекте сбили пешехода.")
        self.assertEqual((ev.day, ev.month, ev.hour), (14, 9, 20))

    def test_today_exact_time(self):
        ev = self.ev("Сегодня в 7:49 произошло ДТП на пересечении.")
        self.assertEqual((ev.day, ev.hour, ev.minute), (15, 7, 49))

    def test_explicit_date_noon_default(self):
        ev = self.ev("13 сентября губернатор открыл парк.")
        self.assertEqual((ev.day, ev.month, ev.hour), (13, 9, 12))

    def test_numeric_date(self):
        ev = self.ev("09.09.2026г в 7:49 пересечение пр-т Ульяновский.")
        self.assertEqual((ev.day, ev.month), (9, 9))

    def test_weekday_needs_past_verb(self):
        # «в среду» + глагол прошлого — принимаем ближайшую прошедшую среду
        ev = self.ev("В среду на улице Гончарова загорелся гараж.")
        self.assertEqual(ev.day, 9)          # 09.09 — среда перед вторником 15.09
        # без глагола прошлого — пропускаем (неоднозначность: прошедшая или следующая)
        self.assertIsNone(self.ev("В среду состоится приём граждан."))

    def test_future_announce_skipped(self):
        self.assertIsNone(self.ev("Фестиваль пройдёт 20 сентября, приглашаем всех."))
        self.assertIsNone(self.ev("Уже 12 сентября в 22:00 ты погрузишься в атмосферу."))
        self.assertIsNone(self.ev("Приглашаем вас на экофестиваль 2 сентября."))

    def test_range_and_deadline_skipped(self):
        self.assertIsNone(self.ev("Горячую воду отключат до 20 сентября."))
        self.assertIsNone(self.ev("Ремонт ведётся с 1 сентября по 30 октября."))

    def test_history_other_year_skipped(self):
        self.assertIsNone(self.ev("Завод построили 5 сентября 1974 года."))

    def test_minduvshaya_noch(self):
        ev = self.ev("Минувшей ночью сбили беспилотник над областью.")
        self.assertEqual((ev.day, ev.hour), (14, 2))

    def test_first_marker_wins(self):
        ev = self.ev("Сегодня утром коммунальщики вышли на улицу. Напомним, 10 сентября было совещание.")
        self.assertEqual(ev.day, 15)

    def test_no_marker(self):
        self.assertIsNone(self.ev("Губернатор провёл совещание по развитию."))
        self.assertIsNone(self.ev(""))

    def test_sameday_kind_is_day(self):
        got = analytics.extract_event_time("Сегодня в городе стартовал фестиваль.", self.PUB)
        self.assertIsNotNone(got)
        ev, kind = got
        self.assertEqual(kind, "day")
        self.assertEqual(ev.date(), self.PUB.date())

    def test_exact_time_kind(self):
        _, kind = analytics.extract_event_time("Сегодня в 7:49 произошло ДТП.", self.PUB)
        self.assertEqual(kind, "time")


class TestInfospaceW1Latency(unittest.TestCase):
    """Агрегация латентности в build_infospace_ext."""

    CFG = TestInfospaceW1.CFG_W1

    def _it(self, id, hours_ago, title="Новость", text="", category="society", tier=None):
        return TestInfospaceW1._it(self, id, hours_ago, title=title, text=text,
                                   category=category, tier=tier)

    def test_latency_aggregation(self):
        items = [
            self._it("a", 3, text="Вчера вечером произошло ДТП на проспекте."),           # raw > 0 при любом часе запуска
            self._it("b", 2, text="Вчера в 8:00 открыли выставку."),                     # точное время → измеряемо
            self._it("c", 5, text="Обычная новость без временных маркеров."),             # нет события
            self._it("d", 4, text="То же событие, перепечатка", category="security"),
        ]
        items[3]["dup_of"] = "a"                                                          # не первоисточник
        r = analytics.build_infospace_ext(items, None, self.CFG)
        lt = r["latency"]
        self.assertEqual(lt["n"], 2)                # только первоисточники с извлечённым временем
        self.assertAlmostEqual(lt["coverage"], 2 / 3, places=2)
        self.assertIsNotNone(lt["median_h"])
        self.assertGreaterEqual(lt["median_h"], 0.0)
        self.assertEqual(sum(lt["buckets"].values()), 1.0)

    def test_sameday_counted_separately(self):
        # «сегодня» без времени суток: точная задержка неизмерима — отдельный класс, не медиана
        items = [self._it("a", 1, text="Сегодня в городе стартовал фестиваль.")]
        r = analytics.build_infospace_ext(items, None, self.CFG)
        lt = r["latency"]
        self.assertEqual(lt["sameday_n"], 1)
        self.assertEqual(lt["n"], 0)
        self.assertIsNone(lt["median_h"])
        self.assertEqual(lt["sameday_share"], 1.0)

    def test_latency_empty_when_nothing_extracted(self):
        items = [self._it("a", 3, text="Новость без маркеров времени.")]
        r = analytics.build_infospace_ext(items, None, self.CFG)
        self.assertEqual(r["latency"], {})


class TestInfospaceW3(unittest.TestCase):
    """Волна 3: HHI концентрации собственности по учредителям."""

    CFG_W3 = {"municipalities": {}, "categories": [{"id": "society", "name": "Общество"}]}
    REG_W3 = {
        # два источника одного юрлица (слияние по ИНН)
        "tg:press1": {"id": "tg:press1", "producer_type": "редакция",
                      "owner": "ООО «Ромашка» (ИНН 7325000001)", "owner_status": "подтверждён",
                      "owner_form": "частный бизнес"},
        "rss:Ромашка": {"id": "rss:Ромашка", "producer_type": "редакция",
                        "owner": "ООО «Ромашка» (ИНН 7325000001)", "owner_status": "подтверждён",
                        "owner_form": "частный бизнес"},
        "tg:gov": {"id": "tg:gov", "producer_type": "пресс-служба",
                   "owner": "Правительство области", "owner_status": "подтверждён",
                   "owner_form": "официальные"},
        "tg:anon1": {"id": "tg:anon1", "producer_type": "агрегатор", "owner": None,
                     "owner_status": "уточнить", "owner_form": "аноним"},
        "tg:anon2": {"id": "tg:anon2", "producer_type": "агрегатор", "owner": None,
                     "owner_status": "уточнить", "owner_form": "аноним"},
    }

    def _it(self, id, sid_channel, hours_ago=2, source_type="tg"):
        from datetime import datetime, timedelta, timezone
        UTC4 = timezone(timedelta(hours=4))
        dt = datetime.now(UTC4) - timedelta(hours=hours_ago)
        return {"id": id, "title": "Новость", "text": "", "published": dt.isoformat(),
                "category": "society", "source_type": source_type,
                "channel": sid_channel if source_type == "tg" else None,
                "source": sid_channel if source_type == "rss" else f"t.me/{sid_channel}"}

    def test_hhi_merges_same_inn(self):
        items = [self._it("a", "press1"), self._it("b", "press1"),
                 self._it("c", "Ромашка", source_type="rss"),
                 self._it("d", "gov"), self._it("e", "anon1"), self._it("f", "anon2")]
        r = analytics.build_infospace_w3(items, self.CFG_W3, registry=self.REG_W3)
        # 6 сообщений: Ромашка 3 (50%), gov 1, anon1 1, anon2 1 → HHI = 2500+3×(1/6)²×10000
        self.assertEqual(r["week_items"], 6)
        top = r["top_owners"][0]
        self.assertIn("Ромашка", top["name"])
        self.assertEqual(top["n_sources"], 2)
        self.assertAlmostEqual(top["share"], 0.5, places=2)
        expected = round((0.5 ** 2 + 3 * (1 / 6) ** 2) * 10000)
        self.assertEqual(r["hhi"], expected)
        # подтверждённые: Ромашка 3/4 + gov 1/4 → (0.75²+0.25²)*1e4 = 6250
        self.assertEqual(r["hhi_confirmed"], 6250)
        self.assertEqual(r["verdict"], "высокая концентрация")

    def test_groups_and_shares(self):
        items = [self._it("a", "press1"), self._it("b", "gov"),
                 self._it("c", "anon1"), self._it("d", "anon2")]
        r = analytics.build_infospace_w3(items, self.CFG_W3, registry=self.REG_W3)
        g = r["groups"]
        self.assertAlmostEqual(g["аноним"]["share"], 0.5, places=2)
        self.assertAlmostEqual(r["state_official_share"], 0.25, places=2)
        self.assertAlmostEqual(r["anon_share"], 0.5, places=2)

    def test_empty_when_no_week(self):
        r = analytics.build_infospace_w3([], self.CFG_W3, registry=self.REG_W3)
        self.assertNotIn("hhi", r)


class TestEisMetrics(unittest.TestCase):
    """ЕИС «Госзакупки»: CSV-выгрузка → метрики проекта."""

    ROWS = [
        {"date": "2026-09-14", "_dt": None, "customer": "Минздрав области",
         "method": "Электронный аукцион", "nmck": 5_000_000.0, "supplier": "ООО «Медиа»",
         "price": 4_500_000.0},
        {"date": "2026-09-10", "_dt": None, "customer": "Мэрия",
         "method": "Закупка у единственного поставщика", "nmck": 2_000_000.0,
         "supplier": "ООО «Ромашка»", "price": 2_000_000.0},
        {"date": "2026-08-01", "_dt": None, "customer": "Минздрав области",
         "method": "Открытый конкурс", "nmck": 3_000_000.0, "supplier": "ИП Иванов",
         "price": 2_400_000.0},
    ]

    def setUp(self):
        from datetime import datetime, timedelta, timezone
        UTC4 = timezone(timedelta(hours=4))
        now = datetime.now(UTC4)
        for r, back in zip(self.ROWS, (1, 5, 45)):
            r = r
        # проставляем _dt относительно «сейчас»: 1 день, 5 дней, 45 дней назад
        for r, back in zip(self.ROWS, (1, 5, 45)):
            r["_dt"] = now - timedelta(days=back)
        self.now = now

    def test_compute(self):
        m = analytics.compute_eis_metrics(self.ROWS, now=self.now)
        self.assertEqual(m["n_rows"], 3)
        self.assertEqual(m["week_n"], 2)          # 1 и 5 дней назад
        self.assertEqual(m["month_n"], 2)         # 45 дней — вне месяца
        self.assertAlmostEqual(m["total_nmck"], 10_000_000.0)
        self.assertAlmostEqual(m["sole_share_n"], round(1 / 3, 4))
        self.assertAlmostEqual(m["avg_savings"], round((0.10 + 0.20) / 2, 4))  # 10% и 20%, ед. поставщик исключён
        self.assertEqual(m["top_customers"][0]["name"], "Минздрав области")
        self.assertIsNotNone(m["supplier_hhi"])

    def test_load_csv_roundtrip(self):
        import tempfile
        csv_text = ("date,customer,method,nmck,supplier,price\n"
                    "14.09.2026,Мэрия,Аукцион,\"1 500 000,50\",ООО «Вектор»,\"1 200 000,00\"\n")
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f:
            f.write(csv_text)
            path = f.name
        try:
            rows = analytics.load_eis_csv(path)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["nmck"], 1500000.5)
            self.assertEqual(rows[0]["price"], 1200000.0)
            self.assertEqual(rows[0]["_dt"].day, 14)
        finally:
            os.unlink(path)

    def test_load_missing_file(self):
        self.assertIsNone(analytics.load_eis_csv("/nonexistent/path.csv"))


# ─────────────────────────────────────────────────────────────────────────────
# Волна 4 «Инфопространства»: язык (агентность, фреймы), труд (ИИ-след),
# методика (устойчивость дедупликации)
# ─────────────────────────────────────────────────────────────────────────────
class TestAgencyRoles(unittest.TestCase):
    """Разметка ролей: субъект / объект / упоминание / безличный / без актора."""

    def _roles(self, sentence):
        return {c: (role, word) for c, role, word, _o, _p in analytics.agency_roles(sentence)}

    def _one(self, title, text=""):
        return analytics.agency_of({"title": title, "text": text})

    def test_official_is_subject(self):
        r = self._one("Губернатор Алексей Русских заявил о сохранении льготного питания")
        self.assertEqual(r["role"], "субъект")
        self.assertEqual(r["actor"], "власть")

    def test_residents_are_subjects(self):
        r = self._one("Жители улицы Заречной второй год требуют ремонта дороги")
        self.assertEqual(r["role"], "субъект")
        self.assertEqual(r["actor"], "жители")

    def test_speech_inversion_keeps_subject(self):
        # «сообщил мэр» — глагол речи стоит перед актором, это инверсия, а не объект
        r = self._one("Мост откроют 15–17 сентября — об этом сообщил мэр Ульяновска")
        self.assertEqual(r["role"], "субъект")
        self.assertEqual(r["actor"], "власть")

    def test_victim_is_object(self):
        r = self._one("В результате ДТП пострадали два человека, один госпитализирован")
        self.assertEqual(r["role"], "объект")
        self.assertEqual(r["object"], "жители")

    def test_address_verb_makes_object(self):
        # «жителей призвали» — адресат рекомендации, а не субъект действия
        r = self._one("Жителей региона призвали быть бдительнее и избегать открытых участков")
        self.assertEqual(r["role"], "объект")
        self.assertEqual(r["object"], "жители")

    def test_transitive_verb_makes_object(self):
        r = self._one("Делегация посетила металлургический завод в Димитровграде")
        self.assertEqual(r["role"], "объект")
        self.assertEqual(r["object"], "бизнес")

    def test_oblique_case_not_subject(self):
        # «в аэропорту» — косвенный падеж: место, а не действующее лицо
        r = self._one("Ограничения в аэропорту Ульяновска сняты Росавиацией")
        self.assertNotEqual(r.get("actor"), "учреждения")

    def test_attribution_is_not_object(self):
        # «по данным полиции» — источник сведений, а не объект действия
        roles = self._roles("По данным полиции, водитель скрылся с места происшествия")
        self.assertEqual(roles["контроль"][0], "упоминание")

    def test_clause_boundary_protects_subject(self):
        # пассив в другом придаточном не должен понижать роль актора
        r = self._one("Погибли два человека, еще шестеро пострадали, сообщил глава города")
        self.assertEqual(r["role"], "субъект")
        self.assertEqual(r["actor"], "власть")

    def test_impersonal_lead(self):
        r = self._one("Сообщается о перебоях с подачей горячей воды в Засвияжском районе")
        self.assertEqual(r["role"], "безличный")

    def test_no_actor_in_lead(self):
        r = self._one("Мост между улицами Смычки и Шевченко откроют 15 сентября")
        self.assertEqual(r["role"], "без актора")

    def test_word_boundaries_block_false_actors(self):
        # «улице» ≠ «лицей», «беспилотника» ≠ «пилот», «почти» ≠ «почта»,
        # «машиностроитель» ≠ «строитель», «Губернаторский» ≠ «губернатор»
        for sent in ("Работы на улице Кирова продолжились ночью",
                     "ПВО перехватили 222 украинских беспилотника",
                     "Интернет может почти опустеть от живых людей",
                     "Фестиваль «Юный машиностроитель» прошёл в регионе",
                     "В Ульяновске после благоустройства открыли сквер «Губернаторский»"):
            roles = self._roles(sent)
            self.assertNotIn("учреждения", roles, sent)
            self.assertNotIn("бизнес", roles, sent)

    def test_service_kinds(self):
        self.assertEqual(analytics.service_kind({"title": "Прогноз погоды на 15 сентября",
                                                 "text": "Гидрометцентр обещает заморозки"}), "погода")
        self.assertEqual(analytics.service_kind({"title": "Ракетная опасность в регионе",
                                                 "text": "Укройтесь в помещении"}), "оповещение")
        # сообщение о последствиях — новость, а не уведомление
        self.assertIsNone(analytics.service_kind({"title": "Ракетная опасность в регионе",
                                                  "text": "ПВО сбили три цели, пострадавших нет"}))
        self.assertIsNone(analytics.service_kind({"title": "Открылась выставка", "text": ""}))

    def test_first_person_marked(self):
        self.assertTrue(analytics.AGENCY_FIRST_PERSON_X.search("Мы решили сохранить льготы"))
        self.assertFalse(analytics.AGENCY_FIRST_PERSON_X.search("Администрация решила сохранить льготы"))


class TestAgencyIndex(unittest.TestCase):
    """Агрегат «Индекс агентности»: кому поле отдаёт действие."""

    CFG = {"municipalities": {}, "categories": [{"id": "society", "name": "Общество"}]}

    def _it(self, i, title, hours_ago=3, tier=2, channel="ch1"):
        from datetime import datetime, timedelta, timezone
        UTC4 = timezone(timedelta(hours=4))
        dt = datetime.now(UTC4) - timedelta(hours=hours_ago)
        return {"id": f"x{i}", "title": title, "text": title, "published": dt.isoformat(),
                "category": "society", "source_type": "tg", "channel": channel,
                "source": f"t.me/{channel}", "tier": tier}

    def test_index_and_verdict(self):
        items = [self._it(1, "Жители села Карлинское требуют ремонта дороги"),
                 self._it(2, "Рабочие завода начали забастовку и требуют зарплату"),
                 self._it(3, "Губернатор заявил о решении проблемы")]
        r = analytics.agency_index(items)
        self.assertEqual(r["n"], 3)
        self.assertEqual(r["people_subjects"], 2)
        self.assertEqual(r["power_subjects"], 1)
        self.assertAlmostEqual(r["agency_index"], 2.0)
        self.assertEqual(r["verdict"], "действие у людей")
        self.assertGreater(r["actor_density"], 0)

    def test_service_messages_excluded(self):
        items = [self._it(1, "Жители требуют ремонта"),
                 self._it(2, "Ракетная опасность на территории области"),
                 self._it(3, "Прогноз погоды: гидрометцентр обещает заморозки")]
        r = analytics.agency_index(items)
        self.assertEqual(r["n"], 1)
        self.assertEqual(r["excluded_service"].get("оповещение"), 1)
        self.assertEqual(r["excluded_service"].get("погода"), 1)

    def test_empty_week(self):
        r = analytics.agency_index([])
        self.assertNotIn("agency_index", r)
        self.assertEqual(r["n"], 0)


class TestFrames(unittest.TestCase):
    """Фрейм-карта: как один сюжет назван в разных каналах."""

    def _it(self, i, title, channel="a", tier=1, cluster=None, dup_of=None, text=""):
        from datetime import datetime, timedelta, timezone
        UTC4 = timezone(timedelta(hours=4))
        dt = datetime.now(UTC4) - timedelta(hours=2)
        it = {"id": f"f{i}", "title": title, "text": text or title, "published": dt.isoformat(),
              "category": "society", "source_type": "tg", "channel": channel,
              "source": f"t.me/{channel}", "tier": tier}
        if cluster:
            it["cluster"] = cluster
        if dup_of:
            it["dup_of"] = dup_of
        return it

    def test_frame_classification(self):
        cases = [("На трассе столкнулись два автомобиля, есть погибшие", "ЧП"),
                 ("Прокуратура проверила школы и выписала предписание", "надзор"),
                 ("Плановый ремонт дороги завершён досрочно", "работы"),
                 ("Наша команда выиграла кубок и завоевала медаль", "достижение"),
                 ("Губернатор посетил район с рабочим визитом и провёл совещание", "ритуал"),
                 ("Как получить льготу: инструкция и список документов", "услуга"),
                 ("Ракетная опасность объявлена в регионе, звучат сирены", "тревога"),
                 ("Опрос: две трети россиян не читали программу партий", "статистика"),
                 ("Открываем ночной чат: поиграем в города, пишите в комментарии", "интерактив"),
                 ("Гидрометцентр: завтра облачная погода, местами дождь", "погода")]
        for title, expected in cases:
            self.assertEqual(analytics.frame_of({"title": title, "text": ""})[0], expected, title)

    def test_default_frame(self):
        self.assertEqual(analytics.frame_of({"title": "Встреча прошла спокойно", "text": ""})[0],
                         analytics.FRAME_DEFAULT)

    def test_divergence_within_cluster(self):
        head = self._it(1, "Отключение воды на три дня: плановые работы на сетях",
                        channel="gov", tier=1, cluster=2)
        dup = self._it(2, "😱 Район остался без воды, жители жалуются на аварию",
                       channel="agg", tier=2, dup_of="f1")
        r = analytics.frame_map([head, dup])
        self.assertEqual(r["clusters"], 1)
        self.assertEqual(r["divergent"], 1)
        self.assertAlmostEqual(r["divergence_share"], 1.0)
        self.assertTrue(r["examples"][0]["tier_conflict"])
        self.assertEqual(r["tier_conflicts"], 1)

    def test_same_frame_no_divergence(self):
        head = self._it(1, "На трассе столкнулись два автомобиля, есть пострадавшие",
                        channel="a", tier=2, cluster=2)
        dup = self._it(2, "ДТП на трассе: столкнулись автомобили, пострадали люди",
                       channel="b", tier=2, dup_of="f1")
        r = analytics.frame_map([head, dup])
        self.assertEqual(r["divergent"], 0)
        self.assertEqual(r["tier_conflicts"], 0)

    def test_tier_matrix_shares(self):
        items = [self._it(1, "Пожар в доме: погибли люди", channel="agg", tier=2),
                 self._it(2, "Открыли новую школу, вручили подарки", channel="gov", tier=1)]
        r = analytics.frame_map(items)
        self.assertEqual(r["tier_matrix"]["T2"]["frames"]["ЧП"], 1.0)
        self.assertEqual(r["tier_matrix"]["T1"]["frames"]["достижение"], 1.0)


class TestAiTrace(unittest.TestCase):
    """ИИ-след: признаки шаблонного и машинного производства текста."""

    def _it(self, i, title, text, channel="a", tier=2):
        from datetime import datetime, timedelta, timezone
        UTC4 = timezone(timedelta(hours=4))
        dt = datetime.now(UTC4) - timedelta(hours=2)
        return {"id": f"t{i}", "title": title, "text": text, "published": dt.isoformat(),
                "category": "society", "source_type": "tg", "channel": channel,
                "source": f"t.me/{channel}", "tier": tier}

    def test_boilerplate_tail(self):
        r = analytics.ai_trace([self._it(1, "Новость", "Текст новости. Мы в Telegram | Мы в MAX")])
        self.assertIn("шаблонная концовка", r["signals"])

    def test_emoji_block(self):
        r = analytics.ai_trace([self._it(1, "🔥⚡️❗️🚨 Срочно", "🔥 🔥 🔥 Пожар потушен")])
        self.assertIn("эмодзи-блок", r["signals"])

    def test_caps_title(self):
        r = analytics.ai_trace([self._it(1, "РОЗЫГРЫШ БИЛЕТА НА КОНЦЕРТ", "Обычный текст")])
        self.assertIn("капс-заголовок", r["signals"])

    def test_machine_cliche(self):
        r = analytics.ai_trace([self._it(1, "Открытие завода",
                                         "Важно отметить, что в современном мире предприятие "
                                         "играет важную роль и является неотъемлемой частью экономики")])
        self.assertIn("клише машинного текста", r["signals"])

    def test_verbatim_across_sources(self):
        sent1 = ("Глава города подчеркнул, что ремонт моста завершится до конца месяца "
                 "и движение откроют для всех участников.")
        sent2 = ("Подрядчик обязался уложить верхний слой асфальта и нанести разметку "
                 "до начала октября текущего года.")
        items = [self._it(1, "Мост откроют", sent1 + " " + sent2 + " Первое предложение уникальное А.",
                          channel="a"),
                 self._it(2, "Мост откроют скоро", sent1 + " " + sent2 + " Второе предложение другое Б.",
                          channel="b")]
        r = analytics.ai_trace(items)
        self.assertEqual(r["verbatim_items"], 2)
        self.assertGreaterEqual(r["verbatim_groups"], 2)
        self.assertIn("дословный повтор", r["signals"])

    def test_verbatim_same_source_not_counted(self):
        long_sent = ("Глава города подчеркнул, что ремонт моста завершится до конца месяца "
                     "и движение откроют для всех участников. "
                     "Подрядчик обязался уложить верхний слой асфальта и нанести разметку "
                     "до начала октября текущего года")
        items = [self._it(1, "Мост", long_sent, channel="a"),
                 self._it(2, "Мост 2", long_sent, channel="a")]
        r = analytics.ai_trace(items)
        self.assertEqual(r["verbatim_items"], 0)

    def test_clean_news_has_no_trace(self):
        r = analytics.ai_trace([self._it(1, "В Ульяновске отремонтировали дорогу",
                                         "Подрядчик завершил работы на улице Гагарина. "
                                         "Движение открыто, гарантия пять лет.")])
        self.assertEqual(r["any_n"], 0)
        self.assertEqual(r["any_share"], 0.0)

    def test_strong_signal_needs_two(self):
        items = [self._it(1, "🔥⚡️❗️🚨 Срочно", "🔥 🔥 🔥 Мы в Telegram | Мы в MAX")]
        r = analytics.ai_trace(items)
        self.assertEqual(r["strong_n"], 1)
        self.assertEqual(r["strong_share"], 1.0)

    def test_empty_week(self):
        r = analytics.ai_trace([])
        self.assertNotIn("any_share", r)


class TestDedupStability(unittest.TestCase):
    """Устойчивость дедупликации: пороговый эксперимент и сомнительные склейки."""

    def _it(self, i, title, text, hours_ago=2, channel=None, tier=2):
        from datetime import datetime, timedelta, timezone
        UTC4 = timezone(timedelta(hours=4))
        dt = datetime.now(UTC4) - timedelta(hours=hours_ago)
        ch = channel or f"ch{i}"
        return {"id": f"d{i}", "title": title, "text": text, "published": dt.isoformat(),
                "category": "society", "source_type": "tg", "channel": ch,
                "source": f"t.me/{ch}", "tier": tier, "views": 100}

    def _week(self):
        return [
            self._it(1, "На трассе Барыш — Карсун столкнулись два автомобиля",
                     "По предварительным данным, водитель не справился с управлением, "
                     "пострадали два человека, движение восстановлено", hours_ago=3, channel="a"),
            self._it(2, "На трассе Барыш — Карсун столкнулись две легковушки",
                     "По предварительным данным, водитель не справился с управлением, "
                     "пострадали два человека, движение восстановлено", hours_ago=4, channel="b"),
            self._it(3, "Открылась новая школа в Засвияжском районе",
                     "Школа приняла 800 учеников, построена по национальному проекту",
                     hours_ago=5, channel="c"),
            self._it(4, "Внимание! Ракетная опасность на территории Ульяновской области",
                     "Просим немедленно укрыться в помещениях, соблюдать спокойствие и не выходить "
                     "на улицу до отбоя", hours_ago=6, channel="d"),
            self._it(5, "Снят режим «Ракетная опасность» на территории Ульяновской области",
                     "Просим покинуть укрытия, соблюдать спокойствие и не выходить на улицу "
                     "без необходимости", hours_ago=7, channel="d"),
            self._it(6, "Фермеры района завершили уборочную кампанию",
                     "Урожайность выше прошлогодней, техника отработала без сбоев",
                     hours_ago=8, channel="e"),
        ]

    def test_sweep_is_monotonic(self):
        r = analytics.dedup_stability(self._week(), {"settings": {"dedup_threshold": 0.45}})
        shares = [s["original_share"] for s in r["sweep"]]
        # чем выше порог, тем меньше склеек и выше доля оригинального
        self.assertEqual(shares, sorted(shares))
        dups = [s["dups"] for s in r["sweep"]]
        self.assertEqual(dups, sorted(dups, reverse=True))
        self.assertEqual(r["threshold"], 0.45)
        self.assertLessEqual(r["original_range"][0], r["original_share"])
        self.assertGreaterEqual(r["original_range"][1], r["original_share"])

    def test_near_duplicates_are_merged(self):
        r = analytics.dedup_stability(self._week(), {"settings": {"dedup_threshold": 0.45}})
        self.assertGreaterEqual(r["clusters"], 1)
        self.assertGreater(r["pairs"], 0)

    def test_antagonistic_pair_detected(self):
        items = self._week()
        self.assertTrue(analytics._antagonistic(items[3], items[4]))
        self.assertFalse(analytics._antagonistic(items[4], items[4]))
        self.assertFalse(analytics._antagonistic(items[0], items[2]))

    def test_guards_block_antagonistic_merge(self):
        # «Ракетная опасность» ↔ «Снят режим» больше не склеиваются: охрана по антагонизму
        r = analytics.dedup_stability(self._week(), {"settings": {"dedup_threshold": 0.40}})
        self.assertEqual(r["antagonistic_dups"], 0)
        self.assertGreaterEqual(r["blocked_by_guards"].get("антагонизм формуляра", 0), 1)
        self.assertIn("policy", r)
        self.assertEqual(r["policy"]["dedup_max_span_h"], 24)

    def test_guards_block_service_episode_merge(self):
        # разные сутки служебного формуляра не склеиваются даже на очень низком пороге
        items = self._five(2, 60)
        for thr in (0.45, 0.30, 0.20):
            r = analytics.dedup_stability(items, {"settings": {"dedup_threshold": thr}})
            self.assertGreaterEqual(
                r["blocked_by_guards"].get("служебный формуляр вне окна", 0), 1,
                f"порог {thr}: формуляр разных суток склеился")

    def test_sweep_reports_guards_effect(self):
        r = analytics.dedup_stability(self._week(), {"settings": {"dedup_threshold": 0.45}})
        for row in r["sweep"]:
            self.assertIn("original_share_noguards", row)
            # с охранными правилами склеек не больше, чем без них
            # без охранных правил склеек больше → доля оригинального ниже
            self.assertLessEqual(row["original_share_noguards"], row["original_share"] + 1e-9)

    def _five(self, first_h, second_h, first_ch="w", second_ch="v",
              title="Прогноз погоды на завтра: облачно и небольшой дождь",
              text="По информации гидрометцентра ожидается переменная облачность и небольшой дождь"):
        return [self._it(1, title, text, hours_ago=first_h, channel=first_ch),
                self._it(2, title, text, hours_ago=second_h, channel=second_ch),
                self._it(3, "Открылась новая школа в Засвияжском районе",
                         "Школа приняла восемьсот учеников", hours_ago=3, channel="c"),
                self._it(4, "Фермеры завершили уборочную кампанию",
                         "Урожайность выше прошлогодней", hours_ago=4, channel="e"),
                self._it(5, "Губернатор провёл совещание по развитию района",
                         "Обсудили строительство дорог", hours_ago=5, channel="g")]

    def test_service_episode_not_merged(self):
        # одинаковый прогноз погоды с разбросом 58 ч — разные сутки, склейка запрещена
        r = analytics.dedup_stability(self._five(2, 60), {"settings": {"dedup_threshold": 0.45}})
        self.assertEqual(r["episode_clusters"], 0)
        self.assertGreaterEqual(r["blocked_by_guards"].get("служебный формуляр вне окна", 0), 1)

    def test_service_episode_merged_inside_window(self):
        # тот же формуляр в пределах 6 ч — это одно и то же сообщение, склеиваем
        r = analytics.dedup_stability(self._five(2, 5), {"settings": {"dedup_threshold": 0.45}})
        self.assertEqual(r["episode_clusters"], 0)
        self.assertGreaterEqual(r["clusters"], 1)

    def test_verbatim_reprint_outside_window_still_merges(self):
        # дословный повтор (Жаккар 1.0) обычного материала через 40 ч — склеиваем
        items = self._five(2, 42,
                           title="На улице Гагарина уложили новый асфальт и нанесли разметку",
                           text="Подрядчик завершил работы по национальному проекту, "
                                "гарантия на покрытие составляет пять лет")
        r = analytics.dedup_stability(items, {"settings": {"dedup_threshold": 0.45}})
        self.assertGreaterEqual(r["clusters"], 1)
        self.assertEqual(r["blocked_by_guards"].get("вне окна перепечаток", 0), 0)

    def test_sample_marks_flags(self):
        r = analytics.dedup_stability(self._week(), {"settings": {"dedup_threshold": 0.45}})
        for s in r["sample"]:
            self.assertIn("same_source", s)
            self.assertIn("antagonistic", s)
            self.assertIn("jaccard", s)
            self.assertIn("a", s)
            self.assertIn("b", s)

    def test_too_few_items(self):
        r = analytics.dedup_stability([], {"settings": {"dedup_threshold": 0.45}})
        self.assertNotIn("sweep", r)


class TestInfospaceW4(unittest.TestCase):
    """Сборка Волны 4 и её появление в infospace.json."""

    def test_w4_has_four_blocks(self):
        from datetime import datetime, timedelta, timezone
        UTC4 = timezone(timedelta(hours=4))
        dt = (datetime.now(UTC4) - timedelta(hours=3)).isoformat()
        items = [{"id": "w1", "title": "Жители улицы Заречной требуют ремонта дороги",
                  "text": "Жители улицы Заречной требуют ремонта дороги уже второй год",
                  "published": dt, "category": "society", "source_type": "tg",
                  "channel": "a", "source": "t.me/a", "tier": 2} for _ in range(6)]
        w4 = analytics.build_infospace_w4(items, {"settings": {"dedup_threshold": 0.45}})
        self.assertEqual(set(w4), {"generated_local", "agency", "frames", "ai_trace", "dedup"})
        self.assertEqual(w4["agency"]["n"], 6)
        self.assertIn("frame_mix", w4["frames"])

    def test_w4_survives_bad_items(self):
        w4 = analytics.build_infospace_w4([{"id": "x"}], None)
        self.assertIn("agency", w4)


class TestPageStructure(unittest.TestCase):
    """Регрессия на вёрстку: незакрытый .sec-head в «Волне 3» (15.09) превращал все
    следующие разделы во flex-потомки заголовка — страница «съезжала» вниз, а
    оборванный тег «<» в «Выводах наблюдения» проглатывал закрытие .page.
    Проверяем сгенерированные страницы: баланс div, единая глубина разделов,
    отсутствие оборванных тегов."""

    PAGES = ("infospace.html", "index.html", "digests/today.html")

    @staticmethod
    def _read(path):
        with open(path, encoding="utf-8") as f:
            return f.read()

    @staticmethod
    def _depths(html):
        import re
        depth, heads = 0, []
        for m in re.finditer(r"<div\b|</div>|<h2[^>]*>([^<]{3,70})</h2>", html):
            t = m.group(0)
            if t.startswith("<h2"):
                heads.append((m.group(1).strip(), depth))
            elif t.startswith("<div"):
                depth += 1
            else:
                depth -= 1
        return depth, heads

    def test_pages_balanced_and_no_broken_tags(self):
        import os
        import re
        checked = 0
        for rel in self.PAGES:
            path = os.path.join(BASE, rel)
            if not os.path.exists(path):
                continue
            html = self._read(path)
            checked += 1
            depth, _heads = self._depths(html)
            self.assertEqual(depth, 0, f"{rel}: баланс <div> не нулевой ({depth:+d})")
            self.assertNotRegex(html, r"<\s*\n", f"{rel}: оборванный тег «<»")
            self.assertNotRegex(html, r"</div>\s*/div>", f"{rel}: битый закрывающий тег")
        self.assertGreaterEqual(checked, 1, "нет ни одной сгенерированной страницы для проверки")

    def test_infospace_sections_are_siblings(self):
        """Все разделы «Инфопространства», включая Волны 1–4, — соседи одного уровня."""
        import os
        path = os.path.join(BASE, "infospace.html")
        if not os.path.exists(path):
            self.skipTest("infospace.html не собран")
        _depth, heads = self._depths(self._read(path))
        self.assertTrue(heads, "не найдено ни одного <h2>")
        deep = [h for h, d in heads if d != heads[0][1]]
        self.assertEqual(deep, [], f"разделы на разной глубине: {deep[:4]}")
        waves = {h: d for h, d in heads if h.startswith("Волна ")}
        self.assertGreaterEqual(len(waves), 4, f"ожидались Волны 1–4, найдено: {list(waves)}")


class TestCiPush(unittest.TestCase):
    """ci_push.sh: защита публикации выпуска от гонки с ручным push.
    Кейс 15.09.2026 — прогон на 7a50309 упал на «git push» (rejected, fetch first),
    Pages не опубликовался. Проверены синтаксис, стратегия (rebase → пересборка → retry)
    и то, что все три workflow переведены на скрипт."""

    def setUp(self):
        self.path = os.path.join(BASE, "ci_push.sh")
        if not os.path.exists(self.path):
            self.skipTest("ci_push.sh отсутствует")
        with open(self.path, encoding="utf-8") as f:
            self.src = f.read()

    def test_bash_syntax(self):
        import subprocess
        r = subprocess.run(["bash", "-n", self.path], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, f"bash -n: {r.stderr}")

    def test_strategy_present(self):
        for needle in ("git fetch -q origin", "git rebase", "git rebase --abort",
                       'git reset --hard -q "origin/$BRANCH"', "REBUILD", "git push origin",
                       "CI_PUSH_ATTEMPTS", "sleep 15"):
            self.assertIn(needle, self.src, f"в ci_push.sh нет «{needle}»")

    def test_no_set_e(self):
        # set -e оборвал бы скрипт на первом же отклонённом push — нужен мягкий режим
        first = [l for l in self.src.split("\n") if l.startswith("set ")][:1]
        self.assertTrue(first, "нет строки set …")
        self.assertNotIn("-e", first[0], "set -e сломает повторные попытки push")

    def test_workflows_use_script(self):
        wf_dir = os.path.join(BASE, ".github", "workflows")
        names = [f for f in os.listdir(wf_dir) if f.endswith((".yml", ".yaml"))]
        self.assertGreaterEqual(len(names), 3)
        for name in names:
            with open(os.path.join(wf_dir, name), encoding="utf-8") as f:
                text = f.read()
            self.assertIn("ci_push.sh", text, f"{name}: не использует ci_push.sh")
            self.assertIn("REBUILD_CMD", text, f"{name}: не задана команда пересборки")
            self.assertNotRegex(text, r"^\s*git push\s*$",
                                f"{name}: остался голый «git push» — гонка не защищена")

    def test_rebuild_command_is_pipeline(self):
        # пересборка при конфликте должна гонять настоящий конвейер, а не только генератор
        with open(os.path.join(BASE, ".github", "workflows", "daily.yml"), encoding="utf-8") as f:
            daily = f.read()
        self.assertIn("bash run.sh", daily)

    def test_stages_everything_by_default(self):
        """Без явных путей коммитится всё. Дефолт «только сгенерированное» однажды
        оставил правки кода вне коммита (15.09.2026), и их стёр последующий reset --hard."""
        self.assertIn("git add -A", self.src)

    def test_hard_reset_only_for_generated(self):
        """reset --hard допустим, только если в локальных коммитах нет кода:
        иначе берём merge -X ours (код наш, сгенерированное пересобирается)."""
        for needle in ("GENERATED_RE", "CODE_FILES", "merge -X ours"):
            self.assertIn(needle, self.src, f"нет {needle} — защита от потери кода отсутствует")
        # проверка состава локальных коммитов идёт ДО разрушающей команды
        # (ищем именно «git reset --hard»: в шапке-комментарии слово тоже упоминается)
        reset_cmd = self.src.index("git reset --hard")
        self.assertLess(self.src.index("GENERATED_RE"), reset_cmd)
        self.assertLess(self.src.index("CODE_FILES"), reset_cmd)
        # и до слияния, которое приходит на смену reset при наличии кода
        self.assertLess(self.src.index("CODE_FILES"), self.src.index("git merge -X ours"))

    def test_warns_about_uncommitted_files(self):
        """Неотданные правки в рабочем дереве — молча потерянная работа; скрипт обязан
        сообщить о них вслух."""
        self.assertIn("git status --porcelain", self.src)
        self.assertIn("незакоммиченные", self.src)


class TestDedupGuards(unittest.TestCase):
    """Правки dedup.py (пункт 7 спринта): окно перепечаток, антагонизм формуляров,
    внутриканальные повторы не считаются каскадом."""

    def _it(self, i, title, text, hours_ago=2, channel=None, tier=2):
        from datetime import datetime, timedelta, timezone
        UTC4 = timezone(timedelta(hours=4))
        dt = datetime.now(UTC4) - timedelta(hours=hours_ago)
        ch = channel or f"ch{i}"
        return {"id": f"g{i}", "title": title, "text": text, "published": dt.isoformat(),
                "category": "society", "source_type": "tg", "channel": ch,
                "source": f"t.me/{ch}", "tier": tier, "views": 100}

    def _run(self, items, threshold=0.45):
        """Прогон dedup.main() на временной базе."""
        import json
        import os
        import tempfile
        import dedup
        tmp = tempfile.mkdtemp()
        store = os.path.join(tmp, "store.jsonl")
        cfgp = os.path.join(tmp, "config.json")
        with open(store, "w", encoding="utf-8") as f:
            for it in items:
                f.write(json.dumps(it, ensure_ascii=False) + "\n")
        with open(cfgp, "w", encoding="utf-8") as f:
            json.dump({"settings": {"dedup_threshold": threshold, "dedup_max_span_h": 24,
                                    "dedup_service_span_h": 6, "dedup_verbatim_jaccard": 0.85}}, f)
        old_store, old_base = dedup.STORE, dedup.BASE
        old_argv = sys.argv
        try:
            dedup.STORE = store
            dedup.BASE = tmp
            sys.argv = ["dedup.py", "--quiet"]
            dedup.main()
            with open(store, encoding="utf-8") as f:
                return [json.loads(l) for l in f if l.strip()]
        finally:
            dedup.STORE, dedup.BASE, sys.argv = old_store, old_base, old_argv

    def test_antagonistic_pair_not_merged(self):
        items = [self._it(1, "Внимание! Ракетная опасность на территории Ульяновской области",
                          "Просим немедленно укрыться в помещениях, соблюдать спокойствие "
                          "и не выходить на улицу до отбоя", hours_ago=2, channel="gov"),
                 self._it(2, "Снят режим «Ракетная опасность» на территории Ульяновской области",
                          "Просим покинуть укрытия, соблюдать спокойствие и не выходить "
                          "на улицу без необходимости", hours_ago=3, channel="media")]
        out = self._run(items)
        self.assertTrue(all(not it.get("dup_of") for it in out),
                        "режим и его отмена склеились — охрана не сработала")

    def test_same_source_repeat_flagged_and_excluded_from_cascade(self):
        text = ("На улице Гагарина уложили новый асфальт и нанесли разметку, "
                "работы приняты комиссией администрации города")
        items = [self._it(1, "На улице Гагарина уложили новый асфальт", text, hours_ago=2, channel="a"),
                 self._it(2, "На улице Гагарина уложили новый асфальт", text, hours_ago=3, channel="a"),
                 self._it(3, "Гагарина: новый асфальт уложили, разметку нанесли", text,
                          hours_ago=4, channel="b")]
        out = self._run(items)
        dups = [it for it in out if it.get("dup_of")]
        head = [it for it in out if it.get("cluster")][0]
        self.assertEqual(len(dups), 2)
        self.assertTrue(any(it.get("same_source") for it in dups), "повтор своего канала не помечен")
        self.assertNotIn("t.me/a", head["also_in"], "свой же канал попал в «также сообщили»")
        self.assertEqual(head["also_in"], ["t.me/b"])
        self.assertEqual(head["cluster"], 3)
        self.assertEqual(head["cluster_src"], 2)

    def test_old_window_rule_replaced(self):
        # прежний фильтр «diff > 100 по номеру даты» позволял склеивать разные сутки
        items = [self._it(1, "Сегодня облачно, небольшой дождь, ветер южный",
                          "Гидрометцентр сообщает о переменной облачности", hours_ago=2, channel="w"),
                 self._it(2, "Сегодня облачно, небольшой дождь, ветер южный",
                          "Гидрометцентр сообщает о переменной облачности", hours_ago=50, channel="v")]
        out = self._run(items)
        self.assertTrue(all(not it.get("dup_of") for it in out))

    def test_dedup_and_analytics_dictionaries_agree(self):
        """Словари намеренно продублированы в dedup.py и analytics.py — проверяем совпадение."""
        import dedup
        samples = [
            ({"title": "Ракетная опасность в регионе", "text": "Укройтесь в помещении"}, "оповещение"),
            ({"title": "Прогноз погоды на 15 сентября", "text": "Гидрометцентр обещает заморозки"}, "погода"),
            ({"title": "Ракетная опасность", "text": "ПВО сбили три цели, пострадавших нет"}, None),
            ({"title": "Открыли новую школу", "text": "Приняла 800 учеников"}, None),
        ]
        for it, expected in samples:
            self.assertEqual(dedup.service_kind(it), expected, it["title"])
            self.assertEqual(analytics.service_kind(it), expected, it["title"])
        onset = {"title": "Ракетная опасность объявлена", "text": "Укройтесь"}
        cancel = {"title": "Снят режим «Ракетная опасность»", "text": "Можно выходить"}
        self.assertTrue(dedup.antagonistic(onset, cancel))
        self.assertTrue(analytics._antagonistic(onset, cancel))
        self.assertFalse(dedup.antagonistic(cancel, cancel))
        self.assertFalse(analytics._antagonistic(cancel, cancel))


class TestCascadeSources(unittest.TestCase):
    """Каскады считаются по независимым источникам, а не по числу участников."""

    def _it(self, i, title, channel, cluster=None, cluster_src=None, dup_of=None, tier=2):
        from datetime import datetime, timedelta, timezone
        UTC4 = timezone(timedelta(hours=4))
        dt = datetime.now(UTC4) - timedelta(hours=2)
        it = {"id": f"c{i}", "title": title, "text": title, "published": dt.isoformat(),
              "category": "society", "source_type": "tg", "channel": channel,
              "source": f"t.me/{channel}", "tier": tier}
        if cluster:
            it["cluster"] = cluster
        if cluster_src:
            it["cluster_src"] = cluster_src
        if dup_of:
            it["dup_of"] = dup_of
        return it

    def test_cascade_sources_helper(self):
        self.assertEqual(analytics.cascade_sources({"cluster": 7, "cluster_src": 4}), 4)
        self.assertEqual(analytics.cascade_sources({"cluster": 7}), 7)   # старые записи
        self.assertEqual(analytics.cascade_sources({}), 0)

    def test_frames_skip_single_source_clusters(self):
        # 7 участников, но источника два: один канал повторил свой же пост
        head = self._it(1, "На трассе столкнулись два автомобиля, есть пострадавшие",
                        "a", cluster=7, cluster_src=2)
        dups = [self._it(i, "ДТП на трассе: пострадали люди", "a", dup_of="c1") for i in range(2, 8)]
        r = analytics.frame_map([head] + dups)
        self.assertEqual(r["clusters"], 1)

    def test_frames_ignore_pure_self_repeats(self):
        # cluster_src = 1 → каскада нет, в фрейм-карту не попадает
        head = self._it(1, "Пожар в доме на Гончарова: эвакуированы жители",
                        "a", cluster=3, cluster_src=1)
        dups = [self._it(i, "Пожар на Гончарова", "a", dup_of="c1") for i in (2, 3)]
        r = analytics.frame_map([head] + dups)
        self.assertEqual(r["clusters"], 0)


class TestSourcesRegistry(unittest.TestCase):
    """Реестр источников и config.json не должны расходиться: подключённый источник
    без атрибутов реестра молча искажает метрики «кто пишет», HHI и «свой голос»
    (кейс 15.09.2026 — районные газеты d4)."""

    def setUp(self):
        self.cfg = CFG
        with open(os.path.join(BASE, "sources_registry.json"), encoding="utf-8") as f:
            self.reg = json.load(f)
        self.entries = {e["id"]: e for e in self.reg.get("sources", [])}

    def _config_ids(self):
        ids = set()
        for ch in self.cfg.get("telegram_channels") or []:
            ids.add(f"tg:{ch['username']}")
        for s in self.cfg.get("rss_sources") or []:
            ids.add(f"rss:{s['name']}")
        for c in self.cfg.get("vk_communities") or []:
            ids.add(f"vk:{c['domain']}")
        for w in self.cfg.get("web_sources") or []:
            ids.add(f"web:{w['name']}")
        return ids

    def test_registry_matches_config(self):
        cfg_ids = self._config_ids()
        self.assertEqual(set(self.entries), cfg_ids,
                         f"расхождение: лишние {sorted(set(self.entries) - cfg_ids)[:4]}, "
                         f"не хватает {sorted(cfg_ids - set(self.entries))[:4]}")

    def test_meta_counts(self):
        self.assertEqual(self.reg["_meta"]["sources_total"], len(self.reg["sources"]))
        enabled = sum(1 for e in self.reg["sources"] if e.get("enabled"))
        self.assertEqual(self.reg["_meta"]["sources_enabled"], enabled)

    def test_enabled_sources_have_producer_type(self):
        missing = [e["id"] for e in self.reg["sources"]
                   if e.get("enabled") and not e.get("producer_type")]
        self.assertEqual(missing, [], f"без типа производителя: {missing}")

    def test_district_sources_connected(self):
        """Черновик d4 разморожен 15.09.2026: 4 районные газеты + 1 TG."""
        want = ["rss:Карсунский вестник", "rss:Кумәк көч", "rss:Звезда (Новомалыклинский р-н)",
                "rss:Кузоватовские вести", "tg:gazetazvezda73"]
        for sid in want:
            self.assertIn(sid, self.entries, f"{sid} не подключён")
            e = self.entries[sid]
            self.assertTrue(e.get("enabled"), f"{sid} выключен")
            self.assertEqual(e.get("producer_type"), "редакция", sid)
            self.assertTrue(e.get("territory", "").endswith("р-н"),
                            f"{sid}: территория {e.get('territory')}")
            self.assertTrue(e.get("voice_of"), f"{sid}: не заполнен «свой голос»")
            self.assertIn(e.get("owner_form"), ("государство", "не установлен"),
                          f"{sid}: районная газета не может быть «анонимом» ({e.get('owner_form')})")

    def test_municipal_sources_resolve(self):
        """Каждый ключ «своего голоса» — реальный источник мониторинга."""
        channels = {ch["username"] for ch in self.cfg.get("telegram_channels") or []}
        names = {s["name"] for s in self.cfg.get("rss_sources") or []}
        domains = {c["domain"] for c in self.cfg.get("vk_communities") or []}
        for key in self.cfg.get("municipal_sources") or []:
            self.assertTrue(key in channels or key in names or key in domains,
                            f"«свой голос» ссылается на несуществующий источник: {key}")

    def test_owner_form_anonymous_only_for_anonymous(self):
        """«аноним» — только агрегаторы/авторские/промо, не редакции и не пресс-службы."""
        bad = [e["id"] for e in self.reg["sources"]
               if e.get("owner_form") == "аноним"
               and e.get("producer_type") in ("редакция", "пресс-служба")]
        self.assertEqual(bad, [], f"редакции/пресс-службы в «анонимах»: {bad}")

class TestGosWebCollector(unittest.TestCase):
    """Сайты ОМСУ на платформе Госвеб (ulmeria.gosuslugi.ru): RSS нет, список новостей
    рендерится на сервере с микроформатом schema.org/NewsArticle. Фикстура — реальная
    страница, сохранена 15.09.2026 (первые 3 карточки из 10)."""

    URL = "https://ulmeria.gosuslugi.ru/dlya-zhiteley/novosti-i-reportazhi/"

    def setUp(self):
        self.html = read_fixture("gosweb_news.html")

    def test_parse_cards(self):
        items = collector.parse_gosweb_news(self.html, self.URL)
        self.assertEqual(len(items), 3)
        self.assertIn("афиша Ульяновска", items[0]["title"])
        self.assertEqual(items[0]["url"],
                         self.URL + "novosti-193_6946.html")
        self.assertTrue(items[0]["text"].startswith("По поручению главы города"))

    def test_date_local_to_utc(self):
        # 16:04:27 по Ульяновску (UTC+4) → 12:04:27 UTC
        items = collector.parse_gosweb_news(self.html, self.URL)
        self.assertEqual(items[0]["published"], "2026-09-15T12:04:27+00:00")

    def test_date_formats(self):
        self.assertEqual(collector.gosweb_to_utc("2026-09-15 16:04:27"),
                         "2026-09-15T12:04:27+00:00")
        self.assertTrue(collector.gosweb_to_utc("2026-09-15 07:30").startswith("2026-09-15T03:30"))
        self.assertTrue(collector.gosweb_to_utc("2026-09-15").startswith("2026-09-14T20:00"))
        self.assertTrue(collector.gosweb_to_utc("15.09.2026 16:04").startswith("2026-09-15T12:04"))
        self.assertIsNone(collector.gosweb_to_utc(""))
        self.assertIsNone(collector.gosweb_to_utc(None))

    def test_categories_and_photo_absolute(self):
        items = collector.parse_gosweb_news(self.html, self.URL)
        self.assertEqual(items[0]["categories"], ["Культура", "Физическая культура и спорт"])
        self.assertEqual(items[1]["categories"][0], "Образование")
        self.assertTrue(items[0]["photo"].startswith("https://ulmeria.gosuslugi.ru/netcat_files/"),
                        "фото должно быть абсолютным URL")

    def test_empty_and_garbage(self):
        self.assertEqual(collector.parse_gosweb_news("", self.URL), [])
        self.assertEqual(collector.parse_gosweb_news(None, self.URL), [])
        self.assertEqual(collector.parse_gosweb_news("<html><body>нет новостей</body></html>", self.URL), [])

    def test_card_without_headline_skipped(self):
        broken = self.html.replace("itemprop='url'", "itemprop='url-broken'", 1)
        items = collector.parse_gosweb_news(broken, self.URL)
        self.assertLessEqual(len(items), 3)

    def test_normalize_web_item(self):
        raw = {"source_type": "web", "source": "Администрация Ульяновска",
               "url": self.URL + "novosti-193_6946.html",
               "title": "Концерты, фотоконкурс, экскурсии и футбол: афиша Ульяновска на эту неделю",
               "text": "По поручению главы города учреждения социальной сферы подготовили программу.",
               "published": "2026-09-15T12:04:27+00:00", "views": None, "channel": None,
               "tier": 1, "photo": "https://ulmeria.gosuslugi.ru/netcat_files/x.jpg",
               "web_cats": ["Культура"]}
        it = collector.normalize_item(CFG, raw)
        self.assertIsNotNone(it)
        self.assertEqual(it["source_type"], "web")
        self.assertEqual(it["tier"], 1)
        self.assertEqual(it["channel"], None)
        self.assertEqual(it["web_cats"], ["Культура"])
        self.assertEqual(it["published"], "2026-09-15T12:04:27+00:00")
        self.assertTrue(it["id"])

    def test_collect_web_uses_fixture(self):
        cfg = dict(CFG, settings=dict(CFG["settings"], http_delay_sec=0),
                   web_sources=[{"name": "Администрация Ульяновска", "url": self.URL,
                                 "tier": 1, "enabled": True}])
        orig = collector.http_get
        collector.http_get = lambda url, c, timeout=None: self.html
        try:
            status = {}
            items = collector.collect_web(cfg, status, quiet=True)
        finally:
            collector.http_get = orig
        self.assertEqual(len(items), 3)
        self.assertTrue(status["web:Администрация Ульяновска"]["ok"])
        self.assertEqual(status["web:Администрация Ульяновска"]["items"], 3)
        self.assertTrue(all(i["source_type"] == "web" for i in items))

    def test_collect_web_disabled_and_empty(self):
        cfg = {"settings": dict(CFG["settings"], http_delay_sec=0),
               "web_sources": [{"name": "X", "url": "https://example.invalid/", "enabled": False}]}
        status = {}
        self.assertEqual(collector.collect_web(cfg, status, quiet=True), [])
        self.assertNotIn("web:X", status)                     # отключённый источник не опрашивается
        self.assertEqual(collector.collect_web({"settings": CFG["settings"]}, {}, quiet=True), [])

    def test_collect_web_error_is_soft(self):
        cfg = {"settings": dict(CFG["settings"], http_delay_sec=0, http_timeout_sec=1),
               "web_sources": [{"name": "Недоступный", "url": "https://nonexistent.invalid/",
                                "tier": 1, "enabled": True}]}
        status = {}
        self.assertEqual(collector.collect_web(cfg, status, quiet=True), [])
        self.assertFalse(status["web:Недоступный"]["ok"])
        self.assertTrue(status["web:Недоступный"]["error"])

    def test_config_has_web_source(self):
        ws = CFG.get("web_sources") or []
        self.assertTrue(ws, "в config.json нет web_sources")
        src = [w for w in ws if "ulmeria" in w.get("url", "")]
        self.assertEqual(len(src), 1)
        self.assertEqual(src[0]["tier"], 1)
        self.assertTrue(src[0]["enabled"])
        self.assertEqual(src[0]["platform"], "gosweb")


class TestWebSourceInRegistry(unittest.TestCase):
    """web-источник виден метрикам «Инфопространства» и реестру."""

    REG = {"web:Администрация Ульяновска": {
        "id": "web:Администрация Ульяновска", "producer_type": "пресс-служба",
        "territory": "Ульяновск", "owner": "Администрация города Ульяновска",
        "owner_status": "подтверждён", "owner_form": "официальные", "voice_of": "Ульяновск"}}

    def _it(self, i, source_type="web", source="Администрация Ульяновска", channel=None):
        from datetime import datetime, timedelta, timezone
        UTC4 = timezone(timedelta(hours=4))
        dt = datetime.now(UTC4) - timedelta(hours=2)
        return {"id": f"r{i}", "title": "Новость", "text": "Текст", "published": dt.isoformat(),
                "category": "politics", "source_type": source_type, "channel": channel,
                "source": source, "tier": 1}

    def test_registry_entry_resolved(self):
        w2 = analytics.build_infospace_w2([self._it(1)], {}, {}, registry=self.REG)
        self.assertEqual(w2["producer_mix"]["week"].get("пресс-служба"), 1)

    def test_web_counts_into_hhi(self):
        w3 = analytics.build_infospace_w3([self._it(1), self._it(2)], {}, registry=self.REG)
        self.assertEqual(w3["week_items"], 2)
        top = w3["top_owners"][0]
        self.assertIn("Администрация города Ульяновска", top["name"])
        self.assertEqual(top["form"], "официальные")
        self.assertEqual(top["n_sources"], 1)
        self.assertAlmostEqual(top["share"], 1.0)

    def test_web_without_registry_entry_is_press_office(self):
        # даже без записи в реестре сайт ОМСУ — пресс-служба, а не «не атрибутирован»
        w2 = analytics.build_infospace_w2([self._it(1)], {}, {}, registry={})
        self.assertEqual(w2["producer_mix"]["week"].get("пресс-служба"), 1)

    def test_seed_registry_knows_web_source(self):
        with open(os.path.join(BASE, "sources_registry.json"), encoding="utf-8") as f:
            reg = json.load(f)
        ids = {e["id"] for e in reg["sources"]}
        self.assertIn("web:Администрация Ульяновска", ids)
        e = [x for x in reg["sources"] if x["id"] == "web:Администрация Ульяновска"][0]
        self.assertEqual(e["kind"], "web")
        self.assertEqual(e["producer_type"], "пресс-служба")
        self.assertEqual(e["owner_form"], "официальные")
        self.assertEqual(e["owner_status"], "подтверждён")
        self.assertEqual(e["voice_of"], "Ульяновск")
