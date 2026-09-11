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
