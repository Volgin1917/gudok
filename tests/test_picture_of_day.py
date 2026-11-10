#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_picture_of_day.py — модуль «Картина дня» (Yandex ART).

Проверяются ТОЛЬКО офлайн-пути: сборка брифа, конструирование промпта,
детерминизм выбора стиля, сохранение/чтение изображения и jsonl-истории,
эволюция весов, грациозный skip без API-ключа. Сетевой вызов Yandex ART
юнит-тестом не покрывается (требует ключ и сеть).
"""
import json
import os
import sys
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

import picture_of_day as pa  # noqa: E402

# гарантируем отсутствие живого ключа в тестах
os.environ.pop("GUDOK_ART_API_KEY", None)


class TestBrief(unittest.TestCase):
    def test_build_brief_structure(self):
        b = pa.build_brief("2026-09-30")
        self.assertEqual(b["date_iso"], "2026-09-30")
        self.assertIn("clusters", b)
        self.assertIn("contradictions", b)
        self.assertIn("frames", b)
        self.assertIn("agency_roles", b)
        self.assertIn("setters", b)
        self.assertIn("cascades", b)
        self.assertIsInstance(b["clusters"], list)
        # противоречия — это подмножество имён кластеров с gap=True
        gap_names = {c["name"] for c in b["clusters"] if c["gap"]}
        self.assertEqual(set(b["contradictions"]), gap_names)

    def test_brief_to_prompt_contains_style_and_topic(self):
        b = pa.build_brief("2026-09-30")
        prompt = pa.brief_to_prompt(b, "caricature")
        self.assertIn("политическая карикатура", prompt)
        self.assertIn("Без текста на изображении", prompt)
        # если есть кластеры — в промпте должно быть его имя или ключевые слова
        if b["clusters"]:
            top = b["clusters"][0]
            needle = top["name"] if top["name"] else ", ".join(top["terms"])
            self.assertIn(needle, prompt)

    def test_caption_self_contained(self):
        b = pa.build_brief("2026-09-30")
        cap = pa.caption_for(b, "constructivism")
        self.assertIn(b["date_ru"], cap)
        self.assertIn("#Гудок", cap)
        self.assertIn("#КартинаДня", cap)


class TestStyleChoice(unittest.TestCase):
    def test_override_wins(self):
        self.assertEqual(pa.choose_style(override="infographic"), "infographic")
        self.assertEqual(pa.choose_style(override="caricature", seed=1), "caricature")

    def test_deterministic_with_fixed_seed(self):
        w = {s: {"weight": 1.0} for s in pa.STYLES}
        a = pa.choose_style(weights=w, seed=42)
        b = pa.choose_style(weights=w, seed=42)
        self.assertEqual(a, b)

    def test_weighted_pick_favors_dominant(self):
        # все стили мизерны, один — доминирует => выбирается он при любом seed
        w = {s: {"weight": 0.0001} for s in pa.STYLES}
        w["caricature"]["weight"] = 1e9
        for seed in range(20):
            self.assertEqual(pa.choose_style(weights=w, seed=seed), "caricature")

    def test_unknown_override_falls_back(self):
        # неизвестный стиль -> выбор по весам (не падает)
        w = {s: {"weight": 1.0} for s in pa.STYLES}
        self.assertIn(pa.choose_style(override="nope", weights=w, seed=7), pa.STYLES)


class TestImageIO(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.join(BASE, "data", "pictures")
        os.makedirs(self.tmp, exist_ok=True)

    def test_save_and_read_image(self):
        data = b"\x89PNG\r\n\x1a\n" + bytes(range(256)) * 4
        path = pa.save_image(data, "2026-09-30", "infographic")
        self.assertTrue(os.path.exists(path))
        with open(path, "rb") as f:
            self.assertEqual(f.read(), data)
        # cleanup
        try:
            os.remove(path)
        except OSError:
            pass


class TestHistory(unittest.TestCase):
    def setUp(self):
        self.path = pa.JSONL
        self._bak = None
        if os.path.exists(self.path):
            self._bak = self.path + ".testbak"
            os.replace(self.path, self._bak)
        open(self.path, "w", encoding="utf-8").close()

    def tearDown(self):
        if os.path.exists(self.path):
            os.remove(self.path)
        if self._bak and os.path.exists(self._bak):
            os.replace(self._bak, self.path)

    def test_record_and_load(self):
        pa.record({"date": "2026-09-30", "style": "infographic",
                   "prompt": "p", "image": "x.png", "caption": "c"})
        pa.record({"date": "2026-10-01", "style": "caricature",
                   "prompt": "p2", "image": "y.png", "caption": "c2"})
        recs = pa.load_records()
        self.assertEqual(len(recs), 2)
        self.assertEqual(recs[0]["style"], "infographic")
        self.assertEqual(recs[1]["style"], "caricature")


class TestEvolve(unittest.TestCase):
    def test_update_weights_favors_better_style(self):
        recs = [
            {"style": "caricature", "views": 4000, "forwards": 1, "reactions": 1},
            {"style": "caricature", "views": 3500, "forwards": 1, "reactions": 1},
            {"style": "constructivism", "views": 0, "forwards": 0, "reactions": 0},
        ]
        w = pa.update_weights(records=recs)
        self.assertAlmostEqual(sum(v["weight"] for v in w.values()), 1.0, places=3)
        self.assertGreater(w["caricature"]["weight"], w["constructivism"]["weight"])
        self.assertEqual(w["caricature"]["count"], 2)
        self.assertEqual(w["constructivism"]["count"], 1)

    def test_update_weights_no_metrics_neutral(self):
        recs = [
            {"style": "infographic", "views": 0, "forwards": 0, "reactions": 0},
            {"style": "abstract_metaphor", "views": 0, "forwards": 0, "reactions": 0},
        ]
        w = pa.update_weights(records=recs)
        # без метрик все средние баллы равны 1.0 -> веса близки (сглаживание по count)
        vals = [v["weight"] for v in w.values() if v["count"] > 0]
        self.assertTrue(all(0.05 < x < 0.6 for x in vals))


class TestNoKeySkip(unittest.TestCase):
    def test_generate_image_raises_without_key(self):
        # токен точно пуст (файла data/art_token в тестах нет)
        self.assertEqual(pa.art_token(), "")
        with self.assertRaises(RuntimeError):
            pa.generate_image("test prompt")

    def test_run_offline_returns_prompt_not_image(self):
        # без флага --publish генерации нет; возвращается промпт, ключа image нет
        res = pa.run(date_str="2026-09-30", style="constructivism", quiet=True)
        self.assertIn("prompt", res)
        self.assertNotIn("image", res)
        self.assertIn(res["style"], pa.STYLES)


if __name__ == "__main__":
    unittest.main()
