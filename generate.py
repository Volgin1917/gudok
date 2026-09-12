#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generate.py — рендер выпусков издание Гудок.

Создаёт:
  * digests/digest_YYYY-MM-DD.html — ежедневный дайджест (лента, тренды, Telegram-монитор)
  * index.html — витрина центра: статус системы, пульс повестки, архив, источники, автоматизация

Данные: config.json, data/store.jsonl, data/trends.json, data/fetch_status.json
Запуск: python3 generate.py [--date YYYY-MM-DD]
"""
import argparse
from collections import Counter
import glob
import re
import html as H
import json
import os
from datetime import datetime, timedelta, timezone

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")
DIGESTS = os.path.join(BASE, "digests")
SPECIAL = os.path.join(BASE, "special")
UTC4 = timezone(timedelta(hours=4))

STATUS_META = {
    "rising": ("🔥 растёт", "#fde7e8", "#b02a2f"),
    "new": ("🆕 новая тема", "#e0f4ea", "#1d7a4d"),
    "stable": ("⚖️ стабильно", "#e8eef5", "#3d5a7a"),
    "fading": ("📉 спадает", "#f3edfa", "#5f418f"),
    "silent": ("💤 тишина", "#f0f2f5", "#8a99aa"),
}

CSS = """
:root{
  --paper:#faf9f6; --card:#fffdf9; --ink:#15181d; --ink2:#39424c; --muted:#57616c;
  --rule:#ddd8ce; --rule-strong:#15181d; --accent:#a31621; --accent-soft:#8c2b31;
  --link:#1d5b8f; --chip:#f1efe8; --focus:#1a6fd4;
  --navy:#15181d; --navy2:#15181d; --navy3:#22262c; --blue:#1d5b8f; --gold:#a31621;
  --line:#ddd8ce; --txt:#15181d; --bg:#faf9f6; --shadow:none;
  --serif:Georgia,"Times New Roman","Noto Serif",serif;
  --sans:-apple-system,"Segoe UI",Roboto,Arial,"Helvetica Neue",sans-serif;
}
:root[data-theme="dark"]{
  --paper:#131519; --card:#1a1d23; --ink:#e9e7e2; --ink2:#c3c9d0; --muted:#9aa4ae;
  --rule:#31363e; --rule-strong:#e9e7e2; --accent:#e05252; --accent-soft:#e88a8a;
  --link:#8fc1e9; --chip:#22262c;
  --navy:#e9e7e2; --navy2:#1a1d23; --navy3:#22262c; --blue:#8fc1e9; --gold:#e05252;
  --line:#31363e; --txt:#e9e7e2; --bg:#131519;
}
*{margin:0;padding:0;box-sizing:border-box;}
html{scroll-behavior:smooth;}
body{background:var(--paper);color:var(--ink);font:16.5px/1.6 var(--sans);-webkit-font-smoothing:antialiased;}
a{color:var(--link);text-decoration:underline;text-decoration-thickness:1px;text-underline-offset:2px;}
a:hover{color:var(--accent);}
h1,h2,h3,.mast-title,.lead-main h2,.lead-card h3,.news-item h4 a{font-family:var(--serif);}
:focus-visible{outline:2px solid var(--focus);outline-offset:2px;}
.skip{position:absolute;left:-999px;top:0;background:var(--ink);color:var(--paper);padding:8px 14px;z-index:99;}
.skip:focus{left:8px;}
@media (prefers-reduced-motion:reduce){*,*::before,*::after{animation:none!important;transition:none!important;scroll-behavior:auto!important;}}

/* шапка по образцу ведущих мировых изданий: флаг-линия, центровый мастхэд, линейки */
.flagline{max-width:1200px;margin:0 auto;display:flex;justify-content:space-between;gap:14px;
  font:400 11.5px/1.4 var(--sans);color:var(--muted);letter-spacing:.6px;text-transform:uppercase;
  padding-bottom:7px;border-bottom:1px solid var(--rule);flex-wrap:wrap;}
.flagline b{color:var(--ink2);font-weight:700;}
.topbar,.masthead{background:var(--paper);color:var(--ink);border-bottom:1px solid var(--rule-strong);padding:10px 22px 0;}
.topbar::after,.masthead::after{content:"";display:block;border-bottom:3px double var(--rule-strong);margin-top:10px;}
.topbar-inner,.mast-inner{max-width:1200px;margin:0 auto;display:block;text-align:center;}
.brand{display:flex;align-items:center;justify-content:center;gap:0;}
.brand>div{display:block;}
.brand-title{font-family:var(--serif);font-size:34px;font-weight:900;letter-spacing:4px;line-height:1.05;color:var(--ink);text-transform:uppercase;}
.brand-title span{color:var(--ink);}
.brand-sub{font-size:11px;color:var(--muted);letter-spacing:1.6px;text-transform:uppercase;margin-top:5px;}
.mast-brand{display:block;text-align:center;}
.mast-title{font-family:var(--serif);font-size:clamp(44px,9vw,84px);font-weight:900;letter-spacing:10px;line-height:1;color:var(--ink);text-transform:uppercase;}
.mast-title em{font-style:normal;color:var(--accent);}
.mast-slogan{font-size:11.5px;color:var(--muted);letter-spacing:2px;text-transform:uppercase;margin-top:9px;}
.mast-logo{display:none;}
.logo{display:none;}
.mast-right{display:none;}
.top-meta{margin:9px auto 0;display:flex;gap:0;flex-wrap:wrap;align-items:center;justify-content:center;}
.chip{background:none;border:none;border-radius:0;padding:0 10px;font:400 11.5px var(--sans);color:var(--muted);position:relative;}
.chip+.chip::before{content:"·";position:absolute;left:-3px;color:var(--rule);}
.chip b{color:var(--ink2);font-weight:700;}
.chip a,.chip-link,.flink{color:var(--muted);text-decoration:none;}
.chip a:hover,.chip-link:hover,.flink:hover{color:var(--accent);}
.theme-btn,.print-btn{border:none;background:none;color:var(--muted);font:400 11.5px var(--sans);padding:0 10px;cursor:pointer;text-decoration:underline;text-underline-offset:2px;}
.theme-btn:hover,.print-btn:hover{color:var(--accent);}
.ticker-wrap{background:var(--paper);color:var(--ink2);border-bottom:1px solid var(--rule);overflow:hidden;position:relative;height:30px;}
.ticker{display:flex;white-space:nowrap;animation:none;padding-left:110px;align-items:center;height:100%;}

.chip a,.chip-link,.flink{color:var(--ink2);text-decoration:none;}
.chip a:hover,.chip-link:hover{color:var(--accent);}
.dot{width:8px;height:8px;border-radius:50%;background:#2e7d4f;display:inline-block;}
.dot.err{background:var(--accent);}
.theme-btn,.print-btn{border:1px solid var(--rule);background:var(--chip);color:var(--ink2);font:700 12.5px var(--sans);padding:6px 12px;border-radius:3px;cursor:pointer;}
.theme-btn:hover,.print-btn:hover{border-color:var(--ink);color:var(--ink);}
.logo{width:40px;height:40px;object-fit:contain;border-radius:8px;background:#fff;flex-shrink:0;}

/* навигация: линейка с линейками, мобильный гамбургер */
.nav{background:var(--paper);border-bottom:1px solid var(--rule-strong);}
.nav-inner{max-width:1200px;margin:0 auto;display:flex;gap:0;flex-wrap:wrap;}
.nav a{color:var(--ink2);font:700 13px/1 var(--sans);text-transform:uppercase;letter-spacing:.8px;padding:12px 14px;border-bottom:3px solid transparent;text-decoration:none;}
.nav a:hover{color:var(--accent);}
.nav a.active{color:var(--ink);border-bottom-color:var(--accent);}
.nav a.nav-util{color:var(--muted);}
.nav-util-first{margin-left:auto;}
.nav-toggle{display:none;border:1px solid var(--rule);background:var(--chip);color:var(--ink);font:700 13px var(--sans);padding:8px 12px;border-radius:3px;cursor:pointer;margin:8px 14px;}
.nav-search{margin:8px 14px 8px auto;display:flex;}
.nav-search input{border:1px solid var(--rule);background:var(--card);color:var(--ink);font:14px var(--sans);padding:7px 11px;border-radius:3px;width:210px;}
.nav-search input:focus{outline:2px solid var(--focus);}
.search-drop{position:absolute;right:14px;top:100%;width:340px;max-height:320px;overflow:auto;background:var(--card);border:1px solid var(--rule);box-shadow:0 6px 18px rgba(0,0,0,.12);display:none;z-index:40;}
.search-drop.on{display:block;}
.search-drop a{display:block;padding:8px 12px;border-bottom:1px solid var(--rule);color:var(--ink);font-size:13px;text-decoration:none;}
.search-drop a:hover{background:var(--chip);}
.search-drop a span{color:var(--muted);font-size:11px;display:block;}
@media (max-width:900px){
  .nav-toggle{display:block;}
  .nav-inner{display:none;flex-direction:column;}
  body.nav-open .nav-inner{display:flex;}
  .nav a{border-bottom:1px solid var(--rule);padding:12px 16px;}
  .nav-search{margin:8px 14px;}
  .search-drop{width:auto;left:14px;}
}
.subnav{background:var(--paper);border-bottom:1px solid var(--rule);}
.subnav-inner{max-width:1200px;margin:0 auto;padding:7px 16px;display:flex;gap:15px;flex-wrap:wrap;font-size:12.5px;align-items:center;}
.subnav-inner a{color:var(--muted);text-decoration:none;}
.subnav-inner a:hover{color:var(--accent);}
.subnav .lbl{color:var(--ink);font-weight:800;text-transform:uppercase;font-size:10px;letter-spacing:1px;}

/* ленты и карточки — линейная газетная вёрстка без теней */
.page,.wrap1200{max-width:1200px;margin:0 auto;padding:0 18px;}
.sec-head{display:flex;align-items:baseline;gap:12px;margin:30px 0 14px;border-top:2px solid var(--rule-strong);padding-top:10px;}
.sec-head h2{font-family:var(--serif);font-size:23px;font-weight:900;color:var(--ink);}
.sec-head .line{flex:1;}
.sec-head .badge{font-size:11px;font-weight:700;background:var(--chip);color:var(--muted);padding:3px 10px;border-radius:3px;text-transform:uppercase;letter-spacing:.6px;}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:22px;}
.grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;}
.main-grid{display:grid;grid-template-columns:1fr 360px;gap:26px;align-items:start;}
.card{background:var(--card);border:1px solid var(--rule);border-radius:4px;}
.card-pad{padding:16px 18px;}
.lead-grid{display:grid;grid-template-columns:1.45fr 1fr;gap:26px;}
.lead-main{border-top:3px solid var(--rule-strong);padding-top:12px;}
.lead-main h2{font-size:31px;font-weight:900;line-height:1.15;color:var(--ink);margin-bottom:10px;}
.lead-main h2 a{color:var(--ink);text-decoration:none;}
.lead-main h2 a:hover{color:var(--accent);}
.lead-main p{font-size:17px;color:var(--ink2);line-height:1.6;font-family:var(--serif);}
.lead-side{display:flex;flex-direction:column;gap:16px;}
.lead-card{border-top:1px solid var(--rule-strong);padding-top:10px;}
.lead-card h3{font-size:19px;font-weight:800;line-height:1.25;color:var(--ink);}
.lead-card h3 a{color:var(--ink);text-decoration:none;}
.lead-card h3 a:hover{color:var(--accent);}
.lead-card p{font-size:14.5px;color:var(--ink2);line-height:1.55;}
.lead-kicker{font-size:10.5px;font-weight:800;letter-spacing:1.4px;text-transform:uppercase;color:var(--accent);margin-bottom:6px;}
.lead-meta{margin-top:8px;font-size:12px;color:var(--muted);}
.lead-meta a{color:var(--muted);}
.more-heads{columns:2;column-gap:28px;margin-top:6px;}
.more-heads a{display:block;font:700 14.5px/1.35 var(--serif);color:var(--ink);padding:6px 0;border-bottom:1px solid var(--rule);break-inside:avoid;text-decoration:none;}
.more-heads a:hover{color:var(--accent);}
.more-heads a span{color:var(--muted);font:400 11.5px var(--sans);}

/* «сейчас» */
.now-panel{border-top:3px solid var(--rule-strong);border-bottom:1px solid var(--rule);padding:14px 0;}
.now-alert{padding:8px 0;font-size:14px;font-weight:700;color:var(--ink);}
.now-alert.calm{color:#2e7d4f;}
.now-alert.danger{color:var(--accent);}
.now-grid{display:grid;grid-template-columns:1.25fr 1fr 0.9fr;gap:24px;}
.now-col{border-left:1px solid var(--rule);padding-left:18px;}
.now-col:first-child{border-left:none;padding-left:0;}
.now-h{font-size:10.5px;font-weight:800;letter-spacing:1.3px;text-transform:uppercase;color:var(--muted);margin-bottom:9px;}
.tl-row{display:flex;gap:10px;padding:6px 0;border-bottom:1px solid var(--rule);align-items:baseline;}
.tl-row:last-child{border-bottom:none;}
.tl-time{flex-shrink:0;font:700 11.5px var(--sans);color:var(--accent);width:44px;}
.tl-txt{font-size:14px;line-height:1.45;color:var(--ink2);}
.tl-txt a{color:var(--ink);text-decoration:none;}
.tl-txt a:hover{color:var(--accent);}
.tl-src{color:var(--muted);font-size:11px;}
.now-line{font-size:13px;color:var(--ink2);margin-top:3px;line-height:1.5;}
.now-line b{color:var(--ink);}
.now-num{font-family:var(--serif);font-size:26px;font-weight:900;color:var(--ink);line-height:1.1;}
.now-num small{font-size:11px;font-weight:700;color:var(--muted);}

/* рубрики ленты */
.cat-block{border-top:2px solid var(--rule-strong);margin-bottom:22px;}
.cat-head{display:flex;align-items:center;gap:10px;padding:9px 0;border-bottom:1px solid var(--rule);}
.cat-ico{width:26px;height:26px;border-radius:4px;display:flex;align-items:center;justify-content:center;font-size:13px;background:var(--chip);}
.cat-head h3{font-family:var(--serif);font-size:18px;font-weight:900;color:var(--ink);}
.cat-head .count{margin-left:auto;font-size:11px;color:var(--muted);}
.news-item{padding:12px 0;border-bottom:1px solid var(--rule);}
.news-item:last-child{border-bottom:none;}
.news-item h4{font-size:16.5px;font-weight:800;line-height:1.35;margin-bottom:4px;}
.news-item h4 a{color:var(--ink);text-decoration:none;}
.news-item h4 a:hover{color:var(--accent);}
.news-item p{font-size:14.5px;color:var(--ink2);line-height:1.55;}
.news-item .meta{font-size:11.5px;color:var(--muted);margin-top:5px;}
.news-item .meta .tg{color:var(--link);}
.tchip{display:inline-block;font-size:10.5px;font-weight:700;background:var(--chip);color:var(--muted);border:1px solid var(--rule);border-radius:3px;padding:1px 8px;margin:5px 4px 0 0;}
.stchip{font-size:10.5px;font-weight:800;border-radius:3px;padding:2px 9px;}

/* боковые и таблицы */
.side-card,.side-head+.side-body{background:var(--card);}
.side-head{padding:10px 16px;background:var(--chip);color:var(--ink);font-size:13.5px;font-weight:800;border-bottom:1px solid var(--rule);}
.side-head .sub{margin-left:auto;font-size:10.5px;font-weight:600;color:var(--muted);}
.side-body{padding:12px 16px;}
.tbl{width:100%;border-collapse:collapse;font-size:13.5px;}
.tbl th{background:var(--chip);color:var(--ink);text-align:left;padding:7px 11px;font-size:11px;text-transform:uppercase;letter-spacing:.6px;border-bottom:2px solid var(--rule-strong);}
.tbl td{padding:7px 11px;border-bottom:1px solid var(--rule);vertical-align:top;}
.tbl tr:nth-child(even) td{background:transparent;}
.note{font-size:12.5px;color:var(--muted);margin-top:9px;line-height:1.55;border-left:2px solid var(--rule);padding-left:11px;}
.verdict{border-left:3px solid var(--accent);padding:9px 13px;font-size:13.5px;color:var(--ink2);margin-top:10px;background:var(--chip);}
.verdict b{color:var(--accent);text-transform:uppercase;font-size:11px;letter-spacing:.8px;display:block;margin-bottom:3px;}
.bar-row .bt,.bar-wrap{background:var(--chip);}
.bar-fill{background:var(--ink2);}
.bar-fill.hot{background:var(--accent);}
.bar-fill.cool{background:#2e7d4f;}
.bar-fill.gold{background:var(--accent-soft);}
.bar-fill.violet{background:var(--ink2);}
.topic-row{display:grid;grid-template-columns:200px 1fr 120px 92px;gap:10px;align-items:center;padding:7px 0;border-bottom:1px solid var(--rule);font-size:13px;}
.topic-row:last-child{border-bottom:none;}
.topic-name{font-weight:700;color:var(--ink);}
.topic-name small{display:block;font-weight:600;color:var(--muted);font-size:11px;}
.kpi{background:var(--card);border:1px solid var(--rule);border-left:3px solid var(--ink);border-radius:4px;padding:12px 14px;}
.kpi .num{font-family:var(--serif);font-size:24px;font-weight:900;color:var(--ink);line-height:1.1;}
.kpi .num small{font-size:11px;font-weight:700;color:var(--muted);}
.kpi .lbl{font-size:11.5px;color:var(--muted);margin-top:4px;}
.kpi.gold,.kpi.red,.kpi.green,.kpi.violet{border-left-color:var(--accent);}
.kpi-grid{display:grid;grid-template-columns:repeat(6,1fr);gap:12px;}

/* афиша/события/календарь */
.cal-badge{flex-shrink:0;width:44px;height:42px;border-radius:4px;background:var(--chip);border:1px solid var(--rule);color:var(--ink);display:flex;flex-direction:column;align-items:center;justify-content:center;line-height:1;}
.cal-badge b{font-family:var(--serif);font-size:16px;}
.cal-badge span{font-size:8.5px;text-transform:uppercase;color:var(--muted);margin-top:2px;}
.cal-badge.gold{background:var(--accent);border-color:var(--accent);color:#fff;}
.cal-badge.gold span{color:#f4dcdc;}
.af-mini{display:flex;gap:11px;padding:8px 0;border-bottom:1px solid var(--rule);align-items:flex-start;}
.af-mini:last-child{border-bottom:none;}
.af-mini a{color:var(--ink);text-decoration:none;font-weight:700;}
.af-mini a:hover{color:var(--accent);}
.af-daybar,.af-chips{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:14px;}
.af-chip{border:1px solid var(--rule);background:var(--card);color:var(--muted);font-size:12.5px;font-weight:700;padding:6px 14px;border-radius:3px;cursor:pointer;}
.af-chip.on{background:var(--ink);border-color:var(--ink);color:var(--paper);}
.sec-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;max-width:1200px;margin:0 auto;padding:0 18px;}
.sec-card{background:var(--card);border:1px solid var(--rule);border-top:3px solid var(--ink);border-radius:4px;padding:15px 16px;display:flex;flex-direction:column;text-decoration:none;}
.sec-card:hover{border-top-color:var(--accent);}
.sec-card .ic{font-size:20px;}
.sec-card b{display:block;font-family:var(--serif);font-size:16px;color:var(--ink);margin-top:5px;}
.sec-card .fig{font-family:var(--serif);font-size:18px;font-weight:900;color:var(--accent);margin-top:2px;}
.sec-card .fig small{font-size:10.5px;font-weight:700;color:var(--muted);}
.sec-card p{font-size:12.5px;color:var(--muted);line-height:1.5;margin-top:5px;flex:1;}
.sec-card .go{font-size:11.5px;font-weight:800;color:var(--accent);margin-top:8px;}
.arch-item{display:flex;gap:12px;padding:9px 0;border-bottom:1px solid var(--rule);align-items:center;}
.arch-item:last-child{border-bottom:none;}
.arch-date{width:46px;height:44px;border-radius:4px;background:var(--chip);border:1px solid var(--rule);color:var(--ink);display:flex;flex-direction:column;align-items:center;justify-content:center;line-height:1;}
.arch-date b{font-family:var(--serif);font-size:16px;}
.arch-date span{font-size:8.5px;color:var(--muted);margin-top:2px;text-transform:uppercase;}
.btn{display:inline-block;background:var(--ink);color:var(--paper);border-radius:3px;padding:7px 14px;font-size:12.5px;font-weight:700;text-decoration:none;}
.btn:hover{background:var(--accent);color:#fff;}
.btn.gold{background:var(--accent);color:#fff;}

/* недели/месяцы/рельс */
.wk-grid{display:grid;grid-template-columns:2fr 1fr;gap:24px;align-items:start;margin-top:14px;}
.wk-rail{display:flex;flex-direction:column;gap:12px;}
.wk-box{background:var(--card);border:1px solid var(--rule);border-radius:4px;padding:12px 14px;}
.wk-box h4{font-size:10.5px;letter-spacing:1.2px;text-transform:uppercase;color:var(--muted);margin:0 0 8px;font-weight:800;}
.wk-passport{background:var(--card);border:1px solid var(--rule);border-left:4px solid var(--accent);border-radius:4px;padding:12px 16px;margin-top:14px;display:flex;gap:16px;flex-wrap:wrap;align-items:baseline;}
.wk-passport b{font-family:var(--serif);font-size:17px;color:var(--ink);}
.wk-stamp{font-size:11px;font-weight:800;border-radius:3px;padding:3px 10px;background:#e2efe6;color:#20603c;}
:root[data-theme="dark"] .wk-stamp{background:#1d2a22;color:#8fd0a8;}
.wk-stamp.wip{background:#f4e8d8;color:#8a5a17;}
:root[data-theme="dark"] .wk-stamp.wip{background:#2a241a;color:#d9b06a;}

/* прочее */
.util-bar-wrap{max-width:1200px;margin:0 auto;padding:16px 18px 0;}
.util-bar{display:flex;gap:22px;align-items:center;flex-wrap:wrap;border-top:1px solid var(--rule);padding-top:12px;}
.util-bar a{color:var(--muted);font-size:12.5px;font-weight:700;text-decoration:none;}
.util-bar a:hover{color:var(--accent);}
.util-lbl{font-size:10px;font-weight:800;letter-spacing:1.2px;text-transform:uppercase;color:var(--muted);}
.filters{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:16px;}
.fbtn{border:1px solid var(--rule);background:var(--card);color:var(--muted);font-size:12.5px;font-weight:700;padding:6px 14px;border-radius:3px;cursor:pointer;}
.fbtn.active{background:var(--ink);border-color:var(--ink);color:var(--paper);}
.alert-banner{background:var(--accent);color:#fff;padding:10px 20px;font-size:14px;font-weight:700;display:flex;align-items:center;gap:12px;flex-wrap:wrap;}
.alert-banner a{color:#ffe3e3;}
.alert-banner .blink{animation:none;font-size:16px;}
.ticker-wrap{background:var(--chip);color:var(--ink2);border-bottom:1px solid var(--rule);overflow:hidden;position:relative;height:32px;}
.ticker-label{position:absolute;left:0;top:0;bottom:0;z-index:2;background:var(--accent);color:#fff;font-size:11px;font-weight:800;letter-spacing:1px;display:flex;align-items:center;padding:0 12px;text-transform:uppercase;}
.ticker{display:flex;white-space:nowrap;animation:ticker 60s linear infinite;padding-left:120px;align-items:center;height:100%;}
.ticker:hover{animation-play-state:paused;}
.ticker span{font-size:12.5px;padding-right:52px;}
.ticker span b{color:var(--accent);}
@keyframes ticker{0%{transform:translateX(0);}100%{transform:translateX(-50%);}}
.tone-bar{height:14px;border-radius:3px;background:linear-gradient(90deg,#b04848,#e8e2d6 50%,#4c8a63);position:relative;}
.tone-pin{position:absolute;top:-4px;width:3px;height:22px;background:var(--ink);border-radius:2px;}
.tone-cat{font-size:11px;border-radius:3px;padding:3px 9px;border:1px solid var(--rule);background:var(--card);font-weight:700;color:var(--ink2);}
.fc-tbl{width:100%;border-collapse:collapse;font-size:13px;margin-top:8px;}
.fc-tbl th{text-align:left;padding:6px 10px;background:var(--chip);color:var(--muted);font-size:10.5px;text-transform:uppercase;}
.fc-tbl td{padding:6px 10px;border-bottom:1px solid var(--rule);}
.fc-up{color:var(--accent);font-weight:800;} .fc-down{color:#2e7d4f;font-weight:800;} .fc-flat{color:var(--muted);font-weight:800;}
.drone{width:24px;height:24px;border-radius:4px;background:var(--chip);border:1px solid var(--rule);display:flex;align-items:center;justify-content:center;font-size:12px;}
.hl{background:linear-gradient(transparent 62%,#f3d9a4 62%);}
:root[data-theme="dark"] .hl{background:linear-gradient(transparent 62%,#5a4a22 62%);}

/* печать */
.pm-mast{text-align:center;border-bottom:3px double var(--rule-strong);padding-bottom:4mm;}
.pm-title{font-family:var(--serif);font-size:44pt;font-weight:900;letter-spacing:10px;line-height:1;margin:0;color:var(--ink);}
.pm-line{font-size:8.5pt;letter-spacing:1.2px;text-transform:uppercase;margin-top:2.5mm;color:var(--muted);}
.pm-line b{color:var(--ink);}
.pm-kicker{font-size:8pt;letter-spacing:2px;text-transform:uppercase;color:var(--accent);font-weight:700;margin:3mm 0 1.5mm;}
.pm-lead-h{font-family:var(--serif);font-size:21pt;font-weight:900;line-height:1.15;margin:0 0 2.5mm;color:var(--ink);}
.pm-deck{font-size:10.5pt;font-style:italic;color:var(--ink2);line-height:1.45;margin:0 0 3mm;font-family:var(--serif);}
.cols{column-count:3;column-gap:6mm;column-rule:.5pt solid var(--rule);}
.cols p{font-size:9.3pt;line-height:1.42;margin:0 0 2.2mm;text-align:justify;hyphens:auto;}
.pm-h3{font-family:var(--serif);font-size:10pt;font-weight:900;text-transform:uppercase;letter-spacing:1px;border-top:1.6pt solid var(--ink);padding-top:1.4mm;margin:3mm 0 1.8mm;break-after:avoid;}
.pm-item{margin-bottom:2.4mm;break-inside:avoid;}
.pm-item b{font-size:9.6pt;line-height:1.25;display:block;}
.pm-item span{font-size:8.6pt;color:var(--muted);line-height:1.35;display:block;}
.pm-item i{font-size:7.6pt;color:var(--muted);font-style:normal;}
.pm-box{border:1.2pt solid var(--ink);padding:3mm;margin:3mm 0;break-inside:avoid;}
.pm-box h4{font-size:9pt;text-transform:uppercase;letter-spacing:1.4px;margin:0 0 2mm;border-bottom:.8pt solid var(--ink);padding-bottom:1.2mm;}
.pm-box ul{list-style:none;margin:0;padding:0;}
.pm-box li{font-size:8.8pt;line-height:1.4;margin-bottom:1.4mm;}
.pm-box li b{color:var(--accent);}
.pm-stats{display:flex;gap:4mm;justify-content:space-between;margin:3mm 0;break-inside:avoid;}
.pm-stat{flex:1;text-align:center;border:.8pt solid var(--ink);padding:2mm 1mm;}
.pm-stat b{display:block;font-family:var(--serif);font-size:15pt;font-weight:900;}
.pm-stat span{font-size:7.4pt;text-transform:uppercase;letter-spacing:.8px;color:var(--muted);}
.pm-colophon{border-top:3px double var(--rule-strong);margin-top:4mm;padding-top:2mm;font-size:7.6pt;color:var(--muted);line-height:1.5;display:flex;justify-content:space-between;gap:6mm;}
.pm-page{position:absolute;bottom:4mm;right:13mm;font-size:8pt;color:var(--muted);}
.pm-ed{font-size:9.3pt;line-height:1.5;text-align:justify;}
.pm-ed p{margin:0 0 2.2mm;}

/* подвал */
.footer{background:var(--paper);color:var(--muted);border-top:3px double var(--rule-strong);margin-top:40px;padding:22px;}
.footer b{color:var(--ink);font-family:var(--serif);}
.footer a,.flink{color:var(--muted);}
.footer a:hover{color:var(--accent);}
.footer-inner{max-width:1200px;margin:0 auto;display:flex;gap:34px;flex-wrap:wrap;}
.footer p{line-height:1.6;max-width:440px;font-size:12.5px;}

@media (max-width:1080px){
  .main-grid,.grid2,.lead-grid,.wk-grid{grid-template-columns:1fr;}
  .now-grid{grid-template-columns:1fr;}
  .now-col{border-left:none;padding-left:0;border-top:1px solid var(--rule);padding-top:10px;}
  .kpi-grid{grid-template-columns:repeat(3,1fr);}
  .sec-grid{grid-template-columns:repeat(2,1fr);}
  .more-heads{columns:1;}
  .topic-row{grid-template-columns:140px 1fr 90px;}
  .topic-row .sparkcell{display:none;}
}
@media (max-width:640px){
  .kpi-grid{grid-template-columns:repeat(2,1fr);}
  .sec-grid{grid-template-columns:1fr;}
  body{font-size:16px;}
}
@media print{
  .nav,.ticker-wrap,.filters,.print-btn,.theme-btn,.nav-toggle,.nav-search,.util-bar-wrap{display:none!important;}
  body{background:#fff;}
  .card,.kpi,.sec-card{border-color:#bbb;}
}
"""

THEME_HEAD = """<script>
(function(){try{var t=localStorage.getItem("gudok-theme");
if(!t){t=window.matchMedia&&matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light";}
document.documentElement.setAttribute("data-theme",t);}catch(e){document.documentElement.setAttribute("data-theme","light");}})();
</script>"""

THEME_FOOT = """<script>
function toggleTheme(){var c=document.documentElement.getAttribute("data-theme")==="dark"?"light":"dark";
document.documentElement.setAttribute("data-theme",c);
try{localStorage.setItem("gudok-theme",c);}catch(e){}
syncThemeBtn();}
function syncThemeBtn(){var b=document.getElementById("themeBtn");
if(b){b.textContent=document.documentElement.getAttribute("data-theme")==="dark"?"\u2600\ufe0f":"\U0001F319";}}
syncThemeBtn();
</script>"""

THEME_BTN = '<button class="theme-btn" id="themeBtn" onclick="toggleTheme()" title="Светлая/тёмная тема">\U0001F319</button>'


INDEX_CSS = """
.masthead{background:linear-gradient(135deg,var(--navy) 0%,#10263d 55%,var(--navy3) 100%);color:#fff;padding:20px 22px 0;border-bottom:4px double var(--gold);}
:root[data-theme="dark"] .masthead{background:linear-gradient(135deg,#08121e,#0d1f33 55%,#122b45);}
.mast-inner{max-width:1200px;margin:0 auto;display:flex;align-items:center;gap:20px;flex-wrap:wrap;}
.mast-brand{flex:1;min-width:280px;display:flex;align-items:center;gap:18px;}
.mast-brand>div{display:flex;flex-direction:column;justify-content:center;}
.brand>div{display:flex;flex-direction:column;justify-content:center;}
.mast-title{font-size:44px;font-weight:900;letter-spacing:5px;line-height:1;font-family:Georgia,'Times New Roman',serif;}

.mast-slogan{font-size:12px;color:#a9c1d9;letter-spacing:1.6px;text-transform:uppercase;margin-top:7px;}
.mast-right{text-align:right;font-size:12.5px;color:#c9d8e8;}
.mast-right .date{font-size:15px;font-weight:800;color:#fff;}
.mast-right .wx{margin-top:4px;color:#a9c1d9;}
.mast-tools{display:flex;gap:8px;justify-content:flex-end;margin-top:8px;}
.lead-sec{max-width:1200px;margin:0 auto;padding:22px 18px 0;}
.lead-kicker{font-size:10.5px;font-weight:800;letter-spacing:1.4px;text-transform:uppercase;margin-bottom:6px;}
.lead-grid{display:grid;grid-template-columns:1.4fr 1fr;gap:18px;}
.lead-main{background:var(--card);border-radius:var(--radius);box-shadow:var(--shadow);padding:20px 24px;border-top:5px solid var(--gold);}
.lead-main h2{font-size:24px;font-weight:900;color:var(--navy);line-height:1.25;margin-bottom:10px;}
.lead-main h2 a{color:var(--navy);} .lead-main h2 a:hover{color:var(--blue);}
.lead-main p{font-size:14px;color:var(--muted);line-height:1.6;}
.lead-side{display:flex;flex-direction:column;gap:14px;}
.lead-card{background:var(--card);border-radius:var(--radius);box-shadow:var(--shadow);padding:14px 18px;flex:1;border-top:4px solid var(--blue);}
.lead-card h3{font-size:16px;font-weight:800;color:var(--navy);line-height:1.3;margin-bottom:6px;}
.lead-card h3 a{color:var(--navy);} .lead-card h3 a:hover{color:var(--blue);}
.lead-card p{font-size:12.6px;color:var(--muted);line-height:1.5;}
.lead-meta{margin-top:8px;font-size:11px;color:#8a99aa;font-weight:600;}
.tiles{display:grid;grid-template-columns:repeat(6,1fr);gap:12px;max-width:1200px;margin:20px auto 0;padding:0 18px;}
.tile{background:var(--card);border-radius:var(--radius);box-shadow:var(--shadow);padding:15px 16px;border-left:4px solid var(--blue);transition:transform .12s;}
.tile:hover{transform:translateY(-2px);text-decoration:none;}
.tile .ic{font-size:21px;}
.tile b{display:block;font-size:13.5px;color:var(--navy);margin-top:5px;}
.tile span{display:block;font-size:11.3px;color:var(--muted);margin-top:2px;line-height:1.35;}
.tile .n{font-size:19px;font-weight:800;color:var(--blue);}
.wrap1200{max-width:1200px;margin:0 auto;padding:0 18px;}
.af-mini{display:flex;gap:11px;padding:9px 0;border-bottom:1px dashed var(--line);align-items:flex-start;}
.af-mini:last-child{border-bottom:none;}
@media (max-width:900px){.lead-grid{grid-template-columns:1fr;}.tiles{grid-template-columns:repeat(2,1fr);}.mast-title{font-size:34px;}}
"""

FRONT2_CSS = """
.now-wrap{max-width:1200px;margin:0 auto;padding:20px 18px 0;}
.now-panel{background:var(--card);border-radius:var(--radius);box-shadow:var(--shadow);border-left:5px solid var(--gold);overflow:hidden;}
.now-alert{padding:9px 18px;font-size:12.8px;font-weight:700;display:flex;align-items:center;gap:10px;}
.now-alert.calm{background:#e6f4ec;color:#1d7a4d;}
.now-alert.danger{background:#fde7e8;color:#b02a2f;}
:root[data-theme="dark"] .now-alert.calm{background:#12291d;color:#6fd39b;}
:root[data-theme="dark"] .now-alert.danger{background:#2a1416;color:#ff8a8e;}
.now-grid{display:grid;grid-template-columns:1.25fr 1fr 0.9fr;gap:0;}
.now-col{padding:14px 18px;border-right:1px dashed var(--line);}
.now-col:last-child{border-right:none;}
.now-h{font-size:10.5px;font-weight:800;letter-spacing:1.3px;text-transform:uppercase;color:var(--muted);margin-bottom:9px;}
.tl-row{display:flex;gap:10px;padding:6px 0;border-bottom:1px dashed var(--line);align-items:baseline;}
.tl-row:last-child{border-bottom:none;}
.tl-time{flex-shrink:0;font-size:11px;font-weight:800;color:var(--blue);width:42px;}
.tl-txt{font-size:12.6px;line-height:1.4;color:var(--txt);}
.tl-txt a{color:var(--txt);font-weight:600;}
.tl-txt a:hover{color:var(--blue);}
.tl-src{color:var(--muted);font-size:10.8px;}
.now-num{font-size:24px;font-weight:900;color:var(--navy);line-height:1.1;}
.now-num small{font-size:11px;font-weight:700;color:var(--muted);}
.now-line{font-size:12.3px;color:var(--muted);margin-top:2px;line-height:1.4;}
.now-line b{color:var(--navy);}
.more-heads{columns:2;column-gap:26px;margin-top:4px;}
.more-heads a{display:block;font-size:13px;font-weight:700;color:var(--navy);padding:5px 0;border-bottom:1px dashed var(--line);break-inside:avoid;}
.more-heads a:hover{color:var(--blue);}
.more-heads a span{color:var(--muted);font-weight:600;font-size:11px;}
.sec-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;max-width:1200px;margin:0 auto;padding:0 18px;}
.sec-card{background:var(--card);border-radius:var(--radius);box-shadow:var(--shadow);padding:16px 18px;border-top:4px solid var(--blue);display:flex;flex-direction:column;text-decoration:none;}
.sec-card:hover{transform:translateY(-2px);text-decoration:none;}
.sec-card .ic{font-size:22px;}
.sec-card b{display:block;font-size:14.5px;color:var(--navy);margin-top:6px;}
.sec-card .fig{font-size:17px;font-weight:900;color:var(--blue);margin-top:2px;}
.sec-card .fig small{font-size:10.5px;font-weight:700;color:var(--muted);}
.sec-card p{font-size:12px;color:var(--muted);line-height:1.45;margin-top:5px;flex:1;}
.sec-card .go{font-size:11.5px;font-weight:800;color:var(--blue);margin-top:8px;}
@media (max-width:980px){.now-grid{grid-template-columns:1fr;}.now-col{border-right:none;border-bottom:1px dashed var(--line);}.sec-grid{grid-template-columns:repeat(2,1fr);}.more-heads{columns:1;}}
"""

PRINT_CSS = """
body.print-mode{background:#8b939c;margin:0;font-family:Georgia,'Times New Roman',serif;}
.sheet{width:186mm;min-height:266mm;margin:10mm auto;background:#fdfcf8;color:#141414;
padding:11mm 13mm 9mm;box-shadow:0 4px 24px rgba(0,0,0,.45);position:relative;box-sizing:border-box;}
.pm-mast{text-align:center;border-bottom:3px double #141414;padding-bottom:4mm;}
.pm-title{font-size:44pt;font-weight:900;letter-spacing:10px;line-height:1;margin:0;}
.pm-line{font-size:8.5pt;letter-spacing:1.2px;text-transform:uppercase;margin-top:2.5mm;color:#333;}
.pm-line b{color:#141414;}
.pm-kicker{font-size:8pt;letter-spacing:2px;text-transform:uppercase;color:#7a1f1f;font-weight:700;margin:3mm 0 1.5mm;}
.pm-lead-h{font-size:21pt;font-weight:900;line-height:1.15;margin:0 0 2.5mm;}
.pm-deck{font-size:10.5pt;font-style:italic;color:#3a3a3a;line-height:1.45;margin:0 0 3mm;}
.cols{column-count:3;column-gap:6mm;column-rule:.6pt solid #b9b2a6;}
.cols p{font-size:9.3pt;line-height:1.42;margin:0 0 2.2mm;text-align:justify;hyphens:auto;}
.pm-h3{font-size:10pt;font-weight:900;text-transform:uppercase;letter-spacing:1px;border-top:1.6pt solid #141414;
padding-top:1.4mm;margin:3mm 0 1.8mm;break-after:avoid;}
.pm-item{margin-bottom:2.4mm;break-inside:avoid;}
.pm-item b{font-size:9.6pt;line-height:1.25;display:block;}
.pm-item span{font-size:8.6pt;color:#4a4a4a;line-height:1.35;display:block;}
.pm-item i{font-size:7.6pt;color:#8a8378;font-style:normal;}
.pm-box{border:1.2pt solid #141414;padding:3mm;margin:3mm 0;break-inside:avoid;}
.pm-box h4{font-size:9pt;text-transform:uppercase;letter-spacing:1.4px;margin:0 0 2mm;border-bottom:.8pt solid #141414;padding-bottom:1.2mm;}
.pm-box ul{list-style:none;margin:0;padding:0;}
.pm-box li{font-size:8.8pt;line-height:1.4;margin-bottom:1.4mm;}
.pm-box li b{color:#7a1f1f;}
.pm-stats{display:flex;gap:4mm;justify-content:space-between;margin:3mm 0;break-inside:avoid;}
.pm-stat{flex:1;text-align:center;border:.8pt solid #141414;padding:2mm 1mm;}
.pm-stat b{display:block;font-size:15pt;font-weight:900;}
.pm-stat span{font-size:7.4pt;text-transform:uppercase;letter-spacing:.8px;color:#4a4a4a;}
.pm-colophon{border-top:3px double #141414;margin-top:4mm;padding-top:2mm;font-size:7.6pt;color:#5a5a5a;line-height:1.5;
display:flex;justify-content:space-between;gap:6mm;}
.pm-page{position:absolute;bottom:4mm;right:13mm;font-size:8pt;color:#7a7a7a;}
.pm-ed{font-size:9.3pt;line-height:1.5;text-align:justify;}
.pm-ed p{margin:0 0 2.2mm;}
.pm-toolbar{position:fixed;top:10px;right:14px;z-index:9;display:flex;gap:8px;}
.pm-toolbar a,.pm-toolbar button{background:#141414;color:#fff;border:none;border-radius:8px;padding:8px 14px;
font-size:12.5px;font-weight:700;cursor:pointer;text-decoration:none;font-family:Segoe UI,Arial,sans-serif;}
@media print{
  body.print-mode{background:#fff;}
  .sheet{margin:0;box-shadow:none;width:auto;min-height:auto;page-break-after:always;}
  .sheet:last-of-type{page-break-after:auto;}
  .pm-toolbar{display:none;}
  @page{size:A4;margin:0;}
}
"""

EMBLEM = """<svg width="44" height="50" viewBox="0 0 46 52" fill="none">
<path d="M23 1 L44 9 V25 C44 38 35 47 23 51 C11 47 2 38 2 25 V9 Z" fill="#1d4066" stroke="#f2b134" stroke-width="2"/>
<rect x="19" y="13" width="8" height="4.5" rx="1" fill="#e8eef5"/>
<rect x="20.2" y="18.5" width="5.6" height="17" fill="#e8eef5"/>
<rect x="17" y="35.5" width="12" height="3.4" rx="1" fill="#e8eef5"/>
<rect x="15.4" y="39.2" width="15.2" height="3" rx="1" fill="#c9d8e8"/>
<circle cx="23" cy="10.4" r="2.6" fill="#f2b134"/></svg>"""


# ------------------------------------------------------------------ helpers
def load_json(path, default=None):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default


def load_store():
    items = []
    p = os.path.join(DATA, "store.jsonl")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        items.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    return items


def fmt_views(v):
    if not v:
        return ""
    if v >= 1_000_000:
        return f"{v/1_000_000:.1f}M".replace(".0M", "M")
    if v >= 1000:
        return f"{v/1000:.1f}K".replace(".0K", "K")
    return str(v)


def local_dt(iso):
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso).astimezone(UTC4)
    except ValueError:
        return None


def sparkline(series, w=120, h=26, color="#2f80ed"):
    if not series:
        return ""
    mx = max(series) or 1
    n = len(series)
    pts = []
    for i, v in enumerate(series):
        x = round(i * (w - 4) / max(1, n - 1) + 2, 1)
        y = round(h - 3 - (v / mx) * (h - 8), 1)
        pts.append(f"{x},{y}")
    area = f"M{pts[0]} L" + " L".join(pts[1:]) + f" L{w-2},{h-2} L2,{h-2} Z"
    line = "M" + " L".join(pts)
    last = pts[-1].split(",")
    return (f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
            f'<path d="{area}" fill="{color}" opacity="0.12"/>'
            f'<path d="{line}" fill="none" stroke="{color}" stroke-width="1.8" stroke-linejoin="round"/>'
            f'<circle cx="{last[0]}" cy="{last[1]}" r="2.6" fill="{color}"/></svg>')


def esc(s):
    return H.escape(s or "", quote=False)


CHRONO_KEYS = ("ракетная опасность", "беспилотная опасность", "бпла", "беспилот",
               "воздушная тревога", "пво", "атак", "аэропорт", "баратаевка", "сбит")


def hero_pick(window, trends, now, n=3):
    """Топ-N событий дня: просмотры + «теплота» тем + свежесть, с разнообразием рубрик."""
    def score(it):
        s = 0.0
        if it.get("views"):
            s += min(it["views"] / 500.0, 40)   # вовлечённость аудитории — весомее
        pub = local_dt(it.get("published"))
        if pub:
            age_h = max(0.0, (now - pub).total_seconds() / 3600)
            s += max(0.0, 18 - age_h / 2)      # свежесть
        heat = sorted(((trends or {}).get("topics", {}).get(t, {}).get("week", 0)
                       for t in it.get("topics", [])), reverse=True)[:2]
        s += sum(min(h, 25) / 2.5 for h in heat)  # топ-2 темы материала
        if it.get("image"):
            s += 4
        tier = it.get("tier")
        if tier == 1:
            s += 8
        elif tier == 3:
            s -= 6
        return s
    ranked = sorted(window, key=score, reverse=True)
    picked, used_cat = [], set()
    for it in ranked:
        c = it.get("category")
        if c in used_cat:
            continue
        picked.append(it)
        used_cat.add(c)
        if len(picked) >= n:
            return picked
    for it in ranked:
        if len(picked) >= n:
            break
        if it not in picked:
            picked.append(it)
    return picked


def chrono_items(window):
    """Оперативная хроника безопасности: БПЛА / ракетная опасность / аэропорт."""
    out = [it for it in window
           if any(k in (it.get("title", "") + " " + (it.get("text") or "")).lower() for k in CHRONO_KEYS)]
    out.sort(key=lambda x: x.get("published") or "")
    return out[-10:]


def render_editorial(date_str):
    """Колонка редактора — нарративный LLM-слой: data/editorial_YYYY-MM-DD.md пишет ассистент в чате."""
    path = os.path.join(DATA, f"editorial_{date_str}.md")
    if not os.path.exists(path):
        return ""
    md = open(path, encoding="utf-8").read().strip()
    if not md:
        return ""
    txt = esc(md)
    txt = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", txt)
    blocks = []
    for block in txt.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        if block.startswith("- "):
            lis = "".join(f"<li>{l[2:]}</li>" for l in block.split("\n") if l.startswith("- "))
            blocks.append(f'<ul style="padding-left:20px;font-size:13.4px;line-height:1.65;margin-bottom:8px;">{lis}</ul>')
        else:
            blocks.append(f'<p style="font-size:13.6px;line-height:1.7;margin-bottom:9px;">{block.replace(chr(10), " ")}</p>')
    return f"""<div class="sec-head" id="editorial"><h2>\u270d\ufe0f Колонка редактора</h2><div class="line"></div>
<div class="badge">нарративный слой · подготовлено ассистентом</div></div>
<div class="card" style="border-left:4px solid var(--gold);"><div class="card-pad">{''.join(blocks)}
<div class="note">Колонка пишется ассистентом в чате (LLM-слой проекта, без внешних API) поверх верифицированных фактов выпуска. При автономной работе конвейера секция опускается.</div></div></div>"""


def render_utilbar(prefix=""):
    return f"""<div class="util-bar-wrap"><div class="util-bar">
<span class="util-lbl">Служебное</span>
<a href="{prefix}roadmap.html">🧭 Роадмап издания</a>
<a href="{prefix}status.html">🩺 Статус системы</a>
<a href="https://github.com/Volgin1917/gudok" target="_blank" rel="noopener"> GitHub: исходники, выпуски и конвейер</a>
</div></div>"""


# ------------------------------------------------------------------ навигация
SUBNAV_DIGEST = ('<div class="subnav"><div class="subnav-inner"><span class="lbl">В выпуске:</span>'
                 '<a href="#heroes">Главное</a><a href="#pulse">Пульс повестки</a><a href="#afisha">Автоафиша</a>'
                 '<a href="#feed">Лента дня</a><a href="#tg">Telegram-монитор</a><a href="#clusters">Сюжеты 72 ч</a>'
                 '<a href="#tone">Тон дня</a><a href="#forecast">Прогноз</a></div></div>')

SUBNAV_INDEX = ('<div class="subnav"><div class="subnav-inner"><span class="lbl">На полосе:</span>'
                '<a href="#now">Сейчас</a><a href="#news">Новости</a>'
                '<a href="#sections">Разделы портала</a></div></div>')


def digest_number(cfg, date_str):
    """Номер выпуска = дней от launch_date (день запуска = №0, тестовый)."""
    launch = cfg.get("launch_date")
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d").date()
        if launch:
            n = (d - datetime.strptime(launch, "%Y-%m-%d").date()).days
            return max(n, 0), n <= 0
    except (ValueError, TypeError):
        pass
    return 1, False


def render_nav(cfg, current, prefix="", subnav=""):
    """Единая сквозная навигация для всех страниц издания."""
    dig = sorted(glob.glob(os.path.join(DIGESTS, "digest_*.html")))
    latest = os.path.basename(dig[-1]) if dig else ""
    latest_date = latest.replace("digest_", "").replace(".html", "")
    num, test = digest_number(cfg, latest_date) if latest_date else (1, False)
    ex = f"exec_{latest_date}.html" if latest_date else ""
    ex_exists = os.path.exists(os.path.join(DIGESTS, ex))
    label_num = f"№ {num}" + (" 🧪" if test else "")
    items = [
        ("index", "🏠 Первая полоса", f"{prefix}index.html"),
        ("digest", f"📰 День · № {num}" + (" 🧪" if test else ""), f"{prefix}digests/{latest}" if latest else ""),
        ("weekly", "📕 Неделя", f"{prefix}weekly.html"),
        ("monthly", "📊 Месяц", f"{prefix}monthly.html"),
        ("afisha", "🎭 Афиша", f"{prefix}afisha.html"),
        ("projects", "📁 Проекты", f"{prefix}projects.html"),
        ("archive", "🗄 Архив", f"{prefix}archive.html"),
        ("exec", "📋 Руководителю", f"{prefix}digests/{ex}" if ex_exists else ""),
    ]
    utils = []
    html_items = []
    for key, txt, href in items:
        if not href:
            continue
        cls = "active" if key == current else ""
        html_items.append(f'<a class="{cls}" href="{href}">{txt}</a>')
    for i, (key, txt, href) in enumerate(utils):
        cls = ("nav-util nav-util-first" if i == 0 else "nav-util") + (" active" if key == current else "")
        html_items.append(f'<a class="{cls}" href="{href}">{txt}</a>')
    search_box = ""
    if getattr(render_nav, "search_manifest", None) and current in ("index", "digest"):
        js = (
            "var QMAN=" + render_nav.search_manifest + ";"
            "function qSearch(v){var d=document.getElementById('qdrop');v=v.trim().toLowerCase();"
            "if(v.length<3){d.classList.remove('on');return;}"
            "var r=QMAN.filter(function(x){return x.t.toLowerCase().indexOf(v)>=0;}).slice(0,8);"
            "d.innerHTML=r.map(function(x){return '<a href=\"'+x.u+'\">'+x.t+'<span>'+x.d+' \u00b7 '+x.c+'</span></a>';}).join('')"
            "||'<a href=\'#\'>Ничего не найдено</a>';d.classList.add('on');}"
            "document.addEventListener('click',function(e){if(!e.target.closest('.nav-search'))document.getElementById('qdrop').classList.remove('on');});"
        )
        search_box = ('<div class="nav-search" style="position:relative;">'
                      '<input id="q" type="search" placeholder="Поиск по выпуску…" aria-label="Поиск по выпуску" '
                      'oninput="qSearch(this.value)" onfocus="qSearch(this.value)">'
                      '<div class="search-drop" id="qdrop"></div></div><script>' + js + '</script>')
    toggle = ('<button class="nav-toggle" aria-label="Открыть разделы" '
              "onclick=\"document.body.classList.toggle('nav-open')\">☰ Разделы</button>")
    return (f'<nav class="nav">{toggle}{search_box}<div class="nav-inner">{"".join(html_items)}</div></nav>'
            + subnav)


# ------------------------------------------------------------------ digest
def render_digest(cfg, trends, store, status, date_str, digest_no):
    now = datetime.now(UTC4)
    an = load_json(os.path.join(DATA, "analytics.json")) or {}
    nav_html = render_nav(cfg, "digest", "../", subnav=SUBNAV_DIGEST)
    day = datetime.strptime(date_str, "%Y-%m-%d").date()
    cats = {c["id"]: c for c in cfg["categories"]}
    tg_channels = {c["username"]: c for c in cfg["telegram_channels"] if c.get("enabled", True)}

    # окно выборки: сутки вокруг даты дайджеста (+6 ч запас)
    # утренний выпуск за дату D собирает материалы календарных суток D-1 (+3 ч ночи D)
    cover_day = day - timedelta(days=1)
    win_start = datetime.combine(cover_day, datetime.min.time(), tzinfo=UTC4)
    win_end = win_start + timedelta(days=1) + timedelta(hours=3)
    window = []
    for it in store:
        if it.get("dup_of"):
            continue
        dt = local_dt(it.get("published"))
        if dt and win_start <= dt < win_end:
            window.append(it)
    if len(window) < 8:
        win_start -= timedelta(days=1)
        window = [it for it in store if not it.get("dup_of")
                  and local_dt(it.get("published")) and win_start <= local_dt(it["published"]) < win_end]
    window.sort(key=lambda x: x.get("published") or "", reverse=True)

    by_cat = {}
    for it in window:
        by_cat.setdefault(it.get("category", "society"), []).append(it)

    kpi_24 = trends["counts"]["last24h"] if trends else 0
    kpi_7 = trends["counts"]["last7d"] if trends else 0
    kpi_total = trends["counts"]["total"] if trends else len(store)
    tg_items = [it for it in store if it.get("source_type") == "tg"]
    alerts = [it for it in window if any(
        k in (it["title"] + " " + it["text"]).lower()
        for k in ("ракетная опасность", "бпла", "беспилот", "воздушная тревога", "пво"))]

    parts = []
    alerts_data = load_json(os.path.join(DATA, "alerts.json"), {"active": [], "resolved": []})
    active_alerts = alerts_data.get("active", [])
    if active_alerts:
        a0 = active_alerts[-1]
        adt = local_dt(a0.get("published")) or now
        alert_banner = (f'<div class="alert-banner"><span class="blink">🚨</span> АЛЕРТ: {esc(a0["title"][:140])} '
                        f'<span style="font-weight:600;font-size:12px;">@{esc(a0["channel"])} · {adt.strftime("%d.%m %H:%M")}</span> '
                        f'<a href="{esc(a0["url"])}" target="_blank" rel="noopener">источник →</a></div>')
    else:
        recent_res = [a for a in alerts_data.get("resolved", [])
                      if a.get("resolved_at") and (now - local_dt(a["resolved_at"])).total_seconds() < 12 * 3600] if alerts_data.get("resolved") else []
        alert_banner = (f'<div class="alert-banner" style="background:linear-gradient(90deg,#1d7a4d,#2ea36b);"><span>✅</span> '
                        f'Угрозы неактивны · последних отбоев за 12 ч: {len(recent_res)} · монитор: alert_monitor.py</div>') if recent_res else ""

    parts.append(f"""<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Дайджест №{digest_no} · Ульяновская область · {day:%d.%m.%Y} — {cfg['brand']}</title>
<link rel="icon" type="image/png" href="../assets/logo_gudok.png"><style>{CSS}</style></head><body>
<header class="topbar"><div class="topbar-inner">
<div class="brand"><div>
<div class="brand-title">ИЗДАНИЕ <span>ГУДОК</span></div>
<div class="brand-sub">Информационно-аналитическое издание · выпуск № {digest_no}{' · 🧪 ТЕСТОВЫЙ' if digest_no == 0 else ''} · материалы за {cover_day:%d.%m.%Y}</div>
</div></div>
<div class="top-meta">
<div class="chip">{'🧪 тестовый номер · ' if digest_no == 0 else ''}<span class="dot"></span> Выпуск от <b>{day:%d.%m.%Y}</b></div>
<div class="chip"><a href="print_{date_str}.html" class="chip-link">📄 Печатная полоса</a></div>
<div class="chip">🤖 сгенерирован <b>{now:%H:%M}</b> (UTC+4)</div>
<a class="chip" href="../index.html">← Центр</a>
{THEME_BTN}
<button class="print-btn" onclick="window.print()">🖨 PDF</button>
</div></div></header>
{alert_banner}{nav_html}
<div class="page">""")

    # ---- KPI
    parts.append(f"""<div class="kpi-grid" style="margin-bottom:8px;">
<div class="kpi"><div class="num">{kpi_24}</div><div class="lbl">публикаций за 24 часа</div></div>
<div class="kpi gold"><div class="num">{len(window)}</div><div class="lbl">материалов в этом выпуске</div></div>
<div class="kpi green"><div class="num">{len(tg_channels)}</div><div class="lbl">Telegram-каналов на мониторинге</div></div>
<div class="kpi violet"><div class="num">{kpi_total}</div><div class="lbl">записей в накопленной базе</div></div>
<div class="kpi red"><div class="num">{len(alerts)}</div><div class="lbl">сообщений о воздушных угрозах за сутки</div></div>
</div>""")

    # ---- Колонка редактора (LLM-слой, если подготовлена)
    ed = render_editorial(date_str)
    if ed:
        parts.append(ed)

    # ---- Главные события дня (hero) + оперативная хроника
    topic_names = {t["id"]: t["name"] for t in cfg["topics"]}
    hero_pool = [it for it in window if is_regional(it) and it.get("category") != "security"] or window
    heroes = hero_pick(hero_pool, trends, now, 3)
    if heroes:
        hero_html = []
        for rank, it in enumerate(heroes, 1):
            cat = cats.get(it.get("category"), {})
            color = cat.get("color", "#2f80ed")
            dt = local_dt(it.get("published"))
            views = f" · 👁 {fmt_views(it['views'])}" if it.get("views") else ""
            link = esc(it.get("url") or "#")
            img = (f'<img src="{esc(it["image"])}" alt="" loading="lazy" '
                   f'style="width:100%;height:150px;object-fit:cover;border-radius:9px;margin-bottom:9px;" '
                   f'onerror="this.style.display=\'none\'">' ) if it.get("image") else ""
            hero_html.append(f"""<div class="hero-card" style="border-top-color:{color};">
{img}<div class="hk" style="color:{color};">{cat.get('icon','📌')} {esc(cat.get('name','Главное'))}<span class="w">событие №{rank}</span></div>
<h3><a href="{link}" target="_blank" rel="noopener">{esc(it['title'])}</a></h3>
<p>{esc(it.get('text') or '')}</p>
<div class="hero-meta">{dt.strftime('%d.%m %H:%M') if dt else ''} · {esc(it.get('source',''))}{views} · <a href="{link}" target="_blank" rel="noopener">источник →</a></div></div>""")
        parts.append(f"""<div class="sec-head" id="heroes"><h2>Главные события дня</h2><div class="line"></div>
<div class="badge">авторанжирование: просмотры × темы × свежесть</div></div>
<div class="hero-grid">{''.join(hero_html)}</div>""")

    chron = chrono_items(window)
    if chron:
        rows = []
        for it in chron:
            dt = local_dt(it.get("published"))
            link = esc(it.get("url") or "#")
            rows.append(f"""<div class="chrono-item"><span class="chrono-time">{dt.strftime('%d.%m %H:%M') if dt else ''}</span>
<a href="{link}" target="_blank" rel="noopener"><b>{esc(it['title'][:150])}</b></a>
<span style="color:var(--muted);font-size:11.5px;">· {esc(it.get('source',''))}</span></div>""")
        parts.append(f"""<div class="sec-head"><h2>Оперативная хроника: безопасность</h2><div class="line"></div>
<div class="badge">БПЛА · ракетная опасность · аэропорт</div></div>
<div class="card"><div class="card-pad"><div class="chrono">{''.join(rows)}</div>
<div class="note">Хронология сообщений о воздушных угрозах и работе ПВО за окно выпуска. Официальные подтверждения — каналы губернатора и МЧС.</div></div></div>""")

    # ---- Пульс повестки
    if trends:
        rows = []
        topics = trends["topics"]
        mx = max((t["week"] for t in topics.values()), default=1) or 1
        order = sorted(topics.items(), key=lambda kv: (kv[1]["week"], kv[1]["today"]), reverse=True)
        for tid, t in order[:12]:
            if t["week"] == 0 and t["today"] == 0:
                continue
            label, bgc, fgc = STATUS_META.get(t["status"], STATUS_META["stable"])
            st_color = "#d5494e" if t["status"] == "rising" else ("#218a58" if t["status"] == "new" else "#2f80ed")
            width = max(4, int(t["week"] / mx * 100))
            fill_cls = "hot" if t["status"] == "rising" else ("cool" if t["status"] == "new" else "")
            rows.append(f"""<div class="topic-row">
<div class="topic-name">{esc(t['name'])}<small>за 7 дней: {t['week']} · сегодня: {t['today']}</small></div>
<div class="bar-wrap"><div class="bar-fill {fill_cls}" style="width:{width}%"></div></div>
<div class="sparkcell">{sparkline(t['series'], color=st_color)}</div>
<div><span class="stchip" style="background:{bgc};color:{fgc};">{label}</span></div>
</div>""")
        parts.append(f"""<div class="sec-head" id="pulse"><h2>Пульс информационной повестки</h2><div class="line"></div>
<div class="badge">динамика {trends['days'][0][8:10]}.{trends['days'][0][5:7]}–{trends['days'][-1][8:10]}.{trends['days'][-1][5:7]}</div></div>
<div class="card"><div class="card-pad">{''.join(rows) or '<i>Нет данных — сначала запустите collector.py</i>'}
<div class="note">Спарклайны — упоминания темы за {len(trends['days'])} дней. Статус: сравнение последних 3 дней с предшествующей неделей.</div></div></div>""")

        # топ TG
        if trends.get("tg_top"):
            tgrows = "".join(
                f"""<div class="tgpost"><div class="views">👁 {fmt_views(p['views'])}</div>
<div><div class="t"><a href="{esc(p['url'])}" target="_blank" rel="noopener">{esc(p['title'])}</a></div>
<div class="m">@{esc(p['channel'] or '')} · {(local_dt(p['published']) or now):%d.%m %H:%M}</div></div></div>"""
                for p in trends["tg_top"][:6])
            parts.append(f"""<div class="sec-head"><h2>Самое читаемое в Telegram за 7 дней</h2><div class="line"></div></div>
<div class="card"><div class="card-pad">{tgrows}</div></div>""")

    # ---- Автоафиша (Фаза 2: NLP-извлечение событий)
    cal = an.get("calendar", [])
    if cal:
        wd = {"Mon": "пн", "Tue": "вт", "Wed": "ср", "Thu": "чт", "Fri": "пт", "Sat": "сб", "Sun": "вс"}
        rows = []
        for e in cal[:14]:
            try:
                d = datetime.strptime(e["date"], "%Y-%m-%d")
            except ValueError:
                continue
            end = e.get("date_end")
            day_txt = f"{d:%d}"
            sub = wd.get(d.strftime("%a"), "")
            gold = ' gold' if end or d.date() == now.date() else ''
            span = f" — по {end[8:10]}.{end[5:7]}" if end else ""
            venue = f' · 📍 {esc(e["venue"])}' if e.get("venue") else ""
            rows.append(f"""<div class="cal-ev"><div class="cal-badge{gold}"><b>{day_txt}</b><span>{sub} {d:%m}</span></div>
<div class="cal-txt"><a href="{esc(e.get('url') or '#')}" target="_blank" rel="noopener"><b>{esc(e['title'][:120])}</b></a>{span}
<div class="t2">{esc(e.get('time','')) or 'время уточняйте'}{venue} · {esc(e.get('source',''))}</div></div></div>""")
        parts.append(f"""<div class="sec-head" id="afisha"><h2>Автоафиша: ближайшие события</h2><div class="line"></div>
<div class="badge">извлечено из новостей · {len(cal)} дат</div></div>
<div class="card"><div class="card-pad">{''.join(rows)}
<div class="note">Даты извлекаются из текстов автоматически (analytics.py): одиночные дни, диапазоны, время и площадки 📍. Погода и исторические даты отсеиваются. Перед визитом сверяйтесь с первоисточником.</div></div></div>""")

    # ---- Лента дня
    parts.append(f"""<div class="sec-head" id="feed"><h2>Лента дня</h2><div class="line"></div>
<div class="badge">{len(window)} материалов</div></div>""")
    if not window:
        parts.append('<div class="card"><div class="card-pad">За выбранный период материалов нет. Запустите <code>python3 collector.py</code>.</div></div>')
    else:
        ordered_cats = [c["id"] for c in cfg["categories"] if by_cat.get(c["id"])]
        cols = [[], []]
        for i, cid in enumerate(ordered_cats):
            c = cats[cid]
            items_html = []
            for it in by_cat[cid][:10]:
                dt = local_dt(it.get("published"))
                link = esc(it.get("url") or "#")
                tg_badge = ""
                if it.get("source_type") == "tg":
                    tg_badge = f' · <span class="tg">Telegram @{esc(it.get("channel") or "")}</span>'
                    if it.get("views"):
                        tg_badge += f' · 👁 {fmt_views(it["views"])}'
                chips = "".join(f'<span class="tchip">#{esc(topic_names[t])}</span>'
                                for t in it.get("topics", [])[:3] if t in topic_names)
                also = it.get("also_in") or []
                if also:
                    more = f" +{len(also)-3}" if len(also) > 3 else ""
                    chips += f'<span class="tchip" style="background:#fdf3dd;border-color:#ecd9a8;color:#96690a;">🔁 также: {esc(", ".join(also[:3]))}{more}</span>'
                thumb = (f'<img src="{esc(it["image"])}" alt="" loading="lazy" '
                           f'style="float:right;width:118px;height:78px;object-fit:cover;border-radius:9px;margin:2px 0 8px 12px;" '
                           f'onerror="this.style.display=\'none\'">' ) if it.get("image") else ""
                items_html.append(f"""<article class="news-item">
{thumb}<h4><a href="{link}" target="_blank" rel="noopener">{esc(it['title'])}</a></h4>
<p>{esc(it.get('text') or '')}</p>
<div class="meta"><time datetime="{dt.isoformat() if dt else ''}">{dt.strftime('%d.%m %H:%M') if dt else ''}</time> · {esc(it.get('source',''))}{tg_badge}</div>
{chips}</article>""")
            block = (f"""<div class="card cat-block"><div class="cat-head">

<h3>{esc(c['name'])}</h3><div class="count">{len(by_cat[cid])}</div></div>
{''.join(items_html)}</div>""")
            cols[i % 2].append(block)
        parts.append(f"""<div class="grid2">
<div>{''.join(cols[0])}</div><div>{''.join(cols[1])}</div></div>""")

    # ---- Telegram monitor: tier1 карточками, tier2/3 компактной таблицей
    cutoff24 = now - timedelta(hours=24)
    def ch_posts(username, n=2):
        return sorted([it for it in tg_items if it.get("channel") == username],
                      key=lambda x: x.get("published") or "", reverse=True)[:n]
    def ch_count24(username):
        return sum(1 for it in tg_items if it.get("channel") == username
                   and local_dt(it.get("published")) and local_dt(it["published"]) >= cutoff24)
    t1 = [(u, c) for u, c in tg_channels.items() if c.get("tier") == 1]
    t23 = sorted([(u, c) for u, c in tg_channels.items() if c.get("tier", 2) != 1],
                 key=lambda x: (x[1].get("tier", 2), -(x[1].get("subs") or 0)))
    total24 = sum(ch_count24(u) for u in tg_channels)
    parts.append(f"""<div class="sec-head" id="tg"><h2>Telegram-монитор</h2><div class="line"></div>
<div class="badge">{len(tg_channels)} каналов · {total24} постов за 24 ч · через t.me/s</div></div>""")

    if t1:
        parts.append('<div class="grid2">')
        for username, ch in t1:
            posts = ch_posts(username, 2)
            st = (status or {}).get(f"tg:{username}", {})
            st_icon = '<span class="ok">●</span>' if st.get("ok") else ('<span class="fail">●</span>' if st else "●")
            rows = "".join(
                f"""<div class="tgpost">{'<div class="views">👁 ' + fmt_views(p['views']) + '</div>' if p.get('views') else ''}
<div><div class="t"><a href="{esc(p.get('url') or '#')}" target="_blank" rel="noopener">{esc(p['title'][:130])}</a></div>
<div class="m">{(local_dt(p.get('published')) or now).strftime('%d.%m %H:%M')}</div></div></div>"""
                for p in posts) or '<div class="tgpost"><div class="t" style="color:var(--muted);">Нет свежих сообщений</div></div>'
            parts.append(f"""<div class="card" style="margin-bottom:14px;"><div class="side-head">{st_icon}
<a href="https://t.me/{esc(username)}" target="_blank" rel="noopener" style="color:#fff;">@{esc(username)}</a>
<span class="sub">{esc(ch.get('title',''))}</span></div><div class="side-body">{rows}</div></div>""")
        parts.append('</div>')

    tier_badge = {2: ('<span class="stchip" style="background:#e8eef5;color:#3d5a7a;">агрегатор</span>'),
                  3: ('<span class="stchip" style="background:#f3edfa;color:#5f418f;">мнения</span>')}
    trows = []
    for username, ch in t23:
        last = ch_posts(username, 1)
        st = (status or {}).get(f"tg:{username}", {})
        dot = '<span class="ok">●</span>' if st.get("ok") else ('<span class="fail">●</span>' if st else "●")
        subs = f"{ch['subs']/1000:.0f}K" if ch.get("subs") else "—"
        if last:
            lp = last[0]
            last_html = (f'<a href="{esc(lp.get("url") or "#")}" target="_blank" rel="noopener">{esc(lp["title"][:80])}</a> '
                         f'<span style="color:var(--muted);">{(local_dt(lp.get("published")) or now).strftime("%d.%m %H:%M")}</span>')
        else:
            last_html = '<span style="color:#8a99aa;">нет постов</span>'
        trows.append(f"""<tr><td>{dot} <a href="https://t.me/{esc(username)}" target="_blank" rel="noopener">@{esc(username)}</a><br>
<span style="color:var(--muted);font-size:11px;">{esc(ch.get('title',''))}</span></td>
<td>{tier_badge.get(ch.get('tier',2),'')}</td><td>{subs}</td><td>{ch_count24(username)}</td><td>{last_html}</td></tr>""")
    if trows:
        parts.append(f"""<div class="card"><div class="side-head">📋 Агрегаторы и авторские каналы <span class="sub">tier 2–3</span></div>
<div class="side-body" style="padding:8px 12px;"><table class="tbl">
<tr><th>Канал</th><th>Тип</th><th>Подп.</th><th>24ч</th><th>Последний пост</th></tr>
{''.join(trows)}</table>
<div class="note">Материалы tier-3 (анонимные/сатирические каналы) используются как сигнал повестки и требуют верификации по tier-1 перед цитированием. Подписчики — TGStat, 11.09.2026.</div></div></div>""")

    # ---- Сюжетные кластеры (Фаза 2: TF-IDF без словаря)
    clusters = an.get("clusters", [])
    if clusters:
        cl_html = []
        for c in clusters:
            gap_badge = ('<span class="cl-badge" style="background:#fdf3dd;color:#96690a;">⚠️ вне словаря тем</span>'
                         if c.get("gap") else
                         f'<span class="cl-badge" style="background:#e0f4ea;color:#1d7a4d;">словарь: {int(c["coverage"]*100)}%</span>')
            samples = "".join(
                f'<div>• <a href="{esc(smp["url"]) or "#"}" target="_blank" rel="noopener">{esc(smp["title"])}</a> '
                f'<span style="color:#8a99aa;">({esc(smp["source"])}{" · 👁 " + fmt_views(smp["views"]) if smp.get("views") else ""})</span></div>'
                for smp in c.get("samples", [])[:2])
            cl_html.append(f"""<div class="cl-card{' gap' if c.get('gap') else ''}">
<div class="cl-head"><span class="cl-name">«{esc(c['name'])}»</span>
<span class="cl-badge" style="background:#e8eef5;color:#3d5a7a;">×{c['size']} материалов за 72 ч</span>{gap_badge}</div>
<div class="cl-samples">{samples}</div></div>""")
        parts.append(f"""<div class="sec-head" id="clusters"><h2>Сюжеты последних 72 часов</h2><div class="line"></div>
<div class="badge">TF-IDF кластеризация без словаря</div></div>
<div class="card"><div class="card-pad">{''.join(cl_html)}
<div class="note">Кластеры собираются методом лидера по косинусу TF-IDF-векторов. «Вне словаря» — сюжет, который тематический словарь config.json почти не покрыл: кандидат в новые темы трекера.</div></div></div>""")

    # ---- Тон дня (Фаза 2: лексиконная тональность)
    sent = an.get("sentiment") or {}
    if sent.get("today_items"):
        sc = sent.get("today_score") or 0
        pin = max(2, min(98, int((sc + 1) * 50)))
        spark = sparkline([x["score"] if x["score"] is not None else 0 for x in sent.get("series", [])],
                          w=200, h=34, color="#1d4066")
        cats_html = "".join(
            f'<span class="tone-cat" style="color:{"#b02a2f" if v < -0.1 else ("#1d7a4d" if v > 0.1 else "var(--muted)")}">'
            f'{esc((cats.get(k, {}) or {}).get("name", k))}: {v:+.2f}</span>'
            for k, v in (sent.get("by_category") or {}).items())
        label = ("негативный" if sc < -0.15 else ("позитивный" if sc > 0.15 else "нейтрально-смешанный"))
        parts.append(f"""<div class="sec-head" id="tone"><h2>Тон повестки дня</h2><div class="line"></div>
<div class="badge">лексиконная оценка</div></div>
<div class="card"><div class="card-pad"><div class="tone-wrap">
<div class="tone-gauge">
<div style="font-size:12.5px;font-weight:800;color:var(--navy);margin-bottom:6px;">Сегодня: {sc:+.2f} — {label} фон</div>
<div class="tone-bar"><div class="tone-pin" style="left:{pin}%;"></div></div>
<div style="display:flex;justify-content:space-between;font-size:10.5px;color:var(--muted);margin-top:3px;"><span>−1 тревожно</span><span>0 нейтрально</span><span>+1 позитивно</span></div>
<div class="tone-cats">{cats_html}</div>
</div>
<div style="text-align:center;"><div style="font-size:11px;font-weight:800;color:var(--muted);text-transform:uppercase;letter-spacing:.7px;margin-bottom:4px;">Динамика тона, 14 дней</div>{spark}
<div style="font-size:11.3px;color:var(--muted);margin-top:4px;">+{sent.get('today_pos',0)} позитивных · −{sent.get('today_neg',0)} негативных · {sent.get('today_neu',0)} нейтральных</div></div>
</div>
<div class="note">{esc(sent.get('method',''))}. Тон ≠ качество новостей: негатив часто означает важную проблему, попавшую в повестку.</div></div></div>""")

    # ---- Прогноз повестки (rule-based)
    if trends:
        def plural(n, forms):
            n10, n100 = n % 10, n % 100
            if n10 == 1 and n100 != 11:
                return forms[0]
            if 2 <= n10 <= 4 and not (12 <= n100 <= 14):
                return forms[1]
            return forms[2]

        rising = sorted(((t["name"], t["week"]) for t in trends["topics"].values() if t["status"] == "rising"), key=lambda x: -x[1])
        new_t = [t["name"] for t in trends["topics"].values() if t["status"] == "new"]
        fading = [t["name"] for t in trends["topics"].values() if t["status"] == "fading"]
        top = max(trends["topics"].values(), key=lambda t: t["week"]) if trends["topics"] else None
        cat_top = max(trends["categories"].values(), key=lambda c: c["week"]) if trends["categories"] else None
        lines = []
        if top:
            lines.append(f"Доминирующая тема недели — <b>«{esc(top['name'])}»</b> ({top['week']} {plural(top['week'], ('упоминание', 'упоминания', 'упоминаний'))} за 7 дней).")
        if cat_top:
            lines.append(f"Ведущая рубрика — <b>{esc(cat_top['name'])}</b> ({cat_top['week']} {plural(cat_top['week'], ('материал', 'материала', 'материалов'))}).")
        if rising:
            shown = ", ".join("<b>" + esc(n) + "</b>" for n, _ in rising[:5])
            tail = f" и ещё {len(rising)-5}" if len(rising) > 5 else ""
            lines.append(f"🔥 На подъёме: {shown}{tail} — вероятно сохранение/усиление в ближайшие 1–2 дня.")
        if new_t:
            lines.append(f"🆕 Новые темы окна: {', '.join('<b>' + esc(n) + '</b>' for n in new_t)} — взять на усиленный мониторинг.")
        if fading:
            lines.append(f"📉 Угасают: {', '.join(esc(x) for x in fading)}.")
        if not (rising or new_t or fading):
            lines.append("Повестка стабильна, резких сдвигов не зафиксировано.")
        if len(rising) > 5:
            lines.append("⚠️ Массовый рост большинства тем — признак пиковой новостной недели (День города + предвыборная кампания + инциденты); интерпретируйте статусы с учётом общей интенсивности повестки.")
        fc = an.get("forecast", [])[:6]
        fc_rows = ""
        if fc:
            arrow = {"рост": ('<span class="fc-up">↑ рост</span>'), "спад": ('<span class="fc-down">↓ спад</span>'), "плато": '<span class="fc-flat">→ плато</span>'}
            fc_rows = ('<table class="fc-tbl"><tr><th>Тема</th><th>Завтра</th><th>Ожидание</th><th>Уверенность</th></tr>'
                       + "".join(f'<tr><td><b>{esc(f["name"])}</b></td><td>{arrow.get(f["direction"], f["direction"])}</td>'
                                 f'<td>~{f["expected"]} упоминаний</td><td>{esc(f["confidence"])}</td></tr>' for f in fc)
                       + '</table>')
        parts.append(f"""<div class="sec-head" id="forecast"><h2>Прогноз повестки</h2><div class="line"></div>
<div class="badge">автоматические выводы</div></div>
<div class="card"><div class="card-pad"><div class="verdict"><b>Сводка трекера</b>{' '.join(lines)}</div>{fc_rows}
<div class="note">Выводы — правила trends.py; прогноз — наклон ряда + EMA (analytics.py), уверенность по разбросу остатков. При накоплении истории точность растёт.</div></div></div>""")

    meta = (status or {}).get("_meta", {})
    parts.append(f"""</div>
<footer class="footer"><div class="footer-inner">
<div><b>{cfg['brand']}</b><p>{esc(cfg['tagline_full'])}</p><p style="margin-top:6px;">Выпуск №{digest_no} от {day:%d.%m.%Y}. Собрано автоматически: {esc(meta.get('last_run_local','—'))} (UTC+4).</p></div>
<div><b>Методика</b><p>Мониторинг RSS ({', '.join(s['name'] for s in cfg['rss_sources'] if s.get('enabled', True))}) и публичных превью Telegram-каналов (t.me/s/…). Классификация — по словарю config.json; тренды — сравнение 3-дневного окна с недельной базой.</p></div>
<div><b>Навигация</b><p><a href="../index.html" class="flink">← Первая полоса</a> · <a href="../weekly.html" class="flink">Аналитика недели</a></p></div>
</div></footer></body></html>""")
    return "".join(parts)


REGIONAL_RE = None


def is_regional(it):
    """Региональная релевантность: tier-1/RSS/seed — всегда; агрегаторы — по маркерам."""
    global REGIONAL_RE
    if REGIONAL_RE is None:
        REGIONAL_RE = re.compile(r"ульяновск|димитровград|симбирск|\b73\b|област|русских|болдакин|\bуаз|волг|баратаевк|свияг", re.I)
    if it.get("tier") == 1 or it.get("source_type") in ("seed", "rss"):
        return True
    return bool(REGIONAL_RE.search(it.get("title", "") + " " + (it.get("text") or "")[:300]))


# ------------------------------------------------------------------ exec-digest
DECISION_RE = None  # инициализируется в render_exec


def render_exec(cfg, trends, store, status, date_str):
    """«Дайджест руководителя»: одна страница A4 — 5 событий, 3 риска, 2 решения."""
    import re as _re
    nav_html = render_nav(cfg, "exec", "../")
    global DECISION_RE
    if DECISION_RE is None:
        DECISION_RE = _re.compile(
            r"поручил|принято решение|подписал|дал старт|утвердил|выделил|договорились|"
            r"соглашение|запустил|открыли|начнётся|начнется|продлится|увеличат|проложат|выплатит")
    now = datetime.now(UTC4)
    day = datetime.strptime(date_str, "%Y-%m-%d").date()
    cats = {c["id"]: c for c in cfg["categories"]}
    win_start = datetime.combine(day, datetime.min.time(), tzinfo=UTC4) - timedelta(hours=6)
    win_end = win_start + timedelta(hours=30)
    window = [it for it in store if not it.get("dup_of")
              and local_dt(it.get("published")) and win_start <= local_dt(it["published"]) < win_end]
    if len(window) < 8:
        win_start -= timedelta(days=2)
        window = [it for it in store if not it.get("dup_of")
                  and local_dt(it.get("published")) and win_start <= local_dt(it["published"]) < win_end]

    # события — без безопасности (её место в рисках) и без федерального шума
    ev_pool = [it for it in window if it.get("category") != "security" and is_regional(it)]
    events = hero_pick(ev_pool, trends, now, 5)
    ev_ids = {it["id"] for it in events}
    # риски — разнообразие по темам (не три поста об одной сирене)
    risk_pool = sorted([it for it in window if it.get("category") == "security" and it["id"] not in ev_ids],
                       key=lambda x: (x.get("views") or 0, x.get("published") or ""), reverse=True)
    risks, seen_keys = [], set()
    for r in risk_pool:
        k = tuple(sorted(r.get("topics", [])[:2])) or (r.get("title", "")[:24],)
        if k in seen_keys:
            continue
        seen_keys.add(k)
        risks.append(r)
        if len(risks) == 3:
            break
    risk_ids = {it["id"] for it in risks}
    decisions = [it for it in window
                 if it["id"] not in ev_ids and it["id"] not in risk_ids
                 and DECISION_RE.search((it.get("title", "") + " " + (it.get("text") or "")).lower())
                 and (it.get("tier") == 1 or it.get("source_type") == "seed")]
    decisions = sorted(decisions, key=lambda x: ((x.get("views") or 0), x.get("published") or ""), reverse=True)[:2]
    rising = sorted((t for t in (trends or {}).get("topics", {}).values() if t["status"] == "rising"),
                    key=lambda t: -t["week"])[:3]

    def li(items, kind):
        out = []
        for it in items:
            dt = local_dt(it.get("published"))
            src = esc(it.get("source", ""))
            views = f" · 👁 {fmt_views(it['views'])}" if it.get("views") else ""
            out.append(f"""<li><b><a href="{esc(it.get('url') or '#')}">{esc(it['title'][:150])}</a></b>
<div class="sub">{esc((it.get('text') or '')[:230])}</div>
<div class="src">{dt.strftime('%d.%m %H:%M') if dt else ''} · {src}{views}</div></li>""")
        return "".join(out) or f"<li><span class='sub'>Нет данных за период ({kind})</span></li>"

    rising_txt = ", ".join(f"«{esc(t['name'])}»" for t in rising) or "резких сдвигов нет"
    meta = (status or {}).get("_meta", {})
    return f"""<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Дайджест руководителя · {day:%d.%m.%Y} — {cfg['brand']}</title>
<link rel="icon" type="image/png" href="../assets/logo_gudok.png"><style>{CSS}
@page {{ size: A4; margin: 14mm; }}
.exec-wrap{{max-width:860px;margin:0 auto;padding:26px 30px 40px;background:#fff;}}
.exec-head{{display:flex;justify-content:space-between;align-items:center;border-bottom:3px solid var(--navy);padding-bottom:12px;margin-bottom:18px;flex-wrap:wrap;gap:8px;}}
.exec-head h1{{font-size:22px;color:var(--navy);}}
.exec-head .d{{font-size:13px;color:var(--muted);text-align:right;}}
.exec-sec{{margin-bottom:20px;break-inside:avoid;}}
.exec-sec h2{{font-size:14px;text-transform:uppercase;letter-spacing:1.2px;color:#fff;background:var(--navy);display:inline-block;padding:5px 14px;border-radius:7px;margin-bottom:10px;}}
.exec-sec.risk h2{{background:#b02a2f;}}
.exec-sec.dec h2{{background:#1d7a4d;}}
.exec-sec ol,.exec-sec ul{{padding-left:22px;}}
.exec-sec li{{margin-bottom:12px;font-size:13.5px;line-height:1.5;}}
.exec-sec li b a{{color:var(--navy);}}
.exec-sec .sub{{color:var(--muted);font-size:12.3px;margin-top:2px;}}
.exec-sec .src{{color:#8a99aa;font-size:10.8px;font-weight:700;margin-top:3px;}}
.exec-trend{{background:#f7fafd;border:1px solid var(--line);border-radius:10px;padding:11px 15px;font-size:13px;color:var(--navy3);}}
.exec-foot{{border-top:1px solid var(--line);margin-top:24px;padding-top:10px;font-size:10.5px;color:#8a99aa;display:flex;justify-content:space-between;flex-wrap:wrap;gap:6px;}}
@media print{{ .topbar,.nav,.print-btn{{display:none!important;}} .exec-wrap{{padding:0;}} }}
</style></head><body>
{nav_html}<div class="exec-wrap">
<div class="exec-head">
<h1>📋 Дайджест руководителя</h1>
<div class="d"><b>Гудок</b> · информационно-аналитическое издание<br>{day:%d.%m.%Y} · сформирован {now:%H:%M} (UTC+4) · 1 страница</div>
</div>

<div class="exec-sec"><h2>5 событий дня</h2><ol>{li(events, 'события')}</ol></div>
<div class="exec-sec risk"><h2>3 риска</h2><ol>{li(risks, 'риски')}</ol></div>
<div class="exec-sec dec"><h2>2 решения</h2><ol>{li(decisions, 'решения')}</ol></div>

<div class="exec-sec"><h2>Повестка</h2>
<div class="exec-trend">🔥 На подъёме: {rising_txt}. Материалов за 24 ч: <b>{(trends or {}).get('counts',{}).get('last24h','—')}</b>, всего в базе: <b>{(trends or {}).get('counts',{}).get('total','—')}</b>. Последний сбор: {esc(meta.get('last_run_local','—'))}.</div></div>

<div class="exec-foot">
<span>Автономный режим: события/риски/решения отобраны алгоритмом по просмотрам, темам и свежести; решения — по маркерам действий в tier-1 источниках. Требует вычитки перед рассылкой (human-in-the-loop).</span>
<span>Подробная версия: digest_{date_str}.html · {cfg['brand']}</span>
</div>
<button class="print-btn" onclick="window.print()" style="margin-top:14px;">🖨 Печать / PDF</button>
{THEME_BTN}
</div></body></html>"""


# ------------------------------------------------------------------ elections special
CANDIDATES = [
    # (имя, партия, css-класс партии, био, факт)
    ("Алексей Русских", "КПРФ", "p-kprf",
     "Действующий губернатор (с 2021). Сенатор РФ в 2018–2021, до этого — депутат Госдумы и Мособлдумы, инженер-предприниматель (транспорт, ЖКХ).",
     "Идёт при поддержке «Единой России» — редкая конфигурация: один из трёх губернаторов-коммунистов в стране (по данным «Ведомостей»). Фаворит кампании."),
    ("Марина Ким", "Справедливая Россия", "p-sr",
     "Актриса, телеведущая («Утро России»), депутат Госдумы VIII созыва.",
     "Самый медийный кандидат кампании — федеральная узнаваемость работает на явку и результат СР."),
    ("Сергей Маринин", "ЛДПР", "p-ldpr",
     "Депутат Госдумы VII созыва (2016–2021), координатор ЛДПР в регионе, инженер-экономист.",
     "Единственный кандидат, идущий «паровозом» сразу в двух кампаниях: губернатор + Госдума по округу № 186."),
    ("Юлия Ясайтис", "Новые люди", "p-nl",
     "Предприниматель, представительница «Новых людей».",
     "Партия впервые участвует в ульяновской губернаторской кампании — тест региональной инфраструктуры."),
]

DUMA = {
    "185": [
        ("Владимир Камеко", "ЕР", "p-er"), ("Антон Шилов", "КПРФ", "p-kprf"),
        ("Дмитрий Грачёв", "ЛДПР", "p-ldpr"), ("Андрей Седов", "СР", "p-sr"),
        ("Юрий Белоусов", "Новые люди", "p-nl"), ("Леонид Костиков", "Коммунисты России", "p-kpk"),
        ("Игорь Южалин", "Зелёные", "p-zel"), ("Алексей Якушев", "Родина", "p-rod"),
    ],
    "186": [
        ("Владимир Кононов", "ЕР", "p-er"), ("Роман Султашов", "КПРФ", "p-kprf"),
        ("Сергей Маринин", "ЛДПР", "p-ldpr"), ("Григорий Матвеев", "СР", "p-sr"),
        ("Марат Аряпов", "Новые люди", "p-nl"), ("Камиль Сафиуллин", "Коммунисты России", "p-kpk"),
        ("Владимир Малинин", "Партия пенсионеров", "p-pens"), ("Анжелика Берестовская", "Зелёные", "p-zel"),
        ("Игорь Сафонов", "Родина", "p-rod"),
    ],
}

EXTRA_CSS = """
.pill{font-size:10.5px;font-weight:800;color:#fff;border-radius:999px;padding:3px 10px;white-space:nowrap;display:inline-block;}
.p-kprf{background:#d52b1e;} .p-er{background:#2d6fd6;} .p-sr{background:#e2622a;}
.p-ldpr{background:#1f3a93;} .p-nl{background:#00b3a4;} .p-kpk{background:#8e1b1b;}
.p-zel{background:#3aa655;} .p-rod{background:#b03050;} .p-pens{background:#7b5aa6;}
.cand-card{background:var(--card);border-radius:var(--radius);box-shadow:var(--shadow);border:1px solid var(--line);padding:15px 17px;border-top:4px solid var(--blue);}
.cand-card h3{font-size:16px;color:var(--navy);margin-bottom:4px;}
.cand-card .bio{font-size:12.6px;color:var(--muted);line-height:1.5;margin:7px 0;}
.cand-card .fact{font-size:12.3px;background:#f7fafd;border-left:3px solid var(--gold);padding:7px 11px;border-radius:0 8px 8px 0;color:var(--navy3);}
.countdown{background:linear-gradient(135deg,#b02a2f,#e5484d);border-radius:var(--radius);color:#fff;padding:18px 24px;display:flex;align-items:center;gap:22px;flex-wrap:wrap;box-shadow:var(--shadow);}
.countdown .big{font-size:40px;font-weight:800;line-height:1;}
.countdown .txt b{font-size:16px;display:block;}
.countdown .txt span{font-size:12.5px;opacity:.9;}
.dist-card{background:var(--card);border-radius:var(--radius);box-shadow:var(--shadow);border:1px solid var(--line);overflow:hidden;}
.dist-head{background:var(--navy);color:#fff;padding:11px 16px;font-size:14px;font-weight:800;display:flex;gap:10px;align-items:center;}
.dist-head .n{background:var(--gold);color:#3d2e04;border-radius:7px;padding:2px 10px;font-size:12.5px;}
.dist-body{padding:12px 16px;display:flex;flex-wrap:wrap;gap:7px;}
.person{border:1px solid var(--line);border-radius:9px;padding:6px 10px;font-size:12.3px;display:flex;align-items:center;gap:7px;background:#fbfdff;}
.reserved{background:repeating-linear-gradient(45deg,#f7fafd,#f7fafd 12px,#eef2f7 12px,#eef2f7 24px);border:2px dashed #b9c9da;border-radius:var(--radius);padding:20px 22px;text-align:center;color:var(--muted);}
.reserved b{color:var(--navy);display:block;font-size:15px;margin-bottom:6px;}
.watch li{font-size:13px;margin-bottom:8px;line-height:1.5;}
"""


def render_elections(cfg, trends, store, status):
    now = datetime.now(UTC4)
    nav_html = render_nav(cfg, "elections", "../")
    vote_day = datetime(2026, 9, 18, tzinfo=UTC4).date()
    days_left = (vote_day - now.date()).days

    # выборные материалы из базы
    elec = [it for it in store if not it.get("dup_of") and "elections" in (it.get("topics") or [])]
    elec.sort(key=lambda x: (x.get("views") or 0, x.get("published") or ""), reverse=True)
    # кто активнее пишет о выборах (7 дней)
    from collections import Counter
    week_ago = now - timedelta(days=7)
    src_counter = Counter()
    for it in elec:
        dt = local_dt(it.get("published"))
        if dt and dt >= week_ago:
            src_counter[it.get("channel") or it.get("source") or "?"] += 1
    src_rows = "".join(
        f'<div class="bar-row" style="display:flex;gap:9px;align-items:center;margin-bottom:6px;font-size:12.3px;">'
        f'<div style="width:150px;text-align:right;font-weight:600;color:var(--txt);">{esc(str(k))}</div>'
        f'<div style="flex:1;background:#edf2f8;border-radius:6px;height:15px;overflow:hidden;">'
        f'<div style="width:{max(4, int(v / max(src_counter.values()) * 100))}%;height:100%;background:linear-gradient(90deg,#2d6fd6,#5aa0f5);border-radius:6px;"></div></div>'
        f'<div style="width:26px;font-weight:800;color:var(--navy);">{v}</div></div>'
        for k, v in src_counter.most_common(8))

    topic = (trends or {}).get("topics", {}).get("elections", {})
    spark = sparkline(topic.get("series", []), w=260, h=44, color="#b02a2f") if topic else ""

    feed = "".join(
        f"""<div class="news-item">
<h4><a href="{esc(it.get('url') or '#')}" target="_blank" rel="noopener">{esc(it['title'][:140])}</a></h4>
<p>{esc((it.get('text') or '')[:300])}</p>
<div class="meta">{(local_dt(it.get('published')) or now).strftime('%d.%m %H:%M')} · {esc(it.get('source',''))}{(' · 👁 ' + fmt_views(it['views'])) if it.get('views') else ''}</div></div>"""
        for it in elec[:10]) or '<div class="news-item"><p>Материалов пока нет — запустите сбор.</p></div>'

    party_colors = {'p-kprf': '#d52b1e', 'p-sr': '#e2622a', 'p-ldpr': '#1f3a93', 'p-nl': '#00b3a4'}
    cand_cards = "".join(
        f"""<div class="cand-card" style="border-top-color:{party_colors.get(css, 'var(--blue)')};">
<h3>{esc(name)} <span class="pill {css}">{esc(party)}</span></h3>
<div class="bio">{esc(bio)}</div>
<div class="fact">{esc(fact)}</div></div>"""
        for name, party, css, bio, fact in CANDIDATES)

    dist_blocks = "".join(
        f"""<div class="dist-card"><div class="dist-head"><span class="n">Округ № {no}</span> Госдума IX созыва · {len(lst)} кандидатов</div>
<div class="dist-body">{''.join(f'<span class="person">{esc(nm)} <span class="pill {pc}" style="font-size:9.5px;padding:2px 8px;">{esc(pt)}</span></span>' for nm, pt, pc in lst)}</div></div>"""
        for no, lst in DUMA.items())

    cd_word = "день" if days_left % 10 == 1 and days_left != 11 else ("дня" if 2 <= days_left % 10 <= 4 and not 12 <= days_left <= 14 else "дней")
    cd_text = f"до единого дня голосования осталось <b>{days_left}</b> {cd_word}" if days_left > 0 else "голосование идёт / завершилось"

    return f"""<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Спецвыпуск «Выборы-2026» · Ульяновская область — {cfg['brand']}</title>
<link rel="icon" type="image/png" href="../assets/logo_gudok.png"><style>{CSS}{EXTRA_CSS}
@media print{{.nav,.print-btn{{display:none!important;}}body{{background:#fff;}}}}
</style></head><body>
<header class="topbar"><div class="topbar-inner">
<div class="brand"><div>
<div class="brand-title">ИЗДАНИЕ <span>ГУДОК</span> · ВЫБОРЫ-2026</div>
<div class="brand-sub">Информационно-аналитическое издание · спецвыпуск: губернатор, Госдума IX созыва, довыборы в ЗСО</div>
</div></div>
<div class="top-meta">
<div class="chip">🗳 Голосование <b>18–20 сентября</b></div>
<div class="chip">🤖 обновлён <b>{now:%d.%m %H:%M}</b></div>
<a class="chip" href="../index.html">← Первая полоса</a>
{THEME_BTN}
<button class="print-btn" onclick="window.print()">🖨 PDF</button>
</div></div></header>
{nav_html}
<div class="page">

<div class="countdown" style="margin-bottom:18px;">
<div class="big">{days_left if days_left > 0 else '🗳'}</div>
<div class="txt"><b>{cd_text.capitalize() if days_left>0 else cd_text}</b>
<span>18, 19 и 20 сентября 2026 · трёхдневное голосование · участки 8:00–20:00 · ДЭГ в области не проводится</span></div>
</div>

<div class="kpi-grid" style="grid-template-columns:repeat(5,1fr);margin-bottom:22px;">
<div class="kpi"><div class="num">925 350</div><div class="lbl">избирателей в регионе</div></div>
<div class="kpi gold"><div class="num">52,6%</div><div class="lbl">избирателей — в Ульяновске</div></div>
<div class="kpi violet"><div class="num">4</div><div class="lbl">кандидата на пост губернатора</div></div>
<div class="kpi green"><div class="num">17</div><div class="lbl">кандидатов в Госдуму по двум округам</div></div>
<div class="kpi red"><div class="num">3</div><div class="lbl">кампании одновременно (губернатор, ГД, ЗСО)</div></div>
</div>

<div class="sec-head" style="margin-top:8px;"><h2>Кандидаты на пост губернатора</h2><div class="line"></div>
<div class="badge">избран на 5 лет · назначает сенатора</div></div>
<div class="grid2" style="margin-bottom:8px;">{cand_cards}</div>
<div class="note" style="margin-bottom:22px;">Порога явки нет — выборы состоятся при любой активности. Профили составлены по данным Википедии, «Ведомостей» и региональных СМИ (проверено 11.09.2026).</div>

<div class="sec-head"><h2>Государственная Дума: одномандатные округа</h2><div class="line"></div>
<div class="badge">по данным gogov.ru, 23.08.2026</div></div>
<div class="grid2" style="margin-bottom:6px;">{dist_blocks}</div>
<div class="note" style="margin-bottom:22px;">Всего по округам выдвигались 20 человек: 1 снялся, 2 выбыли после регистрации (Д. Гондаренко, «Яблоко», № 185; Е. Скрипкин, «Яблоко», № 186). Также 20 сентября — довыборы депутата Законодательного Собрания VII созыва по Вешкаймскому одномандатному округу № 2.</div>

<div class="sec-head"><h2>Выборная повестка в мониторинге</h2><div class="line"></div>
<div class="badge">трекер трендов</div></div>
<div class="grid2" style="margin-bottom:8px;">
<div class="card"><div class="card-pad">
<div style="font-size:12.5px;font-weight:800;color:var(--navy);margin-bottom:6px;">Тема «Выборы-2026»: {topic.get('week',0)} упоминаний за 7 дней, {topic.get('today',0)} за сегодня</div>
{spark}
<div class="verdict"><b>Статус трекера</b>{ {'rising':'🔥 тема на подъёме — ожидаем пик 18–20 сентября','new':'🆕 тема вошла в повестку окна наблюдения','stable':'⚖️ ровный фон','fading':'📉 интерес спадает','silent':'💤 тишина'}.get(topic.get('status',''), '—') }. До голосования публикационная активность каналов будет расти — классическая предвыборная динамика.</div>
</div></div>
<div class="card"><div class="card-pad">
<div style="font-size:12.5px;font-weight:800;color:var(--navy);margin-bottom:8px;">Кто активнее пишет о выборах (7 дней)</div>
{src_rows or '<span style="color:var(--muted);font-size:12.5px;">Нет данных</span>'}
<div class="note">Считаются только первичные материалы (перепечатки исключены дедупликацией).</div>
</div></div></div>

<div class="sec-head"><h2>Выборная лента из базы центра</h2><div class="line"></div>
<div class="badge">топ-10 по просмотрам и свежести</div></div>
<div class="card" style="margin-bottom:22px;">{feed}</div>

<div class="sec-head"><h2>Что будем отслеживать 18–20 сентября</h2><div class="line"></div></div>
<div class="card"><div class="card-pad"><ul class="watch" style="padding-left:20px;">
<li><b>Явка по дням</b> — трёхдневное голосование без ДЭГ делает мобилизацию в Ульяновске (52,6% избирателей) ключевым фактором; сравним с 2021 годом (губернаторские: ~48% на трёх днях).</li>
<li><b>Результаты губернаторской кампании</b> — интрига не в победе фаворита, а в распределении мест 2–4 (Ким vs Маринин vs Ясайтис) и проценте ЕР/КПРФ по партспискам.</li>
<li><b>Округа № 185 и № 186</b> — Камеко (ЕР) и Кононов (ЕР) против сильных коммунистов (Шилов, Султашов); Маринин тянет ЛДПР сразу в двух кампаниях.</li>
<li><b>Сообщения о нарушениях</b> — мониторинг Ulnovosti.ru, «Компромат Ульяновск», tier-3 каналов с обязательной верификацией по tier-1.</li>
<li><b>Первые шаги избранного губернатора</b> — назначение сенатора из трёх заявленных протеже, кадровые решения в правительстве области.</li>
</ul></div></div>

<div class="sec-head"><h2>Итоги голосования</h2><div class="line"></div>
<div class="badge">после 20.09.2026</div></div>
<div class="reserved" style="margin-bottom:22px;">
<b>Раздел будет наполнен после закрытия участков</b>
Данные облизбиркома, явка, результаты по всем трём кампаниям, карта округов и первая реакция победителей.
Финализация: запустить <code>python3 generate.py --elections</code> после 20 сентября (лента и тренды подтянутся автоматически),
либо написать в чат: <b>«собери итоги выборов»</b> — выпуск будет дополнен верифицированными результатами.
</div>

</div>
<footer class="footer"><div class="footer-inner">
<div><b>{cfg['brand']}</b><p>Спецвыпуск «Выборы-2026». Предвыборная редакция от {now:%d.%m.%Y}. Обновляется ежедневно конвейером run.sh до дня голосования.</p></div>
<div><b>Источники профилей</b><p>Википедия («Выборы губернатора Ульяновской области (2026)»), gogov.ru (сводка кандидатов от 23.08.2026), Избирательная комиссия Ульяновской области, «Ведомости», региональные СМИ.</p></div>
<div><b>Дисклеймер</b><p>Выпуск информационно-аналитический, не является агитацией. Оценки помечены как редакционные. Фактические данные сверены с первоисточниками на дату обновления.</p></div>
</div></footer>
</body></html>"""


# ------------------------------------------------------------------ projects
def render_projects(cfg, trends, store, status):
    """Хаб рубрики «Проекты»: спецстраницы-досье издания."""
    now = datetime.now(UTC4)
    nav_html = render_nav(cfg, "projects", "")
    cards = f"""<div class="sec-card" style="border-top-color:var(--accent);text-decoration:none;display:block;">
<div><b>Инфопространство</b></div>
<div class="fig">live <small>дашборд</small></div>
<p>Скользящее исследование инфополя: метрики, тон, каскады, карта муниципалитетов, очередь новых метрик.</p>
<a class="go" href="infospace.html">открыть дашборд →</a></div>"""
    for pr in cfg.get("projects", []):
        st = {"active": ("в работе", "#1d7a4d"), "plan": ("в плане", "#96690a")}.get(pr.get("status"), (pr.get("status", ""), "#5b6b7c"))
        cards += f"""<div class="sec-card" style="border-top-color:{st[1]};text-decoration:none;display:block;">
<b>{esc(pr['title'])}</b>
<div class="fig" style="font-size:12px;color:{st[1]};">{st[0]}</div>
<p>{esc(pr.get('desc',''))}</p>
<a class="go" href="{esc(pr['path'])}">открыть досье →</a></div>"""
    return f"""<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Проекты — {cfg['brand']}</title>
<link rel="icon" type="image/png" href="assets/logo_gudok.png">
<style>{CSS}{INDEX_CSS}</style></head><body>
<header class="topbar"><div class="topbar-inner">
<div class="brand"><div>
<div class="brand-title">ИЗДАНИЕ <span>ГУДОК</span> · ПРОЕКТЫ</div>
<div class="brand-sub">Специальные досье и кампанийные страницы издания</div>
</div></div>
<div class="top-meta">
<div class="chip">обновлено <b>{now:%d.%m %H:%M}</b></div>
<button class="theme-btn" id="themeBtn" onclick="toggleTheme()" title="Светлая/тёмная тема">🌙</button>
</div></div></header>
{nav_html}
<div class="wrap1200" style="padding-top:20px;">
<div class="sec-head" style="margin-top:0;"><h2>Проекты издания</h2><div class="line"></div>
<div class="badge">{len(cfg.get('projects', []))} в работе</div></div>
<div class="note" style="margin-bottom:16px;">Проект — это спецстраница-досье с собственной методикой наблюдения: кампания (выборы),
сквозной мониторинг (госзакупки) или расследование. Проекты живут вне ежедневной ленты, но питаются общей базой
и «Инфопространством». Название рубрики рабочее — редакция обсуждает варианты: «Проекты», «Спецпроекты», «Досье».</div>
<div class="sec-grid">{cards}</div>
</div>
<footer class="footer"><div class="footer-inner">
<div><b>Гудок</b><p>{esc(cfg['tagline_full'])}</p></div>
<div><b>Разделы</b><p><a href="index.html" class="flink">Первая полоса</a> · <a href="infospace.html" class="flink">Инфопространство</a> · <a href="afisha.html" class="flink">Афиша</a></p></div>
</div></footer>
</body></html>"""


GZ_RE = None


def render_goszakupki(cfg, trends, store, status, an):
    """Проект «Госзакупки»: повестка закупок в инфопотоке + методики ЕИС."""
    global GZ_RE
    import re as _re
    from analytics import sentiment_of
    if GZ_RE is None:
        GZ_RE = _re.compile(cfg.get("goszakupki_keywords", "закуп|тендер|аукцион"), _re.I)
    now = datetime.now(UTC4)
    nav_html = render_nav(cfg, "projects", "../")
    week_ago = now - timedelta(days=7)
    live = [it for it in store if not it.get("dup_of") and local_dt(it.get("published"))]
    gz = [it for it in live if GZ_RE.search(f"{it.get('title','')} {(it.get('text') or '')[:300]}")]
    gz_week = [it for it in gz if local_dt(it["published"]) >= week_ago]
    sc = [sentiment_of(f"{it.get('title','')} {(it.get('text') or '')[:250]}")[0] for it in gz_week]
    tone = round(sum(sc) / len(sc), 2) if sc else 0
    src_c = {}
    for it in gz_week:
        k = it.get("channel") or it.get("source") or "?"
        src_c[k] = src_c.get(k, 0) + 1
    src_rows = "".join(
        f'<div class="bar-row" style="display:flex;gap:9px;align-items:center;margin-bottom:6px;font-size:12.4px;">'
        f'<div style="width:150px;text-align:right;font-weight:600;flex-shrink:0;">{esc(k)}</div>'
        f'<div style="flex:1;background:#edf2f8;border-radius:6px;height:15px;overflow:hidden;">'
        f'<div style="width:{max(4, int(v / max(src_c.values()) * 100))}%;height:100%;background:#96690a;border-radius:6px;"></div></div>'
        f'<div style="width:30px;font-weight:800;">{v}</div></div>'
        for k, v in sorted(src_c.items(), key=lambda x: -x[1])[:8])
    stories = "".join(
        f"""<div class="af-mini"><div class="cal-badge"><b>{(local_dt(it['published']) or now):%d}</b><span>{(local_dt(it['published']) or now):%b}</span></div>
<div style="flex:1;"><a href="{esc(it.get('url') or '#')}" target="_blank" rel="noopener" style="font-size:13px;font-weight:700;color:var(--navy);">{esc(it['title'][:110])}</a>
<div style="font-size:11.3px;color:var(--muted);">{esc(it.get('source',''))} · 👁 {fmt_views(it.get('views')) if it.get('views') else '—'}</div></div></div>"""
        for it in sorted(gz_week, key=lambda x: x.get("views") or 0, reverse=True)[:8])
    eis_metrics = [
        ("Число извещений 44-ФЗ заказчиков Ульяновской области", "неделя / месяц", "ожидает подключения"),
        ("Суммарная НМЦК и цена заключённых контрактов", "млн ₽", "ожидает подключения"),
        ("Доля закупки у единственного поставщика", "%", "ожидает подключения"),
        ("Среднее снижение цены на конкурентных процедурах", "%", "ожидает подключения"),
        ("Топ-10 заказчиков региона по объёму", "рейтинг", "ожидает подключения"),
        ("Топ-10 поставщиков и концентрация рынка", "HHI", "ожидает подключения"),
    ]
    eis_rows = "".join(
        f'<tr><td>{esc(n)}</td><td>{esc(u)}</td><td><span class="stchip" style="background:#fdf3dd;color:#96690a;">{esc(st)}</span></td></tr>'
        for n, u, st in eis_metrics)
    return f"""<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Проект «Госзакупки» — {cfg['brand']}</title>
<link rel="icon" type="image/png" href="../assets/logo_gudok.png">
<style>{CSS}{INDEX_CSS}</style></head><body>
<header class="topbar"><div class="topbar-inner">
<div class="brand"><div>
<div class="brand-title">ИЗДАНИЕ <span>ГУДОК</span> · ГОСЗАКУПКИ</div>
<div class="brand-sub">Проект рубрики «Проекты»: аналитика государственных закупок региона</div>
</div></div>
<div class="top-meta">
<div class="chip">неделя: <b>{len(gz_week)}</b> упоминаний</div>
<div class="chip">обновлено <b>{now:%d.%m %H:%M}</b></div>
<button class="theme-btn" id="themeBtn" onclick="toggleTheme()" title="Светлая/тёмная тема">🌙</button>
</div></div></header>
{nav_html}
<div class="wrap1200" style="padding-top:20px;">
<div class="sec-head" style="margin-top:0;"><h2>Паспорт проекта</h2><div class="line"></div></div>
<div class="note" style="margin-bottom:16px;"><b>Цель</b> — видеть, как расходуются бюджетные деньги региона: что закупается,
кем, у кого и по какой цене; и как закупочная повестка отражается в СМИ и телеграм-каналах.
<b>Источники:</b> (1) инфопоток издания — упоминания закупок в 30+ мониторируемых источниках; (2) ЕИС zakupki.gov.ru
(44-ФЗ и 223-ФЗ) — прямое подключение возможно из контура РФ (сервер редакции или ручной экспорт выгрузки:
csv/json со полями заказчик, НМЦК, способ, дата, поставщик); из песочницы и облачных раннеров ЕИС недоступна (таймауты).
<b>Методика:</b> недельные срезы, сравнение периодов, разбор аномалий (крупные единственные поставщики, рост НМЦК по темам).</div>

<div class="grid2">
<div>
<div class="sec-head"><h2>Закупки в инфопотоке</h2><div class="line"></div>
<div class="badge">{len(gz_week)} за неделю · тон {tone:+.2f}</div></div>
<div class="card"><div class="card-pad">
<div style="font-size:12.5px;font-weight:800;color:var(--navy);margin-bottom:8px;">Кто освещает закупки</div>
{src_rows or '<div class="now-line">За неделю упоминаний не было.</div>'}
</div></div>
<div class="card" style="margin-top:14px;"><div class="side-head">🗂 Сюжеты недели о закупках</div>
<div class="side-body">{stories or '<div style="color:var(--muted);font-size:12.5px;">Сюжетов за неделю нет.</div>'}</div></div>
</div>
<div>
<div class="sec-head"><h2>Метрики ЕИС</h2><div class="line"></div>
<div class="badge">подключение</div></div>
<div class="card"><div class="card-pad" style="padding:10px 14px;">
<table class="tbl"><tr><th>Метрика</th><th>Ед.</th><th>Статус</th></tr>{eis_rows}</table>
<div class="note">Как подключить: выгрузка ЕИС (личный кабинет / открытые данные) кладётся в <code>data/goszakupki_eis.csv</code>
со столбцами date, customer, method, nmck, supplier — страница начнёт считать метрики автоматически (следующая итерация).
До подключения проект ведёт повесточную часть и готовит разборы вручную.</div>
</div></div>
</div>
</div>
</div>
<footer class="footer"><div class="footer-inner">
<div><b>Гудок</b><p>{esc(cfg['tagline_full'])}</p></div>
<div><b>Рубрика</b><p><a href="../projects.html" class="flink">Все проекты</a> · <a href="../infospace.html" class="flink">Инфопространство</a></p></div>
</div></footer>
</body></html>"""


# ------------------------------------------------------------------ afisha
ETYPE_META = {
    "festival": ("🎪", "Фестивали и праздники"),
    "theatre":  ("🎭", "Театр и спектакли"),
    "concert":  ("🎵", "Концерты и музыка"),
    "expo":     ("🖼", "Выставки, музеи, библиотеки"),
    "kids":     ("👶", "Детям и семьям"),
    "cinema":   ("🎬", "Кино"),
    "sport":    ("🏃", "Спорт и ЗОЖ"),
    "other":    ("📌", "Прочее и официальное"),
}
AFISHA_ORDER = ["festival", "theatre", "concert", "expo", "kids", "cinema", "sport", "other"]
AFISHA_CHANNELS = ["culturnik", "ulpromo", "ProNovosty73"]

AFISHA_CSS = """
.af-chips{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:16px;}
.af-chip{border:1px solid var(--line);background:var(--card);color:var(--muted);font-size:12.5px;font-weight:700;padding:7px 15px;border-radius:999px;cursor:pointer;}
.af-chip:hover{border-color:var(--blue);color:var(--blue);}
.af-chip.on{background:var(--navy3);border-color:var(--navy3);color:#fff;}
:root[data-theme="dark"] .af-chip.on{background:#2f80ed;border-color:#2f80ed;}
.af-event{display:flex;gap:12px;padding:10px 0;border-bottom:1px dashed var(--line);align-items:flex-start;}
.af-event:last-child{border-bottom:none;}
.af-body{flex:1;}
.af-body a b{font-size:13.6px;color:var(--navy);line-height:1.35;display:inline-block;}
.af-body a:hover b{color:var(--blue);}
.af-meta{font-size:11.8px;color:var(--muted);margin-top:3px;}
.af-time{display:inline-block;background:#e8f4ff;color:#1d4f9c;border-radius:7px;padding:1px 8px;font-weight:800;font-size:11px;margin-right:6px;}
:root[data-theme="dark"] .af-time{background:#16283c;color:#8ab4e8;}
.dist-badge{display:inline-block;background:#fdf3dd;color:#96690a;border-radius:7px;padding:1px 8px;font-weight:800;font-size:10.5px;margin-left:6px;}
.af-sec{margin-bottom:20px;}
.af-empty{padding:26px;text-align:center;color:var(--muted);font-size:13px;}
.af-daybar{display:flex;gap:7px;flex-wrap:wrap;margin-bottom:18px;}
.af-day{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:7px 11px;text-align:center;min-width:64px;}
.af-day b{display:block;font-size:15px;color:var(--navy);}
.af-day span{font-size:10px;color:var(--muted);text-transform:uppercase;}
.af-day i{display:block;font-style:normal;font-size:11px;font-weight:800;color:var(--blue);margin-top:2px;}
.af-day.we{border-color:var(--gold);}
"""

AFISHA_JS = """<script>
function afFilter(mode,btn){
  document.querySelectorAll('.af-chip').forEach(function(c){c.classList.remove('on');});
  btn.classList.add('on');
  var today=new Date();today.setMinutes(today.getMinutes()-today.getTimezoneOffset());
  var iso=today.toISOString().slice(0,10);
  var tom=new Date(today.getTime()+86400000)).toISOString().slice(0,10);
  document.querySelectorAll('.af-event').forEach(function(ev){
    var d=ev.getAttribute('data-date');var show=true;
    if(mode==='today')show=(d===iso);
    else if(mode==='tomorrow')show=(d===tom);
    else if(mode==='weekend')show=ev.getAttribute('data-weekend')==='1';
    else if(mode==='week'){var t=new Date(iso);var x=new Date(d);show=((x-t)/86400000)<=7;}
    ev.style.display=show?'':'none';
  });
  document.querySelectorAll('.af-sec').forEach(function(sec){
    var vis=sec.querySelectorAll('.af-event[style=""], .af-event:not([style])');
    var any=Array.prototype.some.call(sec.querySelectorAll('.af-event'),function(e){return e.style.display!=='none';});
    sec.style.display=any?'':'none';
  });
}
</script>"""


def render_afisha(cfg, trends, store, status, an):
    now = datetime.now(UTC4)
    nav_html = render_nav(cfg, "afisha", "")
    today = now.date()
    cal = (an or {}).get("calendar", [])

    def edate(e):
        try:
            return datetime.strptime(e["date"], "%Y-%m-%d").date()
        except ValueError:
            return None

    cal = [e for e in cal if edate(e) and edate(e) >= today]
    seen, uniq = set(), []
    for e in sorted(cal, key=lambda x: (x["date"], x.get("time", ""))):
        k = (e["date"], re.sub(r"\W+", "", e["title"].lower())[:30])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(e)
    cal = uniq

    # ближайшие выходные (сб+вс)
    sat = today + timedelta(days=(5 - today.weekday()) % 7)
    weekend = {sat, sat + timedelta(days=1)}
    if today.weekday() == 6:
        weekend = {today}

    wd = {0: "пн", 1: "вт", 2: "ср", 3: "чт", 4: "пт", 5: "сб", 6: "вс"}

    # панель дней (10 дней вперёд)
    daybar = []
    for i in range(10):
        dd = today + timedelta(days=i)
        n = sum(1 for e in cal if edate(e) == dd)
        we = ' we' if dd in weekend else ''
        daybar.append(f'<div class="af-day{we}"><b>{dd:%d}</b><span>{wd[dd.weekday()]} {dd:%m}</span><i>{n} соб.</i></div>')

    # секции по типам
    sections = []
    n_culture = 0
    for et in AFISHA_ORDER:
        evs = [e for e in cal if e.get("etype", "other") == et]
        if not evs:
            continue
        if et not in ("sport", "other"):
            n_culture += len(evs)
        icon, name = ETYPE_META[et]
        rows = []
        for e in evs:
            d = edate(e)
            gold = ' gold' if d in weekend else ''
            t = f'<span class="af-time">{esc(e["time"])}</span>' if e.get("time") else ''
            venue = f' · 📍 {esc(e["venue"])}' if e.get("venue") else ''
            dist = '<span class="dist-badge">район/область</span>' if e.get("district") else ''
            end = e.get("date_end")
            span = f' — {end[8:10]}.{end[5:7]}' if end else ''
            rows.append(f"""<div class="af-event" data-date="{e['date']}" data-weekend="{'1' if d in weekend else '0'}">
<div class="cal-badge{gold}"><b>{d:%d}</b><span>{wd[d.weekday()]} {d:%m}</span></div>
<div class="af-body"><a href="{esc(e.get('url') or '#')}" target="_blank" rel="noopener"><b>{esc(e['title'][:130])}</b></a>{span}
<div class="af-meta">{t}{esc(e.get('source',''))}{venue}{dist}</div></div></div>""")
        sections.append(f"""<div class="af-sec" id="et-{et}"><div class="sec-head" style="margin:16px 0 8px;"><h2>{icon} {name}</h2><div class="line"></div>
<div class="badge">{len(evs)}</div></div><div class="card"><div class="card-pad">{''.join(rows)}</div></div></div>""")

    # анонсы культурных каналов
    tg_items = [it for it in store if it.get("source_type") == "tg"]
    chan_html = []
    for chn in AFISHA_CHANNELS:
        ch_cfg = next((c for c in cfg.get("telegram_channels", []) if c["username"] == chn), None)
        posts = sorted([it for it in tg_items if it.get("channel") == chn],
                       key=lambda x: x.get("published") or "", reverse=True)[:3]
        rows = "".join(
            f"""<div class="tgpost"><div><div class="t"><a href="{esc(it.get('url') or '#')}" target="_blank" rel="noopener">{esc(it['title'][:120])}</a></div>
<div class="m">{(local_dt(it.get('published')) or now).strftime('%d.%m %H:%M')}{' · 👁 ' + fmt_views(it['views']) if it.get('views') else ''}</div></div></div>"""
            for it in posts) or '<div class="tgpost"><div class="t" style="color:var(--muted);">нет свежих постов</div></div>'
        chan_html.append(f"""<div class="card" style="margin-bottom:12px;"><div class="side-head">🎟
<a href="https://t.me/{esc(chn)}" target="_blank" rel="noopener" style="color:#fff;">@{esc(chn)}</a>
<span class="sub">{esc((ch_cfg or {}).get('title',''))}</span></div><div class="side-body">{rows}</div></div>""")

    today_n = sum(1 for e in cal if edate(e) == today)
    we_n = sum(1 for e in cal if edate(e) in weekend)
    total_n = len(cal)

    return f"""<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Афиша культурных событий · Ульяновская область — {cfg['brand']}</title>
<link rel="icon" type="image/png" href="assets/logo_gudok.png"><style>{CSS}{AFISHA_CSS}</style></head><body>
<header class="topbar"><div class="topbar-inner">
<div class="brand"><div>
<div class="brand-title">🎭 АФИША <span>ГУДОК</span></div>
<div class="brand-sub">Информационно-аналитическое издание · культурные события Ульяновской области</div>
</div></div>
<div class="top-meta">
<div class="chip">📅 событий: <b>{total_n}</b></div>
<div class="chip">сегодня: <b>{today_n}</b> · выходные: <b>{we_n}</b></div>
<div class="chip">обновлено <b>{now:%d.%m %H:%M}</b></div>
<button class="theme-btn" id="themeBtn" onclick="toggleTheme()" title="Светлая/тёмная тема">🌙</button>
<a class="chip" href="index.html">← Первая полоса</a>
</div></div></header>
{nav_html}
<div class="page">

<div class="af-chips">
<button class="af-chip on" onclick="afFilter('all',this)">Все ({total_n})</button>
<button class="af-chip" onclick="afFilter('today',this)">Сегодня</button>
<button class="af-chip" onclick="afFilter('tomorrow',this)">Завтра</button>
<button class="af-chip" onclick="afFilter('weekend',this)">Выходные {sat:%d.%m}–{sat + timedelta(days=1):%d.%m}</button>
<button class="af-chip" onclick="afFilter('week',this)">7 дней</button>
</div>

<div class="af-daybar">{''.join(daybar)}</div>

{''.join(sections) or '<div class="card"><div class="af-empty">Событий не найдено — запустите сбор конвейером.</div></div>'}

<div class="sec-head"><h2>Анонсы культурных каналов</h2><div class="line"></div>
<div class="badge">Telegram, последние посты</div></div>
<div class="grid2">{''.join(chan_html)}</div>

<div class="note" style="margin-top:16px;">Афиша собирается автоматически (analytics.py → extract_calendar) из текстов всех
мониторируемых источников: даты, время, площадки. Типы событий определяются по ключевым словам; районные мероприятия
помечены бейджем. Культурных событий в выборке: {n_culture}. <b>Перед визитом сверяйте время и билеты у организаторов</b> —
данные извлечены из публикаций автоматически и могут содержать неточности.</div>

</div>
<footer class="footer"><div class="footer-inner">
<div><b>{cfg['brand']} · Афиша</b><p>Автономная страница, обновляется каждым прогоном run.sh. Источники: Telegram-каналы (@culturnik, @ulpromo, @ProNovosty73 и др.) и RSS СМИ региона.</p></div>
<div><b>Навигация</b><p><a href="index.html" class="flink">Первая полоса</a> · <a href="digests/digest_{today.isoformat()}.html" class="flink">Свежий дайджест</a> · <a href="status.html" class="flink">Статус системы</a></p></div>
</div></footer>
{AFISHA_JS}
</body></html>"""


def fetch_weather():
    """Погода Ульяновска: wttr.in (j1), кэш 3 ч в data/weather.json, при отказе — кэш/None."""
    cache_path = os.path.join(DATA, "weather.json")
    cache = load_json(cache_path, {})
    ts = cache.get("ts")
    now_ts = datetime.now(timezone.utc).timestamp()
    if ts and now_ts - ts < 3 * 3600 and cache.get("text"):
        return cache.get("text")
    try:
        import urllib.request
        req = urllib.request.Request("https://wttr.in/Ulyanovsk?format=j1",
                                     headers={"User-Agent": "curl/8.0 gudok-weather"})
        with urllib.request.urlopen(req, timeout=7) as r:
            d = json.load(r)
        cur = d["current_condition"][0]
        today = d["weather"][0]
        text = f"сейчас {cur['temp_C']}° (ощущается {cur['FeelsLikeC']}°), днём до {today['maxtempC']}°"
        cache = {"ts": now_ts, "text": text}
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False)
        return text
    except Exception:  # noqa: BLE001
        return cache.get("text")


MONTHS_RU = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля",
             "августа", "сентября", "октября", "ноября", "декабря"]
DAYS_RU = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]


def ru_date(dt):
    return f"{DAYS_RU[dt.weekday()]}, {dt.day} {MONTHS_RU[dt.month - 1]} {dt.year}"


# ------------------------------------------------------------------ infospace
def render_infospace(cfg, trends, store, status, info):
    """«Инфопространство» — сквозное исследование информационного поля региона."""
    now = datetime.now(UTC4)
    if not info:
        info = {}
    week = info.get("week_items", 0)
    prim = info.get("week_primaries", 0)
    dups = info.get("week_dups", 0)
    orig_pct = int(round(prim / week * 100)) if week else 0
    fed_pct = int(round(info.get("federal_share", 0) * 100))

    def bar_rows(pairs, mx=None, color="#2f80ed", fmt=str):
        mx = mx or max((v for _, v in pairs), default=1) or 1
        out = []
        for label, v in pairs:
            w = max(3, int(v / mx * 100))
            out.append(f"""<div class="bar-row" style="display:flex;gap:9px;align-items:center;margin-bottom:6px;font-size:12.4px;">
<div style="width:170px;text-align:right;font-weight:600;color:var(--txt);flex-shrink:0;">{esc(str(label))}</div>
<div style="flex:1;background:#edf2f8;border-radius:6px;height:16px;overflow:hidden;">
<div style="width:{w}%;height:100%;background:{color};border-radius:6px;"></div></div>
<div style="width:44px;font-weight:800;color:var(--navy);">{fmt(v)}</div></div>""")
        return "".join(out)

    setters = info.get("setters", [])
    cascades = info.get("cascades", [])
    tone_tier = info.get("tone_by_tier", {})
    muni = info.get("municipal", {})
    silent = info.get("silent", [])
    low = info.get("low", [])
    concl = info.get("conclusions", [])
    orig_tier = info.get("orig_by_tier", {})

    # каскады
    casc_html = "".join(
        f"""<div class="cal-ev" style="align-items:center;"><div class="cal-badge" style="background:var(--red);"><b>×{c['size']}</b><span>источн.</span></div>
<div class="cal-txt"><a href="{esc(c.get('url') or '#')}" target="_blank" rel="noopener"><b>{esc(c['title'])}</b></a>
<div class="t2">первоисточник: {esc(str(c.get('source','')))} · разошлось: {esc(', '.join(str(x) for x in c.get('also', [])))}</div></div></div>"""
        for c in cascades) or '<div class="t2">Каскадов за неделю не зафиксировано.</div>'

    # тон по уровням
    def tone_chip(k, v):
        color = "#b02a2f" if v < -0.1 else ("#1d7a4d" if v > 0.1 else "var(--muted)")
        pos = max(2, min(98, int((v + 1) * 50)))
        return f"""<div style="margin-bottom:9px;"><div style="display:flex;justify-content:space-between;font-size:12.4px;font-weight:700;color:var(--navy);">
<span>{esc(k)}</span><span style="color:{color};">{v:+.2f}</span></div>
<div class="tone-bar" style="height:12px;margin-top:3px;"><div class="tone-pin" style="left:{pos}%;height:18px;top:-3px;"></div></div></div>"""
    tone_html = "".join(tone_chip(k, v) for k, v in sorted(tone_tier.items()))

    # муниципалитеты
    muni_pairs = list(muni.items())
    muni_html = bar_rows(muni_pairs, color="#1d4066")
    silence_html = ""
    if silent or low:
        chips = "".join(f'<span class="stchip" style="background:#fde7e8;color:#b02a2f;margin:2px;">{esc(m)} · 0</span>' for m in silent)
        chips += "".join(f'<span class="stchip" style="background:#fdf3dd;color:#96690a;margin:2px;">{esc(m)} · 1–2</span>' for m in low)
        silence_html = f'<div style="margin-top:10px;">{chips}</div>'

    # оригинальность по уровням
    orig_rows = "".join(
        f"""<tr><td><b>{esc(k)}</b></td><td>{v['total']}</td><td>{int(v['original']*100)}%</td></tr>"""
        for k, v in orig_tier.items())

    daily = info.get("daily", [])
    spark = sparkline(daily, w=280, h=48, color="#1d4066") if daily else ""

    concl_html = "".join(f"<li>{esc(c)}</li>" for c in concl)
    m = info.get("metrics") or {}
    planned_metrics = "; ".join(esc(x) for x in cfg.get("infospace_planned_metrics", [])) or "—"
    np = info.get("natproj") or {}
    np_max = max((n for _, n in np.get("by_project", [])), default=1) or 1
    ma = info.get("muni_agenda") or []
    ms = info.get("muni_summary") or {}
    own_share = ms.get("own_share", 0)
    muni_src_list = ", ".join("@" + x for x in ms.get("muni_sources", [])) or "—"
    muni_src_n = len(ms.get("muni_sources", []))
    muni_src_names = "Димитровград (2 канала), Барышский район" if muni_src_n else "—"
    def _own_cell(r):
        return "✅ " + str(r["own"]) if r["own"] else '<span style="color:#b02a2f;font-weight:700;">нет</span>'

    ma_rows = "".join(
        f'<tr><td><b>{esc(r["name"])}</b></td><td>{r["mentions"]}</td><td>{r["subject"]}</td>'
        f'<td>{r["tone"] if r["tone"] is not None else "—"}</td><td>{r["sources"]}</td>'
        f'<td>{_own_cell(r)}</td></tr>'
        for r in ma) or '<tr><td colspan="6">За неделю упоминаний муниципалитетов нет.</td></tr>'
    np_rows = "".join(
        f'<div class="bar-row" style="display:flex;gap:9px;align-items:center;margin-bottom:6px;font-size:12.4px;">'
        f'<div style="width:210px;text-align:right;font-weight:600;flex-shrink:0;">{esc(name)}</div>'
        f'<div style="flex:1;background:#edf2f8;border-radius:6px;height:16px;overflow:hidden;">'
        f'<div style="width:{max(4, int(cnt / np_max * 100))}%;height:100%;background:linear-gradient(90deg,#96690a,#d9b23a);border-radius:6px;"></div></div>'
        f'<div style="width:30px;font-weight:800;color:var(--navy);">{cnt}</div></div>'
        for name, cnt in np.get("by_project", [])) or '<div class="now-line">За неделю нацпроекты в повестке не упоминались.</div>' 

    wow = info.get("wow") or {}
    w_this, w_prev = wow.get("this", 0), wow.get("prev", 0)
    mx = max(w_this, w_prev, 1)
    d_txt = f"{wow.get('delta'):+d}%" if wow.get("delta") is not None else "нет данных о прошлой неделе"
    wow_bars = f"""<div class="bar-row" style="display:flex;gap:9px;align-items:center;margin-bottom:6px;font-size:12.4px;">
<div style="width:110px;text-align:right;font-weight:600;">эта неделя</div>
<div style="flex:1;background:#edf2f8;border-radius:6px;height:18px;overflow:hidden;"><div style="width:{int(w_this/mx*100)}%;height:100%;background:#2f80ed;border-radius:6px;"></div></div>
<div style="width:60px;font-weight:800;color:var(--navy);">{w_this}</div></div>
<div class="bar-row" style="display:flex;gap:9px;align-items:center;margin-bottom:6px;font-size:12.4px;">
<div style="width:110px;text-align:right;font-weight:600;">прошлая</div>
<div style="flex:1;background:#edf2f8;border-radius:6px;height:18px;overflow:hidden;"><div style="width:{int(w_prev/mx*100)}%;height:100%;background:#8fa9c4;border-radius:6px;"></div></div>
<div style="width:60px;font-weight:800;color:var(--navy);">{w_prev}</div></div>
<div class="note" style="margin-top:6px;">{'Прошлая неделя неполная (история наблюдений с 03.09) — процентное изменение пока непоказательно; сравнение набирает силу с каждой неделей.' if w_prev < 100 else f'Изменение: <b>{d_txt}</b>.'}</div>"""

    wow_topics = ""
    for t in info.get("topic_wow", [])[:6]:
        dl = t.get("delta")
        arrow = f'<span style="color:{"#b02a2f" if (dl or 0) > 0 else "#1d7a4d"};font-weight:800;">{dl:+d}%</span>' if dl is not None else '<span style="color:var(--muted);">новая</span>'
        wow_topics += f"""<div class="bar-row" style="display:flex;gap:9px;align-items:center;margin-bottom:5px;font-size:12.2px;">
<div style="width:150px;text-align:right;font-weight:600;color:var(--txt);flex-shrink:0;">{esc(t['name'])}</div>
<div style="flex:1;background:#edf2f8;border-radius:6px;height:14px;overflow:hidden;"><div style="width:{max(3,int(t['this']/max(1,max(x['this'] for x in info.get('topic_wow',[]) or [{'this':1}]))*100))}%;height:100%;background:#1d4066;border-radius:6px;"></div></div>
<div style="width:86px;font-size:11.5px;color:var(--muted);">{t['prev']} → <b style="color:var(--navy);">{t['this']}</b> {arrow}</div></div>"""

    ts = info.get("tone_series") or []
    tone_spark = sparkline([ (t.get("score") or 0) for t in ts ], w=300, h=56, color="#9a4d8f") if ts else ""
    tone_days = "".join(f"<span style='font-size:10px;color:var(--muted);'>{t['date'][8:10]}</span> " for t in ts[-7:])

    return f"""<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Инфопространство — сквозное исследование · {cfg['brand']}</title>
<link rel="icon" type="image/png" href="assets/logo_gudok.png"><style>{CSS}</style></head><body>
<header class="topbar"><div class="topbar-inner">
<div class="brand"><div>
<div class="brand-title">ИЗДАНИЕ <span>ГУДОК</span> · 🔬 ИНФОПРОСТРАНСТВО</div>
<div class="brand-sub">Информационно-аналитическое издание · сквозное исследование информационного поля Ульяновской области</div>
</div></div>
<div class="top-meta">
<div class="chip">период: <b>7 дней</b></div>
<div class="chip">обновлено <b>{esc(info.get('generated_local', now.strftime('%d.%m %H:%M')))}</b></div>
<button class="theme-btn" id="themeBtn" onclick="toggleTheme()" title="Светлая/тёмная тема">🌙</button>
</div></div></header>
{render_nav(cfg, "infospace", "")}

<div class="page">

<div class="kpi-grid" style="grid-template-columns:repeat(5,1fr);margin-bottom:6px;">
<div class="kpi"><div class="num">{week}</div><div class="lbl">сообщений за 7 дней</div></div>
<div class="kpi green"><div class="num">{orig_pct}%</div><div class="lbl">оригинальных (не перепечаток)</div></div>
<div class="kpi violet"><div class="num">{len(cascades) and cascades[0]['size'] or 0}<small> макс.</small></div><div class="lbl">крупнейший каскад недели</div></div>
<div class="kpi gold"><div class="num">{fed_pct}%</div><div class="lbl">федеральное эхо (не про регион)</div></div>
<div class="kpi red"><div class="num">{len(silent)}<small> + {len(low)}</small></div><div class="lbl">молчащих и полунемых муниципалитетов</div></div>
</div>
<div class="note" style="margin-bottom:18px;">Раздел обновляется каждым прогоном конвейера — это не разовый отчёт, а непрерывное наблюдение за устройством регионального инфополя: кто производит новости, кто их тиражирует, какие сюжеты побеждают, кого не слышно. Данные — {esc(str(info.get('generated_local','')))}, база: {len(store)} записей.</div>

<div class="sec-head"><h2>Кто задаёт повестку</h2><div class="line"></div>
<div class="badge">первичность в каскадах перепечаток</div></div>
<div class="grid2">
<div class="card"><div class="card-pad">
{bar_rows(setters, color="#2f80ed")}
<div class="note">Считаются материалы, ставшие первичными в кластерах из 2+ источников (дедупликация). «ulpressa» — Telegram-канал, «Улпресса» — RSS той же редакции.</div></div></div>
<div class="card"><div class="card-pad">
<div style="font-size:12.5px;font-weight:800;color:var(--navy);margin-bottom:8px;">Объём повестки по дням</div>
{spark}
<div style="font-size:12.5px;font-weight:800;color:var(--navy);margin:12px 0 8px;">Оригинальность по уровням</div>
<table class="tbl"><tr><th>Уровень</th><th>Сообщений</th><th>Оригинальных</th></tr>{orig_rows}</table>
<div class="note">T1 — официальные каналы и зарегистрированные СМИ, T2 — агрегаторы, T3 — авторские/анонимные.</div></div></div>
</div>

<div class="sec-head"><h2>Каскады недели</h2><div class="line"></div>
<div class="badge">как сюжеты расходятся по каналам</div></div>
<div class="card"><div class="card-pad">{casc_html}
<div class="note">Каскад — одно событие, разошедшееся перепечатками по нескольким источникам. Ширина каскада = резонанс сюжета в инфополе.</div></div></div>

<div class="sec-head"><h2>Тон информационного пространства</h2><div class="line"></div>
<div class="badge">лексиконная оценка −1…+1</div></div>
<div class="grid2">
<div class="card"><div class="card-pad">{tone_html or '<i>Нет данных</i>'}
<div class="note">Средняя тональность оригинальных сообщений за 7 дней по уровням источников. Оценка лексиконная, приблизительная.</div></div></div>
<div class="card"><div class="card-pad">
<div style="font-size:12.5px;font-weight:800;color:var(--navy);margin-bottom:8px;">Федеральное эхо vs своя повестка</div>
<div class="bar-wrap" style="height:26px;display:flex;border-radius:8px;overflow:hidden;">
<div style="width:{100-fed_pct}%;background:linear-gradient(90deg,#218a58,#3ec27f);color:#fff;font-size:11.5px;font-weight:800;display:flex;align-items:center;justify-content:center;">регион {100-fed_pct}%</div>
<div style="width:{fed_pct}%;background:linear-gradient(90deg,#8a99aa,#b7c4d1);color:#fff;font-size:11.5px;font-weight:800;display:flex;align-items:center;justify-content:center;">федералы {fed_pct}%</div>
</div>
<div class="note">{fed_pct}% оригинальных сообщений недели — федеральные сюжеты (5G, ключевая ставка, Госдума, СВО-сводки и т.п.) без прямой региональной привязки. Для областной повестки это заметная доля «эха» — местное инфополе почти наполовину формируется извне.</div></div></div>
</div>

<div class="sec-head"><h2>Карта муниципалитетов: кого слышно</h2><div class="line"></div>
<div class="badge">по упоминаниям за 7 дней</div></div>
<div class="card"><div class="card-pad">{muni_html}{silence_html}
<div class="note">Ульяновск не участвует в подсчёте (он заведомо доминирует). Красным — муниципалитеты, полностью выпавшие из инфополя за неделю; жёлтым — 1–2 упоминания. Это измеримый признак информационного неравенства территорий: жизнь районов существует для областного читателя только через происшествия или визиты чиновников.</div></div></div>

<div class="sec-head"><h2>Отслеживаемые метрики</h2><div class="line"></div>
<div class="badge">реестр метрик расширяется</div></div>
<div class="card"><div class="card-pad">
<div class="kpi-grid" style="grid-template-columns:repeat(6,1fr);margin-bottom:12px;">
<div class="kpi green"><div class="num">{m.get('original_share', 0)}<small>%</small></div><div class="lbl">оригинального контента (не перепечатки)</div></div>
<div class="kpi"><div class="num">{m.get('concentration_top3', 0)}<small>%</small></div><div class="lbl">концентрация: доля топ-3 источников</div></div>
<div class="kpi violet"><div class="num">{m.get('avg_cascade', 0)}</div><div class="lbl">средняя глубина каскада</div></div>
<div class="kpi gold"><div class="num">{m.get('muni_coverage', 0)}<small>%</small></div><div class="lbl">покрытие муниципалитетов за неделю</div></div>
<div class="kpi red"><div class="num">{m.get('alert_share', 0)}<small>%</small></div><div class="lbl">доля оперативных/тревожных сообщений</div></div>
<div class="kpi"><div class="num">{m.get('tone_volatility', 0)}</div><div class="lbl">волатильность тона (std по дням)</div></div>
</div>
<div class="note"><b>Методики.</b> Оригинальность — дедупликация перепечаток (Жаккар + вложенность заголовков).
Концентрация — доля трёх крупнейших источников в недельном объёме: рост означает зависимость повестки от узкой группы редакций.
Глубина каскада — среднее число источников, подхвативших один сюжет. Покрытие муниципалитетов — доля территорий с хотя бы одним упоминанием.
Волатильность тона — разброс дневных значений: всплески соответствуют тревогам или праздникам.<br>
<b>В очереди на подключение:</b> {planned_metrics}</div>
</div></div>

<div class="sec-head"><h2>Нацпроекты и госпрограммы в повестке</h2><div class="line"></div>
<div class="badge">метрика подключена 12.09</div></div>
<div class="card"><div class="card-pad">
<div style="display:flex;gap:26px;flex-wrap:wrap;align-items:baseline;margin-bottom:10px;">
<div><span style="font-size:22px;font-weight:900;color:var(--navy);">{np.get('total', 0)}</span> <span style="font-size:12px;color:var(--muted);">упоминаний за неделю</span></div>
<div><span style="font-size:15px;font-weight:800;color:var(--blue);">{np.get('share', 0)}%</span> <span style="font-size:12px;color:var(--muted);">объёма повестки</span></div>
<div><span style="font-size:15px;font-weight:800;color:{'#1d7a4d' if (np.get('tone') or 0) > 0 else '#b02a2f'};">{np.get('tone') if np.get('tone') is not None else '—'}</span> <span style="font-size:12px;color:var(--muted);">тон упоминаний</span></div>
</div>
{np_rows}
<div class="note"><b>Методика.</b> Считаются сообщения, где явно назван нацпроект или «национальный проект»; принадлежность
к конкретному проекту — по ключевым словам в окружении упоминания. Одно сообщение может относиться к нескольким проектам.
Метрика показывает, какие госпрограммы реально присутствуют в публичной повестке региона, а какие идут без публичного следа.</div>
</div></div>

<div class="sec-head"><h2>Муниципальная повестка: свой и областной голос</h2><div class="line"></div>
<div class="badge">метрика подключена 12.09</div></div>
<div class="card"><div class="card-pad" style="padding:10px 14px;">
<table class="tbl"><tr><th>Территория</th><th>Упоминаний</th><th>Из них сюжетом</th><th>Тон</th><th>Источников</th><th>Свой голос</th></tr>
{ma_rows}</table>
<div class="note"><b>Методика.</b> «Сюжетом» — упоминание в заголовке (территория является предметом новости), иначе — фоном в тексте.
«Свой голос» — упоминания из муниципальных источников мониторинга ({muni_src_list}); сейчас их {muni_src_n}:
{muni_src_names}. Доля своего голоса в предметных упоминаниях — <b>{own_share}%</b>.
Территории без своего голоса говорят об области только устами областных редакций — это структурный перекос повестки,
а не случайность недели. Кандидаты на подключение: районные газеты и паблики (ищем вручную, tgstat закрыт для ботов).</div>
</div></div>

<div class="sec-head"><h2>Динамика: неделя к неделе</h2><div class="line"></div>
<div class="badge">объём, темы, тон</div></div>
<div class="grid2">
<div class="card"><div class="card-pad">
<div style="font-size:12.5px;font-weight:800;color:var(--navy);margin-bottom:8px;">Объём инфопотока</div>
{wow_bars}
<div style="font-size:12.5px;font-weight:800;color:var(--navy);margin:14px 0 8px;">Темы: эта неделя vs прошлая</div>
{wow_topics}
</div></div>
<div class="card"><div class="card-pad">
<div style="font-size:12.5px;font-weight:800;color:var(--navy);margin-bottom:8px;">Тон повестки по дням (14 дней)</div>
{tone_spark}
<div class="note">Средняя лексиконная тональность оригинальных сообщений за день. Провалы — дни тревог и происшествий, пики — праздники и хорошие новости. По мере накопления истории сравнение недель станет полнее.</div>
</div></div>
</div>

<div class="sec-head"><h2>Выводы наблюдения</h2><div class="line"></div>
<div class="badge">автоматические</div></div>
<div class="card"><div class="card-pad"><div class="verdict"><b>Сводка недели</b>
<ul style="padding-left:20px;margin-top:4px;line-height:1.7;font-size:13px;">{concl_html}</ul></div>
<div class="note">Выводы формируются правилами analytics.py; по мере накопления истории добавятся сравнения неделя-к-неделе и сезонность.</div></div></div>

</div>
<footer class="footer"><div class="footer-inner">
<div><b>Гудок</b><p>{esc(cfg['tagline_full'])}</p></div>
<div><b>Методика</b><p>Дедупликация (Жаккар + вложенность заголовков), TF-IDF-кластеризация, лексикон тональности (±110 маркеров), географические маркеры муниципалитетов. Всё — на открытых данных мониторинга; воспроизводится из data/store.jsonl.</p></div>
<div><b>Навигация</b><p><a href="index.html" class="flink">Первая полоса</a> · <a href="weekly.html" class="flink">Аналитика недели</a> · <a href="roadmap.html" class="flink">Роадмап</a></p></div>
</div></footer>
</body></html>"""


# ------------------------------------------------------------------ print edition
def render_print(cfg, trends, store, status, an, isp, date_str, digest_no, dtest):
    """Печатная полоса A4: газета для PDF/бумаги."""
    now = datetime.now(UTC4)
    day = datetime.strptime(date_str, "%Y-%m-%d").date()
    cats = {c["id"]: c for c in cfg["categories"]}

    win_start = datetime.combine(day, datetime.min.time(), tzinfo=UTC4) - timedelta(hours=30)
    window = [it for it in store if not it.get("dup_of")
              and local_dt(it.get("published")) and local_dt(it["published"]) >= win_start]
    if len(window) < 6:
        win_start -= timedelta(days=2)
        window = [it for it in store if not it.get("dup_of")
                  and local_dt(it.get("published")) and local_dt(it["published"]) >= win_start]
    pool = [it for it in window if is_regional(it) and it.get("category") != "security"] or window
    leads = hero_pick(pool, trends, now, 3)

    ed_path = os.path.join(DATA, f"editorial_{date_str}.md")
    editorial = ""
    if os.path.exists(ed_path):
        editorial = open(ed_path, encoding="utf-8").read().strip()
        editorial = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", esc(editorial))
        editorial = "".join(f"<p>{b.strip().replace(chr(10), ' ')}</p>"
                            for b in editorial.split("\n\n") if b.strip() and not b.strip().startswith("- "))

    lead = leads[0] if leads else None
    lead_body = esc((lead.get("text") or "")[:1500]) if lead else ""
    side_html = ""
    for m in leads[1:4]:
        dt = local_dt(m.get("published"))
        side_html += f"""<div class="pm-item"><b>{esc(m['title'][:120])}</b>
<span>{esc((m.get('text') or '')[:220])}</span>
<i>{cats.get(m.get('category'), {}).get('name', '')} · {dt.strftime('%d.%m %H:%M') if dt else ''} · {esc(m.get('source', ''))}</i></div>"""

    by_cat = {}
    lead_ids = {m["id"] for m in leads}
    for it in window:
        if it["id"] in lead_ids:
            continue
        by_cat.setdefault(it.get("category", "society"), []).append(it)
    rubrics = ""
    for c in cfg["categories"]:
        items = by_cat.get(c["id"], [])
        if not items:
            continue
        rows = "".join(
            f"""<div class="pm-item"><b>{esc(it['title'][:110])}</b>
<span>{esc((it.get('text') or '')[:160])}</span>
<i>{(local_dt(it.get('published')) or now):%H:%M} · {esc(it.get('source', ''))}</i></div>"""
            for it in items[:4])
        rubrics += f'<div class="pm-h3">{c["icon"]} {esc(c["name"])}</div>{rows}'

    tomorrow = day + timedelta(days=1)
    af = [e for e in (an.get("calendar") or []) if e.get("date") in (day.isoformat(), tomorrow.isoformat())][:8]
    af_html = "".join(
        f'<li><b>{e["date"][8:10]}.{e["date"][5:7]} {esc(e.get("time") or "—")}</b> — {esc(e["title"][:95])}</li>'
        for e in af) or "<li>Событий на эти дни в афише нет.</li>"

    topics = (trends or {}).get("topics", {})
    top_topic = max(topics.items(), key=lambda kv: (kv[1]["today"], kv[1]["week"]), default=None)
    sent = (an.get("sentiment") or {})
    tone = sent.get("today_score") or 0
    vote_day = datetime(2026, 9, 18, tzinfo=UTC4).date()
    d_vote = max(0, (vote_day - day).days)
    n24 = (trends or {}).get("counts", {}).get("last24h", 0)
    casc = (isp.get("cascades") or [{}])[0]
    silent = isp.get("silent") or []

    test_mark = " · ТЕСТОВЫЙ НОМЕР" if dtest else ""
    return f"""<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Гудок № {digest_no} от {day:%d.%m.%Y} — печатная полоса</title>
<link rel="icon" type="image/png" href="../assets/logo_gudok.png">
<style>{PRINT_CSS}</style></head>
<body class="print-mode">
<div class="pm-toolbar">
<a href="digest_{date_str}.html">← Электронный выпуск</a>
<button onclick="window.print()">🖨 Печать / PDF</button>
</div>

<div class="sheet">
<div class="pm-mast">
<div class="pm-title">ГУДОК</div>
<div class="pm-line">информационно-аналитическое издание · выпуск № <b>{digest_no}</b>{test_mark} · {ru_date(day)} · Ульяновск</div>
<div class="pm-line">марксистская группа «Победа» · для внутреннего распространения · выходит с 11.09.2026</div>
</div>

<div class="pm-kicker">⟡ Сюжет дня</div>
<div class="pm-lead-h">{esc(lead['title']) if lead else '—'}</div>
<div class="pm-deck">{esc((lead.get('text') or '')[:260]) if lead else ''}</div>

<div class="pm-stats">
<div class="pm-stat"><b>{n24}</b><span>публикаций за сутки</span></div>
<div class="pm-stat"><b>{top_topic[1]['today'] if top_topic else 0}</b><span>тема дня: {esc(top_topic[1]['name']) if top_topic else '—'}</span></div>
<div class="pm-stat"><b>{tone:+.2f}</b><span>тон повестки</span></div>
<div class="pm-stat"><b>{d_vote}</b><span>дн. до голосования</span></div>
<div class="pm-stat"><b>{casc.get('size', 0)}</b><span>каскад недели, источников</span></div>
</div>

<div class="cols">
<p>{lead_body}</p>
{side_html}
{rubrics}
</div>

<div class="pm-box"><h4>Афиша: сегодня и завтра</h4><ul>{af_html}</ul></div>

{'<div class="pm-box"><h4>Колонка редактора</h4><div class="pm-ed">' + editorial + '</div></div>' if editorial else ''}

<div class="pm-colophon">
<div>Набрано и выпущено автоматически: мониторинг {sum(1 for c in cfg.get('telegram_channels', []) if c.get('enabled'))} Telegram-каналов и {sum(1 for c in cfg.get('rss_sources', []) if c.get('enabled', True))} RSS-лент; колонку редактора готовит ассистент.</div>
<div>Материалы принадлежат их изданиям. Листок не является агитацией.{" Зоны инфотишины: " + ", ".join(silent[:4]) + "." if silent else ""}</div>
</div>
<div class="pm-page">стр. 1</div>
</div>
</body></html>"""


def week_num(cfg, monday):
    """Сквозной номер ISO-недели от недели запуска (launch_week_monday)."""
    try:
        base = datetime.strptime(cfg.get("launch_week_monday", "2026-09-07"), "%Y-%m-%d").date()
    except ValueError:
        base = monday
    return max(0, (monday - base).days // 7 + 1)


def period_nav(links):
    """Полоска «пред | текущий | след» для периодических страниц."""
    prev_l, cur, next_l = links
    p = f'<a href="{prev_l[1]}">← {esc(prev_l[0])}</a>' if prev_l else '<span style="color:var(--muted);">← начало</span>'
    n = f'<a href="{next_l[1]}">{esc(next_l[0])} →</a>' if next_l else '<span style="color:var(--muted);">далее выйдет</span>'
    return (f'<div style="display:flex;justify-content:space-between;gap:12px;font-size:12.5px;font-weight:700;'
            f'margin:10px 0 0;">{p}<b style="color:var(--navy);">{esc(cur)}</b>{n}</div>')


def week_arcs(store, start, end, trends=None):
    """Сюжетные дуги недели: кластеры-каскады и крупные одиночные сюжеты."""
    from analytics import sentiment_of

    def pdate(it):
        dt = local_dt(it.get("published"))
        return dt.date() if dt else None

    prim = [it for it in store if not it.get("dup_of") and pdate(it) and start <= pdate(it) <= end]
    by_id = {it["id"]: it for it in prim}
    members = {}
    for it in store:
        if it.get("dup_of") and it["dup_of"] in by_id and pdate(it):
            members.setdefault(it["dup_of"], []).append(it)
    arcs = []
    for it in prim:
        mem = members.get(it["id"], [])
        size = len(mem) + 1
        views = it.get("views") or 0
        if size < 2 and views < 3000:
            continue
        days = sorted([pdate(it)] + [pdate(m) for m in mem])
        cnt = {}
        for d in days:
            cnt[d] = cnt.get(d, 0) + 1
        peak = max(cnt, key=lambda d: cnt[d])
        srcs = {it.get("channel") or it.get("source")} | {m.get("channel") or m.get("source") for m in mem}
        t_first = sentiment_of(f"{it.get('title','')} {(it.get('text') or '')[:200]}")[0]
        last_m = sorted(mem, key=lambda m: pdate(m))[-1] if mem else it
        t_last = sentiment_of(f"{last_m.get('title','')} {(last_m.get('text') or '')[:200]}")[0]
        status = "затух" if days[-1] < end - timedelta(days=1) else ("в развитии" if days[-1] >= end else "пик пройден")
        arcs.append({
            "title": it["title"], "url": it.get("url") or "", "src": it.get("channel") or it.get("source"),
            "first": days[0], "peak": peak, "last": days[-1], "size": size, "views": views,
            "srcs": srcs, "t1": t_first, "t2": t_last, "status": status, "days": sorted(set(days)),
        })
    arcs.sort(key=lambda a: (-a["size"], -a["views"]))
    return arcs[:7]


# ------------------------------------------------------------------ weekly
def fetch_cbr():
    return load_json(os.path.join(DATA, "cbr_rates.json")) or {}


def render_weekly_rail(cfg, an, store, start, end):
    """Правая колонка 1/3 недельника: погода, курсы ЦБ, события региона, промышленность и бизнес."""
    from analytics import extract_calendar
    now = datetime.now(UTC4)
    cbr = fetch_cbr()
    rates = cbr.get("rates", {})
    rate_rows = "".join(
        f'<div style="display:flex;justify-content:space-between;font-size:12.6px;padding:3px 0;border-bottom:1px dashed var(--line);">'
        f'<span>{nm}</span><b style="color:var(--navy);">{rates[key]["value"]:,.2f} ₽ / {rates[key]["nominal"]}</b></div>'
        for nm, key in [("Доллар США", "USD"), ("Евро", "EUR"), ("Юань", "CNY")] if key in rates)
    rate_note = f'ЦБ РФ, {esc(cbr.get("date", ""))}' if cbr else "курсы недоступны"

    cal = (an or {}).get("calendar", [])
    in_period = [e for e in cal if start <= e["date"] <= end]
    upcoming = [e for e in cal if e["date"] > end][:5]

    def ev_rows(evs, limit=6):
        return "".join(
            f'<div class="tl-row"><div class="tl-time">{e["date"][8:10]}.{e["date"][5:7]}{(" " + e["time"]) if e.get("time") else ""}</div>'
            f'<div class="tl-txt"><a href="{esc(e.get("url") or "#")}" target="_blank" rel="noopener">{esc(e["title"][:80])}</a></div></div>'
            for e in evs[:limit]) or '<div class="now-line">Нет событий.</div>'

    econ = [it for it in store if not it.get("dup_of") and it.get("category") in ("economy", "agro")
            and local_dt(it.get("published"))]
    econ_events = extract_calendar(econ, now)[:6]
    corp = []
    for chn in ("UAZ_Today", "uac_ru"):
        posts = sorted([it for it in store if it.get("channel") == chn],
                       key=lambda x: x.get("published") or "", reverse=True)[:2]
        corp.extend(posts)
    corp_rows = "".join(
        f'<div class="tl-row"><div class="tl-time">@{(it.get("channel") or "")[:8]}</div>'
        f'<div class="tl-txt"><a href="{esc(it.get("url") or "#")}" target="_blank" rel="noopener">{esc(it["title"][:80])}</a></div></div>'
        for it in corp[:4]) or '<div class="now-line">Корпоративные каналы молчат.</div>'

    return f"""<aside class="wk-rail">
<div class="wk-box"><h4>Погода</h4>
<div style="font-size:13px;font-weight:700;color:var(--navy);">{esc(fetch_weather() or "—")}</div>
<div class="now-line">Прогноз на выходные — в афише и на первой полосе.</div></div>
<div class="wk-box"><h4>Курсы валют</h4>{rate_rows}<div class="now-line">{rate_note}</div></div>
<div class="wk-box"><h4>События региона за период</h4>{ev_rows(in_period)}
<h4 style="margin-top:10px;">Впереди</h4>{ev_rows(upcoming, 5)}</div>
<div class="wk-box"><h4>Промышленность и бизнес: новости → события</h4>{ev_rows(econ_events, 6)}
<h4 style="margin-top:10px;">Корпоративные каналы</h4>{corp_rows}
<div class="now-line">{esc((cfg.get("enterprise_note") or "")[:220])}</div></div>
</aside>"""


def render_weekly_hub(cfg, trends, store, status):
    """Хаб «Аналитика недели»: реестр выпусков, регламент, методика."""
    now = datetime.now(UTC4)
    nav_html = render_nav(cfg, "analytics", "")
    weeks = sorted(glob.glob(os.path.join(BASE, "weekly", "week_*.html")))
    rows = ""
    for w in weeks:
        nm = os.path.basename(w).replace(".html", "")
        parts_nm = nm.split("_")
        num = parts_nm[1]
        start, end = parts_nm[2], parts_nm[3]
        done = end < now.strftime("%Y-%m-%d")
        stamp = '<span class="wk-stamp">завершён</span>' if done else '<span class="wk-stamp wip">готовится</span>'
        rows += f"""<div class="arch-item"><div class="arch-date"><b>№{num}</b><span>{start[5:7]}.{start[8:10]}–{end[8:10]}</span></div>
<div style="flex:1;"><b style="color:var(--navy);font-size:13.5px;">Неделя {start[8:10]}.{start[5:7]}–{end[8:10]}.{end[5:7]}.{end[2:4]}</b><br>
<span style="font-size:11.8px;color:var(--muted);">аналитика повестки периода {stamp}</span></div>
<a class="btn" href="weekly/{nm}.html">Открыть</a></div>"""
    return f"""<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Аналитика недели — {cfg['brand']}</title>
<link rel="icon" type="image/png" href="assets/logo_gudok.png">
<style>{CSS}{INDEX_CSS}</style></head><body>
<header class="topbar"><div class="topbar-inner">
<div class="brand"><div>
<div class="brand-title">ИЗДАНИЕ <span>ГУДОК</span> · АНАЛИТИКА НЕДЕЛИ</div>
<div class="brand-sub">Завершённые недельные страницы: период, паспорт, правая колонка справочных данных</div>
</div></div>
<div class="top-meta">
<div class="chip">выпусков: <b>{len(weeks)}</b></div>
<button class="theme-btn" id="themeBtn" onclick="toggleTheme()" title="Светлая/тёмная тема">🌙</button>
</div></div></header>
{nav_html}
<div class="wrap1200" style="padding-top:20px;">
<div class="wk-passport"><b>Регламент</b>
<span style="font-size:12.5px;color:var(--muted);">Выпуск недели — законченная страница за период понедельник–воскресенье;
публикуется в понедельник и после доводки получает штамп «завершён». Структура: паспорт периода, основная колонка 2/3
(итоги, сюжеты, аналитика), правая колонка 1/3 — всегда: погода, курсы ЦБ, события региона, промышленность и бизнес.</span></div>
<div class="sec-head"><h2>Выпуски</h2><div class="line"></div></div>
<div class="card"><div class="card-pad">{rows or '<span style="color:var(--muted);">Пока нет выпусков.</span>'}</div></div>
<div class="note" style="margin-top:14px;">Нулевой выпуск (04–11.09.2026) — предпусковой: период нерегулярный, дальше недели идут по календарю.
Правая колонка каждого выпуска генерируется функцией render_weekly_rail (python3 generate.py --weekly-rail START END) —
данные всегда свежие на момент доводки выпуска.</div>
</div>
<footer class="footer"><div class="footer-inner">
<div><b>Гудок</b><p>{esc(cfg['tagline_full'])}</p></div>
<div><b>Разделы</b><p><a href="index.html" class="flink">Первая полоса</a> · <a href="infospace.html" class="flink">Инфопространство</a> · <a href="projects.html" class="flink">Проекты</a></p></div>
</div></footer>
</body></html>"""


# ------------------------------------------------------------------ monthly
MONTHS_RU_GEN = ["январь", "февраль", "март", "апрель", "май", "июнь",
                 "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь"]


def render_monthly(cfg, trends, store, status, ym):
    """Месячный отчёт: все метрики и тенденции месяца."""
    from analytics import sentiment_of
    now = datetime.now(UTC4)
    y, mo = map(int, ym.split("-"))
    start = datetime(y, mo, 1, tzinfo=UTC4).date()
    end = (datetime(y + 1, 1, 1, tzinfo=UTC4).date() if mo == 12
           else datetime(y, mo + 1, 1, tzinfo=UTC4).date()) - timedelta(days=1)
    done = end < now.date()
    nav_html = render_nav(cfg, "monthly", "../")

    def pdate(it):
        dt = local_dt(it.get("published"))
        return dt.date() if dt else None

    all_m = [it for it in store if pdate(it) and start <= pdate(it) <= min(end, now.date())]
    prim = [it for it in all_m if not it.get("dup_of")]
    volume = len(all_m)
    orig = round(len(prim) / volume * 100) if volume else 0
    src_c = Counter(it.get("channel") or it.get("source") or "?" for it in all_m)
    top3 = sum(n for _, n in src_c.most_common(3))
    conc = round(top3 / volume * 100) if volume else 0
    casc = sorted([it for it in prim if it.get("cluster") and it["cluster"] >= 2],
                  key=lambda x: -x["cluster"])[:6]
    # тон: по дням и по неделям
    day_tone = {}
    for it in prim:
        d = pdate(it)
        sc = sentiment_of(f"{it.get('title','')} {(it.get('text') or '')[:250]}")[0]
        day_tone.setdefault(d, []).append(sc)
    days_sorted = sorted(day_tone)
    tone_series = [round(sum(day_tone[d]) / len(day_tone[d]), 2) for d in days_sorted]
    tone_avg = round(sum(tone_series) / len(tone_series), 2) if tone_series else 0
    weeks = []
    d = start - timedelta(days=start.weekday())
    while d <= min(end, now.date()):
        w_end = d + timedelta(days=6)
        w_items = [it for it in prim if pdate(it) and d <= pdate(it) <= w_end]
        sc = [sentiment_of(f"{it.get('title','')} {(it.get('text') or '')[:250]}")[0] for it in w_items]
        weeks.append({"start": d, "n": len(w_items),
                      "tone": round(sum(sc) / len(sc), 2) if sc else None})
        d += timedelta(days=7)
    # темы месяца с недельной разбивкой
    topic_c = Counter()
    topic_week = {}
    for it in all_m:
        d = pdate(it)
        wi = next((i for i, w in enumerate(weeks) if w["start"] <= d <= w["start"] + timedelta(days=6)), None)
        for t in it.get("topics", []):
            topic_c[t] += 1
            if wi is not None:
                topic_week.setdefault(t, [0] * len(weeks))[wi] += 1
    tnames = {t["id"]: t["name"] for t in cfg["topics"]}
    top_topics = topic_c.most_common(8)
    # муниципалитеты за месяц
    muni_rows = []
    muni_src = set(cfg.get("municipal_sources") or [])
    for name, pat in (cfg.get("municipalities") or {}).items():
        rx = re.compile(pat, re.I)
        n = own = 0
        for it in all_m:
            if rx.search(it.get("title", "") or ""):
                n += 1
                if (it.get("channel") or it.get("source")) in muni_src:
                    own += 1
            elif rx.search((it.get("text") or "")[:300]):
                n += 1
        if n:
            muni_rows.append((name, n, own))
    muni_rows.sort(key=lambda x: -x[1])
    # хроника месяца: топ по просмотрам
    chron = sorted([it for it in prim if it.get("views")], key=lambda x: -x["views"])[:10]

    topic_rows = ""
    for tid, n in top_topics:
        wk = topic_week.get(tid, [0] * len(weeks))
        mx = max(wk) if max(wk, default=0) else 1
        bars = "".join(
            f'<div style="flex:1;background:#edf2f8;border-radius:4px;height:14px;overflow:hidden;margin:0 1px;">'
            f'<div style="width:{max(4, int(v / mx * 100))}%;height:100%;background:#1d4066;"></div></div>'
            for v in wk)
        topic_rows += (f'<div style="display:flex;gap:10px;align-items:center;margin-bottom:6px;font-size:12.4px;">'
                       f'<div style="width:190px;text-align:right;font-weight:600;flex-shrink:0;">{esc(tnames.get(tid, tid))}</div>'
                       f'<div style="flex:1;display:flex;">{bars}</div>'
                       f'<div style="width:40px;font-weight:800;color:var(--navy);">{n}</div></div>')
    week_bars = "".join(
        f'<div style="display:flex;gap:9px;align-items:center;margin-bottom:6px;font-size:12.4px;">'
        f'<div style="width:150px;text-align:right;font-weight:600;flex-shrink:0;">нед. {w["start"]:%d.%m}</div>'
        f'<div style="flex:1;background:#edf2f8;border-radius:6px;height:16px;overflow:hidden;">'
        f'<div style="width:{max(4, int(w["n"] / max(x["n"] for x in weeks) * 100))}%;height:100%;background:#2f80ed;"></div></div>'
        f'<div style="width:90px;font-size:11.5px;color:var(--muted);">{w["n"]} · тон {w["tone"] if w["tone"] is not None else "—"}</div></div>'
        for w in weeks)
    casc_rows = "".join(
        f'<div class="af-mini"><div class="cal-badge" style="background:var(--red);"><b>×{c["cluster"]}</b><span>ист.</span></div>'
        f'<div style="flex:1;"><a href="{esc(c.get("url") or "#")}" target="_blank" rel="noopener" style="font-size:13px;font-weight:700;color:var(--navy);">{esc(c["title"][:100])}</a>'
        f'<div style="font-size:11.3px;color:var(--muted);">{(pdate(c) or now):%d.%m} · {esc(c.get("source",""))}</div></div></div>'
        for c in casc) or '<div class="now-line">Каскадов за месяц не зафиксировано.</div>'
    def _muni_own(own):
        return "✅ " + str(own) if own else '<span style="color:#b02a2f;font-weight:700;">нет</span>'

    muni_tbl = "".join(
        f'<tr><td><b>{esc(nm)}</b></td><td>{n}</td><td>{_muni_own(own)}</td></tr>'
        for nm, n, own in muni_rows[:14]) or '<tr><td colspan="3">Нет данных.</td></tr>'
    chron_rows = "".join(
        f'<div class="af-mini"><div class="cal-badge"><b>{(pdate(c) or now):%d}</b><span>{(pdate(c) or now):%b}</span></div>'
        f'<div style="flex:1;"><a href="{esc(c.get("url") or "#")}" target="_blank" rel="noopener" style="font-size:13px;font-weight:700;color:var(--navy);">{esc(c["title"][:100])}</a>'
        f'<div style="font-size:11.3px;color:var(--muted);">👁 {fmt_views(c["views"])} · {esc(c.get("source",""))}</div></div></div>'
        for c in chron)
    concl = [
        f"Объём инфопотока за месяц: {volume} сообщений, оригинальных {orig}%.",
        f"Концентрация источников: топ-3 дают {conc}% потока.",
        f"Средний тон месяца: {tone_avg:+.2f}." + (" Повестка эмоционально умеренная." if abs(tone_avg) < 0.2 else ""),
        f"Крупнейший каскад: ×{casc[0]['cluster']} («{casc[0]['title'][:60]}»)." if casc else "Каскадов нет.",
        f"Территорий с упоминаниями: {len(muni_rows)} из {len(cfg.get('municipalities') or {})}; "
        f"свой голос — у {sum(1 for _, _, o in muni_rows if o)}.",
    ]
    stamp = '<span class="wk-stamp">завершён</span>' if done else '<span class="wk-stamp wip">готовится</span>'
    return f"""<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Месячный отчёт {MONTHS_RU_GEN[mo-1]} {y} — {cfg['brand']}</title>
<link rel="icon" type="image/png" href="../assets/logo_gudok.png">
<style>{CSS}{INDEX_CSS}</style></head><body>
<header class="topbar"><div class="topbar-inner">
<div class="brand"><div>
<div class="brand-title">ИЗДАНИЕ <span>ГУДОК</span> · МЕСЯЧНЫЙ ОТЧЁТ</div>
<div class="brand-sub">Все метрики и тенденции месяца: объём, темы, тон, каскады, территории</div>
</div></div>
<div class="top-meta">
<div class="chip">период: <b>{start:%d.%m}–{end:%d.%m}.{end:%y}</b></div>
<button class="theme-btn" id="themeBtn" onclick="toggleTheme()" title="Светлая/тёмная тема">🌙</button>
</div></div></header>
{nav_html}
<div class="wrap1200" style="padding-top:16px;">
<div class="wk-passport"><b>{MONTHS_RU_GEN[mo-1].capitalize()} {y} · месячный отчёт</b>
<span style="font-size:12.5px;color:var(--muted);">данные на {now:%d.%m.%Y} · источников: {len(src_c)} · публикация 1-го числа следующего месяца</span>{stamp}</div>

<div class="sec-head"><h2>Ключевые метрики месяца</h2><div class="line"></div></div>
<div class="kpi-grid" style="grid-template-columns:repeat(6,1fr);">
<div class="kpi"><div class="num">{volume}</div><div class="lbl">сообщений в потоке</div></div>
<div class="kpi green"><div class="num">{orig}<small>%</small></div><div class="lbl">оригинальных</div></div>
<div class="kpi"><div class="num">{conc}<small>%</small></div><div class="lbl">концентрация топ-3</div></div>
<div class="kpi violet"><div class="num">{tone_avg:+.2f}</div><div class="lbl">средний тон</div></div>
<div class="kpi red"><div class="num">{casc[0]['cluster'] if casc else 0}</div><div class="lbl">макс. каскад</div></div>
<div class="kpi gold"><div class="num">{len(muni_rows)}</div><div class="lbl">территорий в повестке</div></div>
</div>

<div class="grid2" style="margin-top:18px;">
<div class="card"><div class="card-pad">
<div style="font-size:12.5px;font-weight:800;color:var(--navy);margin-bottom:8px;">Темы месяца (недельная разбивка)</div>
{topic_rows}
<div class="note">Столбцы — недели месяца слева направо; высота — относительная интенсивность темы.</div>
</div></div>
<div class="card"><div class="card-pad">
<div style="font-size:12.5px;font-weight:800;color:var(--navy);margin-bottom:8px;">Объём и тон по неделям</div>
{week_bars}
<div style="font-size:12.5px;font-weight:800;color:var(--navy);margin:12px 0 8px;">Тон по дням месяца</div>
{sparkline(tone_series, w=320, h=52, color="#9a4d8f")}
</div></div>
</div>

<div class="grid2" style="margin-top:18px;">
<div>
<div class="sec-head"><h2>Каскады месяца</h2><div class="line"></div></div>
<div class="card"><div class="side-body">{casc_rows}</div></div>
<div class="sec-head"><h2>Территории за месяц</h2><div class="line"></div></div>
<div class="card"><div class="card-pad" style="padding:10px 14px;">
<table class="tbl"><tr><th>Муниципалитет</th><th>Упоминаний</th><th>Свой голос</th></tr>{muni_tbl}</table></div></div>
</div>
<div>
<div class="sec-head"><h2>Хроника месяца: топ-10 по охвату</h2><div class="line"></div></div>
<div class="card"><div class="side-body">{chron_rows}</div></div>
<div class="sec-head"><h2>Выводы</h2><div class="line"></div></div>
<div class="card"><div class="card-pad"><div class="verdict"><b>Итоги периода</b>
<ul style="padding-left:20px;line-height:1.7;font-size:13px;">{''.join(f"<li>{esc(c)}</li>" for c in concl)}</ul></div></div></div>
</div>
</div>
</div>
<footer class="footer"><div class="footer-inner">
<div><b>Гудок</b><p>{esc(cfg['tagline_full'])}</p></div>
<div><b>Периодичности</b><p><a href="../weekly.html" class="flink">Неделя</a> · <a href="../monthly.html" class="flink">Месяц</a> · <a href="../index.html" class="flink">Первая полоса</a></p></div>
</div></footer>
</body></html>"""


def render_monthly_hub(cfg, trends, store, status):
    now = datetime.now(UTC4)
    nav_html = render_nav(cfg, "monthly", "")
    months = sorted(glob.glob(os.path.join(BASE, "monthly", "month_*.html")))
    rows = ""
    for mf in months:
        nm = os.path.basename(mf).replace(".html", "")
        y, mo = map(int, nm.replace("month_", "").split("-"))
        end = (datetime(y + 1, 1, 1, tzinfo=UTC4).date() if mo == 12
               else datetime(y, mo + 1, 1, tzinfo=UTC4).date()) - timedelta(days=1)
        done = end < now.date()
        stamp = '<span class="wk-stamp">завершён</span>' if done else '<span class="wk-stamp wip">готовится</span>'
        rows += f"""<div class="arch-item"><div class="arch-date"><b>{mo:02d}</b><span>{y}</span></div>
<div style="flex:1;"><b style="color:var(--navy);font-size:13.5px;">{MONTHS_RU_GEN[mo-1].capitalize()} {y}</b><br>
<span style="font-size:11.8px;color:var(--muted);">метрики и тенденции месяца {stamp}</span></div>
<a class="btn" href="monthly/{nm}.html">Открыть</a></div>"""
    return f"""<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Месячные отчёты — {cfg['brand']}</title>
<link rel="icon" type="image/png" href="assets/logo_gudok.png">
<style>{CSS}{INDEX_CSS}</style></head><body>
<header class="topbar"><div class="topbar-inner">
<div class="brand"><div>
<div class="brand-title">ИЗДАНИЕ <span>ГУДОК</span> · МЕСЯЦ</div>
<div class="brand-sub">Месячные отчёты: все метрики и тенденции периода</div>
</div></div>
<div class="top-meta"><div class="chip">отчётов: <b>{len(months)}</b></div>
<button class="theme-btn" id="themeBtn" onclick="toggleTheme()" title="Светлая/тёмная тема">🌙</button></div>
</div></header>
{nav_html}
<div class="wrap1200" style="padding-top:20px;">
<div class="wk-passport"><b>Регламент</b>
<span style="font-size:12.5px;color:var(--muted);">Месячный отчёт публикуется 1-го числа следующим месяцем и получает штамп «завершён».
Содержит все метрики инфопространства за период: объём и оригинальность, концентрацию источников, темы с недельной
разбивкой, тон по неделям и дням, каскады, карту территорий с «своим голосом», хронику топ-10 по охвату и авто-выводы.</span></div>
<div class="sec-head"><h2>Отчёты</h2><div class="line"></div></div>
<div class="card"><div class="card-pad">{rows or '<span style="color:var(--muted);">Пока нет отчётов.</span>'}</div></div>
</div>
<footer class="footer"><div class="footer-inner">
<div><b>Гудок</b><p>{esc(cfg['tagline_full'])}</p></div>
<div><b>Периодичности</b><p><a href="index.html" class="flink">Первая полоса</a> · <a href="weekly.html" class="flink">Неделя</a> · <a href="infospace.html" class="flink">Инфопространство</a></p></div>
</div></footer>
</body></html>"""


def render_weekly_full(cfg, trends, store, status, start, end, rail=None):
    """Недельник = сюжетные дуги недели (без повтора ленты) + правая колонка справок."""
    now = datetime.now(UTC4)
    monday = start
    num = week_num(cfg, monday)
    done = end < now.date()
    nav_html = render_nav(cfg, "weekly", "../")
    arcs = week_arcs(store, start, end, trends)
    if rail is None:
        rail = render_weekly_rail(cfg, trends, store, start.isoformat(), end.isoformat())

    def pdate(it):
        dt = local_dt(it.get("published"))
        return dt.date() if dt else None

    wk_all = [it for it in store if pdate(it) and start <= pdate(it) <= end]
    volume = len(wk_all)
    arc_html = ""
    for i, a in enumerate(arcs, 1):
        day_links = " ".join(
            f'<a href="../digests/digest_{d.isoformat()}.html" style="font-weight:700;">{d:%d.%m}</a>'
            for d in a["days"] if os.path.exists(os.path.join(DIGESTS, f"digest_{d.isoformat()}.html")))
        arc_html += f"""<div class="card" style="margin-bottom:12px;"><div class="card-pad">
<div style="display:flex;gap:10px;align-items:baseline;flex-wrap:wrap;">
<span style="font-size:15px;font-weight:900;color:var(--gold);">{i:02d}</span>
<b style="font-size:14.5px;color:var(--navy);flex:1;">{esc(a['title'][:110])}</b>
<span class="wk-stamp{' wip' if a['status'] != 'затух' else ''}">{a['status']}</span></div>
<p style="font-size:13px;color:var(--muted);line-height:1.55;margin:7px 0;">
Возник {a['first']:%d.%m} ({esc(str(a['src']))}), пик {a['peak']:%d.%m} — сюжет держали {a['size']} источника одновременно,
всего источников дуги: {len(a['srcs'])}. Тон дуги: {a['t1']:+.2f} → {a['t2']:+.2f}.
К {a['last']:%d.%m} — {a['status']}.</p>
<div style="font-size:11.8px;color:var(--muted);">Освещение по дням: {day_links or '—'} · охват 👁 {fmt_views(a['views'])}</div>
</div></div>"""
    stamp = '<span class="wk-stamp">завершён</span>' if done else '<span class="wk-stamp wip">готовится</span>'
    # prev/next недели
    weeks = sorted(glob.glob(os.path.join(BASE, "weekly", "week_*.html")))
    cur_name = f"week_{num:02d}_{start.isoformat()}_{end.isoformat()}"
    idx = next((i for i, w in enumerate(weeks) if cur_name in w), None)
    prev_l = next_l = None
    if idx is not None and idx > 0:
        pn = os.path.basename(weeks[idx - 1]).replace(".html", "").split("_")
        prev_l = (f"нед. {pn[1]} ({pn[2][8:10]}.{pn[2][5:7]})", f"../weekly/{weeks[idx - 1].split(os.sep)[-1]}")
    if idx is not None and idx + 1 < len(weeks):
        nn = os.path.basename(weeks[idx + 1]).replace(".html", "").split("_")
        next_l = (f"нед. {nn[1]} ({nn[2][8:10]}.{nn[2][5:7]})", f"../weekly/{weeks[idx + 1].split(os.sep)[-1]}")
    pnav = period_nav((prev_l, f"неделя № {num} · {start:%d.%m}–{end:%d.%m}", next_l))

    return f"""<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Неделя № {num} · {start:%d.%m}–{end:%d.%m} — {cfg['brand']}</title>
<link rel="icon" type="image/png" href="../assets/logo_gudok.png">
<style>{CSS}{INDEX_CSS}
.wk-grid{{display:grid;grid-template-columns:2fr 1fr;gap:18px;align-items:start;margin-top:14px;}}
.wk-rail{{display:flex;flex-direction:column;gap:12px;}}
.wk-box{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 14px;}}
.wk-box h4{{font-size:10.5px;letter-spacing:1.2px;text-transform:uppercase;color:var(--muted);margin:0 0 8px;font-weight:800;}}
.wk-passport{{background:var(--card);border-left:5px solid var(--gold);border-radius:12px;padding:12px 16px;margin-top:14px;display:flex;gap:16px;flex-wrap:wrap;align-items:baseline;}}
.wk-passport b{{font-size:15px;color:var(--navy);}}
.wk-stamp{{font-size:11px;font-weight:800;border-radius:999px;padding:3px 10px;background:#e0f4ea;color:#1d7a4d;}}
.wk-stamp.wip{{background:#fdf3dd;color:#96690a;}}
@media (max-width:980px){{.wk-grid{{grid-template-columns:1fr;}}}}</style></head><body>
<header class="topbar"><div class="topbar-inner">
<div class="brand"><div>
<div class="brand-title">ИЗДАНИЕ <span>ГУДОК</span> · НЕДЕЛЯ</div>
<div class="brand-sub">Сюжетные дуги недели {start:%d.%m}–{end:%d.%m}.{end:%y} · без повтора дневной ленты</div>
</div></div>
<div class="top-meta"><div class="chip">сюжетов: <b>{len(arcs)}</b></div>
<button class="theme-btn" id="themeBtn" onclick="toggleTheme()">🌙</button></div>
</div></header>
{nav_html}
<div class="page" style="max-width:1280px;">
<div class="wk-passport"><b>Неделя № {num}</b>
<span style="font-size:12.5px;color:var(--muted);">период: {start:%d.%m}–{end:%d.%m}.{end:%y} (пн–вс) · объём потока: {volume} сообщений · дуг: {len(arcs)}</span>{stamp}</div>
{pnav}
<div class="wk-grid"><div class="wk-main">
<div class="sec-head" style="margin-top:14px;"><h2>Сюжетные дуги недели</h2><div class="line"></div>
<div class="badge">{len(arcs)} дуг</div></div>
{arc_html or '<div class="card"><div class="card-pad">Выраженных дуг за неделю нет.</div></div>'}
<div class="note">Дуга = сюжет, который держали ≥2 источника одновременно или который собрал большой охват.
Формула дуги: возникновение → пик → развязка, со ссылками на дневные выпуски. Редакционная доводка (оценки, колонка)
вносится ассистентом по понедельникам, после чего штамп меняется на «завершён».</div>
</div>{rail}</div>
</div>
<footer class="footer"><div class="footer-inner">
<div><b>Гудок</b><p>{esc(cfg['tagline_full'])}</p></div>
<div><b>Периоды</b><p><a href="../weekly.html" class="flink">Все недели</a> · <a href="../archive.html" class="flink">Архив-матрица</a> · <a href="../index.html" class="flink">Первая полоса</a></p></div>
</div></footer>
</body></html>"""


# ------------------------------------------------------------------ archive
def render_archive(cfg, trends, store, status):
    """Архив-матрица: месяцы строками, недели колонками, дни точками."""
    now = datetime.now(UTC4)
    nav_html = render_nav(cfg, "archive", "")
    digests = sorted(glob.glob(os.path.join(DIGESTS, "digest_*.html")))
    dset = {os.path.basename(d)[7:17] for d in digests}
    weeks = sorted(glob.glob(os.path.join(BASE, "weekly", "week_*.html")))
    months = sorted({d[:7] for d in dset} | {os.path.basename(m)[6:13] for m in
                    sorted(glob.glob(os.path.join(BASE, "monthly", "month_*.html")))})
    rows = ""
    for ym in months:
        y, mo = map(int, ym.split("-"))
        first = datetime(y, mo, 1, tzinfo=UTC4).date()
        last = (datetime(y + 1, 1, 1, tzinfo=UTC4).date() if mo == 12
                else datetime(y, mo + 1, 1, tzinfo=UTC4).date()) - timedelta(days=1)
        monday = first - timedelta(days=first.weekday())
        cells = ""
        while monday <= last:
            w_end = monday + timedelta(days=6)
            num = week_num(cfg, monday)
            wfile = next((w for w in weeks if f"_{monday.isoformat()}_" in w), None)
            dots = ""
            for k in range(7):
                d = monday + timedelta(days=k)
                if d.month != mo:
                    dots += '<span style="opacity:.25;">·</span>'
                    continue
                has = d.isoformat() in dset
                dots += (f'<a href="digests/digest_{d.isoformat()}.html" title="{d:%d.%m}" '
                         f'style="display:inline-block;width:9px;height:9px;border-radius:50%;'
                         f'background:{"#2f80ed" if has else "#d7dee8"};margin:0 1px;"></a>'
                         if has else f'<span style="display:inline-block;width:9px;height:9px;border-radius:50%;'
                                      f'background:#e3e9f1;margin:0 1px;" title="{d:%d.%m} нет выпуска"></span>')
            wlink = (f'<a href="weekly/{os.path.basename(wfile)}" style="font-weight:800;">№{num}</a>'
                     if wfile else f'<span style="color:var(--muted);">№{num}</span>')
            cells += (f'<td style="text-align:center;padding:6px 8px;border-bottom:1px solid var(--line);">'
                      f'{wlink}<br>{dots}</td>')
            monday += timedelta(days=7)
        mfile = f"monthly/month_{ym}.html"
        mlink = (f'<a href="{mfile}" style="font-weight:800;color:var(--navy);">{MONTHS_RU_GEN[mo-1][:3]} {y}</a>'
                 if os.path.exists(os.path.join(BASE, mfile)) else f'{MONTHS_RU_GEN[mo-1][:3]} {y}')
        rows += f'<tr><td style="padding:6px 10px;border-bottom:1px solid var(--line);font-weight:700;">{mlink}</td>{cells}</tr>'
    return f"""<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Архив-матрица — {cfg['brand']}</title>
<link rel="icon" type="image/png" href="assets/logo_gudok.png">
<style>{CSS}{INDEX_CSS}
table.matrix{{border-collapse:collapse;width:100%;}}
</style></head><body>
<header class="topbar"><div class="topbar-inner">
<div class="brand"><div>
<div class="brand-title">ИЗДАНИЕ <span>ГУДОК</span> · АРХИВ</div>
<div class="brand-sub">Матрица периодов: месяцы строками, недели колонками, дни точками</div>
</div></div>
<div class="top-meta"><button class="theme-btn" id="themeBtn" onclick="toggleTheme()">🌙</button></div>
</div></header>
{nav_html}
<div class="wrap1200" style="padding-top:20px;">
<div class="card"><div class="card-pad" style="overflow-x:auto;">
<table class="matrix"><tr><th style="text-align:left;padding:6px 10px;background:var(--navy3);color:#fff;">Месяц</th>
<th style="padding:6px 8px;background:var(--navy3);color:#fff;">недели →</th></tr>
{rows}</table>
<div class="note">Номер недели — сквозной от недели запуска (07.09.2026 = № 1). Точка — дневной выпуск за дату;
серая точка — выпуска нет (день до запуска или пропуск). Клик по номеру недели — недельник, по месяцу — месячный отчёт.</div>
</div></div>
</div>
<footer class="footer"><div class="footer-inner">
<div><b>Гудок</b><p>{esc(cfg['tagline_full'])}</p></div>
<div><b>Периоды</b><p><a href="index.html" class="flink">Первая полоса</a> · <a href="weekly.html" class="flink">Недели</a> · <a href="monthly.html" class="flink">Месяцы</a></p></div>
</div></footer>
</body></html>"""


# ------------------------------------------------------------------ index
def render_index(cfg, trends, store, status, digest_files, special_files):
    """Первая полоса: СЕЙЧАС → НОВОСТИ → РАЗДЕЛЫ ПОРТАЛА."""
    now = datetime.now(UTC4)
    day = now.date()
    an = load_json(os.path.join(DATA, "analytics.json")) or {}
    isp = load_json(os.path.join(DATA, "infospace.json")) or {}
    alerts = load_json(os.path.join(DATA, "alerts.json")) or {}
    nav_html = render_nav(cfg, "index", "", subnav=SUBNAV_INDEX)

    # ================= СЕЙЧАС =================
    live = sorted([it for it in store if not it.get("dup_of") and local_dt(it.get("published"))],
                  key=lambda x: x.get("published") or "", reverse=True)
    latest = live[:6]
    tl = ""
    for it in latest:
        dt = local_dt(it["published"])
        tl += f"""<div class="tl-row"><div class="tl-time">{dt:%H:%M}</div>
<div class="tl-txt"><a href="{esc(it.get('url') or '#')}" target="_blank" rel="noopener">{esc(it['title'][:110])}</a>
<div class="tl-src">{esc(it.get('source',''))}</div></div></div>"""

    active = alerts.get("active", [])
    if active:
        a0 = active[-1]
        alert_html = f'<div class="now-alert danger">🚨 СЕЙЧАС: {esc(a0["title"][:120])} — @{esc(a0["channel"])} · <a href="{esc(a0["url"])}" style="color:inherit;">источник</a></div>'
    else:
        last_res = (alerts.get("resolved") or [{}])[-1]
        when = local_dt(last_res.get("resolved_at"))
        alert_html = (f'<div class="now-alert calm">✅ Воздушных угроз нет сейчас. '
                      f'Последняя тревога снята {when:%d.%m %H:%M}.</div>' if when else
                      '<div class="now-alert calm">✅ Воздушных угроз сейчас нет.</div>')

    today_events = [e for e in an.get("calendar", []) if e.get("date") == day.isoformat()][:4]
    tev = "".join(
        f'<div class="tl-row"><div class="tl-time">{esc(e.get("time") or "—")}</div>'
        f'<div class="tl-txt"><a href="{esc(e.get("url") or "#")}" target="_blank" rel="noopener">{esc(e["title"][:90])}</a></div></div>'
        for e in today_events) or '<div class="now-line">Событий на сегодня в афише нет — смотрите <a href="afisha.html">всю афишу</a>.</div>'
    weather = fetch_weather()

    sent = an.get("sentiment") or {}
    tone = sent.get("today_score")
    tone_txt = ("тревожный" if tone is not None and tone < -0.15 else
                ("приподнятый" if tone is not None and tone > 0.15 else "ровный"))
    topics = (trends or {}).get("topics", {})
    top_topic = max(topics.items(), key=lambda kv: (kv[1]["today"], kv[1]["week"]), default=None)
    vote_day = datetime(2026, 9, 18, tzinfo=UTC4).date()
    d_vote = (vote_day - day).days
    n24 = (trends or {}).get("counts", {}).get("last24h", 0)
    n_week = (isp.get("week_items") or 0)

    # ================= НОВОСТИ =================
    win_start = datetime.combine(day, datetime.min.time(), tzinfo=UTC4) - timedelta(hours=30)
    window = [it for it in store if not it.get("dup_of")
              and local_dt(it.get("published")) and local_dt(it["published"]) >= win_start]
    if len(window) < 6:
        win_start -= timedelta(days=2)
        window = [it for it in store if not it.get("dup_of")
                  and local_dt(it.get("published")) and local_dt(it["published"]) >= win_start]
    pool = [it for it in window if is_regional(it) and it.get("category") != "security"] or window
    leads = hero_pick(pool, trends, now, 3)

    def lead_meta(it):
        dt = local_dt(it.get("published"))
        views = f" · 👁 {fmt_views(it['views'])}" if it.get("views") else ""
        return esc(it.get("url") or "#"), f"{dt.strftime('%d.%m %H:%M') if dt else ''} · {esc(it.get('source',''))}{views}"

    cats = {c["id"]: c for c in cfg["categories"]}
    lead_html = ""
    if leads:
        m = leads[0]
        cat = cats.get(m.get("category"), {})
        url, meta = lead_meta(m)
        lead_html = f"""<article class="lead-main">
<div class="lead-kicker" style="color:{cat.get('color','var(--gold)')};">{cat.get('icon','📌')} {esc(cat.get('name','Главное'))} · сюжет дня</div>
<h2><a href="{url}" target="_blank" rel="noopener">{esc(m['title'])}</a></h2>
<p>{esc((m.get('text') or '')[:340])}</p>
<div class="lead-meta">{meta} · <a href="{url}" target="_blank" rel="noopener">читать полностью →</a></div></article>"""
        side = ""
        for m in leads[1:3]:
            cat = cats.get(m.get("category"), {})
            url, meta = lead_meta(m)
            side += f"""<article class="lead-card">
<div class="lead-kicker" style="color:{cat.get('color','var(--blue)')};">{cat.get('icon','📌')} {esc(cat.get('name',''))}</div>
<h3><a href="{url}" target="_blank" rel="noopener">{esc(m['title'][:120])}</a></h3>
<p>{esc((m.get('text') or '')[:150])}</p>
<div class="lead-meta">{meta}</div></article>"""
        lead_html += f'<div class="lead-side">{side}</div>'

    # ещё заголовки (после лидов)
    lead_ids = {m["id"] for m in leads}
    rest = sorted([it for it in pool if it["id"] not in lead_ids],
                  key=lambda x: x.get("published") or "", reverse=True)[:6]
    more = "".join(
        f'<a href="{esc(it.get("url") or "#")}" target="_blank" rel="noopener">{esc(it["title"][:100])} '
        f'<span>· {(local_dt(it["published"]) or now):%H:%M}</span></a>' for it in rest)

    # ================= РАЗДЕЛЫ ПОРТАЛА =================
    latest_digest = os.path.basename(digest_files[-1]) if digest_files else ""
    dstr = latest_digest.replace("digest_", "").replace(".html", "")
    dnum, dtest = digest_number(cfg, dstr) if dstr else (1, False)
    ex = f"exec_{dstr}.html"
    ex_ok = os.path.exists(os.path.join(DIGESTS, ex))
    af_n = len(an.get("calendar", []))
    cards = [
        ("📰", f"День · выпуск № {dnum}{' 🧪' if dtest else ''}", f"{n24} <small>материалов за 24 ч</small>",
         "Ежедневный выпуск: лента по девяти рубрикам, пульс повестки, сюжеты 72 часов, тон и прогноз.",
         f"digests/{latest_digest}" if latest_digest else "", "var(--blue)"),
        ("📕", "Неделя · аналитика", f"{len(glob.glob(os.path.join(BASE, 'weekly', 'week_*.html')))} <small>выпуска</small>",
         "Завершённая страница за неделю: паспорт периода, нарратив, правая колонка справок.",
         "weekly.html", "#96690a"),
        ("📊", "Месяц · отчёт", f"{len(glob.glob(os.path.join(BASE, 'monthly', 'month_*.html')))} <small>отчёт</small>",
         "Все метрики и тенденции месяца: темы по неделям, тон, каскады, территории, хроника.",
         "monthly.html", "#0f9b8e"),
        ("📋", "Дайджест руководителя", "1 <small>страница A4</small>",
         "Пять событий, три риска, два решения — для быстрого чтения руководством организации.",
         f"digests/{ex}" if ex_ok else "", "#1d7a4d"),
        ("🎭", "Афиша", f"{af_n} <small>событий на 45 дней</small>",
         "Культурные события области: фестивали, театр, концерты, выставки; фильтры по дням и районам.",
         "afisha.html", "#9a4d8f"),
        ("📁", "Проекты", f"{len(cfg.get('projects', []))} <small>досье</small>",
         f"Выборы-2026 ({d_vote} дн. до голосования), госзакупки региона и будущие кампании — спецстраницы с методиками.",
         "projects.html", "#b02a2f"),

        ("🗄", "Архив", f"{len(digest_files)} <small>выпусков · {len(special_files)} спец.</small>",
         "Все ежедневные выпуски и специальные материалы издания с первого дня.",
         "#archive", "var(--muted)"),
    ]
    sec_cards = ""
    for ic, t, fig, dsc, href, color in cards:
        inner = f"""<b>{esc(t)}</b><div class="fig">{fig}</div>
<p>{esc(dsc)}</p><div class="go">открыть →</div>"""
        sec_cards += (f'<a class="sec-card" style="border-top-color:{color};" href="{href}">{inner}</a>'
                      if href else f'<div class="sec-card" style="border-top-color:{color};opacity:.6;">{inner}</div>')

    # архив-якорь (компактный, внутри раздела-навигатора)
    arch_rows = ""
    for path in reversed(digest_files[-5:]):
        nm = os.path.basename(path)
        d2 = nm.replace("digest_", "").replace(".html", "")
        try:
            dd = datetime.strptime(d2, "%Y-%m-%d")
        except ValueError:
            continue
        num, tst = digest_number(cfg, d2)
        arch_rows += f"""<div class="arch-item"><div class="arch-date"><b>{dd:%d}</b><span>{dd:%b}</span></div>
<div style="flex:1;"><b style="color:var(--navy);font-size:13.5px;">Выпуск № {num}{' 🧪' if tst else ''} за {dd:%d.%m.%Y}</b></div>
<a class="btn" href="digests/{nm}">Открыть</a></div>"""

    return f"""<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Гудок — информационно-аналитическое издание · Ульяновская область</title>
<style>{CSS}{INDEX_CSS}{FRONT2_CSS}</style></head><body>

<header class="masthead"><div class="mast-inner">
<div class="mast-brand">
<div>
<div class="mast-title">ГУДОК</div>
<div class="mast-slogan">{esc(cfg["tagline_short"])}</div>
</div>
</div>
<div class="mast-right">
<div class="date">{ru_date(now)}</div>
{f'<div class="wx">🌡 {esc(weather)}</div>' if weather else ''}
<div class="mast-tools">
<button class="theme-btn" id="themeBtn" onclick="toggleTheme()" title="Светлая/тёмная тема">🌙</button>
<a class="chip" href="digests/{latest_digest}" class="chip-link">Свежий выпуск →</a>
</div>
</div>
</div></header>
{nav_html}

<div class="now-wrap" id="now">
<div class="now-panel">
{alert_html}
<div class="now-grid">
<div class="now-col">
<div class="now-h">⏱ Происходит прямо сейчас</div>
{tl}
</div>
<div class="now-col">
<div class="now-h">Сегодня в области</div>
{tev}
</div>
<div class="now-col">
<div class="now-h">Сегодня в номере</div>
<p style="font-family:var(--serif);font-size:15.5px;line-height:1.55;color:var(--ink2);">
В выпуске <b>{n24} материала</b> за сутки, из них {len(leads)} главных на полосе.
На сегодня в афише <b>{len(today_events)}</b> события. До дня голосования — <b>{d_vote} дн.</b>
Погода: {esc(weather) if weather else '—'}. Тон повестки и все метрики инфополя —
в разделе <a href="infospace.html">«Инфопространство»</a>.</p>
</div>
</div>
</div>
</div>

<div class="wrap1200" id="news" style="padding-top:6px;">
<div class="sec-head"><h2>Новости дня</h2><div class="line"></div>
<div class="badge">{now:%d.%m.%Y} · обновлено {now:%H:%M}</div></div>
<div class="lead-grid">{lead_html}</div>
<div class="sec-head" style="margin:18px 0 6px;"><h2 style="font-size:15px;">Ещё в выпуске</h2><div class="line"></div></div>
<div class="more-heads">{more}</div>
</div>

<div class="sec-head" id="sections" style="max-width:1200px;margin:26px auto 12px;padding:0 18px;"><h2>Разделы портала</h2><div class="line"></div>
<div class="badge">всё издание целиком</div></div>
<div class="sec-grid">{sec_cards}</div>

<div class="wrap1200" id="archive" style="margin-top:26px;">
<div class="sec-head"><h2>Последние выпуски</h2><div class="line"></div>
<div class="badge"><a href="#sections" style="color:var(--muted);">весь архив — в разделе «Архив»</a></div></div>
<div class="card"><div class="card-pad">{arch_rows or '<span style="color:var(--muted);">Пока пусто.</span>'}</div></div>
</div>

<div class="wrap1200" style="margin-top:26px;padding-bottom:6px;">
<div class="util-bar">
<span class="util-lbl">Служебное</span>
<a href="roadmap.html">🧭 Роадмап издания</a>
<a href="status.html">🩺 Статус системы</a>
<a href="https://github.com/Volgin1917/gudok" target="_blank" rel="noopener"> GitHub: исходники, выпуски и конвейер</a>
</div>
</div>

<footer class="footer"><div class="footer-inner">
<div><b>Гудок</b><p>{esc(cfg['tagline_full'])} Выходит ежедневно в 07:30 (UTC+4).</p></div>
<div><b>Разделы</b><p><a href="digests/{latest_digest}" class="flink">Свежий выпуск</a> · <a href="afisha.html" class="flink">Афиша</a> · <a href="projects.html" class="flink">Проекты</a> · <a href="infospace.html" class="flink">Инфопространство</a> · <a href="roadmap.html" class="flink">Роадмап</a> · <a href="status.html" class="flink">Статус</a></p></div>
<div><b>Редакция</b><p>Мониторинг {sum(1 for c in cfg.get('telegram_channels',[]) if c.get('enabled'))} Telegram-каналов и {sum(1 for c in cfg.get('rss_sources',[]) if c.get('enabled',True))} RSS-лент. Колонку редактора и аналитику готовит ассистент. Реестр источников и здоровье конвейера — на <a href="status.html" class="flink">status-странице</a>.</p>
<p style="margin-top:6px;">Исходный код, архив выпусков и конвейер публикации — в репозитории: <a href="https://github.com/Volgin1917/gudok" target="_blank" rel="noopener" class="flink">github.com/Volgin1917/gudok</a></p></div>
</div></footer>
<script>
function tick(){{try{{var f=new Intl.DateTimeFormat('ru-RU',{{timeZone:'Europe/Ulyanovsk',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false}});var el=document.getElementById('clock');if(el)el.textContent=f.format(new Date());}}catch(e){{}}}}
tick();setInterval(tick,1000);
</script>
</body></html>"""


def big_spark(trends):
    """Сводный 14-дневный спарклайн всей повестки."""
    if not trends:
        return ""
    n = len(trends["days"])
    total = [0] * n
    for t in trends["topics"].values():
        for i, v in enumerate(t["series"]):
            total[i] += v
    return (f'<div style="text-align:center;"><div style="font-size:11px;font-weight:800;color:var(--muted);text-transform:uppercase;letter-spacing:.8px;margin-bottom:4px;">Интенсивность повестки, 14 дней</div>'
            + sparkline(total, w=240, h=54, color="#4a7fb5") + f'<div style="font-size:11px;color:var(--muted);">всего упоминаний тем: {sum(total)}</div></div>')


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None, help="дата выпуска YYYY-MM-DD (по умолчанию сегодня)")
    ap.add_argument("--monthly", metavar="YYYY-MM", help="сгенерировать месячный отчёт")
    ap.add_argument("--weekly-new", action="store_true", help="недельник за последнюю завершённую ISO-неделю")
    ap.add_argument("--weekly-period", nargs=2, metavar=("START", "END"), help="недельник за период YYYY-MM-DD")
    ap.add_argument("--weekly-rail", nargs=2, metavar=("START", "END"),
                    help="напечатать HTML правой колонки недельника за период")
    ap.add_argument("--exec", dest="exec_mode", action="store_true",
                    help="сформировать «Дайджест руководителя» (1 страница)")
    ap.add_argument("--elections", action="store_true",
                    help="сформировать спецвыпуск «Выборы-2026»")
    args = ap.parse_args()

    cfg = load_json(os.path.join(BASE, "config.json"))
    trends = load_json(os.path.join(DATA, "trends.json"))
    status = load_json(os.path.join(DATA, "fetch_status.json"), {})
    store = load_store()

    date_str = args.date or datetime.now(UTC4).strftime("%Y-%m-%d")
    os.makedirs(DIGESTS, exist_ok=True)
    os.makedirs(SPECIAL, exist_ok=True)

    digest_files = sorted(glob.glob(os.path.join(DIGESTS, "digest_*.html")))
    target = os.path.join(DIGESTS, f"digest_{date_str}.html")
    if target not in digest_files:
        digest_files.append(target)
        digest_files = sorted(digest_files)
    digest_no, _test = digest_number(cfg, date_str)

    def themed(html):
        now = datetime.now(UTC4)
        html = html.replace("</head>", THEME_HEAD + "</head>", 1)
        WD = ["воскресенье", "понедельник", "вторник", "среда", "четверг", "пятница", "суббота"]
        MR = ["января", "февраля", "марта", "апреля", "мая", "июня",
              "июля", "августа", "сентября", "октября", "ноября", "декабря"]
        flag = ('<div class="flagline"><span>' + WD[now.weekday()] + ', '
                + str(now.day) + ' ' + MR[now.month - 1] + ' ' + str(now.year) + ' г.</span>'
                '<span>Ульяновск · издание внутреннее</span>'
                '<span>выпуск собран ' + now.strftime("%H:%M") + '</span></div>')
        html = html.replace('<header class="topbar"><div class="topbar-inner">',
                            '<header class="topbar">' + flag + '<div class="topbar-inner">', 1)
        html = html.replace('<header class="masthead"><div class="mast-inner">',
                            '<header class="masthead">' + flag + '<div class="mast-inner">', 1)

        html = re.sub(r'(</nav>(?:<div class="subnav">.*?</div></div>)?)', r'\1<main id="main">',
                      html, count=1, flags=re.S)
        html = html.replace('<footer class="footer">', '</main>\n<footer class="footer">', 1)
        return html.replace("</body>", THEME_FOOT + "</body>", 1)

    manifest = []
    for it in sorted([x for x in store if x.get("published")], key=lambda x: x["published"], reverse=True)[:120]:
        dt = local_dt(it["published"])
        manifest.append({"t": it["title"][:110], "u": it.get("url") or "#",
                         "d": dt.strftime("%d.%m") if dt else "",
                         "c": (cats_all.get(it.get("category"), {}) or {}).get("name", "") if False else str(it.get("source", ""))[:18]})
    import json as _json
    render_nav.search_manifest = _json.dumps(manifest, ensure_ascii=False)

    def with_utilbar(html, prefix=""):
        return html.replace("</body>", render_utilbar(prefix) + "</body>", 1)

    digest_html = with_utilbar(themed(render_digest(cfg, trends, store, status, date_str, digest_no)), "../")
    with open(target, "w", encoding="utf-8") as f:
        f.write(digest_html)

    # (выборы-2026 теперь живут в projects/elections_2026.html — см. выше)

    if args.weekly_new:
        this_monday = now.date() - timedelta(days=now.weekday())
        start = this_monday - timedelta(days=7)
        end = this_monday - timedelta(days=1)
        os.makedirs(os.path.join(BASE, "weekly"), exist_ok=True)
        html = themed(render_weekly_full(cfg, trends, store, status, start, end))
        tgt = os.path.join(BASE, "weekly", f"week_{week_num(cfg, start):02d}_{start.isoformat()}_{end.isoformat()}.html")
        with open(tgt, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"[generate] недельник: {os.path.basename(tgt)}")
        return

    if args.weekly_period:
        st_d = datetime.strptime(args.weekly_period[0], "%Y-%m-%d").date()
        en_d = datetime.strptime(args.weekly_period[1], "%Y-%m-%d").date()
        os.makedirs(os.path.join(BASE, "weekly"), exist_ok=True)
        html = themed(render_weekly_full(cfg, trends, store, status, st_d, en_d))
        tgt = os.path.join(BASE, "weekly", f"week_{week_num(cfg, st_d):02d}_{st_d.isoformat()}_{en_d.isoformat()}.html")
        with open(tgt, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"[generate] недельник: {os.path.basename(tgt)}")
        return

    if args.monthly:
        os.makedirs(os.path.join(BASE, "monthly"), exist_ok=True)
        m_html = themed(render_monthly(cfg, trends, store, status, args.monthly))
        mp = os.path.join(BASE, "monthly", f"month_{args.monthly}.html")
        with open(mp, "w", encoding="utf-8") as f:
            f.write(m_html)
        print(f"[generate] месячный отчёт: monthly/month_{args.monthly}.html")
        return

    if args.weekly_rail:
        print(render_weekly_rail(cfg, load_json(os.path.join(DATA, "analytics.json")) or {},
                                 store, args.weekly_rail[0], args.weekly_rail[1]))
        return

    if args.exec_mode:
        exec_html = with_utilbar(themed(render_exec(cfg, trends, store, status, date_str)), "../")
        exec_path = os.path.join(DIGESTS, f"exec_{date_str}.html")
        with open(exec_path, "w", encoding="utf-8") as f:
            f.write(exec_html)
        print(f"[generate] дайджест руководителя: digests/exec_{date_str}.html")

    afisha_html = with_utilbar(themed(render_afisha(cfg, trends, store, status,
                                        load_json(os.path.join(DATA, "analytics.json")) or {})), "")
    print_html = render_print(cfg, trends, store, status,
                              load_json(os.path.join(DATA, "analytics.json")) or {},
                              load_json(os.path.join(DATA, "infospace.json")) or {},
                              date_str, digest_no, _test)
    with open(os.path.join(DIGESTS, f"print_{date_str}.html"), "w", encoding="utf-8") as f:
        f.write(print_html)
    print("[generate] печатная полоса: digests/print_" + date_str + ".html")

    infospace_html = with_utilbar(themed(render_infospace(cfg, trends, store, status,
                                             load_json(os.path.join(DATA, "infospace.json")) or {})), "")
    with open(os.path.join(BASE, "infospace.html"), "w", encoding="utf-8") as f:
        f.write(infospace_html)
    print("[generate] инфопространство: infospace.html")
    with open(os.path.join(BASE, "afisha.html"), "w", encoding="utf-8") as f:
        f.write(afisha_html)
    print("[generate] афиша: afisha.html")

    arch_html = themed(render_archive(cfg, trends, store, status))
    with open(os.path.join(BASE, "archive.html"), "w", encoding="utf-8") as f:
        f.write(arch_html)
    print("[generate] архив-матрица: archive.html")

    os.makedirs(os.path.join(BASE, "monthly"), exist_ok=True)
    monthly_html = themed(render_monthly_hub(cfg, trends, store, status))
    with open(os.path.join(BASE, "monthly.html"), "w", encoding="utf-8") as f:
        f.write(monthly_html)
    print("[generate] хаб месяцев: monthly.html")

    weekly_html = themed(render_weekly_hub(cfg, trends, store, status))
    with open(os.path.join(BASE, "weekly.html"), "w", encoding="utf-8") as f:
        f.write(weekly_html)
    print("[generate] хаб недель: weekly.html")

    proj_dir = os.path.join(BASE, "projects")
    os.makedirs(proj_dir, exist_ok=True)
    proj_html = themed(render_projects(cfg, trends, store, status))
    with open(os.path.join(BASE, "projects.html"), "w", encoding="utf-8") as f:
        f.write(proj_html)
    el_html2 = themed(render_elections(cfg, trends, store, status))
    with open(os.path.join(proj_dir, "elections_2026.html"), "w", encoding="utf-8") as f:
        f.write(el_html2)
    gz_html = themed(render_goszakupki(cfg, trends, store, status,
                                       load_json(os.path.join(DATA, "analytics.json")) or {}))
    with open(os.path.join(proj_dir, "goszakupki.html"), "w", encoding="utf-8") as f:
        f.write(gz_html)
    print("[generate] проекты: projects.html, projects/elections_2026.html, projects/goszakupki.html")

    special_files = sorted(glob.glob(os.path.join(SPECIAL, "*.html")))
    index_html = themed(render_index(cfg, trends, store, status, digest_files, special_files))
    with open(os.path.join(BASE, "index.html"), "w", encoding="utf-8") as f:
        f.write(index_html)

    print(f"[generate] выпуск №{digest_no}: digests/digest_{date_str}.html")
    print(f"[generate] витрина: index.html (архив: {len(digest_files)} выпусков, спец: {len(special_files)})")


if __name__ == "__main__":
    main()
