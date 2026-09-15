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
        self.assertEqual(r["promo_load"]["n"], 1)
        self.assertAlmostEqual(r["promo_load"]["share"], 0.5, places=2)

    def test_silent_groups(self):
        items = [self._it("a", 2, text="Врачи поликлиники №4 получили новое оборудование."),
                 self._it("b", 3, text="«Условия тяжёлые», — рассказали рабочие завода.")]
        r = analytics.build_infospace_w2(items, None, self.CFG_W2, registry=self.REG_W2)
        names = [g["group"] for g in r["silent_groups"]]
        self.assertIn("медики", names)          # упомянуты, но не процитированы
        self.assertNotIn("рабочие и инженеры", names)  # получили прямую речь
