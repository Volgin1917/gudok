#!/usr/bin/env python3
"""Админ-панель модуля «Карта потока» (Flow Map).

Отдельный сервер для стенда (Debian), НЕ часть публичного статического сайта.
Привязан к 127.0.0.1 — без домена (по требованию заказчика домен откладывается).

Внешние зависимости разрешены заказчиком: Flask (роутинг/API) + waitress
(production-WSGI). При отсутствии waitress — откат на встроенный Flask-сервер.

Эндпоинты:
  GET  /                 -> отдаёт projects/flowmap_admin.html
  GET  /api/status       -> здоровье модуля (окно, узлы, гео, сюжеты, каскады, сеттеры, mtime)
  GET  /api/config       -> редактируемая часть config.flowmap
  POST /api/config       -> сохранить config.flowmap (с бэкапом config.json.bak)
  POST /api/rebuild      -> пересобрать projects/flowmap.html из текущих данных

Запуск:
  python3 flowmap_admin.py                 # http://127.0.0.1:8753
  GUDOK_ADMIN_PORT=9000 python3 flowmap_admin.py
  GUDOK_ADMIN_TOKEN=secret python3 flowmap_admin.py   # требует ?token=secret на /api/*
"""
import os
import sys
import json
import shutil
import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import generate

from flask import Flask, request, send_file, jsonify

BASE = generate.BASE
DATA = generate.DATA
CFG_PATH = os.path.join(BASE, "config.json")
FLOWMAP_HTML = os.path.join(BASE, "projects", "flowmap.html")
ADMIN_HTML = os.path.join(BASE, "projects", "flowmap_admin.html")

ALLOWED_X = ["official", "origin", "local"]
ALLOWED_Y = ["significance", "reach", "cascade", "growth"]
LAYER_KEYS = ["reprints", "tone", "setters", "cascades", "blind"]

app = Flask(__name__)


# ------------------------------------------------------------------ helpers
def load_cfg():
    with open(CFG_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_cfg(cfg):
    bak = CFG_PATH + ".bak"
    if os.path.exists(CFG_PATH):
        shutil.copy2(CFG_PATH, bak)
    with open(CFG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=1)


def get_flow_cfg(cfg):
    settings = cfg.setdefault("settings", {})
    fcfg = settings.setdefault("flowmap", {})
    fcfg.setdefault("window_days", 7)
    fcfg.setdefault("node_cap", 1500)
    fcfg.setdefault("default_axes", {"x": "official", "y": "significance"})
    fcfg.setdefault("enabled_layers", ["reprints", "tone", "setters", "cascades"])
    layers = {k: bool(k in fcfg.get("enabled_layers", [])) for k in LAYER_KEYS}
    fcfg["default_layers"] = layers
    return fcfg, layers


def parse_flow_from_html(path):
    """Извлечь FLOW из уже собранной страницы (отражает опубликованное состояние)."""
    try:
        html = open(path, encoding="utf-8").read()
    except OSError:
        return None
    i = html.find("var FLOW =")
    if i < 0:
        return None
    i += len("var FLOW =")
    j = i
    while j < len(html) and html[j] not in "{":
        j += 1
    if j >= len(html):
        return None
    depth = 0
    started = False
    end = None
    for k in range(j, len(html)):
        c = html[k]
        if c == "{":
            depth += 1
            started = True
        elif c == "}":
            depth -= 1
            if started and depth == 0:
                end = k + 1
                break
    if end is None:
        return None
    try:
        return json.loads(html[j:end])
    except Exception:
        return None


def collect_stats():
    cfg = load_cfg()
    fcfg, layers = get_flow_cfg(cfg)
    flow_html_exists = os.path.exists(FLOWMAP_HTML)
    flow = parse_flow_from_html(FLOWMAP_HTML) if flow_html_exists else None

    stats = {
        "window_days": fcfg.get("window_days"),
        "node_cap": fcfg.get("node_cap"),
        "default_axes": fcfg.get("default_axes"),
        "default_layers": layers,
        "flowmap_html_exists": flow_html_exists,
    }
    if flow:
        stats.update({
            "published_nodes": len(flow.get("raw", [])),
            "published_edges": len(flow.get("edges", [])),
            "published_munis": len(flow.get("munis", [])),
            "published_story_clusters": len(flow.get("story_clusters", [])),
            "published_cascades": len(flow.get("cascades_meta", [])),
            "published_setters": len(flow.get("setters", [])),
        })
    else:
        stats.update({
            "published_nodes": None,
            "published_edges": None,
            "published_munis": None,
            "published_story_clusters": None,
            "published_cascades": None,
            "published_setters": None,
        })

    def mt(p):
        return int(os.path.getmtime(p)) if os.path.exists(p) else None

    stats["mtime"] = {
        "config": mt(CFG_PATH),
        "store": mt(os.path.join(DATA, "store.jsonl")),
        "analytics": mt(os.path.join(DATA, "analytics.json")),
        "infospace": mt(os.path.join(DATA, "infospace.json")),
        "flowmap_html": mt(FLOWMAP_HTML),
    }
    data_mtimes = [v for v in (stats["mtime"]["store"],
                               stats["mtime"]["analytics"],
                               stats["mtime"]["infospace"]) if v]
    stats["last_collection"] = max(data_mtimes) if data_mtimes else None
    stats["now"] = int(datetime.datetime.now().timestamp())
    return stats


# ------------------------------------------------------------------ routes
@app.route("/")
def index():
    if os.path.exists(ADMIN_HTML):
        return send_file(ADMIN_HTML)
    return "admin page not found: projects/flowmap_admin.html", 404


@app.route("/api/status")
def api_status():
    return jsonify(collect_stats())


@app.route("/api/config")
def api_config():
    cfg = load_cfg()
    fcfg, layers = get_flow_cfg(cfg)
    return jsonify({
        "window_days": fcfg.get("window_days"),
        "node_cap": fcfg.get("node_cap"),
        "default_axes": fcfg.get("default_axes"),
        "default_layers": layers,
        "axis_options": {"x": ALLOWED_X, "y": ALLOWED_Y},
        "layer_keys": LAYER_KEYS,
    })


@app.route("/api/config", methods=["POST"])
def api_config_post():
    data = request.get_json(force=True, silent=True) or {}
    cfg = load_cfg()
    fcfg, _ = get_flow_cfg(cfg)

    if "window_days" in data:
        try:
            wd = int(data["window_days"])
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": "window_days должен быть числом"}), 400
        if not (1 <= wd <= 365):
            return jsonify({"ok": False, "error": "window_days вне диапазона 1..365"}), 400
        fcfg["window_days"] = wd

    if "node_cap" in data:
        try:
            nc = int(data["node_cap"])
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": "node_cap должен быть числом"}), 400
        if not (50 <= nc <= 20000):
            return jsonify({"ok": False, "error": "node_cap вне диапазона 50..20000"}), 400
        fcfg["node_cap"] = nc

    if "default_axes" in data:
        ax = data["default_axes"] or {}
        if ax.get("x") not in ALLOWED_X or ax.get("y") not in ALLOWED_Y:
            return jsonify({"ok": False, "error": "недопустимая ось X/Y"}), 400
        fcfg["default_axes"] = {"x": ax["x"], "y": ax["y"]}

    if "default_layers" in data:
        dl = data["default_layers"] or {}
        layers = {k: bool(dl.get(k, False)) for k in LAYER_KEYS}
        fcfg["enabled_layers"] = [k for k, v in layers.items() if v]
        fcfg["default_layers"] = layers

    save_cfg(cfg)
    return jsonify({"ok": True, "config": api_config().get_json()})


@app.route("/api/rebuild", methods=["POST"])
def api_rebuild():
    try:
        cfg = load_cfg()
        trends = generate.load_json(os.path.join(DATA, "trends.json")) or {}
        status = generate.load_json(os.path.join(DATA, "fetch_status.json"), {}) or {}
        store = generate.load_store()
        an = generate.load_json(os.path.join(DATA, "analytics.json")) or {}
        info = generate.load_json(os.path.join(DATA, "infospace.json")) or {}
        html = generate.render_flowmap_page(cfg, trends, store, status, an, info)
        os.makedirs(os.path.dirname(FLOWMAP_HTML), exist_ok=True)
        with open(FLOWMAP_HTML, "w", encoding="utf-8") as f:
            f.write(html)
        try:
            published_nodes = len(json.loads(_extract_flow(html)).get("raw", []))
        except Exception:
            published_nodes = None
        return jsonify({"ok": True, "bytes": len(html), "published_nodes": published_nodes})
    except Exception as e:  # noqa: BLE001
        return jsonify({"ok": False, "error": str(e)}), 500


def _extract_flow(html):
    i = html.find("var FLOW =")
    if i < 0:
        return "{}"
    i += len("var FLOW =")
    j = i
    while j < len(html) and html[j] not in "{":
        j += 1
    depth = 0
    started = False
    end = None
    for k in range(j, len(html)):
        c = html[k]
        if c == "{":
            depth += 1
            started = True
        elif c == "}":
            depth -= 1
            if started and depth == 0:
                end = k + 1
                break
    return html[j:end] if end else "{}"


# ------------------------------------------------------------------ run
def main():
    host = os.environ.get("GUDOK_ADMIN_HOST", "127.0.0.1")
    port = int(os.environ.get("GUDOK_ADMIN_PORT", "8753"))
    token = os.environ.get("GUDOK_ADMIN_TOKEN")

    if token:
        @app.before_request
        def _check_token():
            if request.path == "/":
                return None
            if (request.args.get("token") == token
                    or request.headers.get("X-Admin-Token") == token):
                return None
            return jsonify({"ok": False, "error": "forbidden"}), 403

    try:
        from waitress import serve
        print(f"[flowmap_admin] waitress на http://{host}:{port} (localhost, без домена)")
        serve(app, host=host, port=port)
    except ImportError:
        print(f"[flowmap_admin] waitress недоступен — встроенный Flask-сервер на http://{host}:{port}")
        app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    main()
