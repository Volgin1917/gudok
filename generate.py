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
import math
import glob
import re
import html as H
import json
import os
import sys
from datetime import datetime, timedelta, timezone

BASE = os.path.dirname(os.path.abspath(__file__))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

import outlets  # канонические издания: каналы одной редакции = один источник
import footer  # единый подвал всех страниц
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
  --paper:#FAF7F2; --paper-2:#F3EFE7; --ink:#0B0B0B; --ink-2:#2A2620; --muted:#6B655C;
  --rule:#E3DED4; --rule-strong:#0B0B0B; --accent:#D63F1F; --on-ink:#C9C2B6;
  --pos:#4F5F53; --neu:#C9C2B6; --neg:#B04848;
  --serif-display:"Fraunces","Source Serif 4",Georgia,"Times New Roman",serif;
  --serif-body:"Source Serif 4",Georgia,"Times New Roman",serif;
  --sans:"Inter",system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
  --rubleny:Impact,"Arial Black","Franklin Gothic Bold","Helvetica Neue",sans-serif;
  --maxw:1340px; --gutter:28px;
  /* совместимость старых классов */
  --navy:var(--ink); --navy2:var(--ink); --navy3:var(--ink-2); --blue:var(--ink);
  --gold:var(--accent); --line:var(--rule); --txt:var(--ink); --bg:var(--paper);
  --card:var(--paper); --shadow:none;
}
:root[data-theme="dark"]{
  --paper:#101214; --paper-2:#17191c; --ink:#ECE7DE; --ink-2:#D5CFC4; --muted:#9A948A;
  --rule:#2A2D31; --rule-strong:#ECE7DE; --accent:#FF6A4D; --on-ink:#2A2620;
  --pos:#7FA88C; --neu:#4A4E54; --neg:#D07A7A;
  --navy:var(--ink); --navy2:var(--ink); --navy3:var(--ink-2); --blue:var(--ink);
  --gold:var(--accent); --line:var(--rule); --txt:var(--ink); --bg:var(--paper); --card:var(--paper);
}
*,*::before,*::after{box-sizing:border-box;}
html{-webkit-text-size-adjust:100%;scroll-behavior:smooth;}
body{margin:0;background:var(--paper);color:var(--ink);font-family:var(--serif-body);font-size:17px;line-height:1.55;-webkit-font-smoothing:antialiased;}
a{color:inherit;text-decoration:none;}
a:hover{color:var(--accent);}
a:focus-visible{outline:2px solid var(--accent);outline-offset:3px;border-radius:2px;}
img{max-width:100%;display:block;}
.genstamp{background:var(--ink);color:var(--paper);border-left:5px solid var(--accent);}
:root[data-theme="dark"] .genstamp{background:var(--paper);color:var(--ink);}
.genstamp-inner{max-width:var(--maxw);margin:0 auto;padding:10px var(--gutter);display:flex;gap:16px;align-items:baseline;flex-wrap:wrap;}
.genstamp .g1{font-family:var(--serif-display);font-size:17px;font-weight:700;}
.genstamp .g2{font-family:var(--sans);font-size:12px;font-weight:700;color:var(--accent);text-transform:uppercase;letter-spacing:.12em;}
.genstamp .g3{font-family:var(--sans);font-size:11.5px;opacity:.75;}
.skip{position:absolute;left:-999px;top:0;background:var(--ink);color:var(--paper);padding:8px 14px;z-index:99;}
.skip:focus{left:8px;}
@media (prefers-reduced-motion:reduce){*,*::before,*::after{animation-duration:.001ms!important;transition-duration:.001ms!important;scroll-behavior:auto!important;}}

/* рубленый вордмарк */
.brand-title,.mast-title,.wordmark,.footer__brand{
  font-family:var(--rubleny);font-weight:900;text-transform:uppercase;
  letter-spacing:.04em;line-height:.95;color:var(--ink);font-style:normal;
}
.brand-title{font-size:30px;}
.brand-title span,.mast-title span,.wordmark span,.footer__brand span{color:var(--accent);}
.mast-title{font-size:clamp(44px,8vw,76px);letter-spacing:.06em;}

/* топбар-флаглиния */
.flagline,.topbar{background:var(--paper);border-bottom:1px solid var(--rule);
  font-family:var(--sans);font-size:12px;color:var(--muted);}
.flagline{max-width:var(--maxw);margin:0 auto;display:flex;justify-content:space-between;gap:14px;
  padding:10px var(--gutter);flex-wrap:wrap;border-bottom:none;padding-bottom:0;}
.topbar{border-bottom:none;}
.topbar-inner{max-width:var(--maxw);margin:0 auto;padding:0 var(--gutter) 12px;display:block;text-align:center;}
.brand{display:block;}
.brand>div{display:block;}
.brand-sub{font-family:var(--sans);font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);margin-top:6px;}
.top-meta{margin:10px auto 0;display:flex;gap:0;justify-content:center;flex-wrap:wrap;}
.chip{background:none;border:none;border-radius:0;padding:0 10px;font:400 12px var(--sans);color:var(--muted);position:relative;}
.chip+.chip::before{content:"·";position:absolute;left:-3px;color:var(--muted);}
.chip b{color:var(--ink-2);font-weight:600;}
.chip a,.chip-link,.flink{color:var(--muted);}
.chip a:hover,.chip-link:hover,.flink:hover{color:var(--accent);}
.theme-btn,.print-btn{border:none;background:none;color:var(--muted);font:500 12px var(--sans);padding:0 10px;cursor:pointer;border-bottom:1px solid var(--ink);}
.theme-btn:hover,.print-btn:hover{color:var(--accent);border-color:var(--accent);}
.logo,.mast-logo,.mast-right{display:none;}
.masthead::after,.topbar::after{content:"";display:block;max-width:var(--maxw);margin:14px auto 0;border-bottom:1px solid var(--rule-strong);}

/* навигация-секции (sticky) */
.nav{position:sticky;top:0;z-index:20;background:var(--paper);border-top:1px solid var(--ink);border-bottom:1px solid var(--rule);}
.nav-inner{max-width:var(--maxw);margin:0 auto;padding:0 var(--gutter);display:flex;align-items:center;flex-wrap:wrap;}
.nav a{font-family:var(--sans);font-size:13px;font-weight:500;color:var(--ink-2);padding:15px 14px;position:relative;border-bottom:none;}
.nav a:hover{color:var(--ink);}
.nav a.active{color:var(--accent);font-weight:600;}
.nav a.active::after{content:"";position:absolute;left:14px;right:14px;bottom:10px;height:2px;background:var(--accent);}
.nav a.nav-util{color:var(--muted);}
.nav-util-first{margin-left:auto;}
.nav-toggle{display:none;border:1px solid var(--rule);background:none;color:var(--ink);font:600 13px var(--sans);padding:8px 12px;cursor:pointer;margin:8px var(--gutter);}
@media (max-width:900px){
  .nav-toggle{display:block;}
  .nav-inner{display:none;flex-direction:column;align-items:stretch;}
  body.nav-open .nav-inner{display:flex;}
  .nav a{padding:12px 16px;border-top:1px solid var(--rule);}
}
.subnav{background:var(--paper);border-bottom:1px solid var(--rule);}
.subnav-inner{max-width:var(--maxw);margin:0 auto;padding:8px var(--gutter);display:flex;gap:16px;flex-wrap:wrap;font-family:var(--sans);font-size:12.5px;}
.subnav-inner a{color:var(--muted);}
.subnav-inner a:hover{color:var(--accent);}
.subnav .lbl{color:var(--ink);font-weight:700;text-transform:uppercase;letter-spacing:.12em;font-size:10.5px;}

/* страницы: контейнеры и заголовки разделов */
.page,.wrap1200,.wrap{max-width:var(--maxw);margin:0 auto;padding:0 var(--gutter);}
.sec-head{max-width:var(--maxw);margin:56px auto 26px;padding:16px var(--gutter) 0;border-top:1px solid var(--ink);display:flex;align-items:baseline;justify-content:space-between;gap:20px;}
.sec-head h2{font-family:var(--serif-display);font-weight:600;font-size:26px;letter-spacing:-.02em;color:var(--ink);}
.sec-head .line{flex:1;}
.sec-head .badge{font-family:var(--sans);font-size:12px;font-weight:500;color:var(--muted);}
.sec-head .badge a{color:var(--muted);}

/* герой (первая полоса) */
.hero{padding:52px 0 44px;border-bottom:1px solid var(--rule);}
.hero__inner{max-width:var(--maxw);margin:0 auto;padding:0 var(--gutter);display:grid;grid-template-columns:1.45fr 1fr;gap:56px;align-items:center;}
.hero__eyebrow{display:flex;align-items:center;gap:12px;margin-bottom:20px;}
.hero__eyebrow .live{width:8px;height:8px;border-radius:50%;background:var(--accent);}
.kicker{font-family:var(--sans);font-size:11px;font-weight:700;letter-spacing:.16em;text-transform:uppercase;color:var(--accent);}
.kicker--ink{color:var(--ink);}
.hero__title{font-family:var(--serif-display);font-weight:600;font-size:clamp(38px,5.2vw,72px);line-height:1.03;letter-spacing:-.025em;margin:0 0 22px;text-wrap:balance;color:var(--ink);}
.hero__title a{color:var(--ink);}
.hero__title a:hover{color:var(--accent);}
.hero__title em{font-style:italic;font-weight:400;color:var(--accent);}
.hero__dek{font-family:var(--serif-body);font-size:20px;line-height:1.45;color:var(--ink-2);margin:0 0 24px;max-width:62ch;}
.hero__byline{display:flex;align-items:center;gap:14px;font-family:var(--sans);font-size:13px;color:var(--muted);}
.hero__byline .avatar{width:36px;height:36px;border-radius:50%;background:var(--ink);color:var(--paper);display:grid;place-items:center;font-family:var(--rubleny);font-size:13px;letter-spacing:.05em;}
.hero__byline strong{color:var(--ink);font-weight:600;}
.hero__why{font-family:var(--sans);font-size:12px;color:var(--muted);letter-spacing:.01em;margin:14px 0 0;}
.hero__passport{font-family:var(--sans);font-size:12px;color:var(--muted);margin:4px 0 0;}
.hero__passport strong{color:var(--ink-2);font-weight:600;}
.hero__also{font-family:var(--sans);font-size:12px;font-style:italic;color:var(--muted);margin:4px 0 0;}
.hero__timeline{font-family:var(--sans);font-size:12px;color:var(--muted);margin:6px 0 0;letter-spacing:.01em;}
.dot-sep::before{content:"·";margin:0 8px;color:var(--muted);}
.hero__media{position:relative;aspect-ratio:4/5;overflow:hidden;margin:0;
  background:radial-gradient(120% 90% at 30% 20%,#4A5A55 0%,#2E3A38 55%,#1C2322 100%);}
.hero__media--b{background:radial-gradient(120% 90% at 70% 30%,#6D4F3C 0%,#3A2A22 55%,#1A1310 100%);}
.hero__media--c{background:radial-gradient(120% 90% at 40% 60%,#3E4552 0%,#2A2F3A 55%,#171A20 100%);}
.hero__media figcaption{position:absolute;left:18px;right:18px;bottom:16px;color:#EDE8DF;font-family:var(--sans);font-size:11px;letter-spacing:.1em;text-transform:uppercase;display:flex;justify-content:space-between;gap:12px;z-index:2;}
.hero__media::after{content:"";position:absolute;inset:0;background:linear-gradient(180deg,transparent 60%,rgba(0,0,0,.35) 100%);}

/* самое читаемое */
.mostread{border-bottom:1px solid var(--rule);background:var(--paper-2);}
.mostread__inner{max-width:var(--maxw);margin:0 auto;padding:26px var(--gutter) 30px;display:grid;grid-template-columns:180px 1fr;gap:40px;align-items:start;}
.mostread__label{font-family:var(--sans);font-size:12px;font-weight:700;letter-spacing:.16em;text-transform:uppercase;color:var(--ink);display:flex;align-items:center;gap:12px;padding-top:4px;}
.mostread__label::before{content:"";width:22px;height:1px;background:var(--accent);}
.mostread__list{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:repeat(5,1fr);}
.mostread__list li{padding:0 22px;border-left:1px solid var(--rule);display:flex;gap:14px;align-items:baseline;}
.mostread__list li:first-child{border-left:0;padding-left:0;}
.mostread__num{font-family:var(--serif-display);font-weight:400;font-size:34px;line-height:1;color:var(--rule);letter-spacing:-.03em;}
.mostread__list a{font-family:var(--serif-body);font-size:15px;line-height:1.35;font-weight:600;color:var(--ink);}
.mostread__list a:hover{color:var(--accent);}

/* «Коротко: 7 строк дня» */
.brief{border-bottom:1px solid var(--rule);background:var(--paper);}
.brief__inner{max-width:var(--maxw);margin:0 auto;padding:22px var(--gutter) 24px;}
.brief__label{font-family:var(--sans);font-size:12px;font-weight:700;letter-spacing:.16em;text-transform:uppercase;color:var(--ink);display:flex;align-items:center;gap:12px;margin-bottom:14px;}
.brief__label::before{content:"";width:22px;height:1px;background:var(--accent);}
.brief-row{display:grid;grid-template-columns:86px 200px 1fr;gap:16px;align-items:baseline;padding:9px 0;border-top:1px solid var(--rule);}
.brief-row:first-of-type{border-top:0;}
.brief-t{font-family:var(--sans);font-size:12px;color:var(--muted);font-variant-numeric:tabular-nums;}
.brief-k{font-family:var(--sans);font-size:12px;color:var(--muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.brief-row a{font-family:var(--serif-body);font-size:15.5px;line-height:1.35;font-weight:600;color:var(--ink);}
.brief-row a:hover{color:var(--accent);}

/* карточки */
.grid{max-width:var(--maxw);margin:0 auto;padding:0 var(--gutter);display:grid;grid-template-columns:repeat(4,1fr);gap:36px 28px;}
.card{display:flex;flex-direction:column;background:none;border:none;border-radius:0;box-shadow:none;}
.card__media{aspect-ratio:3/2;margin-bottom:14px;position:relative;overflow:hidden;}
.card__media--a{background:linear-gradient(140deg,#D9CFC0 0%,#A89A85 100%);}
.card__media--b{background:linear-gradient(140deg,#B8C2C1 0%,#5F6E6D 100%);}
.card__media--c{background:linear-gradient(140deg,#E5C9B6 0%,#B4795A 100%);}
.card__media--d{background:linear-gradient(140deg,#C9C2D1 0%,#6D6079 100%);}
.card__kicker{margin-bottom:10px;}
.card__title{font-family:var(--serif-display);font-weight:600;font-size:20px;line-height:1.15;letter-spacing:-.015em;margin:0 0 10px;color:var(--ink);}
.card__title a{color:var(--ink);}
.card__title a:hover{color:var(--accent);}
.card__dek{font-family:var(--serif-body);font-size:15px;line-height:1.5;color:var(--muted);margin:0 0 12px;}
.card__meta{font-family:var(--sans);font-size:12px;color:var(--muted);margin-top:auto;}
.card__badges{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px;}
.chip{font-family:var(--sans);font-size:10.5px;font-weight:600;letter-spacing:.04em;padding:3px 8px;border-radius:999px;white-space:nowrap;display:inline-block;}
.chip--cluster{color:var(--ink-2);background:var(--paper-2);border:1px solid var(--rule);}

/* лента: чипы-рубрики + «Показать ещё» (#19/#20) */
.feed-chips{max-width:var(--maxw);margin:0 auto;padding:10px var(--gutter) 0;display:flex;flex-wrap:wrap;gap:6px;position:sticky;top:52px;z-index:20;background:var(--paper);}
.chip-f{font:600 12px var(--sans);color:var(--muted);background:var(--paper-2);border:1px solid var(--rule);border-radius:999px;padding:4px 12px;cursor:pointer;line-height:1.45;}
.chip-f:hover{color:var(--ink);border-color:var(--ink);}
.chip-f.on{color:#fff;background:var(--accent);border-color:var(--accent);}
.chip-f:focus-visible{outline:2px solid var(--accent);outline-offset:2px;}
.chip-f-divider{width:1px;height:18px;margin:0 6px;align-self:center;background:var(--rule);}
.feed-more{display:none;font:600 13px var(--sans);padding:8px 18px;border:1px solid var(--ink);border-radius:999px;background:var(--paper);cursor:pointer;}
.feed-more:hover{background:var(--ink);color:var(--paper);}
.feed-bar{max-width:var(--maxw);margin:14px auto 0;padding:0 var(--gutter);display:flex;align-items:center;gap:18px;font:12px var(--sans);color:var(--muted);}
.feed-bar a{color:var(--muted);text-decoration:underline;text-underline-offset:2px;}
.feed-empty{max-width:var(--maxw);margin:12px auto 0;padding:0 var(--gutter);font:13px var(--sans);color:var(--muted);}
.feed-empty a{color:var(--accent);}
.hidden{display:none!important;}
.ab-link{font:600 11px var(--sans);letter-spacing:.08em;text-transform:uppercase;color:var(--muted);border:1px solid var(--rule);border-radius:999px;background:none;padding:4px 12px;cursor:pointer;}
.ab-link:hover{color:var(--accent);border-color:var(--accent);}
body[data-ab="v2"] .hero__inner{grid-template-columns:1fr 1.05fr;}
body[data-ab="v2"] .feature__inner{grid-template-columns:1.05fr 1fr;}

/* фича-полоса (тёмная) */
.feature{margin-top:72px;background:var(--ink);color:var(--paper);}
.feature__inner{max-width:var(--maxw);margin:0 auto;padding:0 var(--gutter);display:grid;grid-template-columns:1fr 1.05fr;align-items:stretch;}
.feature__text{padding:64px 56px 64px 0;display:flex;flex-direction:column;justify-content:center;}
.feature__kicker{color:var(--accent);font-family:var(--sans);font-size:11px;font-weight:700;letter-spacing:.18em;text-transform:uppercase;margin-bottom:20px;}
.feature__title{font-family:var(--serif-display);font-weight:600;font-size:clamp(32px,3.6vw,50px);line-height:1.05;letter-spacing:-.025em;margin:0 0 22px;color:var(--paper);text-wrap:balance;}
.feature__title em{font-style:italic;font-weight:400;}
.feature__dek{font-family:var(--serif-body);font-size:17px;line-height:1.55;color:var(--on-ink);margin:0 0 24px;max-width:52ch;}
:root[data-theme="dark"] .feature__dek{color:#8B8578;}
.feature__byline{font-family:var(--sans);font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--on-ink);}
:root[data-theme="dark"] .feature__byline{color:#8B8578;}
.feature__byline strong{color:var(--paper);font-weight:600;}
:root[data-theme="dark"] .feature__byline strong{color:var(--ink);}
.feature__media{position:relative;min-height:480px;background:radial-gradient(120% 100% at 70% 30%,#6D4F3C 0%,#3A2A22 55%,#1A1310 100%);}
.feature__media figcaption{position:absolute;bottom:18px;right:18px;font-family:var(--sans);font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:#E9E4DA;}

/* мнения */
.opinion__grid{max-width:var(--maxw);margin:0 auto;padding:0 var(--gutter);display:grid;grid-template-columns:repeat(3,1fr);gap:40px;}
.op{border-top:1px solid var(--ink);padding-top:20px;display:flex;flex-direction:column;gap:14px;}
.op__quote{font-family:var(--serif-display);font-style:italic;font-weight:400;font-size:21px;line-height:1.25;letter-spacing:-.015em;color:var(--ink);margin:0;}
.op__quote a{color:var(--ink);}
.op__quote a:hover{color:var(--accent);}
.op__author{display:flex;align-items:center;gap:12px;margin-top:auto;padding-top:8px;}
.op__avatar{width:40px;height:40px;border-radius:50%;display:grid;place-items:center;font-family:var(--rubleny);font-size:13px;color:var(--paper);flex:0 0 40px;background:var(--ink-2);}
.op__name{font-family:var(--sans);font-size:13px;font-weight:600;color:var(--ink);}
.op__role{font-family:var(--sans);font-size:12px;color:var(--muted);}

/* периодичности (вместо подписки) */
.newsletter{margin-top:80px;border-top:1px solid var(--ink);border-bottom:1px solid var(--ink);background:var(--paper-2);}
.newsletter__inner{max-width:760px;margin:0 auto;padding:56px var(--gutter) 60px;text-align:center;}
.newsletter__kicker{font-family:var(--sans);font-size:11px;font-weight:700;letter-spacing:.18em;text-transform:uppercase;color:var(--accent);margin-bottom:14px;}
.newsletter__title{font-family:var(--serif-display);font-weight:600;font-size:clamp(28px,3vw,40px);line-height:1.08;letter-spacing:-.02em;margin:0 0 14px;color:var(--ink);text-wrap:balance;}
.newsletter__title em{font-style:italic;font-weight:400;}
.newsletter__dek{font-family:var(--serif-body);font-size:17px;color:var(--muted);margin:0 0 26px;}
.period-links{display:flex;gap:14px;justify-content:center;flex-wrap:wrap;}
.period-links a{border:1px solid var(--ink);padding:12px 22px;font-family:var(--sans);font-size:13px;font-weight:600;color:var(--ink);}
.period-links a:hover{background:var(--ink);color:var(--paper);}
.newsletter__fine{font-family:var(--sans);font-size:12px;color:var(--muted);margin-top:14px;}

/* ленты и прочие старые компоненты в новой оптике */
.main-grid{max-width:var(--maxw);margin:0 auto;padding:0 var(--gutter);display:grid;grid-template-columns:1fr 360px;gap:48px;align-items:start;}
.hero-grid{display:grid;grid-template-columns:1.65fr 1fr;gap:0 44px;margin-top:10px;align-items:start;}
.hero-main,.hero-side{border-top:3px solid var(--ink);padding-top:14px;}
.hero-card .rank{font-family:var(--serif-display);font-weight:700;font-size:30px;line-height:1;color:var(--accent);}
.hero-main .rank{font-size:54px;line-height:.85;}
.hero-rank-line{display:flex;align-items:baseline;gap:12px;margin-bottom:7px;}
.hero-card .hk{font-family:var(--sans);font-size:10.5px;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);}
.hero-main .hk{margin:10px 0 6px;}
.hero-card h3{font-family:var(--serif-display);font-weight:600;font-size:18.5px;line-height:1.24;margin:0 0 6px;}
.hero-card h3 a{color:var(--ink);}
.hero-card h3 a:hover{color:var(--accent);}
.hero-main h3{font-size:27px;line-height:1.16;letter-spacing:-.01em;margin:0 0 10px;}
.hero-card p{font-family:var(--serif-body);font-size:13.5px;line-height:1.45;color:var(--ink-2);margin:0 0 7px;}
.hero-main p{font-size:15.5px;line-height:1.5;margin-bottom:10px;}
.hero-meta{font-family:var(--sans);font-size:11px;color:var(--muted);}
.hero-meta a{color:var(--accent);}
.hero-side{display:flex;flex-direction:column;gap:22px;}
.hero-side .hero-card+.hero-card{border-top:1px solid var(--rule);padding-top:18px;}
@media (max-width:900px){.hero-grid{grid-template-columns:1fr;gap:26px;}}
.cat-block{border-top:2px solid var(--ink);margin:0 0 30px;padding-top:10px;break-inside:avoid;}
.cat-head{display:flex;align-items:baseline;gap:12px;padding:0 0 4px;}
.cat-head h3{font-family:var(--serif-display);font-weight:600;font-size:20px;color:var(--ink);margin:0;}
.cat-head .count{margin-left:auto;font-family:var(--sans);font-size:10.5px;font-weight:600;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);white-space:nowrap;}
.feed-cols{display:grid;grid-template-columns:1fr 1fr;gap:0 48px;align-items:start;margin-top:6px;}
.feed-cols>div{min-width:0;}
.fi{padding:13px 0;border-bottom:1px solid var(--rule);}
.fi:last-child{border-bottom:none;}
.fi h4{font-family:var(--serif-body);font-weight:600;font-size:15.5px;line-height:1.32;margin:0;}
.fi h4 a{color:var(--ink);}
.fi h4 a:hover{color:var(--accent);}
.fi .dek{font-family:var(--serif-body);font-size:13.5px;color:var(--ink-2);line-height:1.45;margin:4px 0 0;}
.fi .meta{font-family:var(--sans);font-size:11px;color:var(--muted);margin-top:5px;}
.fi .meta time{font-weight:700;color:var(--ink-2);}
.fi .also{font-family:var(--serif-body);font-size:12px;font-style:italic;color:var(--muted);margin-top:3px;}
.fi .topics{font-family:var(--sans);font-size:9.5px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);margin-top:6px;}
.fi-lead{padding-top:8px;}
.fi-lead h4{font-family:var(--serif-display);font-size:19px;line-height:1.22;}
.fi-lead .dek{font-size:14.5px;}
.fi.with-photo{display:grid;grid-template-columns:minmax(0,1fr) 104px;gap:0 14px;}
.fi.with-photo .fi-body{min-width:0;}
.fi-thumb{width:104px;height:70px;overflow:hidden;align-self:start;margin-top:2px;}
.cat-more{font-family:var(--sans);font-size:11px;color:var(--muted);padding:8px 0 2px;}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:0 40px;align-items:start;}
.grid2>*{min-width:0;}
@media (max-width:1000px){.feed-cols,.grid2{grid-template-columns:1fr;gap:0;}}
.news-item{padding:14px 0;border-bottom:1px solid var(--rule);}
.news-item:last-child{border-bottom:none;}
.news-item h4{font-family:var(--serif-display);font-weight:600;font-size:18px;line-height:1.25;margin-bottom:6px;color:var(--ink);}
.news-item h4 a{color:var(--ink);}
.news-item h4 a:hover{color:var(--accent);}
.news-item p{font-family:var(--serif-body);font-size:15px;color:var(--ink-2);line-height:1.5;}
.news-item .meta{font-family:var(--sans);font-size:12px;color:var(--muted);margin-top:6px;}
.news-item .meta .tg{color:var(--muted);}
.tchip{display:inline-block;font-family:var(--sans);font-size:10.5px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);border:1px solid var(--rule);padding:2px 8px;margin:6px 4px 0 0;}
.cl-card{border-top:1px solid var(--rule);padding:10px 0;}
.cl-card:first-child{border-top:none;padding-top:2px;}
.cl-head{display:flex;align-items:baseline;gap:4px;flex-wrap:wrap;}
.cl-name{font-family:var(--serif-display);font-weight:600;font-size:16px;color:var(--ink);}
.cl-card.gap .cl-name{color:var(--accent);}
.cl-samples{font-family:var(--serif-body);font-size:13px;color:var(--ink-2);margin-top:5px;line-height:1.5;}
.cl-samples a{color:var(--ink);}
.cl-samples a:hover{color:var(--accent);}
.cl-badge{display:inline-block;font-family:var(--sans);font-size:10px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--ink-2);border:1px solid var(--rule);padding:2px 8px;margin-left:6px;background:none;}
.cl-badge.cl-warn{color:var(--accent);border-color:var(--accent);}
.stchip{display:inline-block;font-family:var(--sans);font-size:10px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);border:1px solid var(--rule);padding:2px 8px;background:none;white-space:nowrap;}
.stchip.st-rise{color:var(--accent);border-color:var(--accent);}
.stchip.st-new{color:var(--ink);border-color:var(--ink);}
.side-head{font-family:var(--sans);font-size:11px;font-weight:700;letter-spacing:.16em;text-transform:uppercase;color:var(--ink);background:none;border-bottom:1px solid var(--ink);padding:0 0 8px;}
.side-head .sub{color:var(--muted);font-weight:500;letter-spacing:.04em;text-transform:none;}
.side-body{padding:12px 0;}
.tbl{width:100%;border-collapse:collapse;font-family:var(--sans);font-size:13px;}
.tbl th{background:none;color:var(--muted);text-align:left;padding:7px 10px;font-size:10.5px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;border-bottom:1px solid var(--ink);}
.tbl td{padding:8px 10px;border-bottom:1px solid var(--rule);vertical-align:top;color:var(--ink-2);}
.tbl tr:nth-child(even) td{background:transparent;}
.note{font-family:var(--sans);font-size:12.5px;color:var(--muted);margin-top:10px;line-height:1.6;border-left:2px solid var(--accent);padding-left:12px;}
.verdict{border-left:3px solid var(--accent);padding:10px 14px;font-family:var(--serif-body);font-size:15px;color:var(--ink-2);margin-top:12px;background:var(--paper-2);}
.verdict b{color:var(--accent);text-transform:uppercase;font-family:var(--sans);font-size:11px;letter-spacing:.12em;display:block;margin-bottom:4px;}
.bar-row .bt,.bar-wrap{background:var(--paper-2);}
.bar-fill{background:var(--ink-2);}
.bar-fill.hot{background:var(--accent);}
.bar-fill.cool{background:#4F5F53;}
.bar-fill.gold{background:#B4795A;}
.bar-fill.violet{background:#6D6079;}
.topic-row{display:grid;grid-template-columns:200px 1fr 120px 96px;gap:12px;align-items:center;padding:8px 0;border-bottom:1px solid var(--rule);font-family:var(--sans);font-size:13px;}
.topic-row:last-child{border-bottom:none;}
.topic-name{font-weight:600;color:var(--ink);}
.topic-name small{display:block;font-weight:400;color:var(--muted);font-size:11px;}
.kpi{background:none;border:none;border-top:1px solid var(--ink);border-radius:0;padding:12px 14px 12px 0;}
.kpi .num{font-family:var(--serif-display);font-weight:600;font-size:26px;color:var(--ink);line-height:1.05;}
.kpi .num small{font-size:11px;font-weight:600;color:var(--muted);}
.kpi .lbl{font-family:var(--sans);font-size:11.5px;color:var(--muted);margin-top:4px;}
.kpi.gold,.kpi.red,.kpi.green,.kpi.violet{border-top-color:var(--ink);}
.kpi-grid{display:grid;grid-template-columns:repeat(6,1fr);gap:0 28px;}
.cal-badge{flex-shrink:0;width:46px;height:44px;border:1px solid var(--ink);color:var(--ink);display:flex;flex-direction:column;align-items:center;justify-content:center;line-height:1;background:none;}
.cal-badge b{font-family:var(--serif-display);font-size:17px;font-weight:600;}
.cal-badge span{font-family:var(--sans);font-size:8.5px;text-transform:uppercase;color:var(--muted);margin-top:2px;letter-spacing:.08em;}
.cal-badge.gold{background:var(--ink);border-color:var(--ink);color:var(--paper);}
.cal-badge.gold span{color:var(--on-ink);}
:root[data-theme="dark"] .cal-badge.gold{background:var(--ink);color:var(--paper);}
.af-mini{display:flex;gap:12px;padding:9px 0;border-bottom:1px solid var(--rule);align-items:flex-start;}
.af-mini:last-child{border-bottom:none;}
.af-mini a{font-family:var(--serif-body);font-size:14.5px;font-weight:600;color:var(--ink);}
.af-mini a:hover{color:var(--accent);}
.af-daybar,.af-chips{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:16px;}
.af-chip{border:1px solid var(--rule);background:none;color:var(--muted);font-family:var(--sans);font-size:12.5px;font-weight:600;padding:7px 14px;cursor:pointer;}
.af-chip.on{background:var(--ink);border-color:var(--ink);color:var(--paper);}
.sec-grid{max-width:var(--maxw);margin:0 auto;padding:0 var(--gutter);display:grid;grid-template-columns:repeat(3,1fr);gap:40px;}
.sec-card{background:none;border:none;border-top:1px solid var(--ink);border-radius:0;padding:18px 0 0;display:flex;flex-direction:column;}
.sec-card .ic{display:none;}
.sec-card b{font-family:var(--serif-display);font-weight:600;font-size:19px;color:var(--ink);}
.sec-card .fig{font-family:var(--serif-display);font-size:22px;font-weight:600;color:var(--accent);margin-top:4px;}
.sec-card .fig small{font-family:var(--sans);font-size:10.5px;font-weight:600;color:var(--muted);letter-spacing:.08em;text-transform:uppercase;}
.sec-card p{font-family:var(--serif-body);font-size:14.5px;color:var(--muted);line-height:1.5;margin-top:8px;flex:1;}
.sec-card .go{font-family:var(--sans);font-size:12px;font-weight:600;color:var(--accent);margin-top:10px;}
.arch-item{display:flex;gap:14px;padding:10px 0;border-bottom:1px solid var(--rule);align-items:center;}
.arch-item:last-child{border-bottom:none;}
.arch-date{width:48px;height:46px;border:1px solid var(--ink);color:var(--ink);display:flex;flex-direction:column;align-items:center;justify-content:center;line-height:1;background:none;}
.arch-date b{font-family:var(--serif-display);font-size:17px;font-weight:600;}
.arch-date span{font-family:var(--sans);font-size:8.5px;color:var(--muted);margin-top:2px;text-transform:uppercase;letter-spacing:.08em;}
.btn{display:inline-block;border:1px solid var(--ink);color:var(--ink);background:none;font-family:var(--sans);font-size:12.5px;font-weight:600;padding:8px 16px;}
.btn:hover{background:var(--ink);color:var(--paper);}
.btn.gold{background:var(--ink);color:var(--paper);}
.btn.gold:hover{background:var(--accent);border-color:var(--accent);}
.util-bar-wrap{max-width:var(--maxw);margin:0 auto;padding:20px var(--gutter) 0;}
.util-bar{display:flex;gap:24px;align-items:center;flex-wrap:wrap;border-top:1px solid var(--rule);padding-top:14px;}
.util-bar a{font-family:var(--sans);font-size:12.5px;font-weight:500;color:var(--muted);}
.util-bar a:hover{color:var(--accent);}
.util-lbl{font-family:var(--sans);font-size:10.5px;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);}
.filters{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:18px;}
.fbtn{border:1px solid var(--rule);background:none;color:var(--muted);font-family:var(--sans);font-size:12.5px;font-weight:600;padding:7px 14px;cursor:pointer;}
.fbtn.active{background:var(--ink);border-color:var(--ink);color:var(--paper);}
.alert-banner{background:var(--accent);color:#fff;padding:12px var(--gutter);font-family:var(--sans);font-size:14px;font-weight:600;display:flex;align-items:center;gap:12px;flex-wrap:wrap;}
.alert-banner a{color:#fff;text-decoration:underline;}
.alert-banner .blink{animation:none;}
.ticker-wrap{background:var(--paper-2);color:var(--ink-2);border-bottom:1px solid var(--rule);overflow:hidden;position:relative;height:34px;}
.ticker-label{position:absolute;left:0;top:0;bottom:0;z-index:2;background:var(--accent);color:#fff;font-family:var(--sans);font-size:11px;font-weight:700;letter-spacing:.14em;display:flex;align-items:center;padding:0 14px;text-transform:uppercase;}
.ticker{display:flex;white-space:nowrap;animation:none;padding-left:130px;align-items:center;height:100%;font-family:var(--serif-body);font-size:14px;}
.ticker span{padding-right:56px;}
.ticker span b{color:var(--accent);}
.tone-bar{height:12px;background:linear-gradient(90deg,#B04848,#E3DED4 50%,#4F5F53);position:relative;}
.tone-pin{position:absolute;top:-4px;width:3px;height:20px;background:var(--ink);}
.tone-cat{font-family:var(--sans);font-size:11px;font-weight:600;border:1px solid var(--rule);padding:3px 9px;color:var(--ink-2);}
.fc-tbl{width:100%;border-collapse:collapse;font-family:var(--sans);font-size:13px;margin-top:10px;}
.fc-tbl th{text-align:left;padding:6px 10px;color:var(--muted);font-size:10.5px;text-transform:uppercase;letter-spacing:.1em;border-bottom:1px solid var(--ink);}
.fc-tbl td{padding:7px 10px;border-bottom:1px solid var(--rule);}
.fc-up{color:var(--accent);font-weight:700;} .fc-down{color:#4F5F53;font-weight:700;} .fc-flat{color:var(--muted);font-weight:700;}
.drone{width:24px;height:24px;border:1px solid var(--rule);display:flex;align-items:center;justify-content:center;font-size:12px;}
.hl{background:linear-gradient(transparent 62%,#E5C9B6 62%);}
:root[data-theme="dark"] .hl{background:linear-gradient(transparent 62%,#6D4F3C 62%);}
.wk-grid{max-width:var(--maxw);margin:0 auto;padding:0 var(--gutter);display:grid;grid-template-columns:1fr 340px;gap:48px;align-items:start;margin-top:16px;}
.wk-rail{display:flex;flex-direction:column;gap:20px;}
.wk-box{border-top:1px solid var(--ink);padding:12px 0;background:none;border-left:none;border-right:none;border-bottom:none;border-radius:0;}
.wk-box h4{font-family:var(--sans);font-size:10.5px;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);margin:0 0 10px;}
.wk-passport{border-top:1px solid var(--ink);border-left:none;background:none;padding:14px 0;margin-top:18px;display:flex;gap:18px;flex-wrap:wrap;align-items:baseline;border-radius:0;}
.wk-passport b{font-family:var(--serif-display);font-size:20px;font-weight:600;color:var(--ink);}
.wk-stamp{font-family:var(--sans);font-size:11px;font-weight:700;letter-spacing:.06em;padding:3px 10px;background:var(--paper-2);color:#4F5F53;border:1px solid var(--rule);}
.wk-stamp.wip{background:none;color:var(--accent);border-color:var(--accent);}
.now-panel{border-top:1px solid var(--ink);border-bottom:1px solid var(--rule);padding:18px 0;}
.now-alert{font-family:var(--sans);font-size:14px;font-weight:600;color:var(--ink);padding:6px 0;}
.now-alert.calm{color:#4F5F53;}
.now-alert.danger{color:var(--accent);}
.now-grid{display:grid;grid-template-columns:1.25fr 1fr .9fr;gap:32px;}
.now-col{border-left:1px solid var(--rule);padding-left:24px;}
.now-col:first-child{border-left:none;padding-left:0;}
.now-h{font-family:var(--sans);font-size:10.5px;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);margin-bottom:10px;}
.tl-row{display:flex;gap:12px;padding:7px 0;border-bottom:1px solid var(--rule);align-items:baseline;}
.tl-row:last-child{border-bottom:none;}
.tl-time{flex-shrink:0;font-family:var(--sans);font-weight:700;font-size:11.5px;color:var(--accent);width:46px;}
.tl-txt{font-family:var(--serif-body);font-size:14.5px;line-height:1.45;color:var(--ink-2);}
.tl-txt a{color:var(--ink);}
.tl-txt a:hover{color:var(--accent);}
.tl-src{font-family:var(--sans);color:var(--muted);font-size:11px;}
.now-line{font-family:var(--serif-body);font-size:14px;color:var(--ink-2);margin-top:4px;line-height:1.5;}
.now-line b{color:var(--ink);}
/* v4: алерт-полоса безопасности */
.alertstrip{background:#5d0f13;color:#fff;}
.alertstrip__inner{max-width:var(--maxw);margin:0 auto;padding:9px var(--gutter);display:flex;flex-direction:column;gap:5px;}
body[data-theme="dark"] .alertstrip{background:#7d171d;}
.alert-row{display:flex;gap:9px;align-items:center;font-family:var(--serif-body);font-size:14.5px;line-height:1.4;}
.alert-row a{color:#fff;font-weight:600;text-decoration:none;}
.alert-row a:hover{text-decoration:underline;}
.alert-dot{flex-shrink:0;width:8px;height:8px;border-radius:50%;background:#ff6b6b;box-shadow:0 0 0 0 rgba(255,107,107,.7);animation:alertpulse 1.6s infinite;}
@keyframes alertpulse{0%{box-shadow:0 0 0 0 rgba(255,107,107,.6);}70%{box-shadow:0 0 0 7px rgba(255,107,107,0);}100%{box-shadow:0 0 0 0 rgba(255,107,107,0);}}
.alert-time{margin-left:auto;flex-shrink:0;font-family:var(--sans);font-size:12px;color:rgba(255,255,255,.85);font-weight:700;}
.now-num{font-family:var(--serif-display);font-size:26px;font-weight:600;color:var(--ink);line-height:1.1;}
.now-num small{font-family:var(--sans);font-size:11px;font-weight:600;color:var(--muted);}
.lead-grid{display:grid;grid-template-columns:1.45fr 1fr;gap:48px;}
.lead-main{border-top:1px solid var(--ink);padding-top:14px;}
.lead-main h2{font-family:var(--serif-display);font-weight:600;font-size:30px;line-height:1.1;letter-spacing:-.02em;color:var(--ink);margin-bottom:10px;}
.lead-main h2 a{color:var(--ink);}
.lead-main h2 a:hover{color:var(--accent);}
.lead-main p{font-family:var(--serif-body);font-size:17px;color:var(--ink-2);line-height:1.5;}
.lead-side{display:flex;flex-direction:column;gap:20px;}
.lead-card{border-top:1px solid var(--rule);padding-top:12px;}
.lead-card h3{font-family:var(--serif-display);font-weight:600;font-size:19px;line-height:1.2;color:var(--ink);}
.lead-card h3 a{color:var(--ink);}
.lead-card h3 a:hover{color:var(--accent);}
.lead-card p{font-family:var(--serif-body);font-size:14.5px;color:var(--muted);line-height:1.5;}
.lead-kicker{font-family:var(--sans);font-size:10.5px;font-weight:700;letter-spacing:.16em;text-transform:uppercase;color:var(--accent);margin-bottom:8px;}
.lead-meta{font-family:var(--sans);font-size:12px;color:var(--muted);margin-top:8px;}
.lead-meta a{color:var(--muted);}
.more-heads{columns:2;column-gap:36px;margin-top:8px;}
.more-heads a{display:block;font-family:var(--serif-display);font-weight:600;font-size:16px;line-height:1.3;color:var(--ink);padding:7px 0;border-bottom:1px solid var(--rule);break-inside:avoid;}
.more-heads a:hover{color:var(--accent);}
.more-heads a span{font-family:var(--sans);color:var(--muted);font-weight:400;font-size:11.5px;display:block;}

/* подвал — единый, см. footer.FOOTER_CSS */
.footer h3{color:var(--paper);}

/* печать */
.pm-mast{text-align:center;border-bottom:3px double var(--ink);padding-bottom:4mm;}
.pm-title{font-family:var(--rubleny);font-weight:900;text-transform:uppercase;letter-spacing:.08em;font-size:40pt;line-height:1;margin:0;color:var(--ink);}
.pm-line{font-family:var(--sans);font-size:8.5pt;letter-spacing:1.2px;text-transform:uppercase;margin-top:2.5mm;color:var(--muted);}
.pm-line b{color:var(--ink);}
.pm-kicker{font-family:var(--sans);font-size:8pt;letter-spacing:2px;text-transform:uppercase;color:var(--accent);font-weight:700;margin:3mm 0 1.5mm;}
.pm-lead-h{font-family:var(--serif-display);font-weight:600;font-size:20pt;line-height:1.15;margin:0 0 2.5mm;color:var(--ink);}
.pm-deck{font-family:var(--serif-body);font-size:10.5pt;font-style:italic;color:var(--ink-2);line-height:1.45;margin:0 0 3mm;}
.cols{column-count:3;column-gap:6mm;column-rule:.5pt solid var(--rule);}
.cols p{font-family:var(--serif-body);font-size:9.3pt;line-height:1.42;margin:0 0 2.2mm;text-align:justify;hyphens:auto;}
.pm-h3{font-family:var(--sans);font-size:9pt;font-weight:700;text-transform:uppercase;letter-spacing:1.4px;border-top:1.2pt solid var(--ink);padding-top:1.4mm;margin:3mm 0 1.8mm;break-after:avoid;}
.pm-item{margin-bottom:2.4mm;break-inside:avoid;}
.pm-item b{font-family:var(--serif-display);font-size:9.6pt;line-height:1.25;display:block;}
.pm-item span{font-family:var(--serif-body);font-size:8.6pt;color:var(--muted);line-height:1.35;display:block;}
.pm-item i{font-family:var(--sans);font-size:7.6pt;color:var(--muted);font-style:normal;}
.pm-box{border:1pt solid var(--ink);padding:3mm;margin:3mm 0;break-inside:avoid;}
.pm-box h4{font-family:var(--sans);font-size:9pt;text-transform:uppercase;letter-spacing:1.4px;margin:0 0 2mm;border-bottom:.8pt solid var(--ink);padding-bottom:1.2mm;}
.pm-box ul{list-style:none;margin:0;padding:0;}
.pm-box li{font-family:var(--serif-body);font-size:8.8pt;line-height:1.4;margin-bottom:1.4mm;}
.pm-box li b{color:var(--accent);}
.pm-stats{display:flex;gap:4mm;justify-content:space-between;margin:3mm 0;break-inside:avoid;}
.pm-stat{flex:1;text-align:center;border:.8pt solid var(--ink);padding:2mm 1mm;}
.pm-stat b{display:block;font-family:var(--serif-display);font-size:15pt;font-weight:600;}
.pm-stat span{font-family:var(--sans);font-size:7.4pt;text-transform:uppercase;letter-spacing:.8px;color:var(--muted);}
.pm-colophon{border-top:3px double var(--ink);margin-top:4mm;padding-top:2mm;font-family:var(--sans);font-size:7.6pt;color:var(--muted);line-height:1.5;display:flex;justify-content:space-between;gap:6mm;}
.pm-page{position:absolute;bottom:4mm;right:13mm;font-family:var(--sans);font-size:8pt;color:var(--muted);}
.pm-ed{font-family:var(--serif-body);font-size:9.3pt;line-height:1.5;text-align:justify;}
.pm-ed p{margin:0 0 2.2mm;}
@media (max-width:1100px){
  .hero__inner,.lead-grid,.feature__inner,.wk-grid,.main-grid{grid-template-columns:1fr;}
  .hero__media{aspect-ratio:16/9;}
  .brief-row{grid-template-columns:1fr;row-gap:3px;}
  .brief-t,.brief-k{grid-column:1;}
  .brief-k{white-space:normal;}
  .mostread__inner{grid-template-columns:1fr;gap:18px;}
  .mostread__list{grid-template-columns:repeat(2,1fr);row-gap:18px;}
  .mostread__list li{padding-left:16px;}
  .mostread__list li:nth-child(odd){border-left:0;padding-left:0;}
  .grid{grid-template-columns:repeat(2,1fr);}
  .feature__text{padding:48px 0;}
  .feature__media{min-height:360px;}
  .opinion__grid{grid-template-columns:1fr 1fr;}
  .now-grid{grid-template-columns:1fr;}
  .now-col{border-left:none;padding-left:0;border-top:1px solid var(--rule);padding-top:12px;}
  .kpi-grid{grid-template-columns:repeat(3,1fr);}
  .sec-grid{grid-template-columns:repeat(2,1fr);}
  .more-heads{columns:1;}
  .topic-row{grid-template-columns:140px 1fr 90px;}
  .topic-row .sparkcell{display:none;}
}
@media (max-width:720px){
  :root{--gutter:20px;}
  body{font-size:16px;}
  .masthead__inner{grid-template-columns:1fr;text-align:center;gap:8px;}
  .grid,.sec-grid,.opinion__grid{grid-template-columns:1fr;}
  .mostread__list{grid-template-columns:1fr;}
  .mostread__list li{border-left:0;padding-left:0;border-top:1px solid var(--rule);padding-top:14px;}
  .mostread__list li:first-child{border-top:0;padding-top:0;}
  .sec-head{flex-direction:column;align-items:flex-start;gap:6px;}
  .kpi-grid{grid-template-columns:repeat(2,1fr);}
}
.mast-inner{display:grid;grid-template-columns:1fr auto 1fr;align-items:center;gap:24px;max-width:var(--maxw);margin:0 auto;padding:26px var(--gutter) 20px;}
.mast-side{font-family:var(--sans);font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);line-height:1.7;}
.mast-side--right{text-align:right;}
.mast-actions{display:flex;gap:14px;justify-content:flex-end;align-items:center;margin-top:10px;}
.mast-actions a{font-family:var(--sans);font-size:11px;font-weight:500;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);border-bottom:1px solid var(--rule);}
.mast-actions a:hover{color:var(--accent);border-color:var(--accent);}
.now-panel-wrap{border-bottom:1px solid var(--rule);}
@media (max-width:900px){.mast-inner{grid-template-columns:1fr;text-align:center;gap:10px;}.mast-side,.mast-side--right{text-align:center;}.mast-actions{justify-content:center;}}
@media print{
  .nav,.ticker-wrap,.filters,.print-btn,.theme-btn,.nav-toggle,.util-bar-wrap{display:none!important;}
  body{background:#fff;}
}
"""

CSS = CSS + footer.FOOTER_CSS

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
@media (max-width:900px){.lead-grid{grid-template-columns:1fr;}.tiles{grid-template-columns:repeat(2,1fr);}}
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


def save_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


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


SENT_SPLIT = re.compile(r"(?<=[.!?…])\s+")



ALERT_RE = re.compile(
    r"(ракетн\w*|беспилотн\w*|бпла)\W{0,40}опасност"
    r"|опасност\W{0,40}(бпла|беспилотн\w*|ракетн\w*)"
    r"|план\s*«?ковер"
    r"|при[ёе]м и выпуск\W{0,30}ограничен"
    r"|ограничени\w*\W{0,40}(аэропорт|при[ёе]м)"
    r"|аэропорт\w*\W{0,40}ограничен", re.I)


CASUALTY_RE = re.compile(r"погиб|пострада|ранен|убит|разруш|поврежд|сбит|упал|обломк", re.I)
# «в программе» — только с двоеточием/тиром (афишный формат «В программе: в 16:00 — …»);
# вариант с пробелом давал ложняки на новостях: «в программе посещения Минска», «в программе
# Президента», «в Программе поддержки местных инициатив», «в программе „Первые лица“ на ГТРК».
PROMO_RE = re.compile(r"(приглашаем|жд[её]м вас|приходите|в программе\s*[:—]|анонс|открытие сезона|розыгрыш\w*\s+(?:билет\w*|приз\w*|подарк\w*|мест\w*))", re.I)


def is_alert(it):
    """Служебное уведомление о режиме/ограничениях: не материал и не сюжет.
    Сообщение об атаке с последствиями (погибшие/сбитые/повреждения) — новость, не уведомление."""
    blob = (it.get("title") or "") + " " + (it.get("text") or "")[:200]
    if not ALERT_RE.search(blob):
        return False
    return not CASUALTY_RE.search(blob)


def is_promo(it):
    """Анонс-завлекаловка (фестивали, открытия сезонов): не сюжет недели."""
    blob = (it.get("title") or "") + " " + (it.get("text") or "")[:150]
    return bool(PROMO_RE.search(blob))


def norm_sq(s):
    return re.sub(r"[^a-zа-яё0-9]", "", (s or "").lower())


def strip_title_lead(text, title):
    """Убирает из начала текста повтор заголовка (частая болезнь RSS и TG-постов)."""
    t = (text or "").strip()
    ti = norm_sq(title)
    if not ti or not t:
        return t
    parts = SENT_SPLIT.split(t)
    while parts:
        p0 = norm_sq(parts[0])
        if not p0:
            parts.pop(0)
            continue
        if p0 == ti or p0 in ti or ti in p0:
            parts.pop(0)
            continue
        break
    return " ".join(parts)


def clip_sentences(text, limit):
    text = CHANNEL_TAIL_RE.sub("", text or "").strip()
    parts = SENT_SPLIT.split(text)
    tail_cut = False
    if parts and not re.search(r'[.!?…»]"?$', parts[-1].strip()):
        if len(parts) > 1:
            parts = parts[:-1]
            tail_cut = True
        else:
            cut = text[:limit].rsplit(" ", 1)[0]
            return cut.rstrip(" ,;:—-") + "…"
    full = " ".join(parts)
    if len(full) <= limit:
        return full + ("…" if tail_cut else "")
    out = ""
    for p in parts:
        if not out:
            out = p
            continue
        if len(out) + 1 + len(p) <= limit:
            out += " " + p
        else:
            break
    return out + "…"


def photo_src(it):
    """Годный src изображения: локальное зеркало — только если файл действительно
    лежит в репозитории (иначе на Pages будет 404 и картинка молча исчезнет);
    запасной вариант — исходный удалённый URL. Возвращает None, если ничего нет.

    Историческая причина: CI скачивал фото в assets/photos и генерировал ссылки
    на них, но список `git add` в воркфлоу не включал assets — 635 из 835 зеркал
    не доехали до репозитория (найдено 15.09.2026)."""
    pl = it.get("photo_local")
    if pl and os.path.exists(os.path.join(BASE, pl)):
        return pl                       # относительный путь — prefix добавит вызывающий
    ph = it.get("photo") or ""
    if ph.startswith("http"):
        return ph
    if ph.startswith("//"):
        return "https:" + ph
    return None


def photo_img(it, prefix, style):
    src = photo_src(it)
    if not src:
        return ""
    if not src.startswith("http"):
        src = prefix + src
    alt_text = present_title(it, 120) if it else ""
    return (f'<img src="{esc(src)}" alt="{esc(alt_text)}" loading="lazy" style="{style}" '
            f'onerror="this.style.display=\'none\'">')


def dek_p(it, limit, cls=""):
    """Дек без повтора заголовка; пустой — не выводится."""
    ttl = it.get("title") or ""
    body = strip_title_lead(it.get("text") or "", ttl)
    # лид-дедуп v4: первое предложение почти дублирует заголовок (≥70% биграмм) — съедаем
    parts = SENT_SPLIT.split(body)
    if len(parts) > 1 and similarity(parts[0], ttl) > 0.7:
        body = " ".join(parts[1:])
    d = clip_sentences(body, limit)
    cls_attr = f' class="{cls}"' if cls else ""
    return f"<p{cls_attr}>{esc(d)}</p>" if len(d) >= 40 else ""


def feed_title(it, limit):
    """Заголовок для ленты: достройка оборванных без точки заголовков по тексту поста."""
    t = (it.get("title") or "").strip()
    txt = (it.get("text") or "").strip()
    nt = nice_title(it, limit)
    if (txt and len(txt) > len(t) + 12
            and not re.search(r'[.!?…]["»\']?$', t)
            and norm_sq(txt).startswith(norm_sq(t)[:40])):
        ext = clip_sentences(txt, max(limit, 120))
        if ext and not ext.endswith("…") and len(ext) > len(nt):
            return ext
    return nt


def feed_dek_p(it, limit, title=None):
    """Дек ленты без повтора заголовка: нормализованное вхождение + лексический оверлап.
    title — уже отрендеренный заголовок (feed_title может достраивать его из текста)."""
    ttl = title if title is not None else (it.get("title") or "")
    body = strip_title_lead(it.get("text") or "", ttl)
    d = clip_sentences(body, limit)
    if len(d) < 40:
        return ""
    tn = norm_sq(ttl)
    dn = norm_sq(d)
    if tn and dn and (dn in tn or tn in dn):
        return ""
    tw = set(re.findall(r"[а-яёa-z0-9]{4,}", ttl.lower()))
    dw = set(re.findall(r"[а-яёa-z0-9]{4,}", d.lower()))
    if dw and tw and len(tw & dw) / len(dw) > 0.7:
        return ""
    return f'<p class="dek">{esc(d)}</p>'


def src_label(it):
    """Короткая метка источника: TG-каналы — @username, остальные — имя."""
    if it.get("source_type") == "tg":
        return "@" + str(it.get("channel") or it.get("source") or "")
    return str(it.get("source", ""))


def plural_ru(n, one, few, many):
    n10, n100 = n % 10, n % 100
    if n10 == 1 and n100 != 11:
        return one
    if 2 <= n10 <= 4 and not (12 <= n100 <= 14):
        return few
    return many


BOUND_PAT = re.compile(r"[.!?…][»\"\']?\s|\s—\s|\s–\s(?<=\s)\s-\s|:\s")


def nice_title(it, limit):
    """Заголовок без обрыва. Если коллектор обрезал заголовок TG-поста (… на конце):
    1) первое предложение текста, если короткое; 2) последняя сильная граница
    (конец предложения, тире, дефис-разделитель, двоеточие) в пределах лимита."""
    t = (it.get("title") or "").strip()
    if not t.endswith("\u2026"):
        return clip_words(t, limit)
    txt = (it.get("text") or "").strip()
    if len(txt) <= len(t):
        return clip_words(t, limit)
    sent = clip_sentences(txt, limit + 90)
    if sent and not sent.endswith("\u2026") and len(sent) <= limit + 60:
        return sent
    seg = txt[:limit]
    best = 0
    for m in re.finditer(r"[.!?…][»\"\']?\s|\s—\s|\s-\s|:\s", seg):
        if m.start() >= 30:
            best = m.end()
    if best:
        return seg[:best].rstrip(" ,;:.!…—–-\"\'")
    return clip_words(seg, limit)


def clip_words(text, limit):
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return cut.rstrip(" ,;:—-") + "…"


# ------------------------------------------------------------------ v4: гигиена заголовка
# Своя копия EMOJI_STRIP_RE (collector.py) — не тянем импорт тяжёлого коллектора в рендер.
EMOJI_STRIP_RE = re.compile(r"[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF\uFE0F\u200D\u203C\u2049\u2B50\u2705\u274C\u2764]+")
VARIATION_SEL_RE = re.compile(r"[\uFE0E\uFE0F]")
QUOTES_RE = re.compile(r"[\u00AB\u00BB\u201E\u201C\u201D\u2018\u2019]")
HASHTAG_RE = re.compile(r"(?<!\w)#[\wа-яё_-]+", re.I)
FREE_SPACE_RE = re.compile(r"\s{2,}")
CUT_TAIL_OPEN = re.compile(r"[,;:—–-]$|,\s*$")
DANGLE_OPEN = ("и", "в", "во", "на", "с", "со", "по", "о", "об", "от", "к", "ко",
               "для", "из", "у", "за", "над", "под", "при", "про", "без", "не", "или",
               "а", "но", "что", "как", "где")


def _normalize_quotes(s):
    """Приводит кавычки к «ёлочкам» и типографскому апострофу."""
    return QUOTES_RE.sub(lambda m: "\u00AB" if m.group() in "\u201E\u00AB" else "\u00BB", s)


def _strip_title_junk(t):
    """Снимает эмодзи, селекторы, хэштеги и уплотняет пробелы."""
    t = EMOJI_STRIP_RE.sub("", t)
    t = VARIATION_SEL_RE.sub("", t)
    t = HASHTAG_RE.sub("", t)
    return FREE_SPACE_RE.sub(" ", t).strip(" -—,")


_KNOWN_ABBREVS = frozenset({
    "ПВО", "ЕГЭ", "УФСБ", "ФСБ", "МЧС", "ГИБДД", "ООО", "АО", "ПАО", "НКО",
    "СКР", "УМВД", "ГУВД", "ФМС", "ЕС", "ООН", "НАТО", "СНГ", "ЕАЭС", "ДПС",
    "МРЭО", "ПФР", "ФНС", "КФХ", "СНТ", "ДНК", "ОМС", "ОМВД", "ФССП", "МВД",
    "ФСИН", "ФТС", "ЦВК", "ЕИС", "ОПС", "СОБЕС", "ТКО", "МФЦ", "МФО", "ЦОД",
    "ГИС", "ЕП", "ГПС", "ЗАГС", "УФНС", "УФССП", "ГИТ", "КМВД", "ЦУР",
    "ВС", "КС", "ВАС", "ВЦИОМ", "Левада", "ДОУ", "ОО",
})


def _decap(t):
    """КАПС → обычный регистр. Только для «кричащих» заголовков (≥60% заглавных):
    известные аббревиатуры (ПВО, ЕГЭ, УФСБ — из словаря) сохраняются, остальное
    в нижний регистр. Обычный прописной заголовок не трогаем."""
    letters = [c for c in t if c.isalpha()]
    if not letters:
        return t
    upper_ratio = sum(1 for c in letters if c.isupper()) / len(letters)
    if upper_ratio < 0.6:
        return t
    abbrevs = re.findall(r"[А-ЯЁA-Z]{2,}", t)
    out = t.lower()
    for abbr in abbrevs:
        if abbr in _KNOWN_ABBREVS:
            out = out.replace(abbr.lower(), abbr, 1)
    return out


def _head_from_text(it, limit):
    """Сборка заголовка из первого абзаца, если обрыв вышел на предлоге/союзе."""
    txt = _strip_title_junk(it.get("text") or "")
    if not txt:
        return ""
    first = clip_sentences(txt, limit)
    if first and not first.endswith("\u2026"):
        return first
    return clip_words(first or txt, limit)


def _dangling(cut):
    """True, если обрывку заканчивается открывающим предлогом/союзом или знаком."""
    if CUT_TAIL_OPEN.search(cut):
        return True
    last = cut.rsplit(" ", 1)[-1].lower().strip(" ,;:—-«»\"'")
    return last in DANGLE_OPEN


def present_title(it, limit):
    """Заголовок v4: эмодзи/хэштеги сняты, КАПС нормирован, кавычки — «ёлочки»,
    обрезка ≤limit по границе слова; обрыв на предлоге/союзе или оборванный
    коллектором заголовок (…) перезапускает сборку из первого абзаца. Отдаёт
    только отображение; полную версию кладёт в атрибут `title` вызывающий."""
    raw = _strip_title_junk(it.get("title") or "")
    if raw.endswith("\u2026"):
        rebuilt = _head_from_text(it, limit)
        if rebuilt:
            raw = rebuilt
    if not raw:
        raw = _head_from_text(it, limit) or "(без заголовка)"
    raw = _decap(raw)
    raw = _normalize_quotes(raw)
    if len(raw) <= limit:
        # длинный «и»/«в» на конце без оборванного знака — тоже обрыв смысла
        if _dangling(raw):
            rebuilt = _head_from_text(it, limit)
            if rebuilt and not rebuilt.endswith("\u2026"):
                return rebuilt
        return raw
    if _dangling(raw):
        rebuilt = _head_from_text(it, limit)
        if rebuilt and not rebuilt.endswith("\u2026"):
            return rebuilt
    cut = clip_words(raw, limit)
    if _dangling(cut):
        rebuilt = _head_from_text(it, limit)
        if rebuilt and not rebuilt.endswith("\u2026"):
            return rebuilt
    return cut


def similarity(a, b):
    """Доля общих нормализованных биграмм из короткой строки (лид-дедуп)."""
    norm = lambda s: re.sub(r"[^a-zа-яё0-9]", "", (s or "").lower())
    x, y = norm(a), norm(b)
    if not x or not y:
        return 0.0
    small, big = (x, y) if len(x) <= len(y) else (y, x)
    n = len(small)
    if n < 3:
        return 1.0 if small in big else 0.0
    bigrams = {small[i:i + 2] for i in range(n - 1)}
    return sum(1 for i in range(len(big) - 1) if big[i:i + 2] in bigrams) / max(1, n - 1)


# ------------------------------------------------------------------ v4: время
def fmt_time(iso, now, mode="card"):
    """Единый формат времени. mode: card — «15.09, 22:22»; rel — «18 мин назад»;
    word — «15 сентября» для заголовков."""
    dt = local_dt(iso)
    if not dt:
        return ""
    if mode == "word":
        months = ("января", "февраля", "марта", "апреля", "мая", "июня",
                  "июля", "августа", "сентября", "октября", "ноября", "декабря")
        return f"{dt.day} {months[dt.month - 1]}"
    if mode == "rel":
        delta = now - dt
        sec = int(delta.total_seconds())
        if sec < 60:
            return "только что"
        if sec < 3600:
            return f"{sec // 60} мин назад"
        if sec < 86400:
            return f"{sec // 3600} ч назад"
        days = sec // 86400
        if days == 1:
            return "вчера"
        if days < 7:
            return f"{days} дн назад"
        return dt.strftime("%d.%m.%Y")
    return dt.strftime("%d.%m, %H:%M")


# ------------------------------------------------------------------ v4: афиша (fallback-цепочка)
def pick_afisha(an, day, limit=4):
    """Цепочка афиши v4: сегодня → завтра → выходные → 7 дней → культура недели.
    Возвращает (заголовок, события, дата)."""
    cal = (an or {}).get("calendar", [])
    ev = lambda d: [e for e in cal if e.get("date") == d.isoformat()][:limit]

    today_ev = ev(day)
    if today_ev:
        return "Сегодня в области", today_ev, day

    tomorrow = day + timedelta(days=1)
    tm_ev = ev(tomorrow)
    if tm_ev:
        return "Завтра", tm_ev, tomorrow

    for off in range(2, 8):
        d = day + timedelta(days=off)
        if d.weekday() >= 5:
            we = ev(d)
            if we:
                return f"Выходные · {d:%d.%m}", we, d
            break

    for off in range(1, 8):
        d = day + timedelta(days=off)
        wk = ev(d)
        if wk:
            return "Ближайшие события", wk, d

    week_ev = []
    for off in range(2, 15):
        week_ev += ev(day + timedelta(days=off))
    if week_ev:
        return "Культура недели", week_ev[:limit], day
    return "Сегодня в области", [], day


# ------------------------------------------------------------------ v4: кросс-дедуп полосы
class ShownIds:
    """Реестр показанных id на страницу: блок не повторяет материал выше."""

    def __init__(self):
        self._seen = set()

    def add(self, it):
        self._seen.add(it.get("id"))

    def has(self, it):
        return it.get("id") in self._seen

    def first(self, it):
        """True, если материала ещё не было на полосе; добавляет его в реестр."""
        if not it or it.get("id") in self._seen:
            return False
        self._seen.add(it.get("id"))
        return True


# ------------------------------------------------------------------ v4: скоринг героя
def sig_value(it, cfg):
    """Значимость темы: подрубрика → категория → прочее."""
    sig = cfg.get("settings", {}).get("significance", {})
    sub = it.get("sub_category")
    if sub and sub in sig:
        return sig[sub]
    cat = it.get("category")
    if cat in sig:
        return sig[cat]
    return sig.get("default", 0.15)


def hero_score(it, trends, now, cfg):
    """Формула v4: W1·значимость + W2·охват + W3·свежесть + W4·источник − P·промо."""
    comps, pen = hero_components(it, trends, now, cfg)
    return round(sum(v for v, _k, _h in comps) + pen, 2)


TIER_LABEL = {1: "официальные источники", 2: "СМИ и верифицированные каналы",
              3: "анонимные каналы", 0: "источники"}
TIER_REL = {1: 1.0, 2: 0.7, 3: 0.4}


def _rus_views(v):
    if not v:
        return "0"
    if v >= 1_000_000:
        return f"{v/1_000_000:.1f} млн".replace(".0 млн", " млн")
    if v >= 1000:
        return f"{v/1000:.1f} тыс.".replace(".0 тыс.", " тыс.")
    return str(int(v))


def hero_components(it, trends, now, cfg):
    """Слагаемые скоринга списком (вес, ключ, человекочитаемое) + штраф за промо.
    «Охват» и «свежесть» могут отсутствовать (нет просмотров / нет времени)."""
    w = cfg.get("settings", {}).get("scoring_weights", {})
    W = lambda k, d: w.get(k, d)
    comps = []
    comps.append((W("significance", 30) * sig_value(it, cfg), "significance",
                  _topic_label(it, cfg)))
    views = it.get("views") or 0
    reach = W("reach", 25) * min(math.log1p(views) / math.log1p(100000), 1.0)
    comps.append((reach, "reach", f"{_rus_views(views)} просмотров" if views else "охват не измерен"))
    pub = local_dt(it.get("published"))
    if pub:
        age_h = max(0.0, (now - pub).total_seconds() / 3600)
        comps.append((W("freshness", 20) * math.exp(-age_h / 12), "freshness",
                      fmt_time(pub.isoformat(), now, "rel")))
    tier = it.get("tier")
    comps.append((W("reliability", 15) * TIER_REL.get(tier, 0.5), "reliability",
                  TIER_LABEL.get(tier, "источники")))
    penalty = -W("promo_penalty", 0.6) * 10 if is_promo(it) else 0.0
    return comps, penalty


# человекочитаемые названия факторов для строки «Почему это главное»
_FACTOR_HUMAN = {
    "significance": "значимость",
    "reach": "охват",
    "freshness": "свежесть",
    "reliability": "надёжность источника",
}


def _topic_label(it, cfg):
    """Человекочитаемое имя рубрики/подрубрики для строки «почему это главное»."""
    subs = {s.get("id"): s.get("name") for s in cfg.get("subcategories", [])}
    cats = {c.get("id"): c.get("name") for c in cfg.get("categories", [])}
    if it.get("sub_category") and it["sub_category"] in subs:
        return subs[it["sub_category"]]
    return cats.get(it.get("category"), "тема дня")


def hero_factors(it, trends, now, cfg):
    """Топ-2 фактора скоринга: [(название, пояснение)] для строки «Почему это главное»."""
    comps, _pen = hero_components(it, trends, now, cfg)
    comps.sort(reverse=True, key=lambda x: x[0])
    return [(_FACTOR_HUMAN.get(k, k), h) for _v, k, h in comps[:2]]


def pick_hero(pool, trends, now, cfg):
    """Герой полосы: максимум hero_score с правилом стабильности (3 ч / 15%).
    Состояние прошлого героя хранится в data/hero_state.json, чтобы полоса не
    «прыгала» между пересборками."""
    scored = []
    for it in pool:
        copy = dict(it)
        copy["_score"] = hero_score(it, trends, now, cfg)
        scored.append(copy)
    scored.sort(key=lambda x: -x["_score"])
    if not scored:
        return None
    best = scored[0]
    st_path = os.path.join(DATA, "hero_state.json")
    st = load_json(st_path, {})
    prev = next((x for x in scored if x.get("id") == st.get("id")), None)
    hero = best
    if prev is not None and not hero_stable(prev, best, now, cfg):
        hero = prev
    try:
        save_json(st_path, {"id": hero.get("id"), "score": hero.get("_score"),
                            "published": hero.get("published"),
                            "chosen_at": now.isoformat()})
    except OSError:
        pass
    return hero


def hero_stable(prev, new, now, cfg):
    """Правило стабильности: не чаще раза в 3 ч, перевес ≥15% (или героя нет вовсе)."""
    w = cfg.get("settings", {}).get("scoring_weights", {})
    h_stab = w.get("hero_stability_h", 3)
    margin = w.get("hero_stability_margin", 0.15)
    if prev is None:
        return True
    if prev.get("id") == new.get("id"):
        return True
    prev_pub = local_dt(prev.get("published"))
    if prev_pub and (now - prev_pub).total_seconds() / 3600 < h_stab:
        return False
    prev_s = prev.get("_score") or 0.0
    new_s = new.get("_score") or 0.0
    return new_s >= prev_s * (1 + margin)


# ------------------------------------------------------------------ v4: отчёт качества выпуска
def quality_report(store, cfg, day):
    """8 метрик выпуска: полные заголовки, дубли, промо в топ-5, рубрики,
    время алерта, пустые блоки. Пишем в data/quality_report.json."""
    now = datetime.now(UTC4)
    win_start = datetime.combine(day, datetime.min.time(), tzinfo=UTC4) - timedelta(hours=30)
    window = [it for it in store if not it.get("dup_of")
              and local_dt(it.get("published")) and local_dt(it["published"]) >= win_start]
    n = len(window)

    full_titles = sum(1 for it in window if present_title(it, 90) == _strip_title_junk(it.get("title") or "").strip())
    promo_in_top5 = sum(1 for it in window if it.get("views") and is_promo(it)) / max(1, n)
    cats = Counter(it.get("category") for it in window)
    top_cat_share = cats.most_common(1)[0][1] / max(1, n) if cats else 0.0
    an = load_json(os.path.join(DATA, "analytics.json")) or {}
    events_today = sum(1 for e in an.get("calendar", [])
                       if e.get("date") == day.isoformat())
    report = {
        "date": day.isoformat(),
        "items": n,
        "full_title_share": round(full_titles / max(1, n), 3),
        "promo_share": round(promo_in_top5, 3),
        "dups_on_page": 0,           # заполняется генератором при сборке полосы
        "top_category_share": round(top_cat_share, 3),
        "top_category": cats.most_common(1)[0][0] if cats else None,
        "events_today": events_today,
        "last_alert_lag_min": None,  # заполняется генератором
        "empty_blocks": [],          # заполняется генератором
    }
    return report


# ------------------------------------------------------------------ v4: бейджи и паспорт факта
MATERIAL_LABELS = {"news": "Новость", "opinion": "Мнение", "chronicle": "Хроника",
                   "announce": "Анонс", "alert": "Алерт"}

# (материал, цвет текста, цвет подложки) для чипов
TYPE_STYLE = {
    "alert": ("#7d171d", "#fbe9ea"),
    "opinion": ("#4a4137", "#f2ede4"),
    "chronicle": ("#25435f", "#e8eef5"),
    "announce": ("#14532d", "#e7f6ec"),
    "news": ("#3a3a3a", "#eeeeee"),
}

TRUST_LABELS = {"fact": "Факт", "source_reported": "По данным источника",
                "unconfirmed": "Не подтверждено", "announce": "Анонс", "opinion": "Мнение"}
TRUST_STYLE = {
    "fact": ("#14532d", "#e7f6ec"),
    "source_reported": ("#25435f", "#e8eef5"),
    "unconfirmed": ("#8a4a00", "#fdf1de"),
    "announce": ("#14532d", "#e7f6ec"),
    "opinion": ("#8a2a2a", "#f8e8e6"),
}


def _chip(text, style):
    fg, bg = style
    return (f'<span class="chip" style="color:{fg};background:{bg}">{esc(text)}</span>')


def type_badge(it):
    t = it.get("material_type") or "news"
    return _chip(MATERIAL_LABELS.get(t, "Новость"), TYPE_STYLE.get(t, TYPE_STYLE["news"]))


def status_badge(it):
    ts = it.get("trust_status") or "source_reported"
    return _chip(TRUST_LABELS.get(ts, "Источник"),
                 TRUST_STYLE.get(ts, TRUST_STYLE["source_reported"]))


def card_badges(it):
    """Чипы типа и статуса материала для карточки."""
    return type_badge(it) + status_badge(it)


def kicker_text(it, cfg):
    """Строка-вводка карточки: рубрика · подрубрика · гео (что есть)."""
    subs = {s.get("id"): s.get("name") for s in cfg.get("subcategories", [])}
    cats = {c.get("id"): c.get("name") for c in cfg.get("categories", [])}
    parts = [cats.get(it.get("category"), "Новости")]
    if it.get("sub_category") and it["sub_category"] in subs:
        parts.append(subs[it["sub_category"]])
    if it.get("geo_tag"):
        parts.append(it["geo_tag"])
    return " · ".join(parts)


def fact_passport(it, cfg, now=None):
    """Паспорт факта: «кто · что · где · когда» — нижняя строка крупной карточки.
    Возвращает список пар (метка, значение); пустые позиции пропускаются."""
    now = now or datetime.now(UTC4)
    parts = []
    try:
        from analytics import agency_of
        ag = agency_of(it)
        if ag:
            who = ag.get("word") or ag.get("actor") or ag.get("object")
            if who and ag.get("role") in ("субъект", "упоминание", "объект"):
                parts.append(("Кто", who))
    except Exception:
        pass
    ttl = it.get("title") or ""
    body = strip_title_lead(it.get("text") or "", ttl)
    parts_s = SENT_SPLIT.split(body)
    if len(parts_s) > 1 and similarity(parts_s[0], ttl) > 0.7:
        body = " ".join(parts_s[1:])
    what = clip_sentences(body, 110)
    if what and len(what) >= 40 and not similarity(what, ttl):
        parts.append(("Что", what))
    parts.append(("Где", it.get("geo_tag") or "Ульяновская область"))
    when = ""
    try:
        from analytics import extract_event_time
        res = extract_event_time(it.get("text") or "", it.get("published"))
        if res:
            when = fmt_time(res[0].isoformat(), now, "word")
    except Exception:
        pass
    if not when:
        when = fmt_time(it.get("published"), now, "word")
    if when:
        parts.append(("Когда", when))
    return parts


# ------------------------------------------------------------------ v4: кластер и «Коротко»
def also_reported(members, lead, limit=4):
    """«Также сообщили: …» — разные источники из того же кластера, кроме героя."""
    names = []
    for m in members:
        if m.get("id") == lead.get("id"):
            continue
        src = m.get("source") or m.get("channel") or ""
        if src and src not in names:
            names.append(src)
    if not names:
        return ""
    return f"Также сообщили: {', '.join(names[:limit])}"


def cluster_timeline(members, now=None, limit=5):
    """Хронология сюжета (#13): «12:04 Улпресса → 13:10 Мой город → …» по кластеру.
    Если интервал больше суток — пишем «дд.мм» вместо времени."""
    now = now or datetime.now(UTC4)
    members = sorted(members, key=lambda x: x.get("published") or "")
    steps = []
    for m in members[:limit]:
        dt = local_dt(m.get("published"))
        if not dt:
            continue
        label = "→ " if steps else ""
        stamp = dt.strftime("%d.%m %H:%M") if (now - dt).total_seconds() > 86400 else dt.strftime("%H:%M")
        src = (m.get("source") or m.get("channel") or "источник")[:18]
        steps.append(f"{label}{stamp} {src}")
    return " ".join(steps)


def cluster_card(members, cfg, now=None):
    """Карточка кластера v4: лучший заголовок+фото, суммарный охват, «также сообщили».
    Возвращает (html, показанные id)."""
    now = now or datetime.now(UTC4)
    members = [m for m in members if not m.get("dup_of")] or members
    if not members:
        return "", []
    best = max(members, key=lambda m: hero_score(m, None, now, cfg))
    others = [m for m in members if m.get("id") != best.get("id")]
    seen_ids = [best.get("id")] + [m.get("id") for m in others[:4]]
    title = present_title(best, 78)
    img = best.get("image") or best.get("thumb")
    img_html = (f'<a class="phantom" href="{esc(best.get("url") or "#")}">'
                f'<img loading="lazy" src="{esc(img)}" alt="{esc(title)}"></a>') if img else ""
    total = sum(int(m.get("views") or 0) for m in members)
    extra = (f'<div class="card__meta">{esc(_rus_views(total))} просмотров суммарно</div>'
             if total else "")
    link = esc(best.get("url") or "#")
    t = fmt_time(best.get("published"), now)
    return (f'<article class="card card--cluster">'
            f'<span class="kicker card__kicker">{esc(kicker_text(best, cfg))}'
            f'<span class="chip chip--cluster">кластер · {len(members)} источника</span></span>'
            f'<h3><a href="{link}">{title}</a></h3>'
            f'<p class="card__dek">{esc(dek_p(best, 140))}</p>'
            f'{extra}'
            f'{img_html}'
            f'<div class="card__meta">{esc(also_reported(members, best))}</div>'
            f'<time datetime="{best.get("published") or ""}">{esc(t)}</time>'
            f'</article>'), seen_ids


def short_brief(ranked, seen, limit=7):
    """«Коротко: 7 строк дня» — строки скорингового топа, не показанного выше.
    Берутся по формуле v4, а не «последние посты», чтобы не дублировать ленту."""
    rows = []
    for it in ranked:
        if len(rows) >= limit:
            break
        mt = it.get("material_type") or ""
        if mt in ("alert", "announce"):
            continue
        if is_promo(it):
            continue
        if not seen.first(it):
            continue
        if not gate(it):
            continue
        rows.append(it)
    return rows


# ------------------------------------------------------------------ v4: гейт обязательных полей (#09)
def title_assemble(it, cfg):
    """Заголовок-сборка «кто → что → где» (#16): когда исходного заголовка нет.
    Строится из первого содержательного предложения лида с гео-префиксом и
    агентивной подписью, как в present_title; пустой — дефектная запись."""
    ttl = (it.get("title") or "").strip()
    if len(ttl) >= 25:
        return ttl
    who = ""
    try:
        from analytics import agency_of
        ag = agency_of(it)
        if ag:
            who = ag.get("word") or ""
            if not who:
                who = ag.get("actor") or ag.get("object") or ""
    except Exception:
        pass
    body = strip_title_lead(it.get("text") or "", ttl)
    what = next((s.strip() for s in SENT_SPLIT.split(body) if len(s.strip()) >= 25), "")
    if not what:
        return f"Событие в {it.get('geo_tag') or 'Ульяновской области'}"
    geo = it.get("geo_tag")
    if geo:
        what = f"{geo}: {what}"
    if who and who.lower() not in what.lower() and len(what) > 40:
        what = f"{who}: {what}"
    pseudo = {"title": what, "text": (it.get("text") or "")[:120]}
    return present_title(pseudo, 90)


def gate(it):
    """Гейт обязательных полей (#09): заголовок (или сборка), ссылка, время.
    Записи без них на полосу не попадают."""
    if not it or not it.get("id"):
        return False
    ttl = (it.get("title") or "").strip()
    if len(ttl) < 4:
        if not title_assemble(it, {}):
            return False
    if not it.get("url") or not it.get("published"):
        return False
    return True


CHANNEL_TAIL_RE = re.compile(r"(?is)\s*(подписаться\s*\|\s*прислать|прислать новость|мы в макс|читайте нас в макс|подпишись|информацию о событиях в городе смотрите|смотрите на карточках|новости ульяновска без замедления|новости ульяновска в макс).*$")


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
<a href="{prefix}projects/plans.html">Планы</a>
<a href="{prefix}methods.html">Методы</a>
<a href="{prefix}status.html">Статус системы</a>
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
        d = date_str if hasattr(date_str, "year") else datetime.strptime(str(date_str), "%Y-%m-%d").date()
        if launch:
            n = (d - datetime.strptime(launch, "%Y-%m-%d").date()).days
            return max(n, 0), n <= 0
    except (ValueError, TypeError):
        pass
    return 1, False


def digest_link(date_str):
    """Имя файла выпуска за сутки для ссылок из digests/ и с витрины.

    Датированный выпуск появляется, только когда сутки закрыты; до этого свежий выпуск
    живёт на today.html. Без проверки страница весь день ссылается на отсутствующий файл."""
    name = f"digest_{date_str}.html"
    return name if os.path.exists(os.path.join(DIGESTS, name)) else "today.html"


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
        ("index", "Первая полоса", f"{prefix}index.html"),
        ("today", "Сегодня", f"{prefix}digests/today.html"),
        ("weekly", "Неделя", f"{prefix}weekly.html"),
        ("monthly", "Месяц", f"{prefix}monthly.html"),
        ("afisha", "Афиша", f"{prefix}afisha.html"),
        ("projects", "Проекты", f"{prefix}projects.html"),
        ("archive", "Архив", f"{prefix}archive.html"),
        ("exec", "Руководителю", f"{prefix}digests/{ex}" if ex_exists else ""),
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
    toggle = ('<button class="nav-toggle" aria-label="Открыть разделы" '
              "onclick=\"document.body.classList.toggle('nav-open')\">Меню</button>")
    return (f'<nav class="nav">{toggle}<div class="nav-inner">{"".join(html_items)}</div></nav>'
            + subnav)


# ------------------------------------------------------------------ digest
def render_digest(cfg, trends, store, status, date_str, digest_no, mode="closed"):
    now = datetime.now(UTC4)
    an = load_json(os.path.join(DATA, "analytics.json")) or {}
    nav_html = render_nav(cfg, "today" if mode == "today" else "archive", "../", subnav=SUBNAV_DIGEST)
    day = datetime.strptime(date_str, "%Y-%m-%d").date()
    cats = {c["id"]: c for c in cfg["categories"]}
    tg_channels = {c["username"]: c for c in cfg["telegram_channels"] if c.get("enabled", True)}

    # окно выборки: сутки вокруг даты дайджеста (+6 ч запас)
    # утренний выпуск за дату D собирает материалы календарных суток D-1 (+3 ч ночи D)
    if mode == "today":
        cover_day = day
        win_start = datetime.combine(cover_day, datetime.min.time(), tzinfo=UTC4)
        win_end = now + timedelta(minutes=5)
    else:
        cover_day = day
        win_start = datetime.combine(cover_day, datetime.min.time(), tzinfo=UTC4)
        win_end = win_start + timedelta(days=1)
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
        alert_banner = (f'<div class="alert-banner"><span class="blink">🚨</span> АЛЕРТ: {esc(clip_words(a0["title"],140))} '
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
<header class="masthead"><div class="mast-inner">
<div class="mast-side">Информационно-аналитическое издание<br>марксистской группы «Победа»</div>
<div class="mast-title">ГУДОК<span>.</span></div>
<div class="mast-side mast-side--right">{"«Сегодня» · живая страница" if mode == "today" else f"Выпуск № {digest_no}" + (" · 🧪 тестовый" if digest_no == 0 else "")}<br>сутки {cover_day:%d.%m.%Y}
<div class="mast-actions"><a href="print_{date_str}.html">Печатная полоса</a>{THEME_BTN}<button class="print-btn" onclick="window.print()">🖈 PDF</button></div></div>
</div></header>
{alert_banner}{nav_html}
<div class="genstamp"><div class="genstamp-inner">
<span class="g1">{'Живая страница суток' if mode == 'today' else f'Выпуск № {digest_no} · сутки закрыты'}</span>
<span class="g2">сгенерировано {now:%d.%m.%Y %H:%M} UTC+4</span>
<span class="g3">материалы: {cover_day:%d.%m.%Y}{' с 00:00 по текущий момент' if mode == 'today' else ' 00:00–24:00'} · материалов в выпуске: {len(window)}</span>
</div></div>
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
    hero_pool = [it for it in window if is_regional(it) and it.get("category") != "security"
                 and not is_alert(it)] or window
    heroes = hero_pick(hero_pool, trends, now, 3)
    if heroes:
        hero_html = []
        for rank, it in enumerate(heroes, 1):
            cat = cats.get(it.get("category"), {})
            dt = local_dt(it.get("published"))
            views = f' · 👁 {fmt_views(it["views"])}' if it.get("views") else ""
            link = esc(it.get("url") or "#")
            src_l = esc(src_label(it))
            tstr = dt.strftime('%d.%m %H:%M') if dt else ''
            if rank == 1:
                img = photo_img(it, "../", "width:100%;aspect-ratio:16/9;object-fit:cover;display:block;margin:0 0 14px;")
                ttl = feed_title(it, 135)
                hero_html.append(f"""<article class="hero-card hero-main">{img}
<div class="rank">01</div>
<div class="hk">{esc(cat.get('name', 'Главное'))} · событие дня</div>
<h3><a href="{link}" target="_blank" rel="noopener">{esc(ttl)}</a></h3>
{feed_dek_p(it, 300, ttl)}
<div class="hero-meta">{tstr} · {src_l}{views} · <a href="{link}" target="_blank" rel="noopener">источник →</a></div></article>""")
            else:
                ttl = feed_title(it, 110)
                hero_html.append(f"""<article class="hero-card">
<div class="hero-rank-line"><span class="rank">{rank:02d}</span><span class="hk">{esc(cat.get('name', 'Главное'))}</span></div>
<h3><a href="{link}" target="_blank" rel="noopener">{esc(ttl)}</a></h3>
{feed_dek_p(it, 150, ttl)}
<div class="hero-meta">{tstr} · {src_l}{views} · <a href="{link}" target="_blank" rel="noopener">источник →</a></div></article>""")
        parts.append(f"""<div class="sec-head" id="heroes"><h2>Главные события дня</h2><div class="line"></div>
<div class="badge">авторанжирование: просмотры × темы × свежесть</div></div>
<div class="hero-grid"><div>{hero_html[0]}</div><div class="hero-side">{''.join(hero_html[1:])}</div></div>""")

    chron = chrono_items(window)
    if chron:
        rows = []
        for it in chron:
            dt = local_dt(it.get("published"))
            link = esc(it.get("url") or "#")
            rows.append(f"""<div class="chrono-item"><span class="chrono-time">{dt.strftime('%d.%m %H:%M') if dt else ''}</span>
<a href="{link}" target="_blank" rel="noopener"><b>{esc(clip_words(it['title'],150))}</b></a>
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
            label = STATUS_META.get(t["status"], STATUS_META["stable"])[0]
            st_color = {"rising": "#D63F1F", "new": "#0B0B0B", "fading": "#9A948A",
                        "silent": "#C9C2B6"}.get(t["status"], "#6B655C")
            chip_cls = {"rising": " st-rise", "new": " st-new"}.get(t["status"], "")
            width = max(4, int(t["week"] / mx * 100))
            fill_cls = "hot" if t["status"] == "rising" else ("cool" if t["status"] == "new" else "")
            rows.append(f"""<div class="topic-row">
<div class="topic-name">{esc(t['name'])}<small>за 7 дней: {t['week']} · сегодня: {t['today']}</small></div>
<div class="bar-wrap"><div class="bar-fill {fill_cls}" style="width:{width}%"></div></div>
<div class="sparkcell">{sparkline(t['series'], color=st_color)}</div>
<div><span class="stchip{chip_cls}">{label}</span></div>
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
<div class="cal-txt"><a href="{esc(e.get('url') or '#')}" target="_blank" rel="noopener"><b>{esc(clip_words(e['title'],120))}</b></a>{span}
<div class="t2">{esc(e.get('time','')) or 'время уточняйте'}{venue} · {esc(e.get('source',''))}</div></div></div>""")
        parts.append(f"""<div class="sec-head" id="afisha"><h2>Автоафиша: ближайшие события</h2><div class="line"></div>
<div class="badge">извлечено из новостей · {len(cal)} дат</div></div>
<div class="card"><div class="card-pad">{''.join(rows)}
<div class="note">Даты извлекаются из текстов автоматически (analytics.py): одиночные дни, диапазоны, время и площадки 📍. Погода и исторические даты отсеиваются. Перед визитом сверяйтесь с первоисточником.</div></div></div>""")

    # ---- Лента дня: рубрикатор в газетной оптике (лид + компактные строки)
    parts.append(f"""<div class="sec-head" id="feed"><h2>Лента дня</h2><div class="line"></div>
<div class="badge">{len(window)} материалов</div></div>""")
    if not window:
        parts.append('<div class="card"><div class="card-pad">За выбранный период материалов нет. Запустите <code>python3 collector.py</code>.</div></div>')
    else:
        ordered_cats = [c["id"] for c in cfg["categories"] if by_cat.get(c["id"])]

        def meta_line(it):
            dt = local_dt(it.get("published"))
            views = f' · 👁 {fmt_views(it["views"])}' if it.get("views") else ""
            t = f'<time datetime="{dt.isoformat()}">{dt.strftime("%d.%m %H:%M")}</time>' if dt else ""
            return f'<div class="meta">{t} · {esc(src_label(it))}{views}</div>'

        def also_line(it):
            also = it.get("also_in") or []
            if not also:
                return ""
            more = f" +{len(also) - 3}" if len(also) > 3 else ""
            return f'<div class="also">🔁 также сообщили: {esc(", ".join(also[:3]))}{more}</div>'

        def topics_line(it):
            ts = [topic_names[t] for t in (it.get("topics") or [])[:3] if t in topic_names]
            return f'<div class="topics">{esc(" · ".join(ts))}</div>' if ts else ""

        def feed_item(it, lead=False):
            link = esc(it.get("url") or "#")
            if lead:
                ph = photo_img(it, "../", "width:100%;aspect-ratio:16/9;object-fit:cover;display:block;margin-bottom:9px;")
                ttl = feed_title(it, 130)
                return (f'<article class="fi fi-lead">{ph}'
                        f'<h4><a href="{link}" target="_blank" rel="noopener">{esc(ttl)}</a></h4>'
                        f'{feed_dek_p(it, 220, ttl)}{meta_line(it)}{also_line(it)}{topics_line(it)}</article>')
            ph = photo_img(it, "../", "width:104px;height:70px;object-fit:cover;display:block;")
            thumb = f'<div class="fi-thumb">{ph}</div>' if ph else ""
            cls = "fi with-photo" if ph else "fi"
            ttl = feed_title(it, 105)
            return (f'<article class="{cls}">'
                    f'<div class="fi-body"><h4><a href="{link}" target="_blank" rel="noopener">{esc(ttl)}</a></h4>'
                    f'{feed_dek_p(it, 130, ttl)}{meta_line(it)}{also_line(it)}</div>{thumb}</article>')

        blocks = []
        for cid in ordered_cats:
            c = cats[cid]
            items = by_cat[cid][:10]
            n_all = len(by_cat[cid])
            items_html = feed_item(items[0], lead=True) + "".join(feed_item(it) for it in items[1:])
            more = (f'<div class="cat-more">и ещё {n_all - len(items)} '
                    f'{plural_ru(n_all - len(items), "материал", "материала", "материалов")} за сутки в базе</div>'
                    if n_all > len(items) else "")
            blocks.append((len(items), f"""<section class="cat-block">
<div class="cat-head"><h3>{esc(c['name'])}</h3><div class="count">{n_all} {plural_ru(n_all, 'материал', 'материала', 'материалов')}</div></div>
{items_html}{more}</section>"""))
        # раскладка по двум колонкам: порядок рубрик сохраняется, баланс по числу материалов
        cols = [[], []]
        load = [0, 0]
        for w, html in blocks:
            j = 0 if load[0] <= load[1] else 1
            cols[j].append(html)
            load[j] += w
        parts.append(f"""<div class="feed-cols">
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
<div><div class="t"><a href="{esc(p.get('url') or '#')}" target="_blank" rel="noopener">{esc(clip_words(p['title'],130))}</a></div>
<div class="m">{(local_dt(p.get('published')) or now).strftime('%d.%m %H:%M')}</div></div></div>"""
                for p in posts) or '<div class="tgpost"><div class="t" style="color:var(--muted);">Нет свежих сообщений</div></div>'
            parts.append(f"""<div class="card" style="margin-bottom:14px;"><div class="side-head">{st_icon}
<a href="https://t.me/{esc(username)}" target="_blank" rel="noopener" style="color:#fff;">@{esc(username)}</a>
<span class="sub">{esc(ch.get('title',''))}</span></div><div class="side-body">{rows}</div></div>""")
        parts.append('</div>')

    tier_badge = {1: '<span class="stchip st-new">официальный</span>',
                  2: '<span class="stchip">агрегатор</span>',
                  3: '<span class="stchip">мнение</span>'}
    trows = []
    for username, ch in t23:
        last = ch_posts(username, 1)
        st = (status or {}).get(f"tg:{username}", {})
        dot = '<span class="ok">●</span>' if st.get("ok") else ('<span class="fail">●</span>' if st else "●")
        subs = f"{ch['subs']/1000:.0f}K" if ch.get("subs") else "—"
        if last:
            lp = last[0]
            last_html = (f'<a href="{esc(lp.get("url") or "#")}" target="_blank" rel="noopener">{esc(clip_words(lp["title"],80))}</a> '
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
            gap_badge = ('<span class="cl-badge cl-warn">⚠️ вне словаря тем</span>'
                         if c.get("gap") else
                         f'<span class="cl-badge">словарь: {int(c["coverage"] * 100)}%</span>')
            samples = "".join(
                f'<div>• <a href="{esc(smp["url"]) or "#"}" target="_blank" rel="noopener">{esc(smp["title"])}</a> '
                f'<span style="color:var(--muted);">({esc(smp["source"])}{" · 👁 " + fmt_views(smp["views"]) if smp.get("views") else ""})</span></div>'
                for smp in c.get("samples", [])[:2])
            cl_html.append(f"""<div class="cl-card{' gap' if c.get('gap') else ''}">
<div class="cl-head"><span class="cl-name">«{esc(c['name'])}»</span>
<span class="cl-badge">×{c['size']} {plural_ru(c['size'], 'материал', 'материала', 'материалов')} за 72 ч</span>{gap_badge}</div>
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
{footer.render_footer('../')}</body></html>""")
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
    """«Дайджест руководителя»: один лист A4 — картина информационной повестки области
    для руководителя предприятия.

    Левая колонка: 5 событий суток, 3 риска, 3 решения/возможности, экономика и АПК.
    Правая колонка: оперативная обстановка, пульс повестки, тон инфополя,
    прогноз на завтра, первоисточники инфополя.
    """
    import re as _re
    nav_html = render_nav(cfg, "exec", "../")
    global DECISION_RE
    if DECISION_RE is None:
        DECISION_RE = _re.compile(
            r"поручил|принято решение|подписал|дал старт|утвердил|выделил|договорились|"
            r"соглашение|запустил|открыли|начнётся|начнется|продлится|увеличат|проложат|выплатит")
    now = datetime.now(UTC4)
    day = datetime.strptime(date_str, "%Y-%m-%d").date()
    WD_EX = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
    win_start = datetime.combine(day, datetime.min.time(), tzinfo=UTC4) - timedelta(hours=6)
    win_end = win_start + timedelta(hours=30)
    window = [it for it in store if not it.get("dup_of")
              and local_dt(it.get("published")) and win_start <= local_dt(it["published"]) < win_end]
    if len(window) < 8:
        win_start -= timedelta(days=2)
        window = [it for it in store if not it.get("dup_of")
                  and local_dt(it.get("published")) and win_start <= local_dt(it["published"]) < win_end]

    an = load_json(os.path.join(DATA, "analytics.json")) or {}
    sent = an.get("sentiment") or {}
    forecast = (an.get("forecast") or [])[:3]
    cred = an.get("credibility") or []
    alerts = load_json(os.path.join(DATA, "alerts.json"), {"active": [], "resolved": []}) or {}
    srcs = {k: v for k, v in (status or {}).items() if k != "_meta"}
    ok_n = sum(1 for v in srcs.values() if isinstance(v, dict) and v.get("ok"))
    dno, dtest = digest_number(cfg, date_str)

    # главное за сутки — без безопасности (её место в рисках) и без федерального шума
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
    # решения и возможности — маркеры действий в tier-1 источниках
    decisions = [it for it in window
                 if it["id"] not in ev_ids and it["id"] not in risk_ids
                 and DECISION_RE.search((it.get("title", "") + " " + (it.get("text") or "")).lower())
                 and (it.get("tier") == 1 or it.get("source_type") == "seed")]
    decisions = sorted(decisions, key=lambda x: ((x.get("views") or 0), x.get("published") or ""), reverse=True)[:3]
    dec_ids = {it["id"] for it in decisions}
    # экономика и АПК — профильное для руководителя предприятия
    econ = sorted([it for it in window
                   if it.get("category") in ("economy", "agro")
                   and it["id"] not in (ev_ids | dec_ids) and is_regional(it)],
                  key=lambda x: (x.get("views") or 0, x.get("published") or ""), reverse=True)[:3]

    def li(items, kind, sub_len=170, title_len=130):
        out = []
        for it in items:
            dt = local_dt(it.get("published"))
            src = esc(it.get("source", ""))
            views = f" · 👁 {fmt_views(it['views'])}" if it.get("views") else ""
            sub = clip_sentences((it.get("text") or ""), sub_len)
            sub_html = (f'<div class="sub">{esc(sub)}</div>'
                        if sub and norm_sq(sub) != norm_sq(it.get("title", "")) else "")
            out.append(f"""<li><b><a href="{esc(it.get('url') or '#')}" target="_blank" rel="noopener">{esc(clip_words(it['title'], title_len))}</a></b>
{sub_html}<div class="src">{dt.strftime('%d.%m %H:%M') if dt else ''} · {src}{views}</div></li>""")
        return "".join(out) or f"<li><span class='sub'>Нет данных за период ({kind})</span></li>"

    # оперативная обстановка: уведомления о режимах за окно выпуска
    sec_items = sorted([it for it in window if it.get("category") == "security" and is_alert(it)],
                       key=lambda x: x.get("published") or "")
    act = alerts.get("active") or []
    if act:
        a0 = act[0] if isinstance(act[0], dict) else {"text": str(act[0])}
        regime = "⚠️ действует: " + esc(clip_words(str(a0.get("text") or a0.get("kind") or "режим опасности"), 90))
    else:
        regime = "активных режимов опасности нет"
    if sec_items:
        la = sec_items[-1]
        lad = local_dt(la.get("published"))
        last_txt = f"{lad.strftime('%d.%m %H:%M') if lad else '—'} · {esc(clip_words(la.get('title', ''), 90))}"
    else:
        last_txt = "за окно выпуска уведомлений не зафиксировано"

    # пульс повестки: топ-6 тем недели
    ST_ICO = {"rising": "🔥", "new": "🆕", "stable": "⚖️", "fading": "📉", "silent": "💤"}
    topics = (trends or {}).get("topics", {})
    top6 = sorted(topics.values(), key=lambda t: -(t.get("week") or 0))[:6]
    pulse_rows = "".join(
        f'<div class="pulse-row"><span>{ST_ICO.get(t.get("status", "stable"), "⚖️")}</span>'
        f'<span class="p-name">{esc(t.get("name", ""))}</span>'
        f'<span class="p-nums">24ч {t.get("today", 0)} · 7д {t.get("week", 0)}</span>'
        f'{sparkline(t.get("series", []), w=70, h=16, color="#4a7fb5")}</div>'
        for t in top6) or '<div class="pulse-row"><span class="p-name">Нет данных трекера</span></div>'

    # тон инфополя
    sc = sent.get("today_score")
    mood = ("—" if sc is None else
            "позитивный" if sc >= 0.25 else "спокойный" if sc >= 0.08 else
            "смешанный" if sc > -0.15 else "напряжённый")
    tone_series = [x.get("score") for x in (sent.get("series") or []) if x.get("score") is not None]
    if tone_series and min(tone_series) < 0:
        shift = -min(tone_series)
        tone_series = [v + shift for v in tone_series]
    tone_spark = sparkline(tone_series, w=150, h=28, color="#4a7fb5")
    sc_txt = "—" if sc is None else f"{sc:+.2f}"

    # прогноз на завтра
    fc_rows = ""
    for f in forecast:
        arrow = {"рост": "↑", "спад": "↓"}.get(f.get("direction", ""), "→")
        fc_rows += (f'<div class="fc-row"><span class="fc-a">{arrow}</span>'
                    f'<span class="fc-n">{esc(f.get("name", ""))}</span>'
                    f'<span class="fc-e">~{float(f.get("expected") or 0):.0f} публ. · {esc(f.get("confidence", ""))}</span></div>')
    fc_rows = fc_rows or '<div class="fc-row"><span class="fc-n">прогноз недоступен</span></div>'

    # первоисточники инфополя
    prim = [c for c in cred if c.get("label") == "первоисточник"][:3] or cred[:3]
    cred_rows = "".join(
        f'<div class="cr-row"><span class="fc-n">{esc(str(c.get("source", "")))}</span>'
        f'<span class="cr-v">{c.get("primary", 0)} из {c.get("total", 0)} — оригиналы</span></div>'
        for c in prim) or '<div class="cr-row"><span class="fc-n">статистика источников накапливается</span></div>'

    # #23: компактный отчёт качества для «версии руководителю»
    q = quality_report(store, cfg, day)
    q["dups_on_page"] = sum(1 for it in store if it.get("dup_of"))
    al_times = [local_dt(a.get("published")) for a in sec_items if local_dt(a.get("published"))]
    q["last_alert_lag_min"] = (int((now - max(al_times)).total_seconds() // 60) if al_times else None)
    qual_rows = (
        f'<div style="font-size:12px;line-height:1.5;">'
        f'<b>Материалов:</b> {q["items"]} · '
        f'<b>Дубли:</b> {q["dups_on_page"]} · '
        f'<b>Промо:</b> {int(q["promo_share"] * 100)}%<br>'
        f'<b>Заголовки:</b> {int(q["full_title_share"] * 100)}% полные · '
        f'<b>Ведущая рубрика:</b> {esc(str(q.get("top_category") or "—"))} ({int(q["top_category_share"] * 100)}%)<br>'
        f'<b>Алерт-лаг:</b> {q["last_alert_lag_min"] or "—"} мин · '
        f'<b>Событий на сайте:</b> {q.get("events_today") or 0}'
        + (' · <span style="color:#b02a2f;">Пустые блоки:</span> ' + ", ".join(esc(b) for b in q.get("empty_blocks") or []) if q.get("empty_blocks") else "")
        + '</div>')

    # Спринт 3, п.5: сводка качества выборки афиши для руководителя
    apass = an.get("calendar_passport") or {}
    if apass.get("run_local"):
        aq_bits = [
            f"прошло порог <b>{apass.get('accepted', apass.get('total', 0))}</b>",
            f"дат в текстах: <b>{apass.get('found_dates', '—')}</b>",
            f"отсеяно: <b>{apass.get('rejected', '—')}</b>",
        ]
        if apass.get("no_time"):
            aq_bits.append(f"без времени: <b>{apass['no_time']}</b>")
        if apass.get("no_venue"):
            aq_bits.append(f"без площадки: <b>{apass['no_venue']}</b>")
        if apass.get("other_share") is not None:
            aq_bits.append(f"«Прочее»: <b>{apass['other_share']}%</b>")
        if apass.get("venues_new_n"):
            aq_bits.append(f"новых площадок: <b>{apass['venues_new_n']}</b>")
        aq_extra = ""
        if apass.get("also_n"):
            aq_extra = f' · <b>с др. анонсами:</b> {apass["also_n"]}'
        if apass.get("verdict"):
            aq_extra += f' · <span style="color:var(--muted);">{esc(str(apass["verdict"]))}</span>'
        afisha_qual = (f'<div class="panel"><h3>🎯 Качество афиши</h3>'
                       f'<div style="font-size:12px;line-height:1.5;">'
                       f'{" · ".join(aq_bits)}{aq_extra}</div></div>')
    else:
        afisha_qual = ""

    return f"""<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Дайджест руководителя · {day:%d.%m.%Y} — {cfg['brand']}</title>
<link rel="icon" type="image/png" href="../assets/logo_gudok.png"><style>{CSS}
@page {{ size: A4; margin: 9mm; }}
.exec-wrap{{max-width:1020px;margin:0 auto;padding:22px 26px 30px;}}
.exec-head{{display:flex;justify-content:space-between;align-items:flex-end;border-bottom:3px double var(--ink);padding-bottom:10px;margin-bottom:14px;flex-wrap:wrap;gap:8px;}}
.exec-head .kicker{{font-family:var(--sans);font-size:10px;font-weight:700;letter-spacing:.16em;text-transform:uppercase;color:var(--accent);margin-bottom:4px;}}
.exec-head h1{{font-family:var(--serif-display);font-weight:700;font-size:26px;letter-spacing:-.01em;margin:0;color:var(--ink);}}
.exec-head .d{{font-family:var(--sans);font-size:11.5px;color:var(--muted);text-align:right;line-height:1.55;}}
.exec-head .d b{{color:var(--ink);}}
.exec-grid{{display:grid;grid-template-columns:1.55fr 1fr;gap:24px;align-items:start;}}
.exec-sec{{margin-bottom:13px;break-inside:avoid;}}
.exec-sec h2{{font-family:var(--sans);font-size:10.5px;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:var(--ink);border-top:2px solid var(--ink);padding-top:5px;margin:0 0 7px;display:flex;justify-content:space-between;gap:10px;}}
.exec-sec h2 .cnt{{color:var(--muted);font-weight:500;letter-spacing:.04em;text-transform:none;}}
.exec-sec.risk h2{{border-top-color:#b02a2f;color:#b02a2f;}}
.exec-sec.dec h2{{border-top-color:#1d7a4d;color:#1d7a4d;}}
.exec-sec ol{{padding-left:18px;margin:0;}}
.exec-sec li{{margin-bottom:8px;font-size:13px;line-height:1.42;}}
.exec-sec li b{{font-family:var(--serif-body);font-weight:600;}}
.exec-sec li b a{{color:var(--ink);}}
.exec-sec li b a:hover{{color:var(--accent);}}
.exec-sec .sub{{color:var(--ink-2);font-size:12px;margin-top:1px;}}
.exec-sec .src{{color:var(--muted);font-family:var(--sans);font-size:10px;font-weight:600;margin-top:1px;}}
.panel{{border:1px solid var(--rule);border-top:2px solid var(--ink);padding:9px 12px;margin-bottom:10px;break-inside:avoid;background:var(--paper-2);}}
.panel h3{{font-family:var(--sans);font-size:10px;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);margin:0 0 6px;}}
.panel.op{{border-top-color:#b02a2f;}}
.pulse-row{{display:grid;grid-template-columns:16px minmax(0,1fr) auto auto;gap:6px;align-items:center;font-size:11.5px;padding:2.5px 0;border-bottom:1px dashed var(--rule);}}
.pulse-row:last-child{{border-bottom:none;}}
.p-name{{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-weight:600;color:var(--ink-2);}}
.p-nums{{font-family:var(--sans);font-size:9.5px;color:var(--muted);white-space:nowrap;}}
.tone-big{{font-family:var(--serif-display);font-size:30px;font-weight:700;line-height:1;color:var(--ink);}}
.tone-mood{{font-family:var(--sans);font-size:10.5px;color:var(--muted);margin-top:2px;}}
.fc-row,.cr-row{{display:flex;gap:8px;align-items:baseline;font-size:11.5px;padding:2.5px 0;border-bottom:1px dashed var(--rule);}}
.fc-row:last-child,.cr-row:last-child{{border-bottom:none;}}
.fc-a{{font-weight:800;color:var(--accent);width:12px;flex-shrink:0;}}
.fc-n{{font-weight:600;color:var(--ink-2);}}
.fc-e,.cr-v{{margin-left:auto;font-family:var(--sans);font-size:9.5px;color:var(--muted);white-space:nowrap;}}
.exec-foot{{border-top:1px solid var(--rule);margin-top:14px;padding-top:8px;font-family:var(--sans);font-size:10px;color:var(--muted);display:flex;justify-content:space-between;flex-wrap:wrap;gap:6px;}}
.exec-foot a{{color:var(--accent);}}
@media (max-width:900px){{.exec-grid{{grid-template-columns:1fr;}}}}
@media print{{
  .topbar,.masthead,.flagline,.nav,.subnav,.print-btn,.theme-btn,.util-bar-wrap,.footer{{display:none!important;}}
  .exec-wrap{{padding:0;max-width:none;}}
  body{{background:#fff;}}
  .exec-head h1{{font-size:17pt;}}
  .exec-sec li{{font-size:8.8pt;}} .exec-sec .sub{{font-size:8.2pt;}} .exec-sec .src{{font-size:7pt;}}
  .panel{{background:#fff;}} .pulse-row,.fc-row,.cr-row{{font-size:8.2pt;}}
  .exec-head .d{{font-size:8.5pt;}}
}}
</style></head><body>
<header class="masthead"><div class="mast-inner">
<div class="mast-side">Информационно-аналитическое издание<br>марксистской группы «Победа»</div>
<div class="mast-title">ГУДОК<span>.</span></div>
<div class="mast-side mast-side--right">Дайджест руководителя<br>{day:%d.%m.%Y} · один лист A4
<div class="mast-actions">{THEME_BTN}<button class="print-btn" onclick="window.print()">🖈 PDF</button></div></div>
</div></header>
{nav_html}<div class="exec-wrap">
<div class="exec-head">
<div><div class="kicker">Руководителю предприятия · внутренний документ</div>
<h1>Дайджест руководителя</h1></div>
<div class="d"><b>{WD_EX[day.weekday()]}, {day:%d.%m.%Y}</b> · выпуск №{dno}{' · 🧪 тестовый' if dtest else ''}<br>сформирован {now:%H:%M} (UTC+4) · источников {ok_n}/{len(srcs)} · материалов за 24 ч: <b>{(trends or {}).get('counts', {}).get('last24h', '—')}</b></div>
</div>

<div class="exec-grid">
<div>
<div class="exec-sec"><h2>Главное за сутки <span class="cnt">топ-5 по значимости</span></h2><ol>{li(events, 'события')}</ol></div>
<div class="exec-sec risk"><h2>Риски <span class="cnt">безопасность и происшествия</span></h2><ol>{li(risks, 'риски', 140, 120)}</ol></div>
<div class="exec-sec dec"><h2>Решения и возможности <span class="cnt">власть и tier-1, чем можно воспользоваться</span></h2><ol>{li(decisions, 'решения', 140, 120)}</ol></div>
<div class="exec-sec"><h2>Экономика и АПК <span class="cnt">профильное для предприятия</span></h2><ol>{li(econ, 'экономика', 110, 120)}</ol></div>
</div>
<div>
<div class="panel op"><h3>🚨 Оперативная обстановка</h3>
<div style="font-size:12px;line-height:1.5;"><b>{len(sec_items)}</b> уведомлений о режимах за окно выпуска · {regime}<br>
<span style="color:var(--muted);font-size:11px;">Последнее: {last_txt}</span></div></div>
<div class="panel"><h3>📈 Пульс повестки · топ-6 тем недели</h3>{pulse_rows}</div>
<div class="panel"><h3>🌡 Тон инфополя · {sent.get('today_items', '—')} материалов</h3>
<div style="display:flex;align-items:center;gap:14px;"><div><div class="tone-big">{sc_txt}</div><div class="tone-mood">{mood} · ряд 14 дней →</div></div>{tone_spark}</div></div>
<div class="panel"><h3>📋 Качество выпуска</h3>{qual_rows}</div>
{afisha_qual}
<div class="panel"><h3>🔮 Прогноз на завтра</h3>{fc_rows}</div>
<div class="panel"><h3>📰 Первоисточники инфополя</h3>{cred_rows}</div>
</div>
</div>

<div class="exec-foot">
<span>Сформировано автоматически по мониторингу {len(srcs)} источников; отбор алгоритмический. Требует вычитки редактором перед рассылкой (human-in-the-loop).</span>
<span>Подробно: <a href="{digest_link(date_str)}">полный выпуск №{dno}</a> · {esc(cfg['brand'])}</span>
</div>
<button class="print-btn" onclick="window.print()" style="margin-top:10px;">🖨 Печать / PDF</button>
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
    nav_html = render_nav(cfg, "projects", "../", subnav=subnav_projects("../", "elections"))
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
            src_counter[outlets.outlet(it)] += 1   # одна редакция = одна строка
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
<h4><a href="{esc(it.get('url') or '#')}" target="_blank" rel="noopener">{esc(clip_words(it['title'],140))}</a></h4>
{dek_p(it, 300)}
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
<header class="masthead"><div class="mast-inner">
<div class="mast-side">Информационно-аналитическое издание<br>марксистской группы «Победа»</div>
<div class="mast-title">ГУДОК<span>.</span></div>
<div class="mast-side mast-side--right">Спецвыпуск «Выборы-2026»<br>голосование 18–20 сентября
<div class="mast-actions">{THEME_BTN}<button class="print-btn" onclick="window.print()">🖈 PDF</button></div></div>
</div></header>
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
{footer.render_footer('../')}
{FEED_JS}
</body></html>"""


# ------------------------------------------------------------------ projects
def render_projects(cfg, trends, store, status):
    """Хаб рубрики «Проекты»: спецстраницы-досье издания."""
    import plans as _plans
    now = datetime.now(UTC4)
    nav_html = render_nav(cfg, "projects", "", subnav=subnav_projects("", ""))
    plans_tracks = len(_plans.TRACKS)
    import methods as _methods
    import dossier as _dossier
    methods_total = len(_methods.METHODS)
    methods_ver = _methods.VERSION
    dossier_persons = len(_dossier.PERSONS)
    cards = f"""<div class="sec-card" style="border-top-color:var(--accent);text-decoration:none;display:block;">
<div><b>Инфопространство</b></div>
<div class="fig">live <small>дашборд</small></div>
<p>Скользящее исследование инфополя: метрики, тон, каскады, карта муниципалитетов, очередь новых метрик.</p>
<a class="go" href="infospace.html">открыть дашборд →</a></div>"""
    cards += f"""<div class="sec-card" style="border-top-color:var(--accent);text-decoration:none;display:block;">
<div><b>Методы</b></div>
<div class="fig">{methods_total}<small>методик v{methods_ver}</small></div>
<p>Реестр методик исследования инфополя: паспорт каждой (вход, выход, метрики качества, модуль,
неопределённость, порядок проверки), сквозной раздел «Идеология и гегемония», техконтур из открытых
стандартов и стенд испытания с генератором протокола.</p>
<a class="go" href="methods.html">открыть реестр →</a></div>"""
    cards += f"""<div class="sec-card" style="border-top-color:var(--accent);text-decoration:none;display:block;">
<div><b>Досье</b> <span style="font-family:var(--sans);font-size:10px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--accent);border:1px solid var(--accent);padding:2px 7px;">прототип</span></div>
<div class="fig">{dossier_persons}<small>карточек · демо</small></div>
<p>Действующие лица инфополя: упоминания и источники, индекс тона, дуги сюжетов, роль в цитатах,
статус проверки фактов и конвейер сборки карточки по методикам реестра. Данные демонстрационные.</p>
<a class="go" href="projects/dossier.html">открыть досье →</a></div>"""
    cards += f"""<div class="sec-card" style="border-top-color:var(--accent);text-decoration:none;display:block;">
<div><b>Планы и методы</b></div>
<div class="fig">{plans_tracks}<small>треков</small></div>
<p>Единая страница планов издания: план развития, реестр метрик «Инфопространства» с паспортами,
переезд на сервер, спринты первой полосы и конвейер внедрения метода.</p>
<a class="go" href="projects/plans.html">открыть планы →</a></div>"""
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
<header class="masthead"><div class="mast-inner">
<div class="mast-side">Информационно-аналитическое издание<br>марксистской группы «Победа»</div>
<div class="mast-title">ГУДОК<span>.</span></div>
<div class="mast-side mast-side--right">Проекты издания<br>досье и кампанийные страницы
<div class="mast-actions">{THEME_BTN}</div></div>
</div></header>
{nav_html}
<div class="wrap1200" style="padding-top:20px;">
<div class="sec-head" style="margin-top:0;"><h2>Проекты издания</h2><div class="line"></div>
<div class="badge">{len(cfg.get('projects', []))} в работе</div></div>
<div class="note" style="margin-bottom:16px;">Проект — это спецстраница-досье с собственной методикой наблюдения: кампания (выборы),
сквозной мониторинг (госзакупки) или расследование. Проекты живут вне ежедневной ленты, но питаются общей базой
и «Инфопространством». Название рубрики рабочее — редакция обсуждает варианты: «Проекты», «Спецпроекты», «Досье».</div>
<div class="sec-grid">{cards}</div>
</div>
{footer.render_footer('')}
</body></html>"""


PLANS_CSS = """
/* ---- страница «Планы»: статусы, конвейер метода, реестр метрик, треки ---- */
.pl-st{display:inline-block;font-family:var(--sans);font-size:10.5px;font-weight:800;letter-spacing:.08em;
text-transform:uppercase;padding:2px 8px;border:1px solid var(--rule);color:var(--muted);white-space:nowrap;}
.pl-st--done{color:#1d7a4d;border-color:#1d7a4d;}
.pl-st--ok{color:#1f5fbf;border-color:#1f5fbf;}
.pl-st--queue{color:#96690a;border-color:#e0b04e;}
.pl-st--hard{color:#a3341f;border-color:#a3341f;}
:root[data-theme="dark"] .pl-st--done{color:#7fd49b;border-color:#7fd49b;}
:root[data-theme="dark"] .pl-st--ok{color:#8dc0ff;border-color:#8dc0ff;}
:root[data-theme="dark"] .pl-st--queue{color:#e5b14e;border-color:#e5b14e;}
:root[data-theme="dark"] .pl-st--hard{color:#ff9b85;border-color:#ff9b85;}
.pl-stage{display:grid;grid-template-columns:64px 1fr;gap:4px 18px;border-top:1px solid var(--rule);padding:16px 0;}
.pl-stage:first-child{border-top:1px solid var(--ink);}
.pl-stage__n{font-family:var(--serif-display);font-size:34px;font-weight:700;line-height:.9;color:var(--accent);}
.pl-stage h3{font-family:var(--serif-display);font-size:19px;font-weight:600;margin:0 0 4px;color:var(--ink);}
.pl-stage p{font-family:var(--serif-body);font-size:14.5px;line-height:1.6;margin:0 0 6px;color:var(--ink-2);}
.pl-code{font-family:var(--sans);font-size:11.5px;line-height:1.6;color:var(--muted);}
.pl-code b{color:var(--ink);font-weight:700;}
.pl-ex{font-family:var(--serif-body);font-size:13px;font-style:italic;color:var(--muted);
border-left:2px solid var(--rule);padding-left:10px;margin-top:6px;}
.pl-pass{border:1px solid var(--rule);padding:14px 16px;margin-bottom:12px;background:var(--paper);}
.pl-pass summary{cursor:pointer;font-family:var(--serif-display);font-size:17px;font-weight:600;color:var(--ink);}
.pl-pass__meta{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:8px 0 4px;}
.pl-pass dl{display:grid;grid-template-columns:180px 1fr;gap:9px 18px;margin:12px 0 0;
font-family:var(--serif-body);font-size:13.5px;}
.pl-pass dt{font-family:var(--sans);font-size:10.5px;font-weight:800;letter-spacing:.1em;
text-transform:uppercase;color:var(--muted);padding-top:3px;}
.pl-pass dd{margin:0;line-height:1.55;color:var(--ink-2);}
.pl-formula{font-family:var(--sans);font-size:12.5px;background:var(--paper-2);
border-left:2px solid var(--accent);padding:9px 12px;line-height:1.65;}
.pl-axbar{display:grid;grid-template-columns:160px 1fr 70px;gap:8px 12px;align-items:center;
font-family:var(--sans);font-size:12.5px;margin:5px 0;}
.pl-axbar__t{color:var(--ink);font-weight:600;}
.pl-axbar__n{color:var(--muted);text-align:right;}
#pl-filters{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:0 0 14px;}
#pl-q{flex:1;min-width:210px;border:1px solid var(--rule);background:var(--paper);color:var(--ink);
font-family:var(--sans);font-size:13px;padding:8px 12px;}
#pl-q:focus{outline:2px solid var(--accent);outline-offset:1px;}
.pl-tbl td,.pl-tbl th{vertical-align:top;}
.pl-tbl .pl-n{font-weight:700;color:var(--ink);}
.pl-hide{display:none!important;}
.pl-foot{display:flex;gap:18px;flex-wrap:wrap;align-items:center;font-family:var(--sans);
font-size:12px;color:var(--muted);margin-top:12px;}
.pl-foot b{color:var(--ink);font-size:15px;margin-right:2px;}
.pl-track{border-top:1px solid var(--ink);padding:16px 0;}
.pl-track__h{display:flex;gap:12px;align-items:baseline;flex-wrap:wrap;}
.pl-track h3{font-family:var(--serif-display);font-size:20px;font-weight:600;margin:0;color:var(--ink);}
.pl-track__src{font-family:var(--sans);font-size:11.5px;color:var(--muted);}
.pl-track__dek{font-family:var(--serif-body);font-size:14px;line-height:1.6;color:var(--ink-2);margin:6px 0 0;}
.pl-h4{font-family:var(--sans);font-size:10.5px;font-weight:800;letter-spacing:.12em;
text-transform:uppercase;color:var(--muted);margin:14px 0 6px;}
.pl-list{margin:0;padding-left:18px;font-family:var(--serif-body);font-size:13.5px;line-height:1.6;color:var(--ink-2);}
.pl-list li{margin:4px 0;}
.pl-link{font-family:var(--sans);font-size:12px;font-weight:700;color:var(--accent);text-decoration:none;}
.pl-link:hover{text-decoration:underline;}
.pl-done{color:#1d7a4d;font-weight:700;}
.pl-open{color:#96690a;font-weight:700;}
@media (max-width:900px){
  .pl-stage{grid-template-columns:46px 1fr;}
  .pl-pass dl{grid-template-columns:1fr;gap:4px 0;}
  .pl-pass dt{padding-top:8px;}
  .pl-axbar{grid-template-columns:120px 1fr 60px;}
}
@media print{
  .pl-pass{break-inside:avoid;}
  #pl-filters{display:none;}
  .pl-pass[open] summary{font-weight:700;}
}
"""

# Фильтры реестра метрик: прогрессивный JS по образцу AFISHA_JS — таблица целиком
# отрисована на сервере, без JS видны все строки, скрипт только скрывает лишние.
PLANS_JS = """<script>
(function(){
  var rows=Array.prototype.slice.call(document.querySelectorAll('#pl-reg tbody tr[data-ax]'));
  if(!rows.length){return;}
  var q=document.getElementById('pl-q');
  var shown=document.getElementById('pl-shown');
  var empty=document.getElementById('pl-empty');
  var ST={ax:'all',st:'all',q:''};
  function pass(r){
    if(ST.ax!=='all'&&r.getAttribute('data-ax')!==ST.ax){return false;}
    if(ST.st!=='all'&&r.getAttribute('data-st')!==ST.st){return false;}
    if(ST.q&&(r.getAttribute('data-q')||'').indexOf(ST.q)===-1){return false;}
    return true;
  }
  function paint(){
    var n=0;
    rows.forEach(function(r){var ok=pass(r);r.classList.toggle('pl-hide',!ok);if(ok){n++;}});
    if(shown){shown.textContent=n;}
    if(empty){empty.hidden=n>0;}
    document.querySelectorAll('#pl-filters .fbtn').forEach(function(b){
      var f=b.getAttribute('data-f'),v=b.getAttribute('data-v');
      var on=(f==='ax'&&ST.ax===v)||(f==='st'&&ST.st===v);
      b.classList.toggle('active',!!on);
    });
  }
  document.querySelectorAll('#pl-filters .fbtn').forEach(function(b){
    b.addEventListener('click',function(){
      var f=b.getAttribute('data-f'),v=b.getAttribute('data-v');
      if(f==='ax'){ST.ax=(ST.ax===v?'all':v);}
      if(f==='st'){ST.st=(ST.st===v?'all':v);}
      paint();
    });
  });
  if(q){
    q.addEventListener('input',function(){ST.q=q.value.trim().toLowerCase();paint();});
  }
  paint();
})();
</script>"""


def render_plans(cfg, trends, store, status, an=None):
    """Страница «Планы»: треки планов издания и внедрение методов.

    Собирается из plans.py (редакционный реестр метрик, паспорта, волны, риски)
    и из markdown-документов репозитория (ROADMAP.md, server_plan.md,
    plan_frontpage_v4.md, district_sources_draft.md, owner_verification.md),
    которые читаются при генерации: правка документа сразу видна на витрине.
    Без JavaScript видны все таблицы — скрипт только фильтрует реестр метрик.
    """
    import plans as P
    import methods as M
    now = datetime.now(UTC4)
    nav_html = render_nav(cfg, "projects", "../", subnav=subnav_projects("../", "plans"))
    an = an or {}
    cnt = P.counts()
    axes = P.by_axis()
    open_groups = P.roadmap_open()
    open_n = sum(len(g["items"]) for g in open_groups)
    stages = P.server_stages()
    decided, opened = P.server_choices()
    sprints = P.frontpage_sprints()
    ver, ver_date = P.roadmap_version()
    gh = "https://github.com/Volgin1917/gudok/blob/main/"

    def st_chip(st):
        return f'<span class="pl-st pl-st--{esc(st)}">{esc(P.STATUS.get(st, st))}</span>'

    # ---------------------------------------------------------- конвейер внедрения
    stage_rows = []
    for st in P.METHOD_STAGES:
        stage_rows.append(f"""<div class="pl-stage"><div class="pl-stage__n">{st['n']}</div>
<div><h3>{esc(st['t'])}</h3><p>{esc(st['d'])}</p>
<div class="pl-code"><b>Где в коде:</b> {esc(st['where'])}</div>
<div class="pl-code"><b>Проверка:</b> {esc(st['check'])}</div>
<div class="pl-ex">Пример — {esc(st['ex'])}</div></div></div>""")

    # ---------------------------------------------------------- паспорта метрик
    pass_html = []
    for i, pl in enumerate(P.PILOTS):
        pass_html.append(f"""<details class="pl-pass"{' open' if i == 0 else ''}>
<summary>{esc(pl['n'])}</summary>
<div class="pl-pass__meta">{st_chip(pl.get('st', 'queue'))}
<span class="pl-st">ось: {esc(P.AXIS_NAME.get(pl.get('ax'), pl.get('ax', '')))}</span>
<span class="pl-st">трудозатраты: {esc(pl.get('ef', ''))}</span></div>
<p class="pl-ex">{esc(pl.get('dek', ''))}</p>
<dl>
<dt>Гипотеза</dt><dd>{esc(pl.get('hyp', ''))}</dd>
<dt>Формула</dt><dd><div class="pl-formula">{pl.get('formula', '')}</div></dd>
<dt>Источник данных</dt><dd>{esc(pl.get('src', ''))}</dd>
<dt>Порог тревоги</dt><dd>{esc(pl.get('thr', ''))}</dd>
<dt>Где публикуется</dt><dd>{esc(pl.get('out', ''))}</dd>
<dt>Первый расчёт</dt><dd>{esc(pl.get('first', ''))}</dd>
</dl></details>""")

    # ---------------------------------------------------------- реестр метрик
    ax_order = [a["k"] for a in P.AXES]
    ax_bars = []
    for k in ax_order:
        row = axes.get(k)
        if not row:
            continue
        total = max(1, row.get("total", 0))
        done = row.get("done", 0)
        pct = round(100 * done / total)
        ax_bars.append(f"""<div class="pl-axbar"><span class="pl-axbar__t">{esc(P.AXIS_NAME.get(k, k))}</span>
<span class="bar-wrap"><span class="bar-fill" style="width:{pct}%"></span></span>
<span class="pl-axbar__n">{done} из {row.get('total', 0)}</span></div>""")

    st_order = ["done", "ok", "queue", "search", "hard"]
    reg_rows = []
    reg = sorted(P.REG, key=lambda r: (ax_order.index(r.get("ax")) if r.get("ax") in ax_order else 99,
                                       -int(r.get("p") or 0), r.get("n", "")))
    for r in reg:
        stt = r.get("st") if r.get("st") in P.STATUS else "queue"
        q = " ".join(str(r.get(k, "")) for k in ("n", "h", "s", "ax")).lower()
        q = esc(q + " " + P.AXIS_NAME.get(r.get("ax"), ""))
        reg_rows.append(f"""<tr data-ax="{esc(r.get('ax', ''))}" data-st="{esc(stt)}" data-q="{q}">
<td class="pl-n">{esc(r.get('n', ''))}</td>
<td>{esc(P.AXIS_NAME.get(r.get('ax'), r.get('ax', '')))}</td>
<td>{st_chip(stt)}</td>
<td>{esc(r.get('ef', ''))}</td>
<td>{esc(str(r.get('p', '')))}</td>
<td>{esc(r.get('dn', '') or '—')}</td>
<td>{esc(r.get('h', ''))}</td>
<td>{esc(r.get('s', ''))}</td></tr>""")

    ax_chips = ['<button type="button" class="fbtn active" data-f="ax" data-v="all">Все оси</button>']
    for a in P.AXES:
        n = axes.get(a["k"], {}).get("total", 0)
        ax_chips.append(f'<button type="button" class="fbtn" data-f="ax" data-v="{esc(a["k"])}">'
                        f'{esc(a["n"])} ({n})</button>')
    st_chips = ['<button type="button" class="fbtn active" data-f="st" data-v="all">Любой статус</button>']
    for k in st_order:
        st_chips.append(f'<button type="button" class="fbtn" data-f="st" data-v="{k}">'
                        f'{esc(P.STATUS[k])} ({cnt.get(k, 0)})</button>')

    # ---------------------------------------------------------- волны внедрения
    wave_rows = []
    for w in P.WAVES:
        items = " ".join(f'{esc(n)} {st_chip(s)}' for n, s in w.get("items", []))
        wave_rows.append(f"""<tr><td class="pl-n">{esc(w.get('t', ''))}</td>
<td>{esc(w.get('per', ''))}</td><td>{esc(w.get('req', ''))}</td>
<td style="font-family:var(--serif-body);font-size:13px;line-height:1.9;">{items}</td></tr>""")

    # ---------------------------------------------------------- источники данных
    src_rows = []
    for s in P.SOURCES:
        src_rows.append(f"""<tr><td class="pl-n">{esc(s.get('n', ''))}</td>
<td>{st_chip(s.get('st', 'search'))}</td><td>{esc(s.get('tag', ''))}</td>
<td>{esc(s.get('d', ''))}</td><td>{esc(s.get('note', ''))}</td></tr>""")

    # ---------------------------------------------------------- риски метода
    risk_html = "".join(
        f'<li><b>{esc(t)}</b> — {esc(x)}</li>' for t, x in P.RISKS)

    # ---------------------------------------------------------- треки планов
    def track_head(tr, extra=""):
        return (f'<div class="pl-track" id="track-{esc(tr["key"])}"><div class="pl-track__h">'
                f'<h3>{esc(tr["title"])}</h3>'
                f'<span class="pl-track__src">{esc(tr["src"])}</span>{extra}</div>'
                f'<p class="pl-track__dek">{esc(tr["dek"])}</p>')

    meth = M.counts()
    meth_rows = []
    for mkey, mtitle, _mshort in M.GROUPS:
        items = [m for m in M.METHODS if m.get("group") == mkey]
        meth_rows.append(
            f'<tr><td class="pl-n">{esc(mtitle)}</td><td>{len(items)}</td>'
            f'<td>{sum(1 for m in items if m.get("status") == "work")}</td>'
            f'<td>{sum(1 for m in items if m.get("status") == "test")}</td>'
            f'<td>{sum(1 for m in items if m.get("status") == "queue")}</td>'
            f'<td>{sum(1 for m in items if m.get("ideo"))}</td></tr>')
    meth_rows = "".join(meth_rows)

    passport = an.get("calendar_passport") or {}
    afisha_gate = (cfg.get("settings", {}) or {}).get("afisha", {}) or {}
    venues_n = 0
    try:
        with open(os.path.join(DATA, "venues.json"), encoding="utf-8") as f:
            venues_n = len(json.load(f) or {})
    except (OSError, ValueError):
        venues_n = 0

    tracks_html = []
    for tr in P.TRACKS:
        key = tr["key"]
        if key == "roadmap":
            rows = []
            for g in open_groups:
                lis = "".join(f'<li>{esc(i["text"])}</li>' for i in g["items"])
                rows.append(f'<div class="pl-h4">{esc(g["section"] or "Без раздела")} · {len(g["items"])}</div>'
                            f'<ul class="pl-list">{lis}</ul>')
            extra = (f'<span class="pl-track__src">версия документа {esc(ver)} · {esc(ver_date)}</span>'
                     f'<a class="pl-link" href="{gh}ROADMAP.md" target="_blank" rel="noopener">источник →</a>')
            tracks_html.append(track_head(tr, extra)
                               + f'<div class="pl-h4">Открытые пункты · {open_n}</div>'
                               + "".join(rows)
                               + '<div class="note">Полный журнал решений и история версий — в ROADMAP.md; '
                                 'страница перечисляет только незакрытые пункты, они перечитываются при каждой сборке.</div></div>')
        elif key == "infospace":
            extra = ('<a class="pl-link" href="#metrics">реестр на этой странице ↑</a>'
                     f'<a class="pl-link" href="../infospace.html">витрина раздела →</a>')
            tracks_html.append(track_head(tr, extra)
                               + f'<div class="pl-h4">Статусы реестра</div>'
                               + '<ul class="pl-list">'
                               + "".join(f'<li>{esc(P.STATUS[k])} — <b>{cnt.get(k, 0)}</b></li>'
                                         for k in st_order if cnt.get(k))
                               + '</ul>'
                               + '<div class="note">Метрика добавляется в раздел только через паспорт '
                                 '(см. «Внедрение методов»). Черновик предложения v0.9 — infospace-plan.html.</div></div>')
        elif key == "server":
            st_rows = "".join(
                f'<tr><td class="pl-n">{esc(s["stage"])}</td><td>{esc(s["term"])}</td>'
                f'<td>{esc(s["content"])}</td><td>{esc(s["ready"])}</td></tr>' for s in stages)
            dec = "".join(f'<li><span class="pl-done">решено</span> — {esc(x)}</li>' for x in decided)
            op = "".join(f'<li><span class="pl-open">открыто</span> — {esc(x)}</li>' for x in opened)
            extra = f'<a class="pl-link" href="{gh}server_plan.md" target="_blank" rel="noopener">источник →</a>'
            tracks_html.append(track_head(tr, extra)
                               + '<div class="pl-h4">Этапы миграции</div>'
                               + '<table class="tbl pl-tbl"><thead><tr><th>Этап</th><th>Срок</th>'
                                 '<th>Содержание</th><th>Критерий готовности</th></tr></thead>'
                                 f'<tbody>{st_rows}</tbody></table>'
                               + '<div class="pl-h4">Точки выбора</div>'
                               + f'<ul class="pl-list">{dec}{op}</ul>'
                               + '<div class="note">Не реализовано: в коде нет --snapshot, server.py, deploy.sh, '
                                 'notify.py. Публикация остаётся на GitHub Pages до этапа A.</div></div>')
        elif key == "frontpage":
            sp_html = []
            for sp in sprints:
                rows = "".join(
                    f'<tr><td>{esc(i["no"])}</td><td class="pl-n">{esc(i["proposal"])}</td>'
                    f'<td>{esc(i["status"])}</td><td>{esc(i["note"])}</td></tr>' for i in sp["items"])
                sp_html.append(f'<div class="pl-h4">{esc(sp["title"])} · готово {sp["done"]} из {sp["total"]}</div>'
                               '<table class="tbl pl-tbl"><tbody>' + rows + '</tbody></table>')
            extra = f'<a class="pl-link" href="{gh}plan_frontpage_v4.md" target="_blank" rel="noopener">источник →</a>'
            tracks_html.append(track_head(tr, extra) + "".join(sp_html)
                               + '<div class="note">Статусы берутся из таблиц plan_frontpage_v4.md; '
                                 'колонка «Статус данных» в Спринте 1 описывает готовность данных, а не факт внедрения.</div></div>')
        elif key == "afisha":
            extra = '<a class="pl-link" href="../afisha.html">витрина афиши →</a>'
            tracks_html.append(track_head(tr, extra)
                               + '<div class="pl-h4">Порог входа сейчас</div>'
                               + '<ul class="pl-list">'
                               + f'<li>горизонт — <b>{esc(str(afisha_gate.get("horizon_days", 45)))}</b> дней, '
                                 f'не более <b>{esc(str(afisha_gate.get("max_per_day", 4)))}</b> событий в день, '
                                 f'порог уверенности <b>{esc(str(afisha_gate.get("threshold", 0)))}</b></li>'
                               + f'<li>веса индекса: {esc(json.dumps(afisha_gate.get("weights", {}), ensure_ascii=False))}</li>'
                               + f'<li>площадок в справочнике data/venues.json: <b>{venues_n}</b></li>'
                               + (f'<li>последний прогон: найдено дат <b>{esc(str(passport.get("found_dates", "—")))}</b>, '
                                  f'прошло порог <b>{esc(str(passport.get("accepted", "—")))}</b>, '
                                  f'отсев <b>{esc(str(passport.get("rejected", "—")))}</b> '
                                  f'({esc(str(passport.get("run_local", "")))})</li>' if passport else '')
                               + '</ul>'
                               + '<div class="note">Методика порога опубликована на странице афиши вместе с блоком '
                                 '«Не прошло порог» — отсев виден читателю, а не только в логах.</div></div>')
        else:
            doc = P.read_md(tr["src"])
            heads = [t for lvl, t, _b in P.md_outline(doc) if lvl in (2, 3) and t][:14]
            lis = "".join(f'<li>{esc(h)}</li>' for h in heads)
            extra = f'<a class="pl-link" href="{gh}{esc(tr["src"])}" target="_blank" rel="noopener">источник →</a>'
            tracks_html.append(track_head(tr, extra)
                               + '<div class="pl-h4">Состав документа</div>'
                               + f'<ul class="pl-list">{lis}</ul></div>')

    return f"""<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Планы и внедрение методов — {cfg['brand']}</title>
<link rel="icon" type="image/png" href="../assets/logo_gudok.png">
<style>{CSS}{PLANS_CSS}</style></head><body>
<header class="masthead"><div class="mast-inner">
<div class="mast-side">Информационно-аналитическое издание<br>марксистской группы «Победа»</div>
<div class="mast-title">ГУДОК<span>.</span></div>
<div class="mast-side mast-side--right">Планы издания и методы<br>треков {len(P.TRACKS)} · метрик {cnt['total']} · подключено {cnt['done']}
<div class="mast-actions">{THEME_BTN}</div></div>
</div></header>
{nav_html}
<div class="page">

<div class="kpi-grid" style="margin:18px 0 6px;">
<div class="kpi"><div class="num">{len(P.TRACKS)}</div><div class="lbl">треков плана</div></div>
<div class="kpi"><div class="num">{cnt['total']}</div><div class="lbl">метрик-кандидатов в реестре</div></div>
<div class="kpi green"><div class="num">{cnt['done']}</div><div class="lbl">подключено к витрине</div></div>
<div class="kpi gold"><div class="num">{cnt['queue'] + cnt['ok']}</div><div class="lbl">в очереди на внедрение</div></div>
<div class="kpi"><div class="num">{open_n}</div><div class="lbl">открытых пунктов плана развития</div></div>
<div class="kpi red"><div class="num">{cnt['search'] + cnt['hard']}</div><div class="lbl">ищут данные или с риском метода</div></div>
</div>
<div class="note" style="margin-bottom:8px;">Одна страница вместо четырёх документов: план развития издания, план расширения
«Инфопространства», переезд на выделенный сервер и спринты первой полосы. Страница генерируется
(<code>generate.py → render_plans</code>) из редакционного реестра <code>plans.py</code> и из markdown-документов
репозитория — правка документа попадает на витрину при следующем прогоне конвейера. Собрано {now:%d.%m.%Y %H:%M} (UTC+4).</div>

<div class="sec-head" id="method" style="margin-top:34px;"><h2>Внедрение методов</h2><div class="line"></div>
<div class="badge">паспорт → данные → расчёт → блок → тест</div></div>
<div class="note" style="margin:0 0 14px;">Правило редакции: метрика или методика добавляется в раздел только через паспорт —
с гипотезой, формулой, источником данных, порогом тревоги и местом публикации. Пять шагов ниже одинаковы
для метрик «Инфопространства», для порогов афиши и для правил дедупликации: отличается только файл.</div>
{"".join(stage_rows)}

<div class="pl-h4">Реестр методик · v{M.VERSION}: {meth['total']} паспортов</div>
<table class="tbl pl-tbl"><thead><tr><th>Группа методик</th><th>Всего</th><th>Работают</th>
<th>В тесте</th><th>В очереди</th><th>Идеологический блок</th></tr></thead>
<tbody>{meth_rows}<tr><td class="pl-n">Итого</td><td>{meth['total']}</td><td>{meth['work']}</td>
<td>{meth['test']}</td><td>{meth['queue']}</td><td>{meth['ideo']}</td></tr></tbody></table>
<div class="note">Полные паспорта методик (вход, выход, метрики качества, модуль платформы, оценка
неопределённости и порядок проверки на контрольной выборке), сквозной раздел «Идеология и гегемония»,
техконтур из открытых стандартов и стенд испытания с генератором протокола —
<a href="../methods.html" style="color:var(--accent);font-weight:700;">на странице «Методы» →</a>
Серверный аналог протокола стенда: <code>methods.py → protocol()</code>, покрыт тестами.</div>

<div class="sec-head"><h2>Паспорта метрик-пилотов</h2><div class="line"></div>
<div class="badge">{len(P.PILOTS)} паспорта · образец для остальных</div></div>
{"".join(pass_html)}

<div class="sec-head" id="metrics"><h2>Реестр метрик-кандидатов</h2><div class="line"></div>
<div class="badge">{cnt['total']} метрики · {len(P.AXES)} осей</div></div>
<div class="pl-h4">Готовность по осям</div>
{"".join(ax_bars)}
<div id="pl-filters">{''.join(ax_chips)}</div>
<div id="pl-filters">{''.join(st_chips)}
<input id="pl-q" type="search" placeholder="Поиск по реестру — например «тон», «ЕИС», «Gini», «село»"></div>
<table class="tbl pl-tbl" id="pl-reg"><thead><tr>
<th>Метрика</th><th>Ось</th><th>Статус</th><th>Трудо&shy;ёмкость</th><th>Приоритет</th>
<th>Подклю&shy;чена</th><th>Что даёт</th><th>Данные</th></tr></thead>
<tbody>{''.join(reg_rows)}</tbody></table>
<div class="pl-foot"><span>Показано: <b id="pl-shown">{cnt['total']}</b> из {cnt['total']}</span>
<span id="pl-empty" hidden>Под условия ничего не нашлось — снимите фильтр.</span>
<span style="margin-left:auto;">фильтры работают в браузере; без JavaScript виден весь реестр</span></div>

<div class="sec-head"><h2>Волны внедрения</h2><div class="line"></div>
<div class="badge">порядок работ и что нужно для каждого шага</div></div>
<table class="tbl pl-tbl"><thead><tr><th>Волна</th><th>Срок</th><th>Что нужно</th><th>Состав и статусы</th></tr></thead>
<tbody>{''.join(wave_rows)}</tbody></table>

<div class="sec-head"><h2>Источники данных</h2><div class="line"></div>
<div class="badge">что подключаем ради новых метрик</div></div>
<table class="tbl pl-tbl"><thead><tr><th>Источник</th><th>Статус</th><th>Метка</th><th>Что даёт</th><th>Примечание</th></tr></thead>
<tbody>{''.join(src_rows)}</tbody></table>

<div class="sec-head"><h2>Методологические риски</h2><div class="line"></div>
<div class="badge">что может исказить картину и как это лечим</div></div>
<ul class="pl-list">{risk_html}</ul>

<div class="sec-head"><h2>Треки планов</h2><div class="line"></div>
<div class="badge">{len(P.TRACKS)} трека · документы перечитываются при сборке</div></div>
{''.join(tracks_html)}

<div class="note" style="margin-top:22px;">Историческая справка: до объединения планы жили отдельными страницами —
<code>roadmap.html</code> (визуальная версия ROADMAP.md) и <code>infospace-plan.html</code> (черновик предложения v0.9
по расширению «Инфопространства»). Оба документа сохранены в репозитории как источники; эта страница собирается
из них и из реестра <code>plans.py</code>.</div>

</div>
{footer.render_footer('../')}
{PLANS_JS}
</body></html>"""


DOSSIER_CSS = """
/* ---- «Досье»: панель фильтров, карточки персон, тон, справка, доказательность ---- */
.panel{border:1px solid var(--rule);background:var(--paper-2);padding:14px 16px;margin-top:18px;}
.panel-row{display:flex;gap:10px;flex-wrap:wrap;align-items:center;}
.panel-row+.panel-row{margin-top:10px;}
.plbl{font-family:var(--sans);font-size:10.5px;font-weight:700;letter-spacing:.14em;
text-transform:uppercase;color:var(--muted);margin-right:6px;align-self:center;}
.dsearch{flex:1;min-width:240px;display:flex;align-items:center;gap:8px;border:1px solid var(--ink);
background:var(--paper);padding:8px 12px;}
.dsearch input{border:none;outline:none;background:none;font-family:var(--sans);font-size:13.5px;
color:var(--ink);width:100%;}
.dsearch input::placeholder{color:var(--muted);}
.dsearch .ic{color:var(--muted);font-size:14px;}
.dcount{margin-left:auto;font-family:var(--sans);font-size:12px;color:var(--muted);}
.dcount b{color:var(--ink);}
.dgrid{display:grid;grid-template-columns:1fr 1fr;gap:0 48px;margin-top:22px;}
.dcard{border-top:1px solid var(--ink);padding:16px 0 20px;break-inside:avoid;}
.dsum{list-style:none;cursor:pointer;}
.dsum::-webkit-details-marker{display:none;}
.dsum:focus-visible{outline:2px solid var(--accent);outline-offset:3px;}
.dcard-head{display:flex;gap:16px;align-items:flex-start;}
.davatar{flex:0 0 56px;width:56px;height:56px;border:1px solid var(--ink);display:flex;align-items:center;
justify-content:center;font-family:var(--rubleny);font-size:20px;letter-spacing:.02em;color:var(--paper);
background:var(--ink);}
.dcard.focus .davatar{background:var(--accent);border-color:var(--accent);color:#fff;}
.dtitle{flex:1;min-width:0;}
.dname{font-family:var(--serif-display);font-weight:600;font-size:20px;line-height:1.2;color:var(--ink);}
.drole{font-family:var(--sans);font-size:12.5px;color:var(--ink-2);margin-top:3px;line-height:1.45;}
.dorg{font-family:var(--sans);font-size:11.5px;color:var(--muted);margin-top:2px;}
.dchips{display:flex;gap:6px;flex-wrap:wrap;margin-top:8px;}
.dchip{display:inline-block;font-family:var(--sans);font-size:10px;font-weight:700;letter-spacing:.08em;
text-transform:uppercase;color:var(--muted);border:1px solid var(--rule);padding:2px 8px;white-space:nowrap;}
.dchip.geo{color:var(--ink-2);border-color:var(--ink-2);}
.dstamp{font-family:var(--sans);font-size:10px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;
padding:3px 9px;white-space:nowrap;border:1px solid var(--rule);color:var(--muted);background:var(--paper-2);}
.dstamp.hot{color:#fff;background:var(--accent);border-color:var(--accent);}
.dstamp.new{color:var(--ink);border-color:var(--ink);background:none;}
.dtoggle{margin-left:auto;flex-shrink:0;font-family:var(--sans);font-size:11px;font-weight:600;
color:var(--muted);border-bottom:1px solid var(--rule);padding-top:4px;}
.dsum:hover .dtoggle{color:var(--accent);border-color:var(--accent);}
.dstats{display:grid;grid-template-columns:repeat(4,auto);gap:0 22px;justify-content:start;margin-top:12px;
padding-top:10px;border-top:1px solid var(--rule);}
.dst .n{font-family:var(--serif-display);font-weight:600;font-size:19px;color:var(--ink);line-height:1.1;}
.dst .l{font-family:var(--sans);font-size:10.5px;color:var(--muted);text-transform:uppercase;
letter-spacing:.08em;margin-top:2px;}
.tonebar{grid-column:1/-1;display:flex;height:10px;border:1px solid var(--rule);margin-top:6px;
max-width:340px;background:var(--paper);}
.tonebar i{display:block;height:100%;}
.tonebar .tp{background:var(--pos);}
.tonebar .tn{background:var(--neu);}
.tonebar .tg{background:var(--neg);}
.tonelegend{grid-column:1/-1;font-family:var(--sans);font-size:10.5px;color:var(--muted);margin-top:4px;}
.tonelegend b{font-weight:700;}
.tonelegend .cp{color:var(--pos);}
.tonelegend .cg{color:var(--neg);}
.ddet{margin-top:14px;border-top:1px solid var(--rule);}
.ddet h4{font-family:var(--sans);font-size:10.5px;font-weight:700;letter-spacing:.14em;
text-transform:uppercase;color:var(--muted);margin:14px 0 6px;}
.fact{display:grid;grid-template-columns:130px 1fr;gap:10px;font-family:var(--sans);font-size:12.5px;
padding:5px 0;border-bottom:1px dashed var(--rule);color:var(--ink-2);}
.fact b{color:var(--muted);font-weight:600;font-size:10.5px;letter-spacing:.08em;text-transform:uppercase;
padding-top:2px;}
.story{padding:8px 0;border-bottom:1px solid var(--rule);}
.story:last-child{border-bottom:none;}
.story b{font-family:var(--serif-body);font-size:14.5px;color:var(--ink);font-weight:600;}
.story span{display:block;font-family:var(--sans);font-size:11.5px;color:var(--muted);margin-top:2px;}
.story .arc{font-family:var(--sans);font-size:11px;color:var(--ink-2);}
.quote{font-family:var(--serif-display);font-style:italic;font-size:15px;line-height:1.4;color:var(--ink);
border-left:2px solid var(--rule);padding:4px 0 4px 12px;margin:8px 0;}
.quote span{display:block;font-family:var(--sans);font-style:normal;font-size:11px;color:var(--muted);
margin-top:4px;}
.srcs{display:flex;gap:6px;flex-wrap:wrap;margin-top:4px;}
.src{font-family:var(--sans);font-size:10.5px;font-weight:600;border:1px solid var(--rule);padding:2px 8px;
color:var(--ink-2);}
.src b{color:var(--accent);font-weight:700;}
.dfoot{display:flex;gap:14px;flex-wrap:wrap;align-items:baseline;margin-top:14px;padding-top:10px;
border-top:1px solid var(--ink);}
.dfoot .upd{font-family:var(--sans);font-size:11px;color:var(--muted);}
.dfoot a.go{font-family:var(--sans);font-size:12px;font-weight:600;color:var(--accent);}
.verify{font-family:var(--sans);font-size:11.5px;color:var(--ink-2);background:var(--paper-2);
border:1px solid var(--rule);padding:6px 10px;margin-top:10px;}
.verify b{color:var(--pos);}
.verify.warn b{color:var(--accent);}
.demo-mark{font-family:var(--sans);font-size:10.5px;font-weight:700;letter-spacing:.14em;
text-transform:uppercase;color:var(--accent);border:1px solid var(--accent);padding:3px 9px;}
@media (max-width:1100px){.dgrid{grid-template-columns:1fr;}}
@media (max-width:720px){.fact{grid-template-columns:1fr;gap:2px;}.dstats{grid-template-columns:repeat(2,auto);}}
@media print{
  .panel{display:none!important;}
  .dcard .ddet{display:block!important;}
}
"""

# Прогрессивный JS: фильтры по роли и статусу, поиск, счётчик и подпись раскрытия.
# Без JS видны все карточки (они отрисованы на сервере и отсортированы по упоминаниям),
# раскрытие работает нативным <details>.
DOSSIER_JS = """<script>
(function(){
  var grid=document.getElementById('dGrid');
  if(!grid){return;}
  var cards=Array.prototype.slice.call(grid.querySelectorAll('.dcard'));
  var q=document.getElementById('dq');
  var shown=document.getElementById('cntShown');
  var empty=document.getElementById('dEmpty');
  var ST={r:'all',s:'all',q:''};
  function pass(c){
    if(ST.r!=='all'&&c.getAttribute('data-role')!==ST.r){return false;}
    if(ST.s!=='all'&&c.getAttribute('data-status')!==ST.s){return false;}
    if(ST.q){
      var hay=((c.getAttribute('data-name')||'')+' '+(c.getAttribute('data-hay')||'')).toLowerCase();
      if(hay.indexOf(ST.q)===-1){return false;}
    }
    return true;
  }
  function paint(){
    var n=0;
    cards.forEach(function(c){var ok=pass(c);c.style.display=ok?'':'none';if(ok){n++;}});
    if(shown){shown.textContent=n;}
    if(empty){empty.classList.toggle('hidden',n>0);}
    document.querySelectorAll('#fRole .fbtn').forEach(function(b){b.classList.toggle('active',b.getAttribute('data-r')===ST.r);});
    document.querySelectorAll('#fStatus .fbtn').forEach(function(b){b.classList.toggle('active',b.getAttribute('data-s')===ST.s);});
  }
  document.querySelectorAll('#fRole .fbtn').forEach(function(b){
    b.addEventListener('click',function(){ST.r=b.getAttribute('data-r');paint();});
  });
  document.querySelectorAll('#fStatus .fbtn').forEach(function(b){
    b.addEventListener('click',function(){ST.s=b.getAttribute('data-s');paint();});
  });
  if(q){q.addEventListener('input',function(){ST.q=q.value.trim().toLowerCase();paint();});}
  window._dReset=function(){ST.r='all';ST.s='all';ST.q='';if(q){q.value='';}paint();};
  cards.forEach(function(c){
    c.addEventListener('toggle',function(){
      var t=c.querySelector('.dtoggle');
      if(t){t.textContent=c.open?'досье ↑':'досье ↓';}
    });
  });
  paint();
})();
</script>"""


def render_dossier(cfg, trends, store, status):
    """Раздел «Досье»: карточки действующих лиц инфополя (прототип на демо-данных).

    Данные — dossier.py: состав карточек, таблица «как собирается досье» (поле →
    методика реестра → способ получения), этические границы и очередь развития.
    Страница в общем стиле издания: шапка, навигация, поднавигация рубрики и подвал —
    из общих компонентов; свой только DOSSIER_CSS. Метрики карточки видны без раскрытия,
    справка и сюжеты — в нативном <details>, поэтому всё читается и без JavaScript.
    Все персонажи демонстрационные — метка прототипа выведена в шапке и в вводной.
    """
    import dossier as D
    import methods as M
    now = datetime.now(UTC4)
    prefix = "../"
    nav_html = render_nav(cfg, "projects", prefix, subnav=subnav_projects(prefix, "dossier"))
    cnt = D.counts()
    per_role = D.by_role()
    persons = D.sorted_by_mentions()

    def link(href, text, cls="go"):
        """Ссылка с префиксом глубины: цели хранятся от корня сайта."""
        target = href if href.startswith(("http", "#")) else prefix + href
        return f'<a class="{cls}" href="{esc(target)}">{text}</a>'

    # ------------------------------------------------------------- карточки
    cards = []
    for p in persons:
        st = p.get("status") if p.get("status") in D.STATUS_TITLE else "back"
        stamp_cls = ("dstamp " + D.STATUS_CSS[st]).strip()
        chips = "".join(f'<span class="dchip{" geo" if kind == "geo" else ""}">{esc(text)}</span>'
                        for text, kind in p.get("chips", []))
        pos, neu, neg = p.get("tone_split", (0, 0, 0))
        facts = "".join(f'<div class="fact"><b>{esc(label)}</b><span>{text}</span></div>'
                        for label, text in p.get("facts", []))
        extra = p.get("extra") or {}
        extra_html = ""
        if extra:
            extra_html = (f'<h4>{esc(extra.get("head", ""))}</h4>'
                          + "".join(f'<div class="fact"><b>{esc(l)}</b><span>{t}</span></div>'
                                    for l, t in extra.get("facts", [])))
        stories = p.get("stories") or []
        stories_html = ""
        if stories:
            stories_html = f'<h4>{esc(p.get("stories_head", "Ключевые сюжеты"))}</h4>' + "".join(
                f'<div class="story"><b>{esc(s["t"])}</b><span class="arc">{esc(s["arc"])}</span>'
                f'<span>{esc(s["role"])}</span></div>' for s in stories)
        quote = p.get("quote") or {}
        quote_html = (f'<h4>Характерная цитата (демо)</h4><div class="quote">{esc(quote.get("text", ""))}'
                      f'<span>{esc(quote.get("src", ""))}</span></div>') if quote else ""
        srcs = "".join(f'<span class="src">{esc(n)} <b>{v}</b></span>'
                       for n, v in p.get("sources", []))
        if p.get("sources_more"):
            srcs += f'<span class="src">{esc(p["sources_more"])}</span>'
        srcs_html = f'<h4>Топ-источники упоминаний</h4><div class="srcs">{srcs}</div>' if srcs else ""
        ver = p.get("verify") or {}
        verify_html = (f'<div class="verify{" warn" if ver.get("kind") == "warn" else ""}">{ver.get("text", "")}</div>'
                       if ver else "")
        foot_links = "".join(link(href, esc(text)) for text, href in p.get("foot_links", []))
        hay = esc(" ".join([p.get("search", ""), p.get("name", ""), p.get("role", ""),
                            p.get("org", "")]).lower())
        cards.append(f"""<details class="dcard{' focus' if st == 'focus' else ''}" data-role="{esc(p.get('group', ''))}"
 data-status="{esc(st)}" data-name="{esc(p.get('search', ''))}" data-hay="{hay}"
 data-mentions="{int(p.get('mentions') or 0)}" id="{esc(p.get('id', ''))}">
<summary class="dsum"><div class="dcard-head">
<div class="davatar">{esc(p.get('avatar') or D.initials(p.get('name', '')))}</div>
<div class="dtitle"><div class="dname">{esc(p.get('name', ''))}</div>
<div class="drole">{esc(p.get('role', ''))}</div>
<div class="dorg">{esc(p.get('org', ''))}</div>
<div class="dchips">{chips}</div></div>
<span class="{stamp_cls}">{esc(D.STATUS_TITLE[st])}</span>
<span class="dtoggle">досье ↓</span></div>
<div class="dstats">
<div class="dst"><div class="n">{int(p.get('mentions') or 0)}</div><div class="l">упоминаний / 30 дн.</div></div>
<div class="dst"><div class="n">{int(p.get('stories_n') or 0)}</div><div class="l">сюжетов</div></div>
<div class="dst"><div class="n">{int(p.get('sources_n') or 0)}</div><div class="l">источников</div></div>
<div class="dst"><div class="n">{esc(p.get('tone', ''))}</div><div class="l">индекс тона (М-05)</div></div>
<div class="tonebar"><i class="tp" style="width:{pos}%"></i><i class="tn" style="width:{neu}%"></i><i class="tg" style="width:{neg}%"></i></div>
<div class="tonelegend"><b class="cp">позитив {pos}%</b> · нейтрально {neu}% · <b class="cg">негатив {neg}%</b></div>
</div></summary>
<div class="ddet">
<h4>Справка (открытые данные, демо)</h4>
{facts}
{extra_html}
{stories_html}
{quote_html}
{srcs_html}
{verify_html}
<div class="dfoot"><span class="upd">{esc(p.get('foot_upd', ''))}</span>{foot_links}</div>
</div>
</details>""")

    # ------------------------------------------------------------- панель фильтров
    role_btns = ['<button type="button" class="fbtn active" data-r="all">все</button>']
    for key, title in D.ROLES:
        role_btns.append(f'<button type="button" class="fbtn" data-r="{key}">{esc(title)}'
                         f'{" (" + str(per_role.get(key, 0)) + ")" if per_role.get(key) else ""}</button>')
    st_btns = ['<button type="button" class="fbtn active" data-s="all">все</button>']
    for key, title in D.STATUSES:
        st_btns.append(f'<button type="button" class="fbtn" data-s="{key}">{esc(title)}'
                       f' ({cnt.get(key, 0)})</button>')

    # ------------------------------------------------------------- как собирается досье
    pipe_rows = []
    for field, refs, how in D.PIPELINE:
        ref_html = " ".join(
            f'<a href="{esc(prefix + href)}" style="color:var(--accent);">{esc(label)}</a>' if href
            else esc(label)
            for label, href in refs)
        pipe_rows.append(f'<tr><td><b>{esc(field)}</b></td><td>{ref_html}</td><td>{esc(how)}</td></tr>')

    queue_rows = "".join(f'<tr><td><b>{esc(b)}</b></td><td>{t}</td></tr>' for b, t in D.QUEUE)

    kpi = [(str(cnt["persons"]), "персон в досье"), (str(cnt["focus"]), "сейчас в фокусе"),
           (f"{cnt['mentions']:,}".replace(",", " "), "упоминаний за 30 дней"),
           (str(cnt["stories"]), "сюжетов с участием")]
    kpi += [(n, l) for n, l in D.KPI_STATIC]
    kpi_html = "".join(f'<div class="kpi"><div class="num">{esc(n)}</div><div class="lbl">{esc(l)}</div></div>'
                       for n, l in kpi)

    note_intro = D.NOTES[0].replace("{prefix}", prefix)
    related = "".join(link(href, esc(text), cls="") for text, href in [
        ("дашборд «Инфопространство»", "infospace.html"),
        ("реестр методик", "methods.html"),
        ("планы и внедрение методов", "projects/plans.html"),
        ("досье «Выборы-2026»", "projects/elections_2026.html"),
        ("досье «Госзакупки»", "projects/goszakupki.html"),
        ("архив-матрица", "archive.html")])

    return f"""<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Досье — действующие лица инфополя · {cfg['brand']}</title>
<meta name="description" content="Прототип раздела «Досье»: карточки действующих лиц инфополя Ульяновской области. Упоминания, тон, дуги сюжетов и источники — по методикам реестра. Данные демонстрационные.">
<link rel="icon" type="image/png" href="../assets/logo_gudok.png">
<style>{CSS}{DOSSIER_CSS}</style></head><body>
<a class="skip" href="#main">К содержанию</a>
<header class="masthead"><div class="mast-inner">
<div class="mast-side">Информационно-аналитическое издание<br>марксистской группы «Победа»</div>
<div class="mast-title">ГУДОК<span>.</span></div>
<div class="mast-side mast-side--right">Проекты издания<br>досье действующих лиц инфополя
<div class="mast-actions"><span class="demo-mark">{esc(D.DEMO_LABEL)}</span>{THEME_BTN}</div></div>
</div></header>
{nav_html}
<main id="main">
<div class="wrap1200" style="padding-top:20px;">

<div class="sec-head" style="margin-top:0;"><h2>Досье: действующие лица инфополя</h2><div class="line"></div>
<div class="badge">{esc(D.DEMO_LABEL)} · карточек: {cnt['persons']} · версия {esc(D.VERSION)}</div></div>
<div class="note" style="margin-bottom:6px;">{note_intro}</div>
<div class="note" style="border-left-color:var(--rule);">{D.NOTES[1]}</div>

<div class="kpi-grid" style="margin-top:22px;">{kpi_html}</div>

<div class="panel">
<div class="panel-row"><label class="dsearch"><span class="ic">⌕</span>
<input type="search" id="dq" placeholder="Поиск: фамилия, должность, организация, город…" aria-label="Поиск по досье"></label></div>
<div class="panel-row"><span class="plbl">Роль:</span>
<div class="filters" id="fRole" role="group" aria-label="Фильтр по роли">{''.join(role_btns)}</div></div>
<div class="panel-row"><span class="plbl">Статус:</span>
<div class="filters" id="fStatus" role="group" aria-label="Фильтр по статусу">{''.join(st_btns)}</div>
<span class="dcount">показано <b id="cntShown">{cnt['persons']}</b> из {cnt['persons']} · сортировка: по упоминаниям</span></div>
</div>
<p class="feed-empty hidden" id="dEmpty">Никого по этому фильтру не найдено —
<button type="button" class="btn" onclick="_dReset()">сбросить</button></p>

<div class="dgrid" id="dGrid">
{''.join(cards)}
</div>
</div>

<div class="sec-head" id="how"><h2>Как собирается досье</h2><div class="line"></div>
<div class="badge">конвейер карточки</div></div>
<div class="wrap1200">
<div class="note" style="margin-bottom:14px;">Карточка персоны — не рукописный текст, а <b>производное базы
материалов</b>: конвейер собирает её автоматически, редактор только подтверждает идентификацию и подписывает
справку. Любой элемент карточки раскрывается в список материалов-оснований.</div>
<div class="tbl-wrap"><table class="tbl"><thead><tr>
<th style="width:26%">Поле карточки</th><th style="width:22%">Методика реестра</th><th>Как получается</th>
</tr></thead><tbody>{''.join(pipe_rows)}</tbody></table></div>
<div class="verdict"><b>Этика и границы</b>{esc(D.ETHICS)}</div>

<div class="h3rule">Очередь развития раздела <span class="sub">· чего в прототипе пока нет</span></div>
<div class="tbl-wrap"><table class="tbl"><thead><tr><th style="width:30%">Блок</th><th>Содержание</th></tr></thead>
<tbody>{queue_rows}</tbody></table></div>

<div class="note" style="margin-top:22px;">Методик в реестре: <b>{M.counts()['total']}</b>
(работают {M.counts()['work']}, в тестировании {M.counts()['test']}, в очереди {M.counts()['queue']});
досье опирается на М-01, М-03, М-05, М-07, М-11, М-13, М-15, М-18, М-19, М-22 и М-26. Данные карточек —
редакционный прототип в <code>dossier.py</code>; автогенерация из <code>data/store.jsonl</code> — пункт
«Автогенерация» в очереди развития. Собрано {now:%d.%m.%Y %H:%M} (UTC+4).</div>

<div class="util-bar-wrap" style="padding:20px 0 0;"><div class="util-bar">
<span class="util-lbl">Связано:</span>{related}
<a href="https://github.com/Volgin1917/gudok" target="_blank" rel="noopener">GitHub</a>
</div></div>
</div>
</main>
{footer.render_footer(prefix)}
{DOSSIER_JS}
</body></html>"""


PRESS_JS = """<script>
(function(){
  var grid=document.getElementById('pGrid');
  if(!grid){return;}
  var cards=Array.prototype.slice.call(grid.querySelectorAll('.pcard'));
  if(!cards.length){return;}
  var q=document.getElementById('pq');
  var shown=document.getElementById('cntShown');
  var empty=document.getElementById('pEmpty');
  var ST={e:'all',s:'all',q:''};
  function pass(c){
    if(ST.e!=='all'&&c.getAttribute('data-epoch')!==ST.e){return false;}
    if(ST.s!=='all'&&c.getAttribute('data-status')!==ST.s){return false;}
    if(ST.q){
      var hay=(c.getAttribute('data-hay')||'').toLowerCase();
      if(hay.indexOf(ST.q)===-1){return false;}
    }
    return true;
  }
  function paint(){
    var n=0;
    cards.forEach(function(c){var ok=pass(c);c.classList.toggle('hidden',!ok);if(ok){n++;}});
    if(shown){shown.textContent=n;}
    if(empty){empty.classList.toggle('hidden',n>0);}
    document.querySelectorAll('#fEpoch .fbtn').forEach(function(b){b.classList.toggle('active',b.getAttribute('data-e')===ST.e);});
    document.querySelectorAll('#fStatus .fbtn').forEach(function(b){b.classList.toggle('active',b.getAttribute('data-s')===ST.s);});
  }
  document.querySelectorAll('#fEpoch .fbtn').forEach(function(b){
    b.addEventListener('click',function(){ST.e=b.getAttribute('data-e');paint();});
  });
  document.querySelectorAll('#fStatus .fbtn').forEach(function(b){
    b.addEventListener('click',function(){ST.s=b.getAttribute('data-s');paint();});
  });
  if(q){q.addEventListener('input',function(){ST.q=q.value.trim().toLowerCase();paint();});}
  window._pReset=function(){ST.e='all';ST.s='all';ST.q='';if(q){q.value='';}paint();};
  paint();
})();
</script>"""


PRESS_CSS = """
/* ---- «Архив прессы»: реестр-справочник изданий области (ядро v1) ---- */
.kpi-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-top:8px;}
.kpi{background:var(--paper-2);border:1px solid var(--rule);padding:14px 16px;}
.kpi .num{font-family:var(--serif-display);font-weight:700;font-size:23px;line-height:1;color:var(--ink);}
.kpi .lbl{font-family:var(--sans);font-size:9.5px;font-weight:700;letter-spacing:.14em;text-transform:uppercase;
color:var(--muted);margin-top:8px;}
.pgrid{display:grid;grid-template-columns:1fr 1fr;gap:0 40px;margin-top:6px;}
.pcard{border-top:3px double var(--ink);padding:14px 0 16px;break-inside:avoid;}
.pcard-head{display:flex;gap:14px;align-items:baseline;flex-wrap:wrap;cursor:pointer;list-style:none;}
.pcard-head::-webkit-details-marker{display:none;}
.pcard-head:focus-visible{outline:2px solid var(--accent);outline-offset:3px;}
.pname{font-family:var(--serif-display);font-weight:600;font-size:17px;line-height:1.2;color:var(--ink);}
.pyears{font-family:var(--sans);font-size:11px;font-weight:700;letter-spacing:.06em;color:var(--accent);
white-space:nowrap;}
.pbadge{display:inline-block;font-family:var(--sans);font-size:9.5px;font-weight:700;letter-spacing:.1em;
text-transform:uppercase;color:var(--muted);border:1px solid var(--rule);padding:2px 8px;}
.pbadge.live{color:var(--accent);border-color:var(--accent);}
.pbadge.dead{color:var(--muted);}
.pmeta{display:grid;grid-template-columns:1fr 1fr;gap:0 30px;margin-top:12px;}
.pfact{border-top:1px solid var(--rule);padding:8px 0;font-family:var(--sans);font-size:12.5px;line-height:1.5;
color:var(--ink-2);}
.pfact b{display:block;font-family:var(--sans);font-size:9.5px;font-weight:700;letter-spacing:.12em;
text-transform:uppercase;color:var(--muted);margin-bottom:3px;}
.pnote{font-family:var(--serif-body);font-size:13.5px;color:var(--ink-2);line-height:1.5;margin-top:12px;
max-width:62ch;}
.pdig{font-family:var(--sans);font-size:11px;color:var(--spoiler);border:1px solid var(--spoiler);
padding:9px 12px;}"""


def render_pressa(cfg, trends, store, status):
    """Раздел «Архив прессы»: реестр-справочник изданий Ульяновской области.

    Данные — pressa.py (ядро реестра, 27 сверенных карточек): годы издания,
    эпоха, периодичность, статус, издатель, территория, место хранения
    оригинала и состояние оцифровки. Полных открытых оцифрованных подшивок
    региона нет, поэтому раздел честно собран как <b>реестр-справочник</b>
    с меткой сверки по краеведческим указателям (М-52…М-55), а не как цифровой
    корпус газет. Карточки читаются без JS; поиск и фильтры — прогрессивные.
    """
    import pressa as P
    now = datetime.now(UTC4)
    prefix = "../"
    nav_html = render_nav(cfg, "projects", prefix, subnav=subnav_projects(prefix, "pressa"))
    pubs = P.PUBLICATIONS

    # ------------------------------------------------------------ метрики KPI
    by_epoch = {}
    by_status = {}
    n_digit = 0
    n_dead = 0
    for x in pubs:
        by_epoch[x.get("epoch", "—")] = by_epoch.get(x.get("epoch", "—"), 0) + 1
        st = x.get("status", "—")
        by_status[st] = by_status.get(st, 0) + 1
        if x.get("digitized") == "да":
            n_digit += 1
        if st == "закрыто" or st == "свёл":
            n_dead += 1
    total = len(pubs)
    kpi = [("<b>{0}</b>".format(total), "изданий в ядре реестра"),
           (str(n_dead), "закрыто и свёрнуто"),
           (str(by_epoch.get("постсовет", 0)), "постсоветская эпоха"),
           (str(n_digit), "есть оцифровка (хотя бы частично)")]
    kpi_html = "".join(f'<div class="kpi"><div class="num">{n}</div><div class="lbl">{l}</div></div>'
                       for n, l in kpi)

    # ------------------------------------------------------------ карточки
    cards = []
    for x in pubs:
        st = x.get("status", "—")
        if st == "действ":
            badge_cls, badge_txt = "live", "действует"
        elif st == "свёл":
            badge_cls, badge_txt = "dead", "свёл"
        else:
            badge_cls, badge_txt = "dead", "закрыто"
        per = x.get("periodicity", "—")
        dig = x.get("digitized", "нет")
        note = x.get("note", "")
        note_html = f'<div class="pnote">{esc(note)}</div>' if note else ""
        facts = [
            ("Издатель", x.get("publisher", "—")),
            ("Территория", x.get("place", "—")),
            ("Хранение оригинала", x.get("storage", "—")),
            ("Оцифровка", dig),
            ("Сверка", x.get("verify", "—")),
        ]
        fact_html = "".join(f'<div class="pfact"><b>{esc(t)}</b>{esc(v)}</div>' for t, v in facts)
        links = x.get("links") or []
        extra_html = (f'<h4>Связанные рубрики</h4>'
                      + "".join(f'<div class="fact"><span>{esc(t)}</span></div>' for t in links)) if links else ""
        hay = esc(" ".join((x.get("title", ""), x.get("years", ""), x.get("place", ""),
                            x.get("publisher", ""))).lower())
        cards.append(f"""<details class="pcard" data-epoch="{esc(x.get('epoch', ''))}"
 data-status="{esc(x.get('status', ''))}" data-hay="{esc(hay)}">
<summary class="pcard-head"><span class="pname">{esc(x.get('title', ''))}</span>
<span class="pyears">{esc(x.get('years', ''))}</span>
<span class="pbadge {badge_cls}">{badge_txt}</span>
<span class="mtoggle">паспорт ↓</span></summary>
<div class="pmeta">{fact_html}</div>
{note_html}
{extra_html}
</details>""")

    # ------------------------------------------------------------ фильтры
    ep_btns = ['<button type="button" class="fbtn active" data-e="all">все</button>']
    for key, txt in P.EPOCHS:
        n = by_epoch.get(key, 0)
        ep_btns.append(f'<button type="button" class="fbtn" data-e="{key}">{esc(txt)} ({n})</button>')
    st_btns = ['<button type="button" class="fbtn active" data-s="all">все</button>']
    for key, txt in P.STATUSES:
        n = by_status.get(key, 0)
        st_btns.append(f'<button type="button" class="fbtn" data-s="{key}">{esc(txt)} ({n})</button>')

    queue_rows = "".join(f'<tr><td><b>{esc(a)}</b></td><td>{b}</td></tr>' for a, b in P.QUEUE)
    pipe_rows = "".join(f'<tr><td><b>{esc(a)}</b></td><td>{b}</td><td>{c}</td></tr>'
                        for a, b, c in P.PIPELINE)

    return f"""<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Архив прессы — реестр изданий · Гудок</title>
<meta name="description" content="Справочник-досье изданий Ульяновской области: годы, периодичность, статус, издатель, территория, место хранения оригинала и оцифровка. Ядро сверено по краеведческим указателям (М-52…М-55).">
<link rel="icon" type="image/png" href="../assets/logo_gudok.png">
<style>{CSS}{PRESS_CSS}</style></head><body>
{nav_html}
<main id="main">
<div class="wrap1200" style="padding-top:20px;">
<div class="sec-head" style="margin-top:0;"><h2>Архив прессы: реестр изданий</h2>
<div class="line"></div><div class="badge">{esc(P.LABEL)}</div></div>
<div class="note" style="margin-bottom:6px;">{P.NOTES[0]}</div>
<div class="note" style="border-left-color:var(--rule);">{P.NOTES[1]}</div>

<div class="kpi-grid" style="margin-top:22px;">{kpi_html}</div>

<div class="panel">
<div class="panel-row"><label class="dsearch"><span class="ic">⌕</span>
<input type="search" id="pq" placeholder="Поиск: название, годы, место, издатель…" aria-label="Поиск по прессе"></label>
</div>
<div class="panel-row"><span class="plbl">Эпоха:</span>
<div class="filters" id="fEpoch" role="group" aria-label="Фильтр по эпохе">{''.join(ep_btns)}</div></div>
<div class="panel-row"><span class="plbl">Статус:</span>
<div class="filters" id="fStatus" role="group" aria-label="Фильтр по статусу">{''.join(st_btns)}</div>
<span class="dcount">показано <b id="cntShown">{total}</b> из {total} · сортировка: по эпохам, в эпохе — по алфавиту</span></div>
</div>
<p class="feed-empty hidden" id="pEmpty">По этому фильтру ничего не найдено —
<button type="button" class="btn" onclick="_pReset()">сбросить</button></p>

<div class="pgrid" id="pGrid">
{''.join(cards)}
</div>

<div class="h3rule" style="margin-top:34px;">Как собирается и сверяется реестр<div class="sub"> ·
{esc(P.LABEL)}</div></div>
<div class="tbl-wrap"><table class="tbl"><thead><tr>
<th style="width:26%">Поле карточки</th><th style="width:22%">Методика сверки</th><th>Как получается</th>
</tr></thead><tbody>{pipe_rows}</tbody></table></div>

<div class="h3rule">Полнота и очередь расширения<div class="sub"> · куда движется раздел</div></div>
<p class="mess">Ядро в этой версии — {total} изданий (сверено по краеведческим указателям и
реестрам РКН). Раздел построен как <b>честный реестр</b>: чего нет в сверенных источниках —
того нет в ядре. Расширение до целевого корпуса ведётся отдельными очередями, каждая с меткой сверки.</p>
<div class="tbl-wrap"><table class="tbl"><thead><tr><th style="width:30%">Блок</th><th>Содержание</th></tr></thead>
<tbody>{queue_rows}</tbody></table></div>

<details class="proto-note">
<summary>Об устройстве и границах раздела</summary>
<p class="mess" style="margin-top:10px;">Полных открытых оцифрованных подшивок газет региона нет
(оригиналы — ГАУО, РНБ, РГБ, областная библиотека; оцифрованы отдельные издания и комплекты).
Поэтому этот раздел — <b>справочник-досье изданий</b>, а не цифровой архив текстов. Полнота
охвата и состояние оцифровки честно помечаются в каждой карточке; раздел продолжает развиваться
по {esc(P.LABEL)}.</p>
</details>

<div class="sec-head" style="margin-top:34px;"><h2>Витрина раздела</h2><div class="line"></div></div>
<div class="legend">Карточки реестра сгруппированы по эпохам — от «Симбирских губернских
ведомостей» (1838) до сетевых изданий. Сверка каждой карточки указана в поле «Сверка».</div>

{footer.render_footer("")}
</div>
</main>
{PRESS_JS}
</body></html>"""


def subnav_projects(prefix="", current=""):
    """Поднавигация рубрики «Проекты»: сквозная для всех проектных страниц."""
    items = [("infospace.html", "Инфопространство", "infospace"),
             ("projects/elections_2026.html", "Выборы-2026", "elections"),
             ("projects/goszakupki.html", "Госзакупки", "goszakupki"),
             ("projects/gorodskoy_sovet.html", "Городской совет", "gorsovet"),
             ("methods.html", "Методы", "methods"),
             ("projects/plans.html", "Планы", "plans"),
             ("projects/dossier.html", "Досье", "dossier"),
             ("projects/pressa.html", "Архив прессы", "pressa")]
    links = "".join(
        f'<span class="cur">{txt}</span>' if key == current
        else f'<a href="{prefix}{href}">{txt}</a>'
        for href, txt, key in items)
    return f'<div class="subnav"><div class="subnav-inner"><span class="lbl">Проекты:</span>{links}</div></div>'


METHODS_CSS = """
.tbl-wrap{overflow-x:auto;}
.h3rule{font-family:var(--sans);font-size:11px;font-weight:700;letter-spacing:.16em;text-transform:uppercase;
color:var(--ink);border-bottom:1px solid var(--ink);padding:0 0 8px;margin:34px 0 14px;}
.h3rule .sub{color:var(--muted);font-weight:500;letter-spacing:.04em;text-transform:none;}

/* ---- страница «Методы»: карточки паспортов, таблицы техконтура, стенд ---- */
.mgrid{display:grid;grid-template-columns:1fr 1fr;gap:0 48px;margin-top:8px;}
.mcard{border-top:1px solid var(--ink);padding:14px 0 18px;break-inside:avoid;}
.mcard[data-ideo="1"]{border-top:3px double var(--ink);}
.mcard-head{display:flex;gap:12px;align-items:baseline;flex-wrap:wrap;cursor:pointer;list-style:none;}
.mcard-head::-webkit-details-marker{display:none;}
.mcard-head:focus-visible{outline:2px solid var(--accent);outline-offset:3px;}
.mcode{font-family:var(--sans);font-size:11px;font-weight:700;letter-spacing:.12em;color:var(--accent);}
.mname{font-family:var(--serif-display);font-weight:600;font-size:19px;line-height:1.2;color:var(--ink);}
.mgrp{display:inline-block;font-family:var(--sans);font-size:10px;font-weight:700;letter-spacing:.08em;
text-transform:uppercase;color:var(--muted);border:1px solid var(--rule);padding:2px 8px;white-space:nowrap;}
.mgrp-ideo{color:var(--accent);border-color:var(--accent);}
.wk-stamp.queued{background:none;color:var(--muted);border-color:var(--rule);}
:root[data-theme="dark"] .wk-stamp.queued{color:var(--muted);border-color:var(--rule);}
.mtoggle{margin-left:auto;font-family:var(--sans);font-size:11px;font-weight:600;color:var(--muted);
border-bottom:1px solid var(--rule);}
.mcard-head:hover .mtoggle{color:var(--accent);border-color:var(--accent);}
.mess{font-family:var(--serif-body);font-size:15px;color:var(--ink-2);margin:9px 0 0;line-height:1.5;max-width:72ch;}
.mdet{display:grid;grid-template-columns:1fr 1fr;gap:0 36px;margin-top:14px;}
.mrow{border-top:1px solid var(--rule);padding:8px 0;font-family:var(--sans);font-size:12.5px;
color:var(--ink-2);line-height:1.5;}
.mrow b{display:block;font-size:10.5px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);
font-weight:700;margin-bottom:3px;}
.mrow code,.tbl code{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:12px;
background:var(--paper-2);border:1px solid var(--rule);padding:1px 6px;color:var(--ink);}
.mrow-wide{grid-column:1/-1;}
.mrow-wide ol{margin:4px 0 0;padding-left:18px;}
.mrow-wide li{margin:3px 0;}
.fbtn.ideo{border-color:var(--accent);color:var(--accent);}
.fbtn.ideo.active{background:var(--accent);border-color:var(--accent);color:#fff;}
.proto-form{display:flex;gap:18px;align-items:flex-end;flex-wrap:wrap;margin:6px 0 4px;}
.proto-form label{font-family:var(--sans);font-size:10.5px;font-weight:700;letter-spacing:.12em;
text-transform:uppercase;color:var(--muted);display:flex;flex-direction:column;gap:6px;}
.proto-form select{font-family:var(--sans);font-size:13px;color:var(--ink);background:var(--paper);
border:1px solid var(--ink);border-radius:0;padding:8px 10px;min-width:270px;}
.proto{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:12.5px;line-height:1.6;
background:var(--paper-2);border:1px solid var(--rule);border-left:3px solid var(--accent);
padding:14px 16px;white-space:pre-wrap;color:var(--ink-2);margin-top:14px;}
@media (max-width:1100px){.mgrid{grid-template-columns:1fr;}}
@media (max-width:720px){.mdet{grid-template-columns:1fr;}.proto-form select{min-width:100%;}}
@media print{
  .filters,.proto-form{display:none!important;}
  .mcard .mdet{display:grid!important;}
}
"""

# Прогрессивный JS страницы «Методы»: фильтры реестра, подпись раскрытия паспорта
# и стенд испытания (протокол формируется из data-атрибутов карточки). Без JS
# видны все карточки и все фильтры просто не работают — как на остальных страницах.
METHODS_JS = """<script>
(function(){
  var grid=document.getElementById('mGrid');
  if(!grid){return;}
  var cards=Array.prototype.slice.call(grid.querySelectorAll('.mcard'));
  var shown=document.getElementById('cntShown');
  var empty=document.getElementById('mEmpty');
  var curG='all',curS='all';
  function apply(){
    var n=0;
    cards.forEach(function(c){
      var okG=(curG==='all')||(curG==='ideo'?c.getAttribute('data-ideo')==='1':c.getAttribute('data-group')===curG);
      var ok=okG&&(curS==='all'||c.getAttribute('data-status')===curS);
      c.style.display=ok?'':'none';
      if(ok){n++;}
    });
    if(shown){shown.textContent=n;}
    if(empty){empty.classList.toggle('hidden',n>0);}
  }
  function bind(sel,attr,set){
    document.querySelectorAll(sel+' .fbtn').forEach(function(b){
      b.addEventListener('click',function(){
        set(b.getAttribute(attr));
        document.querySelectorAll(sel+' .fbtn').forEach(function(x){x.classList.toggle('active',x===b);});
        apply();
      });
    });
  }
  bind('#fGroup','data-g',function(v){curG=v;});
  bind('#fStatus','data-s',function(v){curS=v;});
  window._mReset=function(){
    curG='all';curS='all';
    document.querySelectorAll('#fGroup .fbtn').forEach(function(x){x.classList.toggle('active',x.getAttribute('data-g')==='all');});
    document.querySelectorAll('#fStatus .fbtn').forEach(function(x){x.classList.toggle('active',x.getAttribute('data-s')==='all');});
    apply();
  };
  cards.forEach(function(c){
    c.addEventListener('toggle',function(){
      var t=c.querySelector('.mtoggle');
      if(t){t.textContent=c.open?'паспорт ↑':'паспорт ↓';}
    });
  });

  /* ---------- стенд испытания ---------- */
  var sel=document.getElementById('protoMethod');
  if(sel){
    cards.slice().sort(function(a,b){
      return (+a.getAttribute('data-code').replace(/\\D+/g,''))-(+b.getAttribute('data-code').replace(/\\D+/g,''));
    }).forEach(function(c){
      var o=document.createElement('option');
      o.value=c.id;
      o.textContent=c.getAttribute('data-code')+' · '+c.querySelector('.mname').textContent;
      sel.appendChild(o);
    });
  }
  function wilson(n){
    if(!n||n==='—'){return 'детерминированная/качественная процедура — интервал не применяется';}
    return 'интервал Уилсона 95%: при n='+n+' погрешность ≈ ±'+(1.96*0.5/Math.sqrt(+n)*100).toFixed(1)+' пп';
  }
  function metricsOf(c){
    var out='';
    c.querySelectorAll('.mdet .mrow').forEach(function(r){
      var b=r.querySelector('b');
      if(b&&b.textContent.indexOf('Метрики качества')===0){out=r.textContent.replace(b.textContent,'').trim();}
    });
    return out;
  }
  window._mProto=function(){
    var s=document.getElementById('protoMethod');
    var c=document.getElementById(s.value);
    if(!c){return;}
    var size=document.getElementById('protoSize').value;
    var st=c.getAttribute('data-status');
    var stTxt=st==='work'?'работает':(st==='test'?'тест':'очередь');
    var d=new Date();
    var txt='ПРОТОКОЛ ИСПЫТАНИЯ МЕТОДИКИ\\n'+
      'Код: '+c.getAttribute('data-code')+' · Название: '+c.querySelector('.mname').textContent+'\\n'+
      'Текущий статус: '+stTxt+' · Платформа: «Гудок», контур анализа инфополя\\n'+
      'Выборка: '+size+' единиц (случайная из архива, seed=42); минимум по паспорту: n='+c.getAttribute('data-n')+'\\n'+
      'Разметка: два редактора независимо, расхождения — третий; каппа фиксируется\\n'+
      'Шаги:\\n'+
      ' 1. Выгрузить выборку из базы (SQLite; экспорт CSV по RFC 4180).\\n'+
      ' 2. Разметить вручную по инструкции методики.\\n'+
      ' 3. Прогнать модуль: '+c.getAttribute('data-mod')+'.\\n'+
      ' 4. Посчитать метрики: '+metricsOf(c)+'.\\n'+
      ' 5. Неопределённость: '+wilson(c.getAttribute('data-n'))+'.\\n'+
      ' 6. Критерий приёмки: порог ≥ 0.80 с учётом интервала; повторный прогон без расхождений.\\n'+
      ' 7. Вердикт внести в реестр (methods.html), запись — в методологический журнал (М-28).\\n'+
      'Дата: '+d.toLocaleDateString('ru-RU')+' · Подписи: аналитик ______ редактор ______';
    var out=document.getElementById('protoOut');
    out.textContent=txt;
    out.removeAttribute('hidden');
  };
  window._mCopy=function(){
    var out=document.getElementById('protoOut');
    if(out.hasAttribute('hidden')){window._mProto();}
    var txt=out.textContent;
    var b=document.getElementById('copyBtn');
    function flash(m){var old=b.textContent;b.textContent=m;setTimeout(function(){b.textContent=old;},1400);}
    if(navigator.clipboard&&navigator.clipboard.writeText){
      navigator.clipboard.writeText(txt).then(function(){flash('скопировано ✓');},function(){legacy();});
    }else{legacy();}
    function legacy(){
      var ta=document.createElement('textarea');
      ta.value=txt;document.body.appendChild(ta);ta.select();
      try{document.execCommand('copy');flash('скопировано ✓');}catch(e){flash('не удалось скопировать');}
      document.body.removeChild(ta);
    }
  };
  apply();
})();
</script>"""


def render_methods(cfg, trends, store, status):
    """Страница «Методы»: реестр методик исследования инфополя с паспортами.

    Данные — methods.py (редакционный реестр v1.1): 36 методик, восемь групп,
    сквозной идеологический блок, техконтур из открытых стандартов и стенд
    испытания с генератором протокола. Страница в общем стиле издания: шапка,
    навигация и подвал — из общих компонентов, свой только METHODS_CSS.
    Паспорта раскрываются нативным <details> — работают и без JavaScript.
    """
    import methods as M
    now = datetime.now(UTC4)
    cnt = M.counts()
    nav_html = render_nav(cfg, "projects", "", subnav=subnav_projects("", "methods"))

    # ------------------------------------------------------------- карточки
    cards = []
    for m in M.METHODS:
        st = m.get("status") if m.get("status") in M.STATUS else "queue"
        stamp_cls = ("wk-stamp " + M.STATUS_CSS[st]).strip()
        grp = f'<span class="mgrp">{esc(M.GROUP_SHORT.get(m.get("group"), m.get("group", "")))}</span>'
        if m.get("ideo"):
            grp += '<span class="mgrp mgrp-ideo">идеология</span>'
        rows = []
        for r in m.get("rows", []):
            body = r.get("text", "")          # доверенный редакционный текст с <code>/<a>
            if r.get("steps"):
                body += "<ol>" + "".join(f"<li>{s}</li>" for s in r["steps"]) + "</ol>"
            wide = " mrow-wide" if r.get("steps") else ""
            rows.append(f'<div class="mrow{wide}"><b>{esc(r.get("label", ""))}</b>{body}</div>')
        ideo_attr = ' data-ideo="1"' if m.get("ideo") else ""
        cards.append(f"""<details class="mcard" data-group="{esc(m.get('group', ''))}" data-status="{esc(st)}"
 data-mod="{esc(m.get('mod', ''))}" data-n="{esc(str(m.get('n', '')))}" data-code="{esc(m.get('code', ''))}"{ideo_attr}
 id="{esc(m.get('id', ''))}">
<summary class="mcard-head" role="button" aria-expanded="false"><span class="mcode">{esc(m.get('code', ''))}</span>
<span class="mname">{esc(m.get('name', ''))}</span>{grp}
<span class="{stamp_cls}">{esc(M.STATUS[st])}</span><span class="mtoggle">паспорт ↓</span></summary>
<p class="mess">{esc(m.get('ess', ''))}</p>
<div class="mdet">{''.join(rows)}</div>
</details>""")

    # ------------------------------------------------------------- фильтры
    g_chips = ['<button type="button" class="fbtn active" data-g="all">Все группы</button>']
    for key, title, _short in M.GROUPS:
        n = sum(1 for m in M.METHODS if m.get("group") == key)
        g_chips.append(f'<button type="button" class="fbtn" data-g="{esc(key)}">{esc(title)} ({n})</button>')
    g_chips.append(f'<button type="button" class="fbtn ideo" data-g="ideo">{esc(M.IDEO_TITLE)} ({cnt["ideo"]})</button>')
    s_chips = ['<button type="button" class="fbtn active" data-s="all">Все статусы</button>']
    for key, label in M.STATUS.items():
        s_chips.append(f'<button type="button" class="fbtn" data-s="{key}">{esc(label)} ({cnt.get(key, 0)})</button>')

    # ------------------------------------------------------------- таблицы
    def tbl(t, widths):
        ths = "".join(f'<th{" style=" + chr(34) + "width:" + w + chr(34) if w else ""}>{h}</th>'
                      for h, w in zip(t["heads"], widths + [""] * len(t["heads"])))
        rows = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in t["rows"])
        return (f'<div class="tbl-wrap"><table class="tbl"><thead><tr>{ths}</tr></thead>'
                f'<tbody>{rows}</tbody></table></div>')

    def h3rule(text):
        parts = text.split("·", 1)
        sub = f' <span class="sub">· {esc(parts[1].strip())}</span>' if len(parts) > 1 else ""
        return f'<div class="h3rule">{esc(parts[0].strip())}{sub}</div>'

    ideo_tbl = tbl(M.IDEO_TABLE, ["38%", "22%"])
    std_tbl = tbl(M.TECH_STANDARDS, ["24%", "26%"])
    soft_tbl = tbl(M.TECH_SOFTWARE, ["24%", "22%"])
    mod_tbl = tbl(M.TECH_MODULES, ["20%", "44%"])

    verdict_ideo = next((v for v in M.VERDICTS if v["title"].startswith("Принцип")), M.VERDICTS[0])
    verdict_acc = next((v for v in M.VERDICTS if v["title"].startswith("Критерий")), M.VERDICTS[-1])

    opts = "".join(f'<option value="{esc(m["id"])}">{esc(m["code"])} · {esc(m["name"])}</option>'
                   for m in M.sorted_by_code())

    return f"""<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Методы исследования инфополя · {cfg['brand']}</title>
<meta name="description" content="Реестр методик исследования инфополя издания «Гудок» v{M.VERSION}: {cnt['total']} паспортов методик, сквозной раздел «Идеология и гегемония», оценка неопределённости, стенд испытаний, техконтур из открытых стандартов.">
<link rel="icon" type="image/png" href="assets/logo_gudok.png">
<style>{CSS}{METHODS_CSS}</style></head><body>
<a class="skip" href="#main">К содержанию</a>
<header class="masthead"><div class="mast-inner">
<div class="mast-side">Информационно-аналитическое издание<br>марксистской группы «Победа»</div>
<div class="mast-title">ГУДОК<span>.</span></div>
<div class="mast-side mast-side--right">Проекты издания<br>реестр методик v{M.VERSION} и техконтур
<div class="mast-actions">{THEME_BTN}</div></div>
</div></header>
{nav_html}
<main id="main">
<div class="wrap1200" style="padding-top:20px;">

<div class="sec-head" style="margin-top:0;"><h2>Методы исследования инфополя</h2><div class="line"></div>
<div class="badge">реестр v{M.VERSION} · {cnt['total']} методик</div></div>
<div class="note" style="margin-bottom:6px;">{M.NOTES[0]}</div>
<div class="note" style="border-left-color:var(--rule);">{M.NOTES[1]}</div>

<div class="kpi-grid" style="margin-top:22px;">
<div class="kpi"><div class="num">{cnt['total']}</div><div class="lbl">методик в реестре</div></div>
<div class="kpi"><div class="num">{cnt['work']}</div><div class="lbl">работают на платформе</div></div>
<div class="kpi"><div class="num">{cnt['test']}</div><div class="lbl">в тестировании</div></div>
<div class="kpi"><div class="num">{cnt['queue']}</div><div class="lbl">в очереди</div></div>
<div class="kpi"><div class="num">{cnt['ideo']}</div><div class="lbl">методик идеологического блока</div></div>
<div class="kpi"><div class="num">{cnt['standards']}</div><div class="lbl">открытых стандартов и форматов</div></div>
</div>
</div>

<div class="sec-head" id="reestr"><h2>Реестр методик</h2><div class="line"></div>
<div class="badge">показано <span id="cntShown">{cnt['total']}</span> из {cnt['total']}</div></div>
<div class="wrap1200">
<div class="filters" id="fGroup" role="group" aria-label="Фильтр по группе">{''.join(g_chips)}</div>
<div class="filters" id="fStatus" role="group" aria-label="Фильтр по статусу">{''.join(s_chips)}</div>
<p class="feed-empty hidden" id="mEmpty">По этому фильтру методик нет —
<button type="button" class="btn" onclick="_mReset()">показать все</button></p>
<div class="mgrid" id="mGrid">
{''.join(cards)}
</div>
</div>

<div class="sec-head" id="ideo"><h2>{esc(M.IDEO_TITLE)}</h2><div class="line"></div>
<div class="badge">сквозной раздел · {cnt['ideo']} методик</div></div>
<div class="wrap1200">
<div class="note" style="margin-bottom:14px;">{M.NOTES[2]}</div>
{ideo_tbl}
<div class="verdict"><b>{esc(verdict_ideo['title'])}</b>{esc(verdict_ideo['text'])}</div>
</div>

<div class="sec-head" id="tech"><h2>Техконтур: открытые стандарты и решения</h2><div class="line"></div>
<div class="badge">только открытое</div></div>
<div class="wrap1200">
<div class="note" style="margin-bottom:18px;">{M.NOTES[3]}</div>
{h3rule(M.H3RULES[0])}
{std_tbl}
{h3rule(M.H3RULES[1])}
{soft_tbl}
<div class="note">{M.TECH_NOTE}</div>
{h3rule(M.H3RULES[2])}
{mod_tbl}
</div>

<div class="sec-head" id="stand"><h2>Стенд испытания методик</h2><div class="line"></div>
<div class="badge">протокол за 30 секунд</div></div>
<div class="wrap1200">
<div class="note" style="margin-bottom:14px;">{M.NOTES[4]}</div>
<div class="proto-form">
<label>Методика<select id="protoMethod" aria-label="Выбор методики">{opts}</select></label>
<label>Контрольная выборка<select id="protoSize" aria-label="Объём выборки">
<option>100</option><option selected>200</option><option>400</option></select></label>
<button type="button" class="btn gold" onclick="_mProto()">Сформировать протокол</button>
<button type="button" class="btn" id="copyBtn" onclick="_mCopy()">скопировать</button>
</div>
<pre class="proto" id="protoOut" hidden></pre>
<div class="verdict"><b>{esc(verdict_acc['title'])}</b>{esc(verdict_acc['text'])}</div>
<div class="note">Серверный аналог протокола — <code>methods.py → protocol()</code>: тот же текст
собирается на Python и покрыт тестами, поэтому бумажный протокол и стенд на странице не разъедутся.</div>
</div>

<div class="wrap1200"><div class="note" style="margin-top:26px;">Связано:
<a href="infospace.html" style="color:var(--accent);">дашборд «Инфопространство»</a> ·
<a href="projects/plans.html#method" style="color:var(--accent);">внедрение методов в планах</a> ·
<a href="projects/dossier.html" style="color:var(--accent);">досье действующих лиц (прототип)</a> ·
<a href="projects/elections_2026.html" style="color:var(--accent);">досье «Выборы-2026»</a> ·
<a href="projects/goszakupki.html" style="color:var(--accent);">досье «Госзакупки»</a> ·
<a href="status.html" style="color:var(--accent);">статус системы</a>.
Реестр методик — редакционный документ: правится в <code>methods.py</code>, страница пересобирается
конвейером. Собрано {now:%d.%m.%Y %H:%M} (UTC+4).</div></div>
</main>
{footer.render_footer('')}
{METHODS_JS}
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
    nav_html = render_nav(cfg, "projects", "../", subnav=subnav_projects("../", "goszakupki"))
    week_ago = now - timedelta(days=7)
    live = [it for it in store if not it.get("dup_of") and local_dt(it.get("published"))]
    gz = [it for it in live if GZ_RE.search(f"{it.get('title','')} {(it.get('text') or '')[:300]}")]
    gz_week = [it for it in gz if local_dt(it["published"]) >= week_ago]
    sc = [sentiment_of(f"{it.get('title','')} {(it.get('text') or '')[:250]}")[0] for it in gz_week]
    tone = round(sum(sc) / len(sc), 2) if sc else 0
    src_c = {}
    for it in gz_week:
        k = outlets.outlet(it)   # RSS и TG одной редакции — один источник
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
<div style="flex:1;"><a href="{esc(it.get('url') or '#')}" target="_blank" rel="noopener" style="font-size:13px;font-weight:700;color:var(--navy);">{esc(clip_words(it['title'],110))}</a>
<div style="font-size:11.3px;color:var(--muted);">{esc(it.get('source',''))} · 👁 {fmt_views(it.get('views')) if it.get('views') else '—'}</div></div></div>"""
        for it in sorted(gz_week, key=lambda x: x.get("views") or 0, reverse=True)[:8])
    # выгрузка ЕИС (ручной экспорт в data/goszakupki_eis.csv) — метрики считаются автоматически
    eis = None
    try:
        from analytics import load_eis_csv, compute_eis_metrics
        _eis_rows = load_eis_csv()
        if _eis_rows:
            eis = compute_eis_metrics(_eis_rows)
    except Exception:
        eis = None

    def _mln(x):
        return f"{round((x or 0) / 1e6, 1):,.1f}".replace(",", " ")

    if eis:
        eis_metrics = [
            ("Извещения в выгрузке", "неделя / месяц / всего", f"{eis['week_n']} / {eis['month_n']} / {eis['n_rows']}"),
            ("Суммарная НМЦК · цена заключённых контрактов", "млн ₽", f"{_mln(eis['total_nmck'])} · {_mln(eis['total_price'])}"),
            ("Доля закупки у единственного поставщика", "% (штук · суммы)",
             f"{round((eis['sole_share_n'] or 0) * 100)}% · {round((eis['sole_share_sum'] or 0) * 100)}%"),
            ("Среднее снижение цены на конкурентных процедурах", "%",
             "нет данных" if eis['avg_savings'] is None else f"{round(eis['avg_savings'] * 100, 1)}%"),
            ("Топ заказчиков региона по объёму", "позиций", str(len(eis['top_customers']))),
            ("Концентрация рынка поставщиков", "HHI",
             "нет данных" if eis['supplier_hhi'] is None else str(eis['supplier_hhi'])),
        ]
        chip = '<span class="stchip" style="background:#e0f4ea;color:#1d7a4d;">{}</span>'
    else:
        eis_metrics = [
            ("Число извещений 44-ФЗ заказчиков Ульяновской области", "неделя / месяц", "ожидает подключения"),
            ("Суммарная НМЦК и цена заключённых контрактов", "млн ₽", "ожидает подключения"),
            ("Доля закупки у единственного поставщика", "%", "ожидает подключения"),
            ("Среднее снижение цены на конкурентных процедурах", "%", "ожидает подключения"),
            ("Топ-10 заказчиков региона по объёму", "рейтинг", "ожидает подключения"),
            ("Топ-10 поставщиков и концентрация рынка", "HHI", "ожидает подключения"),
        ]
        chip = '<span class="stchip" style="background:#fdf3dd;color:#96690a;">{}</span>'
    eis_rows = "".join(
        f'<tr><td>{esc(n)}</td><td>{esc(u)}</td><td>{chip.format(esc(str(st)))}</td></tr>'
        for n, u, st in eis_metrics)

    eis_extra = ""
    if eis and (eis["top_customers"] or eis["top_suppliers"]):
        def _tbl(title, rows_):
            tr = "".join(f'<tr><td>{esc(x["name"])}</td><td style="text-align:right;white-space:nowrap;">{_mln(x["sum"])} млн ₽</td></tr>'
                         for x in rows_)
            return (f'<div><div style="font-size:12.5px;font-weight:800;color:var(--navy);margin-bottom:6px;">{title}</div>'
                    f'<table class="tbl">{tr}</table></div>') if tr else ""
        eis_extra = ('<div class="grid2" style="margin-top:12px;">'
                     + _tbl("Топ-10 заказчиков по НМЦК", eis["top_customers"])
                     + _tbl("Топ-10 поставщиков по суммам контрактов", eis["top_suppliers"])
                     + '</div>')
    return f"""<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Проект «Госзакупки» — {cfg['brand']}</title>
<link rel="icon" type="image/png" href="../assets/logo_gudok.png">
<style>{CSS}{INDEX_CSS}</style></head><body>
<header class="masthead"><div class="mast-inner">
<div class="mast-side">Информационно-аналитическое издание<br>марксистской группы «Победа»</div>
<div class="mast-title">ГУДОК<span>.</span></div>
<div class="mast-side mast-side--right">Проект «Госзакупки»<br>неделя: {len(gz_week)} упоминаний
<div class="mast-actions">{THEME_BTN}</div></div>
</div></header>
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
{eis_extra}
<div class="note">Как подключить: выгрузка ЕИС (личный кабинет / открытые данные, из контура РФ) кладётся в <code>data/goszakupki_eis.csv</code>
со столбцами <code>date,customer,method,nmck[,supplier[,price]]</code> (даты YYYY-MM-DD или ДД.ММ.ГГГГ; числа с запятой или точкой) —
метрики и топы на этой странице считаются автоматически при каждом прогоне конвейера. Статус: {"выгрузка загружена — метрики считаются" if eis else "файл не загружен — проект ведёт повесточную часть и готовит разборы вручную"}.</div>
</div></div>
</div>
</div>
</div>
{footer.render_footer('../')}
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
    "city":     ("🤝", "Город и встречи"),
    "other":    ("📌", "Прочее"),
}
AFISHA_ORDER = ["festival", "theatre", "concert", "expo", "kids", "cinema", "sport", "city", "other"]
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
.af-badge{display:inline-block;background:#eef6f1;color:#1f7a43;border-radius:7px;padding:1px 8px;font-weight:800;font-size:10.5px;margin-right:6px;}
:root[data-theme="dark"] .af-badge{background:#14301f;color:#7fd49b;}
.af-badge.alt{background:#f4f0ff;color:#5b3fd4;}
:root[data-theme="dark"] .af-badge.alt{background:#221a42;color:#b3a0ff;}
.af-badge.warn{background:#fff4e2;color:#96690a;border:1px dashed #e0b04e;}
:root[data-theme="dark"] .af-badge.warn{background:#2a2110;color:#e5b14e;}
.af-tag{font-size:10px;color:var(--muted);font-style:italic;margin-left:4px;}
.af-rej{margin-top:18px;background:var(--card);border:1px dashed var(--line);border-radius:12px;padding:12px 16px;}
.af-rej summary{cursor:pointer;font-weight:800;font-size:13px;color:var(--muted);margin-bottom:4px;}
.af-rej summary:hover{color:var(--blue);}
.af-rej-row{display:flex;gap:10px;padding:7px 0;border-bottom:1px dashed var(--line);font-size:12.5px;align-items:baseline;flex-wrap:wrap;}
.af-rej-row:last-child{border-bottom:none;}
.af-rej-date{min-width:118px;font-weight:800;color:var(--navy);}
.af-rej-why{color:var(--muted);font-size:11px;margin-left:auto;}
/* ---- спринт 2: календарь и фильтры ---- */
.af-frow{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:9px;}
.af-frow .fl{font-size:10px;font-weight:800;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);flex:0 0 96px;}
.af-q{flex:1;min-width:220px;border:1px solid var(--line);background:var(--card);color:var(--ink);font-family:var(--sans);font-size:13px;padding:8px 12px;border-radius:9px;}
.af-q:focus{outline:2px solid var(--blue);outline-offset:1px;}
.af-sort{border:1px solid var(--line);background:var(--card);color:var(--ink);font-family:var(--sans);font-size:12.5px;font-weight:700;padding:7px 10px;border-radius:9px;cursor:pointer;}
.af-active{display:flex;gap:7px;flex-wrap:wrap;align-items:center;margin:2px 0 14px;font-size:11.5px;color:var(--muted);}
.af-albl{letter-spacing:.06em;text-transform:uppercase;font-size:10px;font-weight:800;}
.af-achip{border:1px solid var(--line);padding:3px 9px;border-radius:999px;cursor:pointer;color:var(--navy);font-weight:700;transition:border-color .15s,color .15s;}
.af-achip:hover{border-color:var(--blue);color:var(--blue);}
.af-achip.reset{border-color:var(--gold);color:var(--gold);}
.af-day{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:7px 11px;text-align:center;min-width:64px;cursor:pointer;font-family:var(--sans);transition:opacity .15s,border-color .15s;}
.af-day.zero{opacity:.42;}
.af-day.on{background:var(--navy3);border-color:var(--navy3);}
:root[data-theme="dark"] .af-day.on{background:#2f80ed;border-color:#2f80ed;}
.af-day.on b,.af-day.on span,.af-day.on i{color:#fff;}
.af-daylist{position:relative;}
.af-day-head{display:flex;align-items:baseline;gap:12px;border-top:1px solid var(--ink);padding-top:10px;margin:18px 0 2px;}
.af-day-head h3{font-family:var(--serif);font-size:19px;font-weight:700;margin:0;color:var(--navy);}
.af-cnt{margin-left:auto;font-size:10.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);}
.af-hide{display:none!important;}
.af-kick{font-size:10px;font-weight:800;letter-spacing:.14em;text-transform:uppercase;color:var(--blue);margin-bottom:2px;}
.af-link b{font-size:13.8px;color:var(--navy);line-height:1.35;}
.af-link:hover b{color:var(--blue);}
.af-also{font-style:italic;color:var(--muted);font-size:11px;margin-left:4px;}
.af-tag-icn{font-size:12.5px;margin-right:1px;}
.af-foot{display:flex;gap:18px;flex-wrap:wrap;align-items:center;margin-top:16px;padding-top:10px;border-top:1px solid var(--line);font-size:12px;color:var(--muted);}
.af-foot b{color:var(--navy);font-size:16px;margin-right:2px;}
/* ---- спринт 3, п.1: выбор редакции ---- */
.af-pick{background:linear-gradient(135deg,#fdf3dd,#fff8ec);border:1px solid var(--gold);border-radius:14px;padding:14px 18px;margin-bottom:16px;}
:root[data-theme="dark"] .af-pick{background:linear-gradient(135deg,#241d0e,#2a2110);border-color:#5a4a16;}
.af-pick h2{font-family:var(--serif);font-size:16px;margin:0 0 10px;color:var(--navy);display:flex;align-items:center;gap:8px;}
:root[data-theme="dark"] .af-pick h2{color:#e8e2d2;}
.af-pick-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:10px;}
.af-pick-card{border:1px solid var(--line);border-radius:10px;padding:10px 12px;background:var(--card);}
.af-pick-card .af-kick{color:var(--gold);}
.af-pick-card .af-pick-why{font-size:11.5px;color:var(--muted);margin-top:6px;font-style:italic;}
/* ---- спринт 3, п.2: экспорт .ics ---- */
.af-ics-link{display:inline-block;margin-top:8px;font-size:12px;font-weight:800;color:var(--blue);cursor:pointer;border:1px solid var(--line);border-radius:9px;padding:6px 12px;background:var(--card);}
.af-ics-link:hover{background:var(--navy3);color:#fff;border-color:var(--navy3);}
/* ---- спринт 3, п.3: метки отмены и переноса ---- */
.af-badge.cancel{background:#ffe4e4;color:#c0392b;border:1px solid #e6a4a4;}
:root[data-theme="dark"] .af-badge.cancel{background:#3a1414;color:#ff8f7d;}
.af-badge.move{background:#e8f0ff;color:#1d4f9c;border:1px solid #b7cdf5;}
:root[data-theme="dark"] .af-badge.move{background:#14223a;color:#8ab4e8;}
.af-event.canceled{opacity:.5;}
.af-event.canceled .cal-badge,.af-event.canceled .af-link b{text-decoration:line-through;}
.af-event .af-ics-one{float:right;font-size:10.5px;font-weight:800;color:var(--blue);cursor:pointer;border:1px solid var(--line);border-radius:7px;padding:3px 9px;background:var(--card);}
.af-event .af-ics-one:hover{background:var(--navy3);color:#fff;}
.af-event.canceled .af-ics-one{display:none;}
"""

# Прогрессивный JS афиши (Спринт 2): фильтры день/тип/район/цена/возраст,
# пресеты времени, поиск, строка активных фильтров, состояние в hash.
# Без JS видны все события серверной группировкой по дням; JS перефильтровывает
# уже отрисованные карточки (.af-event по data-*) — по образцу FEED_JS.
AFISHA_JS = """<script>
(function(){
  var box=document.getElementById('af-list');
  if(!box)return;
  var cards=Array.prototype.slice.call(box.querySelectorAll('.af-event'));
  if(!cards.length){return;}
  var daybar=document.getElementById('af-daybar');
  var activeBox=document.getElementById('af-active');
  var qInput=document.getElementById('af-q');
  var sortSel=document.getElementById('af-sort');
  var emptyEl=document.getElementById('af-empty');
  var shownEl=document.getElementById('af-shown');
  var daysEl=document.getElementById('af-days');
  var REF_I=(daybar?daybar.getAttribute('data-ref'):'')||cards[0].getAttribute('data-d');
  var TOM_I=new Date(new Date(REF_I+'T12:00:00').getTime()+86400000).toISOString().slice(0,10);
  var AF_WD=['вс','пн','вт','ср','чт','пт','сб'];
  var AF_WD_F=['воскресенье','понедельник','вторник','среда','четверг','пятница','суббота'];
  var AF_MON=['января','февраля','марта','апреля','мая','июня','июля','августа','сентября','октября','ноября','декабря'];
  var TYPE_NAMES={},TYPE_KEY={};var TYP_I=0;
  document.querySelectorAll('#af-filters .af-chip[data-f="type"]').forEach(function(ch){
    var v=ch.getAttribute('data-v');
    TYPE_NAMES[v]=ch.textContent.trim();TYPE_KEY[v]=(v==='all'?99:TYP_I++);
  });
  var geos={ulsk:'Ульяновск',dim:'Димитровград',region:'районы области'};
  var dates={all:'Все дни',today:'Сегодня',tomorrow:'Завтра',weekend:'Выходные',week:'7 дней',evening:'вечером (после 17:00)'};
  var ST={date:'all',day:'',type:'all',geo:'all',price:'all',age:'all',sort:'time',q:''};

  function daysFrom(d){return Math.round((new Date(d+'T12:00:00')-new Date(REF_I+'T12:00:00'))/86400000);}
  function isWe(d){var x=new Date(d+'T12:00:00');return x.getDay()===0||x.getDay()===6;}
  function toMin(c){var t=c.getAttribute('data-tm');return t?+t:1440;}
  function dayText(d){var p=d.split('-');var x=new Date(d+'T12:00:00');return (+p[2])+' '+AF_MON[+p[1]-1]+' · '+AF_WD_F[x.getDay()];}

  // --- Спринт 3, п.2: экспорт .ics (выборка целиком / одно событие) ---
  function dtIso(d,min){
    var p=d.split('-');
    var x=new Date(Date.UTC(+p[0],+p[1]-1,+p[2]));
    var m=min!=null?min:720;
    var hh=Math.floor(m/60),mm=m%60;
    var s=function(n){return ('0'+n).slice(-2);};
    return x.toISOString().slice(0,10).replace(/-/g,'')+'T'+s(hh)+s(mm)+'00';
  }
  function icsText(pairs){
    var lines=['BEGIN:VCALENDAR','VERSION:2.0','PRODID:-//Gudok//Afisha//RU',
      'CALSCALE:GREGORIAN','METHOD:PUBLISH'];
    pairs.forEach(function(p){
      var t=p.title.replace(/[\\;,]/g,function(ch){return '\\'+ch;}).replace(/\r?\n/g,'\\n');
      lines.push('BEGIN:VEVENT','DTSTART:'+p.start,'DTEND:'+p.end,
        'SUMMARY:'+t,
        p.place?('LOCATION:'+p.place.replace(/[\\;,]/g,function(ch){return '\\'+ch;}).replace(/\r?\n/g,'\\n')):null,
        p.url?('URL;VALUE=URI:'+p.url):null,
        'END:VEVENT');
    }.bind(this)).forEach(function(l){if(l)lines.push(l);});
    lines.push('END:VCALENDAR');
    return lines.join('\r\n');
  }
  function cardMeta(c){
    var d=c.getAttribute('data-d');
    var min=toMin(c);
    var end=min===1440?1439:min+60;
    return {
      title:(c.querySelector('.af-link b')||{}).textContent||'Событие',
      place:((c.querySelector('.af-meta')||{}).textContent||'').trim().slice(0,80),
      url:(c.querySelector('.af-link')||{}).getAttribute?c.querySelector('.af-link').getAttribute('href'):'',
      start:dtIso(d,min===1440?720:min),
      end:dtIso(d,end)
    };
  }
  function icsFile(pairs,label){
    var blob=new Blob([icsText(pairs)],{type:'text/calendar;charset=utf-8'});
    var a=document.createElement('a');
    a.href=URL.createObjectURL(blob);
    a.download=(label||'afisha')+'.ics';
    document.body.appendChild(a);a.click();a.remove();
    setTimeout(function(){URL.revokeObjectURL(a.href);},4000);
  }
  window._afIcs=function(btn){
    var card=btn&&btn.closest?btn.closest('.af-event,.af-pick-card'):null;
    if(!card)return;
    if(card.classList.contains('canceled'))return;
    var m=cardMeta(card);
    icsFile([m],'afisha-'+(card.getAttribute('data-d')||'afisha-event'));
  };
  window._afIcsAll=function(){
    var vis=cards.filter(function(c){return !c.classList.contains('canceled')&&!c.classList.contains('af-hide');});
    if(!vis.length)return;
    var pairs=vis.map(cardMeta);
    icsFile(pairs,'Афиша Гудка, '+vis.length+' событий');
  };
  window._afIcsOne=function(btn){
    var card=btn.closest?btn.closest('.af-event'):null;
    if(!card||card.classList.contains('canceled'))return;
    icsFile([cardMeta(card)],'afisha-'+card.getAttribute('data-d')||'afisha-event');
  };

  function pass(c){
    var d=c.getAttribute('data-d');
    if(ST.day){if(d!==ST.day)return false;}
    else if(ST.date==='today'){if(d!==REF_I)return false;}
    else if(ST.date==='tomorrow'){if(d!==TOM_I)return false;}
    else if(ST.date==='weekend'){if(!isWe(d)||daysFrom(d)>6)return false;}
    else if(ST.date==='week'){var w=daysFrom(d);if(w<0||w>7)return false;}
    else if(ST.date==='evening'){if(toMin(c)<17*60||daysFrom(d)<0||daysFrom(d)>7)return false;}
    if(ST.type!=='all'&&c.getAttribute('data-type')!==ST.type)return false;
    if(ST.geo!=='all'&&c.getAttribute('data-geo')!==ST.geo)return false;
    if(ST.price==='free'&&c.getAttribute('data-price')!=='free')return false;
    if(ST.age==='kids'){var a=c.getAttribute('data-age');if(a==='16+'||a==='18+'||a==='21+')return false;}
    if(ST.q&&(c.getAttribute('data-q')||'').indexOf(ST.q)===-1)return false;
    return true;
  }

  function paint(){
    var vis=[];
    cards.forEach(function(c){
      if(c.classList.contains('canceled'))return;
      if(pass(c)){vis.push(c);}
    });
    if(ST.sort==='type'){
      vis.sort(function(a,b){
        var ta=a.getAttribute('data-type'),tb=b.getAttribute('data-type');
        if(ta===tb){var da=a.getAttribute('data-d'),db=b.getAttribute('data-d');
          return da===db?toMin(a)-toMin(b):(da<db?-1:1);}
        return ((TYPE_KEY[ta]===undefined)?99:TYPE_KEY[ta])-((TYPE_KEY[tb]===undefined)?99:TYPE_KEY[tb]);
      });
    }else if(ST.sort==='score'){
      vis.sort(function(a,b){return (+b.getAttribute('data-sc'))-(+a.getAttribute('data-sc'));});
    }else{
      vis.sort(function(a,b){
        var da=a.getAttribute('data-d'),db=b.getAttribute('data-d');
        return da===db?toMin(a)-toMin(b):(da<db?-1:1);
      });
    }
    cards.forEach(function(c){c.classList.add('af-hide');});
    vis.forEach(function(c){c.classList.remove('af-hide');});
    var frag=document.createDocumentFragment();
    if(ST.sort==='score'){
      var lone=document.createElement('div');lone.className='af-list';
      vis.forEach(function(c){lone.appendChild(c);});
      frag.appendChild(lone);
    }else{
      var byDay={};
      vis.forEach(function(c){var d=c.getAttribute('data-d');(byDay[d]=byDay[d]||[]).push(c);});
      Object.keys(byDay).sort().forEach(function(d){
        var head=document.createElement('div');head.className='af-day-head';
        head.innerHTML='<h3>'+dayText(d)+'</h3><span class="af-cnt">'+byDay[d].length+' соб. · '+(isWe(d)?'выходные':'будни')+'</span>';
        frag.appendChild(head);
        var l=document.createElement('div');l.className='af-list';
        byDay[d].forEach(function(c){l.appendChild(c);});
        frag.appendChild(l);
      });
    }
    box.innerHTML='';
    box.appendChild(frag);
    if(emptyEl){emptyEl.hidden=vis.length>0;}
    if(shownEl){shownEl.textContent=vis.length;}
    var dcount=ST.sort==='score'?1:0;
    if(ST.sort!=='score'){
      var seen={};vis.forEach(function(c){seen[c.getAttribute('data-d')]=1;});
      dcount=Object.keys(seen).length;
    }
    if(daysEl){daysEl.textContent=dcount;}
    paintChips();paintActive();paintDaybar();syncHash();
  }

  function chipVal(f){return f==='price'?'free':(f==='age'?'kids':'all');}
  function paintChips(){
    document.querySelectorAll('#af-filters .af-chip[data-f]').forEach(function(ch){
      var f=ch.getAttribute('data-f'),v=ch.getAttribute('data-v');
      var on=false;
      if(f==='date'){on=!ST.day&&ST.date===v;}
      else if(f==='type'){on=ST.type===v;}
      else if(f==='geo'){on=ST.geo===v;}
      else if(f==='price'){on=ST.price==='free';}
      else if(f==='age'){on=ST.age==='kids';}
      ch.classList.toggle('on',on);
      ch.setAttribute('aria-pressed',on?'true':'false');
    });
  }

  function paintDaybar(){
    if(!daybar)return;
    daybar.querySelectorAll('.af-day[data-date]').forEach(function(b){
      var on=b.getAttribute('data-date')===ST.day;
      b.classList.toggle('on',on);
      b.setAttribute('aria-pressed',on?'true':'false');
    });
  }

  function paintActive(){
    if(!activeBox)return;
    var out=[];
    if(ST.day){out.push(['день: '+dayText(ST.day),function(){ST.day='';ST.date='all';paint();}]);}
    else if(ST.date!=='all'){out.push(['когда: '+dates[ST.date],function(){ST.date='all';paint();}]);}
    if(ST.type!=='all'){out.push(['тип: '+TYPE_NAMES[ST.type],function(){ST.type='all';paint();}]);}
    if(ST.geo!=='all'){out.push(['где: '+geos[ST.geo],function(){ST.geo='all';paint();}]);}
    if(ST.price==='free'){out.push(['только бесплатные',function(){ST.price='all';paint();}]);}
    if(ST.age==='kids'){out.push(['можно с детьми',function(){ST.age='all';paint();}]);}
    if(ST.q){out.push(['поиск: «'+ST.q+'»',function(){ST.q='';if(qInput){qInput.value='';}paint();}]);}
    var html='<span class="af-albl">'+((out.length)?'Активные фильтры:':'Фильтры не заданы · показаны все события')+'</span>';
    activeBox.innerHTML=html;
    out.forEach(function(pair){
      var s=document.createElement('span');s.className='af-achip';
      s.textContent=pair[0]+' ✕';
      s.addEventListener('click',pair[1]);
      activeBox.appendChild(s);
    });
    if(out.length>1){
      var r=document.createElement('span');r.className='af-achip reset';
      r.textContent='Сбросить всё ✕';
      r.addEventListener('click',resetAll);
      activeBox.appendChild(r);
    }
  }

  function resetAll(){
    ST={date:'all',day:'',type:'all',geo:'all',price:'all',age:'all',sort:(sortSel?sortSel.value:'time'),q:''};
    if(qInput){qInput.value='';}
    paint();
  }
  window._afReset=resetAll;

  function syncHash(){
    var p={date:ST.date==='all'?'':ST.date,day:ST.day,type:ST.type==='all'?'':ST.type,
      geo:ST.geo==='all'?'':ST.geo,price:ST.price==='free'?'1':'',age:ST.age==='kids'?'1':'',
      sort:ST.sort,q:ST.q};
    var h='#af='+encodeURIComponent(JSON.stringify(p));
    try{history.replaceState(null,'',h);}catch(e){}
  }
  function readHash(){
    var s=location.hash;
    var idx=s.indexOf('#af=');
    if(idx<0)return;
    try{var p=JSON.parse(decodeURIComponent(s.slice(idx+4)));}catch(e){return;}
    if(!p||typeof p!=='object')return;
    ST.date=(p.date||'all');ST.day=(p.day||'');ST.type=(p.type||'all');ST.geo=(p.geo||'all');
    ST.price=p.price==='1'?'free':'all';ST.age=p.age==='1'?'kids':'all';
    ST.sort=(p.sort||'time');ST.q=(p.q||'');
    if(qInput){qInput.value=ST.q;}
    if(sortSel){sortSel.value=ST.sort;}
  }

  document.querySelectorAll('#af-filters .af-chip[data-f]').forEach(function(ch){
    ch.addEventListener('click',function(){
      var f=ch.getAttribute('data-f'),v=ch.getAttribute('data-v');
      if(f==='date'){ST.date=(ST.date===v?'all':v);ST.day='';}
      else if(f==='type'){ST.type=(ST.type===v?'all':v);}
      else if(f==='geo'){ST.geo=(ST.geo===v?'all':v);}
      else if(f==='price'){ST.price=(ST.price==='free'?'all':'free');}
      else if(f==='age'){ST.age=(ST.age==='kids'?'all':'kids');}
      paint();
    });
  });
  if(qInput){
    qInput.addEventListener('input',function(ev){ST.q=(ev.target.value||'').trim().toLowerCase();paint();});
  }
  if(sortSel){
    sortSel.addEventListener('change',function(){ST.sort=sortSel.value||'time';paint();});
  }
  if(daybar){
    daybar.querySelectorAll('.af-day[data-date]').forEach(function(b){
      b.addEventListener('click',function(){
        var d=b.getAttribute('data-date');
        ST.day=(ST.day===d?'':d);ST.date='all';
        paint();
      });
    });
  }
  window.addEventListener('hashchange',function(){readHash();paint();});
  readHash();paint();
})();
</script>"""

# прогрессивный JS ленты: чипы-рубрики (#19) + «Показать ещё 12» (#20).
# Без JS видны все карточки; JS добором прячет хвост ленты и фильтрует.
FEED_JS = """<script>
(function(){
  var grid=document.getElementById('feed-grid');
  if(!grid)return;
  var cards=Array.prototype.slice.call(grid.querySelectorAll('.feed-card'));
  var total=cards.length,limit=12,step=12;
  var btn=document.getElementById('feed-more');
  var cnt=document.getElementById('feed-count');
  var empty=document.getElementById('feed-empty');
  function state(){
    var s=location.hash.match(/^#feed=([^:]*)(?::([^:]*))?/);
    return {cat:s?decodeURIComponent(s[1])||'*':'*',type:s?decodeURIComponent(s[2])||'*':'*'};
  }
  function match(c,st){
    return (st.cat==='*'||c.getAttribute('data-cat')===st.cat)
        && (st.type==='*'||c.getAttribute('data-type')===st.type);
  }
  function paint(){
    var st=state(),shown=0,hasMore=false;
    cards.forEach(function(c){
      if(match(c,st)){
        if(shown<limit){c.classList.remove('hidden');shown++;}
        else{c.classList.add('hidden');hasMore=true;}
      }else{c.classList.add('hidden');}
    });
    if(cnt)cnt.textContent='Показано '+shown+' из '+total+' материалов суток';
    if(btn)btn.style.display=hasMore?'grid':'none';
    if(empty)empty.hidden=!((st.cat!=='*'||st.type!=='*')&&shown===0);
    document.querySelectorAll('#feed-chips .chip-f').forEach(function(ch){
      var g=ch.getAttribute('data-group'),v=ch.getAttribute('data-val');
      var want=g==='cat'?st.cat:st.type;
      var on=v===want;
      ch.classList.toggle('on',on);
      ch.setAttribute('aria-pressed',on?'true':'false');
    });
  }
  if(btn)btn.addEventListener('click',function(){limit+=step;paint();});
  window.addEventListener('hashchange',function(){limit=12;paint();});
  document.querySelectorAll('#feed-chips .chip-f').forEach(function(ch){
    ch.addEventListener('click',function(){
      var g=ch.getAttribute('data-group'),v=ch.getAttribute('data-val');
      var st=state();
      if(g==='cat'){st.cat=v;}else{st.type=v;}
      location.hash='feed='+encodeURIComponent(st.cat)+':'+encodeURIComponent(st.type);
    });
  });
  paint();
  // #24: A/B — переключатель «версии B главной» (запоминается локально)
  var ab=document.querySelector('.ab-link');
  if(ab){
    var abv=localStorage.getItem('gudok-ab-v2')==='1';
    function abApply(){document.body.setAttribute('data-ab',abv?'v2':'v1');ab.setAttribute('aria-pressed',abv?'true':'false');}
    ab.addEventListener('click',function(){abv=!abv;localStorage.setItem('gudok-ab-v2',abv?'1':'0');abApply();});
    abApply();
  }
})();
</script>"""


def render_afisha(cfg, trends, store, status, an):
    from analytics import announced_dates
    now = datetime.now(UTC4)
    nav_html = render_nav(cfg, "afisha", "")
    today = now.date()
    cal = (an or {}).get("calendar", [])
    rej = (an or {}).get("calendar_rejected", [])
    passport = (an or {}).get("calendar_passport", {})

    def edate(e):
        try:
            return datetime.strptime(e["date"], "%Y-%m-%d").date()
        except (ValueError, TypeError, KeyError):
            return None

    cal = [e for e in cal if edate(e) and edate(e) >= today]
    cal = sorted(cal, key=lambda x: (x["date"], x.get("time") or "99:99"))
    rej = [e for e in rej if edate(e) and edate(e) >= today]

    # ближайшие выходные (сб+вс)
    sat = today + timedelta(days=(5 - today.weekday()) % 7)
    weekend = {sat, sat + timedelta(days=1)}
    if today.weekday() == 6:
        weekend = {today}

    wd = {0: "пн", 1: "вт", 2: "ср", 3: "чт", 4: "пт", 5: "сб", 6: "вс"}

    def geo_bucket(e):
        t = " ".join(filter(None, [e.get("venue_city", ""), e.get("venue_district", ""), e.get("geo", "")]))
        tl = t.lower()
        if "димитровград" in tl:
            return "dim"
        if "ульяновск" in tl or any(r in tl for r in ("засвияжск", "заволжск", "железнодорожн", "ленинск")):
            return "ulsk"
        return "region"

    # панель дней — 14 дней, кнопки с числом событий и подсказкой у пустых
    def _pl(n):
        if n % 10 == 1 and n % 100 != 11:
            return "событие"
        if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
            return "события"
        return "событий"

    daybar = []
    for i in range(14):
        dd = today + timedelta(days=i)
        n = sum(1 for e in cal if edate(e) == dd)
        we = ' we' if dd in weekend else ''
        zero = ' zero' if n == 0 else ''
        nxt = ""
        if n == 0:
            for j in range(i + 1, 16):
                if any(edate(e) == today + timedelta(days=j) for e in cal):
                    nxt = f"{(today + timedelta(days=j)):%d.%m}"
                    break
        def _pl(n):
            n = int(n or 0)
            if n % 10 == 1 and n % 100 != 11:
                return "событие"
            if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
                return "события"
            return "событий"

        tip = (f"Событий нет · ближайшее {nxt}" if n == 0 and nxt else (f"{n} {_pl(n)}" if n else "Событий нет"))
        cnt = f"{n} соб." if n else "нет соб."
        daybar.append(f'<button type="button" class="af-day{we}{zero}" data-date="{dd.isoformat()}" aria-pressed="false" title="{esc(tip)}"><b>{dd:%d}</b><span>{wd[dd.weekday()]} {dd:%m}</span><i>{cnt}</i></button>')

    # паспорт порога входа
    found_n = passport.get("found_dates")
    passed_n = passport.get("accepted")
    shown_n = len(cal)
    if found_n is None:
        pipeline_note = f"Событий в выборке: <b>{shown_n}</b>."
    else:
        st = passport.get("stats") or {}
        thr = passport.get("threshold") or 0
        extra = []
        if st.get("title_composed"):
            extra.append(f"названий собрано из типа события и имени — <b>{st['title_composed']}</b>")
        if st.get("venue_text"):
            extra.append(f"площадок найдено в тексте без маркера 📍 — <b>{st['venue_text']}</b>")
        if st.get("venue_city"):
            extra.append(f"городских событий без одной площадки — <b>{st['venue_city']}</b>")
        if st.get("with_price"):
            extra.append(f"с известной ценой входа — <b>{st['with_price']}</b>")
        pipeline_note = ("Порог входа: найдено дат <b>{found}</b> → прошло проверку <b>{passed}</b> → "
                         "показано сегодня <b>{shown}</b>. Порог уверенности — <b>{thr}</b>"
                         "{extra}. Сверяйте время и билеты у организаторов — "
                         "данные извлечены из публикаций автоматически.").format(
                             found=found_n, passed=passed_n, shown=shown_n, thr=thr,
                             extra=("; " + "; ".join(extra)) if extra else "")

    def time_html(e):
        t = e.get("time") or ""
        note = e.get("time_note") or ""
        if t:
            return f'<span class="af-time">{esc(t)}</span>'
        if note == "весь день":
            return '<span class="af-badge alt">весь день</span>'
        return '<span class="af-badge warn">время уточняется</span>'

    def venue_html(e):
        v = e.get("venue") or ""
        addr = e.get("venue_addr") or ""
        geo = e.get("geo") or ""
        how = e.get("venue_how") or ""
        parts = []
        if v:
            parts.append("📍 " + esc(v))
            if addr and addr.lower() not in v.lower():
                parts.append(esc(addr))
            if how in ("address", "city"):
                # площадка восстановлена по адресу или событие городское: не выдаём догадку за факт
                parts.append('<span class="af-badge warn">площадка уточняется</span>')
        elif geo:
            parts.append(esc(geo))
        return "".join(f'<span class="af-meta" style="display:inline;"> · {p}</span>' for p in parts) if parts else ""

    # карточка события с data-атрибутами для клиентских фильтров
    def badges_html(e):
        out = []
        if e.get("canceled"):
            out.append('<span class="af-badge cancel">отменено · проверено {}</span>'.format(
                esc(e.get("check_date") or "17.09")))
        if e.get("moved_from"):
            out.append('<span class="af-badge move">перенесено с {}</span>'.format(
                esc(e["moved_from"][8:10] + "." + e["moved_from"][5:7])))
        elif e.get("moved_unknown"):
            out.append('<span class="af-badge move">перенесено, новая дата неизвестна</span>')
        if e.get("price"):
            out.append(f'<span class="af-badge">{esc(e["price"])}</span>')
        if e.get("age"):
            out.append(f'<span class="af-badge alt">{esc(e["age"])}</span>')
        if e.get("title_is_fallback"):
            out.append('<span class="af-badge warn">название уточняется</span>')
        return "".join(out)

    def card_html(e):
        d = edate(e)
        if d is None:
            return ""
        gold = ' gold' if d in weekend else ''
        span = ''
        end = e.get("date_end")
        if end:
            span = f' — {end[8:10]}.{end[5:7]}'
        tm = ""
        t = e.get("time") or ""
        if t and ":" in t:
            hh, mm = t.split(":", 1)
            try:
                tm = str((int(hh) * 60 + int(mm[:2]) + 1440) % 1440)
            except ValueError:
                tm = ""
        etype = e.get("etype") or "other"
        icon, name = ETYPE_META.get(etype, ETYPE_META["other"])
        also_n = int(e.get("also_n") or 0)
        kick = f"{icon} {name}"
        if also_n:
            kick += f'<span class="af-also">· также анонсировали: {also_n} изд.</span>'
        hay = " ".join([
            e.get("event_title") or "", e.get("title") or "",
            e.get("venue") or "", e.get("venue_addr") or "",
            e.get("venue_district") or "", e.get("venue_city") or "",
            e.get("geo") or "", name, e.get("source") or ""]).lower()
        title = esc(clip_words(e.get("event_title") or e.get("title") or "без названия", 140))
        url = esc(e.get("url") or "#")
        state_cls = ""
        if e.get("canceled"):
            state_cls = " canceled"
        elif e.get("moved_from") or e.get("moved_unknown"):
            state_cls = " moved"
        ics_btn = '<button type="button" class="af-ics-one" onclick="_afIcsOne(this)">в календарь</button>'
        if e.get("canceled"):
            ics_btn = ""
        return f"""<div class="af-event{state_cls}" data-d="{e['date']}" data-tm="{tm}" data-type="{etype}"
 data-geo="{geo_bucket(e)}" data-price="{esc(e.get('price_mode') or '')}" data-age="{esc(e.get('age') or '')}"
 data-sc="{e.get('score') or 0}" data-q="{esc(hay.replace('"', ' '))}">
{ics_btn}
<div class="cal-badge{gold}"><b>{d:%d}</b><span>{wd[d.weekday()]} {d:%m}</span></div>
<div class="af-body"><div class="af-kick">{kick}</div>
<a class="af-link" href="{url}" target="_blank" rel="noopener"><b>{title}</b></a>{span}
<div class="af-meta">{time_html(e)}<span>{esc(e.get('source', ''))}</span>{venue_html(e)} {badges_html(e)}</div></div></div>"""

    # группировка по дням (серверная, видна без JS)
    days_map = {}
    for e in cal:
        days_map.setdefault(e["date"], []).append(e)
    day_lists = []
    for d in sorted(days_map):
        evs = days_map[d]
        evs.sort(key=lambda e: (e.get("time") or "99:99"))
        dd = edate(evs[0])
        label = f"{dd:%d} {MONTHS_RU[dd.month - 1]} · {DAYS_RU[dd.weekday()]}"
        kind = "выходные" if dd in weekend else "будни"
        rows = "".join(card_html(e) for e in evs)
        day_lists.append(f'<div class="af-daylist"><div class="af-day-head"><h3>{label}</h3><span class="af-cnt">{len(evs)} соб. · {kind}</span></div><div class="af-list">{rows}</div></div>')
    main_list = "".join(day_lists)
    n_culture = sum(1 for e in cal if e.get("etype") not in ("sport", "other"))
    af_gate = (cfg.get("settings", {}) or {}).get("afisha", {}) or {}
    af_horizon = af_gate.get("horizon_days", 45)
    af_thr = passport.get("threshold") or af_gate.get("threshold") or 0

    # панель фильтров
    def chip(f, v, label, on=False):
        cls = "af-chip on" if on else "af-chip"
        return f'<button type="button" class="{cls}" data-f="{f}" data-v="{v}" aria-pressed="false">{label}</button>'

    weekday_label = f'Выходные {sat:%d.%m}–{sat + timedelta(days=1):%d.%m}' if len(weekend) > 1 else "Выходные"
    filters_html = ('<div id="af-filters">'
                    '<div class="af-frow"><span class="fl">Когда</span>'
                    + chip("date", "all", "Все дни", True)
                    + chip("date", "today", "Сегодня")
                    + chip("date", "tomorrow", "Завтра")
                    + chip("date", "weekend", weekday_label)
                    + chip("date", "week", "7 дней")
                    + chip("date", "evening", "Вечером (после 17:00)")
                    + '</div>'
                    '<div class="af-frow"><span class="fl">Тип</span>'
                    + chip("type", "all", "Все типы", True)
                    + "".join(chip("type", et, ETYPE_META[et][1]) for et in AFISHA_ORDER)
                    + '</div>'
                    '<div class="af-frow"><span class="fl">Где и почём</span>'
                    + chip("geo", "ulsk", "Ульяновск")
                    + chip("geo", "dim", "Димитровград")
                    + chip("geo", "region", "Районы области")
                    + chip("price", "free", "Только бесплатные")
                    + chip("age", "kids", "Можно с детьми")
                    + '<select class="af-sort" id="af-sort" aria-label="Сортировка">'
                    '<option value="time">Сортировка: по времени</option>'
                    '<option value="type">По типу события</option>'
                    '<option value="score">По релевантности</option></select>'
                    '</div>'
                    '<div class="af-frow"><span class="fl">Поиск</span>'
                    '<input class="af-q" id="af-q" type="search" placeholder="Название, площадка, район — например «филармония»">'
                    '</div></div>')

    # анонсы культурных каналов с пометкой распознанной / нераспознанной даты
    tg_items = [it for it in store if it.get("source_type") == "tg"]
    chan_html = []
    for chn in AFISHA_CHANNELS:
        ch_cfg = next((c for c in cfg.get("telegram_channels", []) if c["username"] == chn), None)
        posts = sorted([it for it in tg_items if it.get("channel") == chn],
                       key=lambda x: x.get("published") or "", reverse=True)[:3]
        post_rows = []
        for it in posts:
            blob = (str(it.get("title") or "") + " " + str(it.get("text") or ""))[:400]
            ann = announced_dates(blob, now=now)
            if ann:
                d0 = ann[0]
                badge = f'<span class="af-badge">{d0[8:10]}.{d0[5:7]}</span>'
            else:
                badge = '<span class="af-badge warn">дата не распознана</span>'
            post_rows.append(f"""<div class="tgpost"><div><div class="t">{badge} <a href="{esc(it.get('url') or '#')}" target="_blank" rel="noopener">{esc(clip_words(it.get('title') or 'без заголовка', 120))}</a></div>
<div class="m">{(local_dt(it.get('published')) or now).strftime('%d.%m %H:%M')}{' · 👁 ' + fmt_views(it['views']) if it.get('views') else ''}</div></div></div>""")
        rows = "".join(post_rows) or '<div class="tgpost"><div class="t" style="color:var(--muted);">нет свежих постов</div></div>'
        chan_html.append(f"""<div class="card" style="margin-bottom:12px;"><div class="side-head">🎟
<a href="https://t.me/{esc(chn)}" target="_blank" rel="noopener" style="color:#fff;">@{esc(chn)}</a>
<span class="sub">{esc((ch_cfg or {}).get('title',''))}</span></div><div class="side-body">{rows}</div></div>""")

    # площадки-кандидаты: названы в текстах, но не опознаны справочником
    cand = (passport.get("venues_new") or {})
    cand_html = ""
    if cand:
        rows_c = "".join(f'<div class="af-rej-row"><span>{esc(k[:70])}</span>'
                         f'<span class="af-rej-why">встречается {v} раз(а)</span></div>'
                         for k, v in list(cand.items())[:12])
        cand_html = f"""<details class="af-rej"><summary>Площадки-кандидаты ({len(cand)}) — названы в текстах, но не опознаны</summary>
{rows_c}
<div class="note">Это названия и адреса, которые встретились в анонсах, но не совпали со справочником
<code>data/venues.json</code>. Список — редактору на пополнение: запись с адресом и районом даёт событию
площадку, а событию без площадки порог входа не пройти.</div>
</details>"""

    # блок «не прошло порог»
    rej_html = ""
    if rej:
        rows_rej = []
        for r in sorted(rej, key=lambda e: (e["date"], e.get("event_title") or ""))[:80]:
            why = " · ".join(r.get("reasons") or [])
            rej_title = r.get("event_title") or ""
            if r.get("title_is_fallback") and r.get("title"):
                rej_title = r["title"]      # «событие» без названия заменяем заголовком источника
            rows_rej.append(f"""<div class="af-rej-row"><span class="af-rej-date">{r['date'][8:10]}.{r['date'][5:7]} {time_html(r)}</span>
<span>{esc((rej_title or '—')[:90])}</span>
<span class="af-rej-why">{esc(why)}</span></div>""")
        rej_html = f"""<details class="af-rej"><summary>Не прошло порог ({len(rej)}) — почему отсеяно</summary>
{''.join(rows_rej)}
</details>"""

    today_n = sum(1 for e in cal if edate(e) == today)
    we_n = sum(1 for e in cal if edate(e) in weekend)
    total_n = len(cal)
    days_n = len(days_map)

    if main_list:
        list_html = f'<div id="af-list">{main_list}</div>'
    else:
        list_html = '<div id="af-list"><div class="af-empty">Событий не найдено — запустите сбор конвейером.</div></div>'

    # «Выбор редакции»: до PICK_MAX событий ближайшей недели (Спринт 3, п.1)
    from analytics import editor_pick, pick_reason
    pick_evs = editor_pick(cal, now)
    pick_html = ""
    if pick_evs:
        pick_cards = []
        for e in pick_evs:
            d = edate(e)
            etype = e.get("etype") or "other"
            icon, name = ETYPE_META.get(etype, ETYPE_META["other"])
            title = esc(clip_words(e.get("event_title") or e.get("title") or "без названия", 90))
            url = esc(e.get("url") or "#")
            tm = ""
            t = e.get("time") or ""
            if t and ":" in t:
                hh, mm = t.split(":", 1)
                try:
                    tm = str((int(hh) * 60 + int(mm[:2]) + 1440) % 1440)
                except ValueError:
                    tm = ""
            pick_cards.append(f"""<div class="af-pick-card" data-d="{e['date']}" data-tm="{tm}" data-type="{etype}">
<div class="af-kick">{icon} {name} · {d:%d.%m}</div>
<a class="af-link" href="{url}" target="_blank" rel="noopener"><b>{title}</b></a>
<div class="af-pick-why">{esc(pick_reason(e))}</div>
<button type="button" class="af-ics-link" onclick="_afIcs(this)">в календарь</button>
</div>""")
        pick_html = f"""<div class="af-pick"><h2>⭐ Выбор редакции</h2>
<div class="af-pick-grid">{''.join(pick_cards)}</div></div>"""

    return f"""<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Афиша культурных событий · Ульяновская область — {cfg['brand']}</title>
<link rel="icon" type="image/png" href="assets/logo_gudok.png"><style>{CSS}{AFISHA_CSS}</style></head><body>
<header class="masthead"><div class="mast-inner">
<div class="mast-side">Информационно-аналитическое издание<br>марксистской группы «Победа»</div>
<div class="mast-title">ГУДОК<span>.</span></div>
<div class="mast-side mast-side--right">Афиша культурных событий<br>всего {total_n} · сегодня {today_n} · выходные {we_n}
<div class="mast-actions">{THEME_BTN}</div></div>
</div></header>
{nav_html}
<div class="page">

<div class="note" style="margin-bottom:4px;">{pipeline_note}</div>

{filters_html}
<div class="af-active" id="af-active"></div>
<div class="af-daybar" id="af-daybar" data-ref="{today.isoformat()}">{''.join(daybar)}</div>

{pick_html}

{list_html}
<div class="af-empty" id="af-empty" hidden><b>Под условия ничего не нашлось.</b> Снимите один из фильтров или поиск.
<div style="margin-top:10px;"><button type="button" class="af-chip" onclick="_afReset()">Сбросить фильтры</button></div></div>

<div class="af-foot"><span>Показано: <b id="af-shown">{total_n}</b> событий</span><span>дней с событиями: <b id="af-days">{days_n}</b></span>
<button type="button" class="af-ics-link" onclick="_afIcsAll()" title="Только неотменённые, на видимую выборку">сохранить .ics</button>
<button type="button" class="af-ics-link" onclick="window.print()" title="Печать листка выходных — A4">листок выходных</button>
<span class="af-albl" style="margin-left:auto;">фильтры применяются в браузере; без JS видны все события по дням</span></div>

{rej_html}
{cand_html}

<div class="sec-head"><h2>Анонсы культурных каналов</h2><div class="line"></div>
<div class="badge">Telegram, последние посты</div></div>
<div class="grid2">{''.join(chan_html)}</div>
<div class="note" style="margin-top:10px;">Посты каналов выводятся как есть; если дата не распознана — время и место сверяйте у организатора.</div>

<div class="note" style="margin-top:16px;"><b>Методика порога входа</b> (analytics.py → extract_calendar_full, настройки — config.json → settings.afisha).
Событие проходит, если выполнены четыре условия: <b>дата</b> в горизонте {af_horizon} дней, <b>время</b> (или «весь день»/«уточняется»),
<b>площадка</b> и <b>тип</b> культурного события; сверх того индекс уверенности должен быть не ниже {af_thr}.
Площадка берётся из четырёх источников по убыванию надёжности: маркер 📍 в посте, имя из справочника <code>data/venues.json</code>
в кавычках, то же имя в тексте без маркера (любой падеж и порядок слов, с защитой от «современные языковые модели» ≠ ДК «Современник»)
и адрес («Адрес: Гончарова, 25»). Фестиваль, ярмарка или кросс, у которых площадок несколько, идут как «площадки города»
с пометкой «площадка уточняется» и половиной кредита уверенности. Порог применяется к <b>кластеру</b> анонсов, а не к отдельной записи:
у перепечатки может не быть времени или площадки, хотя у первоисточника они есть, — свидетельства сливаются, а в карточке появляется
«также анонсировали: N изд.». Название события собирается описательным (тип + имя: «Концерт группы «Мураками»», «Матч «Волга» — «Спартак»»),
а не голым именем из кавычек. Что не прошло — видно в блоке «Не прошло порог» с причиной. Культурных событий в выборке: {n_culture}.</div>

</div>
{footer.render_footer('')}
{AFISHA_JS}
</body></html>"""


AF_WEEK_CSS = """
body.afw{background:#8b939c;margin:0;font-family:Georgia,'Times New Roman',serif;}
.afw-sheet{width:186mm;min-height:266mm;margin:10mm auto;background:#fdfcf8;color:#141414;
padding:11mm 13mm 9mm;box-shadow:0 4px 24px rgba(0,0,0,.45);position:relative;box-sizing:border-box;}
.afw-mast{text-align:center;border-bottom:3px double #141414;padding-bottom:4mm;}
.afw-title{font-size:38pt;font-weight:900;letter-spacing:8px;line-height:1;margin:0;}
.afw-line{font-size:8.5pt;letter-spacing:1.2px;text-transform:uppercase;margin-top:2.5mm;color:#333;}
.afw-kicker{font-size:8pt;letter-spacing:2px;text-transform:uppercase;color:#7a1f1f;font-weight:700;margin:3mm 0 1.5mm;}
.afw-day{break-inside:avoid;margin-bottom:4mm;}
.afw-day h2{font-size:15pt;font-weight:900;border-bottom:1.4pt solid #141414;padding-bottom:1.2mm;margin:0 0 2mm;}
.afw-day .afw-date{font-size:8pt;letter-spacing:1px;text-transform:uppercase;color:#5a5a5a;margin-bottom:2mm;}
.afw-item{display:flex;gap:3mm;margin-bottom:1.6mm;break-inside:avoid;}
.afw-time{flex:0 0 26mm;font-weight:900;font-size:9.6pt;padding-top:.2mm;}
.afw-body{flex:1;font-size:9.4pt;line-height:1.35;}
.afw-body .afw-t{font-weight:900;font-size:10pt;}
.afw-body .afw-m{color:#4a4a4a;font-size:8.6pt;}
.afw-body .afw-moved{color:#1d4f9c;font-style:italic;font-size:8.6pt;}
.afw-note{font-style:italic;color:#8a8378;font-size:8.2pt;margin-top:2mm;}
.afw-toolbar{position:fixed;top:10px;right:14px;z-index:9;display:flex;gap:8px;}
.afw-toolbar a,.afw-toolbar button{background:#141414;color:#fff;border:none;border-radius:8px;padding:8px 14px;
font-size:12.5px;font-weight:700;cursor:pointer;text-decoration:none;font-family:Segoe UI,Arial,sans-serif;}
@media print{
  body.afw{background:#fff;}
  .afw-sheet{margin:0;box-shadow:none;width:auto;min-height:auto;page-break-after:always;}
  .afw-toolbar{display:none;}
}
"""

WD_RU_FULL = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]


def render_afisha_print(cfg, an, now=None):
    """Листок выходных (п.4): ближайшие суббота и воскресенье — только сегодня при воскресенье.
    Полные события по времени, отменённые исключены, перенесённые помечены. Самодостаточный A4."""
    now = now or datetime.now(UTC4)
    today = now.date()

    def edate(e):
        try:
            return datetime.strptime(e["date"], "%Y-%m-%d").date()
        except (ValueError, TypeError, KeyError):
            return None

    cal = (an or {}).get("calendar", [])
    cal = [e for e in cal if edate(e) and not e.get("canceled")]
    cal = sorted(cal, key=lambda e: (e["date"], e.get("time") or "99:99"))

    we = {}
    for shift in (0, 1):
        d = today + timedelta(days=shift)
        if shift == 1 and d.weekday() != 5:      # завтра не суббота — листок только на текущие выходные
            break
        if d.weekday() in (5, 6):                # сб=5, вс=6
            we[d] = [e for e in cal if edate(e) == d]
        if shift == 1:
            break
    # если сегодня не выходные — берём ближайшую субботу и воскресенье
    if not we:
        for gap in (0, 1, 2, 3, 4, 5, 6):
            d = today + timedelta(days=gap)
            if d.weekday() in (5, 6):
                we[d] = [e for e in cal if edate(e) == d]
            if len(we) == 2:
                break

    sections = []
    for d in sorted(we):
        title = WD_RU_FULL[d.weekday()] + ", " + d.strftime("%d.%m.%Y")
        rows = []
        for e in we[d]:
            hours = (e.get("time") or "").strip()
            if e.get("time_note") == "весь день":
                hours = "весь день"
            elif not hours and e.get("time_note"):
                hours = e["time_note"]
            elif not hours:
                hours = "время уточняется"
            src = e.get("source") or ""
            moved = ""
            if e.get("moved_from"):
                moved = '<div class="afw-moved">перенесено с {}</div>'.format(
                    esc(e["moved_from"][8:10] + "." + e["moved_from"][5:7]))
            elif e.get("moved_unknown"):
                moved = '<div class="afw-moved">перенесено, новая дата неизвестна</div>'
            extra = " · ".join(x for x in [src, (e.get("price") or ""), (e.get("age") or "")] if x)
            meta = esc(extra)
            if e.get("venue"):
                meta = ("📍 " + esc(e["venue"])) + (" · " + meta if meta else "")
            rows.append(f"""<div class="afw-item"><div class="afw-time">{esc(hours)}</div>
<div class="afw-body"><div class="afw-t">{esc(clip_words(e.get("event_title") or e.get("title") or "без названия", 90))}</div>
<div class="afw-m">{meta}</div>{moved}</div></div>""")
        if not rows:
            rows.append('<div class="afw-note">Событий не найдено — все площадки пустуют или их не анонсировали.</div>')
        sections.append(f"""<section class="afw-day"><h2>{esc(title)}</h2>
<div class="afw-date">культурная афиша · всего {len(we[d])} событий</div>
{''.join(rows)}</section>""")

    return f"""<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Листок выходных · {cfg['brand']}</title>
<style>{AF_WEEK_CSS}</style></head><body class="afw">
<div class="afw-toolbar"><a href="afisha/">← к афише</a><button onclick="window.print()">Печать</button></div>
<div class="afw-sheet">
<div class="afw-mast"><p class="afw-kicker">ГУДОК · выходные · {today:%d.%m.%Y}</p>
<h1 class="afw-title">Листок выходных</h1>
<div class="afw-line">Куда пойти в {now:%B} — {cfg['brand']}</div></div>
{''.join(sections)}
<div class="afw-note" style="margin-top:4mm;">Время и цены — организаторы . Правки, если событие отменено или перенесено, вносятся меткой при пересборке афиши.</div>
</div>
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

    # ── Волна 1 (предложение v0.9 → infospace-plan.html): новые метрики ──
    w1 = info.get("w1") or {}
    w1_html = ""
    if w1.get("matrix") or w1.get("tli"):
        def _pct(x):
            return "—" if x is None else f"{round(x * 100)}%"
        mx = w1.get("matrix") or {}
        cats_w = mx.get("cats") or []
        thead = "".join(f'<th style="text-align:center;font-size:9px;">{esc(c["name"].split(" и ")[0])}</th>' for c in cats_w)
        mrows = ""
        for r in mx.get("rows") or []:
            tds = ""
            for c in cats_w:
                v = (r.get("cats") or {}).get(c["id"], 0)
                bg = "transparent" if not v else ("#E5C9B6" if v <= 3 else ("#B4795A" if v <= 9 else "var(--accent)"))
                fg = "#fff" if v > 9 else "var(--ink-2)"
                tds += f'<td style="text-align:center;background:{bg};color:{fg};font-weight:700;padding:6px 4px;">{v or "·"}</td>'
            mrows += f'<tr><td><b>{esc(r["muni"])}</b></td><td style="text-align:center;color:var(--muted);">{r["total"]}</td>{tds}</tr>'

        rh = w1.get("rhythm") or {}
        wd_h = rh.get("weekday") or [0] * 24
        we_h = rh.get("weekend") or [0] * 24
        rmax = max(wd_h + we_h + [1])
        bars = ""
        for hr in range(24):
            h1 = round(wd_h[hr] / rmax * 100)
            h2 = round(we_h[hr] / rmax * 100)
            bars += (f'<span title="{hr}:00 — будни {wd_h[hr]}, выходные {we_h[hr]}" '
                     f'style="flex:1;display:flex;flex-direction:column;justify-content:flex-end;gap:1px;height:100%;">'
                     f'<i style="display:block;height:{h2}%;background:var(--accent);"></i>'
                     f'<i style="display:block;height:{h1}%;background:var(--ink-2);"></i></span>')
        xlab = "".join(f'<span style="flex:1;text-align:center;">{h if h % 4 == 0 else ""}</span>' for h in range(24))

        ct = w1.get("cascade_time") or {}
        frows = ""
        for x in ct.get("fastest") or []:
            spd = f' · {x["speed"]} ист/ч' if x.get("speed") else ""
            frows += (f'<div style="display:flex;gap:12px;align-items:baseline;padding:5px 0;border-bottom:1px dashed var(--rule);font-size:13px;">'
                      f'<a href="{esc(x.get("url") or "#")}" target="_blank" rel="noopener" style="flex:1;min-width:0;color:var(--ink);">{esc(x.get("title", ""))}</a>'
                      f'<span style="font-family:var(--sans);font-size:11px;color:var(--muted);white-space:nowrap;">×{x.get("size", 0)} за {x.get("span_h", 0)} ч{spd}</span></div>')

        tli = w1.get("tli") or {}
        tbars = ""
        gmax = max([(g.get("share") or 0) for g in (tli.get("groups") or {}).values()] + [0.05])
        for gname, g in (tli.get("groups") or {}).items():
            wdt = max(2, int((g.get("share") or 0) / gmax * 100))
            hot = "background:var(--accent);" if (g.get("share") or 0) >= 0.3 else "background:var(--ink-2);"
            tbars += (f'<div style="display:flex;gap:9px;align-items:center;margin-bottom:6px;font-family:var(--sans);font-size:12px;">'
                      f'<span style="width:170px;text-align:right;font-weight:600;color:var(--ink);flex-shrink:0;">{esc(gname)}</span>'
                      f'<span style="flex:1;background:var(--paper-2);border:1px solid var(--rule);height:14px;overflow:hidden;display:block;"><i style="display:block;height:100%;width:{wdt}%;{hot}"></i></span>'
                      f'<span style="width:56px;font-weight:700;font-size:11px;">{g.get("speaks", 0)}/{g.get("mentioned", 0)}</span></div>')

        emo = w1.get("emoji") or {}
        erows = "".join(
            f'<tr><td>{esc(k)}</td><td style="text-align:center;">{v.get("total", 0)}</td>'
            f'<td style="text-align:center;"><b>{_pct(v.get("with_emoji"))}</b></td></tr>'
            for k, v in emo.items())
        bv = w1.get("budget_voice") or {}

        # словарь власти
        bu = w1.get("bureaucratese") or {}
        buro_bars = ""
        for k, v in (bu.get("by_tier") or {}).items():
            sh = v.get("share") or 0
            buro_bars += (f'<div style="display:flex;gap:9px;align-items:center;margin-bottom:6px;font-family:var(--sans);font-size:12px;">'
                          f'<span style="width:120px;text-align:right;font-weight:600;color:var(--ink);flex-shrink:0;">{esc(k)}</span>'
                          f'<span style="flex:1;background:var(--paper-2);border:1px solid var(--rule);height:14px;overflow:hidden;display:block;"><i style="display:block;height:100%;width:{max(2, int(sh * 100 * 4))}%;background:var(--ink-2);"></i></span>'
                          f'<span style="width:46px;font-weight:700;font-size:11px;">{round(sh * 100)}%</span></div>')
        top_marks = " · ".join(f'<span style="white-space:nowrap;">«{esc(m)}» ×{n}</span>' for m, n in (bu.get("top_markers") or []))

        # тревожность: 7 столбцов
        ax = w1.get("anxiety") or {}
        anx_bars = ""
        axmax = max([(x.get("share") or 0) for x in (ax.get("series") or [])] + [0.1])
        for x in ax.get("series") or []:
            sh = x.get("share") or 0
            h_pct = max(2, int(sh / axmax * 100))
            col = "var(--accent)" if sh >= 0.20 else "var(--ink-2)"
            anx_bars += (f'<span title="{esc(x.get("date","")[5:])}: {round(sh*100)}% ({x.get("sec",0)} из {x.get("n",0)})" '
                         f'style="flex:1;display:flex;flex-direction:column;justify-content:flex-end;height:100%;">'
                         f'<i style="display:block;height:{h_pct}%;background:{col};"></i></span>')
        anx_days = "".join(f'<span style="flex:1;text-align:center;">{esc(x.get("date","")[8:])}</span>' for x in ax.get("series") or [])

        # ЖКХ
        zh = w1.get("zhkh") or {}
        zh_srcs = " · ".join(f'{esc(str(s))} ×{n}' for s, n in (zh.get("top_sources") or []))

        # село
        ri = w1.get("rural_index") or {}
        ri_bars = ""
        if ri:
            for lbl, val, col in (("в повестке недели", ri.get("agenda_share") or 0, "var(--accent)"),
                                  ("в населении области", ri.get("pop_share") or 0, "var(--ink-2)"),
                                  ("сельское население", ri.get("rural_pop_share") or 0, "var(--muted)")):
                ri_bars += (f'<div style="display:flex;gap:9px;align-items:center;margin-bottom:6px;font-family:var(--sans);font-size:12px;">'
                            f'<span style="width:160px;text-align:right;font-weight:600;color:var(--ink);flex-shrink:0;">{lbl}</span>'
                            f'<span style="flex:1;background:var(--paper-2);border:1px solid var(--rule);height:14px;overflow:hidden;display:block;"><i style="display:block;height:100%;width:{max(2,int(val*100*2.4))}%;background:{col};"></i></span>'
                            f'<span style="width:52px;font-weight:700;font-size:11px;">{round(val*100,1)}%</span></div>')

        # федеральное эхо по источникам
        fed_rows = ""
        for x in w1.get("federal_by_source") or []:
            fed_rows += (f'<div style="display:flex;gap:9px;align-items:center;margin-bottom:6px;font-family:var(--sans);font-size:12px;">'
                         f'<span style="width:150px;text-align:right;font-weight:600;color:var(--ink);flex-shrink:0;">{esc(str(x.get("source","")))}</span>'
                         f'<span style="flex:1;background:var(--paper-2);border:1px solid var(--rule);height:14px;overflow:hidden;display:block;"><i style="display:block;height:100%;width:{max(2,int((x.get("fed_share") or 0)*100))}%;background:var(--ink-2);"></i></span>'
                         f'<span style="width:120px;font-size:11px;color:var(--muted);white-space:nowrap;">{round((x.get("fed_share") or 0)*100)}% · {x.get("n",0)} перв.</span></div>')

        # латентность освещения (ось «время»)
        lt = w1.get("latency") or {}
        lt_card = ""
        if lt.get("n") or lt.get("sameday_n"):
            tot = (lt.get("n") or 0) + (lt.get("sameday_n") or 0)
            b = lt.get("buckets") or {}
            segs = [("в тот же день", "var(--ink)", (lt.get("sameday_n") or 0) / tot if tot else 0)]
            for lbl, col in (("<6 ч", "var(--ink-2)"), ("6–24 ч", "#6D6079"),
                             ("24–48 ч", "#B4795A"), (">48 ч", "var(--accent)")):
                key = lbl.replace("–", "-").replace(" ч", "ч")
                segs.append((lbl, col, (b.get(key) or 0) * ((lt.get("n") or 0) / tot if tot else 0)))
            seg = legend = ""
            for lbl, col, val in segs:
                seg += f'<span title="{lbl}: {round(val * 100)}%" style="width:{max(1, round(val * 100))}%;background:{col};display:block;height:100%;"></span>'
                legend += (f'<span style="display:inline-flex;align-items:center;gap:5px;margin-right:14px;">'
                           f'<i style="width:10px;height:10px;background:{col};display:inline-block;"></i>{lbl} · {round(val * 100)}%</span>')
            med = lt.get("median_h") or 1
            lt_rows = "".join(
                f'<div style="display:flex;gap:9px;align-items:center;margin-bottom:6px;font-family:var(--sans);font-size:12px;">'
                f'<span style="width:220px;text-align:right;font-weight:600;color:var(--ink);flex-shrink:0;">{esc(str(t[0]))}</span>'
                f'<span style="flex:1;background:var(--paper-2);border:1px solid var(--rule);height:14px;overflow:hidden;display:block;"><i style="display:block;height:100%;width:{max(2, min(100, int((t[1] or 0) / max(0.1, med) * 50)))}%;background:var(--accent);"></i></span>'
                f'<span style="width:110px;font-size:11px;color:var(--muted);white-space:nowrap;">{t[1]} ч · n={t[2]}</span></div>'
                for t in lt.get("slow_topics") or [])
            tier_line = " · ".join(f"{esc(k)}: {v.get('median_h')} ч (n={v.get('n')})"
                                   for k, v in (lt.get("by_tier") or {}).items()) or "—"
            slow_lines = "".join(
                f'<div style="display:flex;gap:12px;align-items:baseline;padding:5px 0;border-bottom:1px dashed var(--rule);font-size:13px;">'
                f'<a href="{esc(x.get("url") or "#")}" target="_blank" rel="noopener" style="flex:1;min-width:0;color:var(--ink);">{esc(x.get("title", ""))}</a>'
                f'<span style="font-family:var(--sans);font-size:11px;color:var(--muted);white-space:nowrap;">+{x.get("h", 0)} ч</span></div>'
                for x in lt.get("slowest") or []) or '<div class="note">Измеримых задержек за неделю нет.</div>'
            lt_card = f"""
<div class="card"><div class="card-pad">
<div class="side-head">Латентность освещения <span class="sub">сколько поле догоняет реальность · ось «время»</span></div>
<div class="side-body">
<div style="display:flex;gap:26px;align-items:baseline;margin-bottom:10px;flex-wrap:wrap;">
<div><span style="font-family:var(--serif-display);font-size:26px;font-weight:700;">{_pct(lt.get('sameday_share'))}</span> <span style="font-family:var(--sans);font-size:11.5px;color:var(--muted);">измеримых событий — освещены в тот же день</span></div>
<div><span style="font-family:var(--serif-display);font-size:26px;font-weight:700;color:var(--accent);">{lt.get('median_h') if lt.get('median_h') is not None else '—'}</span> <span style="font-family:var(--sans);font-size:11.5px;color:var(--muted);">ч — медианная задержка остальных ({lt.get('n', 0)} сообщ.)</span></div>
<div><span style="font-family:var(--serif-display);font-size:26px;font-weight:700;">{_pct(lt.get('coverage'))}</span> <span style="font-family:var(--sans);font-size:11.5px;color:var(--muted);">первоисточников измеримы — у остальных нет маркеров времени</span></div>
</div>
<div style="display:flex;height:16px;border:1px solid var(--rule);overflow:hidden;margin-bottom:6px;">{seg}</div>
<div style="font-family:var(--sans);font-size:10.5px;color:var(--muted);margin-bottom:4px;">{legend}</div>
<div style="margin:12px 0 6px;font-family:var(--sans);font-size:10.5px;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);">Темы, которые догоняют медленнее · медиана, n≥5</div>
{lt_rows}
<div style="font-family:var(--sans);font-size:11.5px;color:var(--muted);margin:8px 0 4px;">По уровням источников: {tier_line}</div>
<div style="margin:12px 0 6px;font-family:var(--sans);font-size:10.5px;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);">Самые долгие задержки недели</div>
{slow_lines}
<div class="note">Время события извлекается из текста первоисточника по маркерам: явные даты («14 сентября», «14.09»), относительные слова («вчера», «накануне», «минувшей ночью»), день недели («в среду» — только рядом с глаголом прошлого времени); время суток уточняет час («вечером»≈20:00, «в 18:30» — точно), прошедшая дата без времени — полдень. Охраны отсекают анонсы (глаголы будущего времени, «приглашаем/ждём вас»), диапазоны («до 20 сентября») и исторические справки (иной год). «Сегодня» без времени — отдельный класс «в тот же день»: точное запаздывание текст не восстанавливает. Выборка смещена: точное время чаще указывают у вчерашних событий — медиану читайте как задержку «датированных» событий; разрезы по темам и уровням сопоставимы между собой. Оценка ориентировочная. Считаются только первоисточники: скорость подхватов — в блоке «Динамика каскадов».</div>
</div></div></div>
"""

        w1_html = f"""
<div class="sec-head"><h2>Волна 1: деньги, труд, время и территория</h2><div class="line"></div>
<div class="badge"><a href="projects/plans.html#metrics" style="color:var(--accent);">план внедрения и реестр метрик →</a> · метрики подключены 15.09</div></div>

<div class="card"><div class="card-pad">
<div class="side-head">Матрица «территория × рубрика» <span class="sub">неделя · топ-10 территорий по объёму</span></div>
<div class="side-body"><div style="overflow-x:auto;"><table class="tbl"><tr><th>Территория</th><th style="text-align:center;">всего</th>{thead}</tr>{mrows}</table></div>
<div class="note">Пустая клетка — рубрика, по которой о территории за неделю не сказано ничего. Чем выше в строке доля «Безопасности», тем сильнее район существует для областного читателя только через происшествия.</div></div>
</div></div>

<div class="grid2">
<div class="card"><div class="card-pad">
<div class="side-head">Ритм суток <span class="sub">будни (тёмные) и выходные (акцент) · сообщений в час</span></div>
<div class="side-body">
<div style="display:flex;align-items:flex-end;gap:2px;height:110px;border-bottom:1px solid var(--ink);">{bars}</div>
<div style="display:flex;gap:2px;font-family:var(--sans);font-size:9px;color:var(--muted);margin-top:4px;">{xlab}</div>
<div class="note">Ночная доля (00–06): <b>{_pct(rh.get('night_share'))}</b> потока · доля выходных: <b>{_pct(rh.get('weekend_share'))}</b>. Сдвиг поля в ночь — дешёвый индикатор напряжённости: регион живёт в режиме ожидания чрезвычайного, а не развития.</div>
</div></div></div>
<div class="card"><div class="card-pad">
<div class="side-head">Динамика каскадов <span class="sub">полка жизни сюжета · скорость подхватов</span></div>
<div class="side-body">
<div style="display:flex;gap:26px;align-items:baseline;margin-bottom:8px;flex-wrap:wrap;">
<div><span style="font-family:var(--serif-display);font-size:24px;font-weight:700;">{ct.get('median_span_h') if ct.get('median_span_h') is not None else '—'}</span> <span style="font-family:var(--sans);font-size:11.5px;color:var(--muted);">ч — медианная полка сюжета</span></div>
<div><span style="font-family:var(--serif-display);font-size:24px;font-weight:700;">{ct.get('n', 0)}</span> <span style="font-family:var(--sans);font-size:11.5px;color:var(--muted);">каскадов за неделю</span></div></div>
{frows}
<div class="note">Полка — часы от первой публикации до последнего подхвата внутри кластера дедупликации; скорость — источников в час. Выше — пять самых быстрых сюжетов недели.</div>
</div></div></div>
</div>

<div class="grid2">
<div class="card"><div class="card-pad">
<div class="side-head">Индекс присутствия труда (TLI) <span class="sub">{_pct(tli.get('index'))} — {esc(tli.get('verdict', '—'))}</span></div>
<div class="side-body">
{tbars}
<div class="note">Доля сообщений, где социальная группа не только упомянута, но и говорит сама (глагол речи в пределах ±200 знаков от маркера группы). Всего упоминаний: {tli.get('mentioned', 0)}, с прямой речью: {tli.get('speaks', 0)}. Пороги: &lt;10% — «труд невидим», 10–30% — «труд упоминаем», &gt;30% — «труд говорит». Эвристика оценочная; калибровка ручной разметкой — волна 3.</div>
</div></div></div>
<div class="card"><div class="card-pad">
<div class="side-head">Язык и деньги официоза <span class="sub">эмодзи-профиль · бюджетный голос</span></div>
<div class="side-body">
<div style="overflow-x:auto;"><table class="tbl"><tr><th>Уровень источника</th><th style="text-align:center;">сообщений</th><th style="text-align:center;">с эмодзи</th></tr>{erows}</table></div>
<div style="display:flex;gap:26px;align-items:baseline;margin:12px 0 4px;flex-wrap:wrap;">
<div><span style="font-family:var(--serif-display);font-size:24px;font-weight:700;">{_pct(bv.get('t1_share_flow'))}</span> <span style="font-family:var(--sans);font-size:11.5px;color:var(--muted);">потока — tier-1, официальные каналы</span></div>
<div><span style="font-family:var(--serif-display);font-size:24px;font-weight:700;">{_pct(bv.get('echo_of_t1'))}</span> <span style="font-family:var(--sans);font-size:11.5px;color:var(--muted);">перепечаток — эхо официальных каналов</span></div></div>
<div class="note">Эмодзи-профиль — маркер уровня источника: зарегистрированные СМИ эмодзи почти не используют, официальные каналы и агрегаторы — более половины постов. «Бюджетный голос» — доля tier-1 в потоке и в первоисточниках каскадов; полная версия метрики («цена слова» по контрактам ЕИС) — волна 3.</div>
</div></div></div>
</div>

<div class="grid2">
<div class="card"><div class="card-pad">
<div class="side-head">Словарь власти <span class="sub">канцелярит и эвфемизмы по уровням источников</span></div>
<div class="side-body">
{buro_bars}
<div style="font-family:var(--serif-body);font-size:13px;color:var(--ink-2);margin-top:8px;">Частотные маркеры: {top_marks or "—"}</div>
<div class="note">Доля сообщений с маркерами официального языка («оптимизация», «по поручению», «в штатном режиме», «нацпроект»…). Чем выше у уровня — тем ближе источник к пресс-релизной модели речи. Список маркеров расширяемый (config → BUROKRAT_MARKERS в analytics.py).</div>
</div></div></div>
<div class="card"><div class="card-pad">
<div class="side-head">Индекс тревожности <span class="sub">{_pct(ax.get('avg'))} за неделю — {esc(ax.get('verdict', '—'))}</span></div>
<div class="side-body">
<div style="display:flex;align-items:flex-end;gap:3px;height:80px;border-bottom:1px solid var(--ink);">{anx_bars}</div>
<div style="display:flex;gap:3px;font-family:var(--sans);font-size:9px;color:var(--muted);margin-top:4px;">{anx_days}</div>
<div class="note">Доля сообщений безопасности и воздушных угроз (security + topic «БПЛА») в дневном потоке, 7 дней. Пороги: &lt;8% — спокойный фон, 8–20% — повышенный, &gt;20% — высокая тревожность (столбец акцентного цвета). Динамика важнее уровня: рост неделю к неделе — сигнал напряжённости.</div>
</div></div></div>
</div>

<div class="grid2">
<div class="card"><div class="card-pad">
<div class="side-head">ЖКХ и тарифы <span class="sub">доля и тон повестки</span></div>
<div class="side-body">
<div style="display:flex;gap:26px;align-items:baseline;margin-bottom:6px;flex-wrap:wrap;">
<div><span style="font-family:var(--serif-display);font-size:24px;font-weight:700;">{zh.get('n', 0)}</span> <span style="font-family:var(--sans);font-size:11.5px;color:var(--muted);">сообщений за неделю</span></div>
<div><span style="font-family:var(--serif-display);font-size:24px;font-weight:700;">{_pct(zh.get('share'))}</span> <span style="font-family:var(--sans);font-size:11.5px;color:var(--muted);">потока</span></div>
<div><span style="font-family:var(--serif-display);font-size:24px;font-weight:700;color:{'var(--accent)' if (zh.get('tone') or 0) < 0 else 'var(--ink)'};">{zh.get('tone') if zh.get('tone') is not None else '—'}</span> <span style="font-family:var(--sans);font-size:11.5px;color:var(--muted);">тон (−1…+1)</span></div>
</div>
<div style="font-family:var(--sans);font-size:11.5px;color:var(--muted);">Больше всех пишут: {zh_srcs or "—"}</div>
<div class="note">Тема «ЖКХ, газ, тепло» из словаря config.json. Позитивный тон при высокой доле темы обычно означает отчётность о ремонтах и подключениях; негативный — аварийные и тарифные сюжеты. Тон — лексиконная оценка, ориентировочно.</div>
</div></div></div>
<div class="card"><div class="card-pad">
<div class="side-head">Индекс присутствия села <span class="sub">{ri.get('index', '—')} — {esc(ri.get('verdict', '—'))}</span></div>
<div class="side-body">
{ri_bars or '<div class="note">Справочник населения не подключён (config → muni_population).</div>'}
<div class="note">Доля 20 муниципальных районов (без Димитровграда и Новоульяновска) в повестке недели против их доли в населении области. Индекс = повестка / население; 1.0 — паритет, &lt;0.4 — символическое исключение. Население: {esc(ri.get('source', 'Ульяновскстат'))}. Чаще других на неделе: {esc(", ".join(f"{n} ×{c}" for n, c in (ri.get('top') or [])[:3])) or "—"}.</div>
</div></div></div>
</div>

<div class="card"><div class="card-pad">
<div class="side-head">Федеральное эхо в разрезе источников <span class="sub">топ-8 по объёму первичных сообщений</span></div>
<div class="side-body">
{fed_rows}
<div class="note">Доля первичных сообщений источника без региональных маркеров (топонимы, фамилии руководителей, местные предприятия): чем выше, тем больше канал ретранслирует федеральную повестку вместо своей. Высокая доля у агрегаторов — признак конвейерного копирования; у официальных каналов норма ниже.</div>
</div></div></div>
{lt_card}
"""

    # ── Волна 2 (sources_registry.json): кто пишет и кто читает ──
    w2 = info.get("w2") or {}
    w2_html = ""
    if w2.get("producer_mix"):
        def _pct2(x):
            return "—" if x is None else f"{round(x * 100)}%"
        TYPE_COLORS = {"пресс-служба": "var(--ink)", "редакция": "var(--ink-2)",
                       "агрегатор": "var(--muted)", "авторский канал": "#6D6079",
                       "промо/коммерция": "#B4795A", "не атрибутирован": "var(--rule)"}
        pm = w2["producer_mix"]
        wn = pm.get("week_n") or 1
        order = sorted((pm.get("week") or {}).items(), key=lambda kv: -kv[1])
        type_bars = ""
        for t, n in order:
            col = TYPE_COLORS.get(t, "var(--muted)")
            type_bars += (f'<div style="display:flex;gap:9px;align-items:center;margin-bottom:6px;font-family:var(--sans);font-size:12px;">'
                          f'<span style="width:150px;text-align:right;font-weight:600;color:var(--ink);flex-shrink:0;">{esc(t)}</span>'
                          f'<span style="flex:1;background:var(--paper-2);border:1px solid var(--rule);height:14px;overflow:hidden;display:block;"><i style="display:block;height:100%;width:{max(2, round(n / wn * 100))}%;background:{col};"></i></span>'
                          f'<span style="width:96px;font-size:11px;color:var(--muted);">{n} · {round(n / wn * 100)}%</span></div>')
        stack_rows = ""
        for d in pm.get("daily") or []:
            segs = ""
            for t, sh in sorted((d.get("mix") or {}).items(), key=lambda kv: -kv[1]):
                col = TYPE_COLORS.get(t, "var(--muted)")
                segs += f'<i style="width:{max(1, round(sh * 100))}%;background:{col};" title="{esc(t)}: {round(sh * 100)}%"></i>'
            stack_rows += (f'<div style="display:grid;grid-template-columns:84px 1fr;gap:10px;align-items:center;margin-bottom:5px;">'
                           f'<span style="font-family:var(--sans);font-size:11px;color:var(--muted);text-align:right;">{esc(d.get("date", "")[5:])} · {d.get("n", 0)}</span>'
                           f'<span style="display:flex;height:16px;border:1px solid var(--rule);overflow:hidden;">{segs}</span></div>')
        legend = "".join(f'<span style="display:inline-flex;align-items:center;gap:5px;margin-right:14px;"><i style="width:10px;height:10px;background:{TYPE_COLORS.get(t, "var(--muted)")};display:inline-block;"></i>{esc(t)}</span>' for t, _ in order)

        at = w2.get("attention") or {}
        at_rows = ""
        amax = max([x.get("share") or 0 for x in at.get("top") or []] + [0.01])
        for x in at.get("top") or []:
            at_rows += (f'<div style="display:flex;gap:9px;align-items:center;margin-bottom:6px;font-family:var(--sans);font-size:12px;">'
                        f'<span style="width:150px;text-align:right;font-weight:600;color:var(--ink);flex-shrink:0;">@{esc(str(x.get("source", "")))}</span>'
                        f'<span style="flex:1;background:var(--paper-2);border:1px solid var(--rule);height:14px;overflow:hidden;display:block;"><i style="display:block;height:100%;width:{max(2, int((x.get("share") or 0) / amax * 100))}%;background:var(--accent);"></i></span>'
                        f'<span style="width:110px;font-size:11px;color:var(--muted);">{round((x.get("share") or 0) * 100)}% · {fmt_views(x.get("views", 0))}</span></div>')

        sp = w2.get("speech") or {}
        pl = w2.get("promo_load") or {}
        plc = pl.get("commercial") or {}
        plx = pl.get("crosspromo") or {}
        sg = w2.get("silent_groups") or []
        sg_chips = "".join(
            f'<span style="display:inline-block;border:1px solid var(--accent);color:var(--accent);font-family:var(--sans);font-size:10.5px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;padding:3px 9px;margin:0 6px 6px 0;">{esc(g["group"])} · упомянуты {g["mentioned"]}×, речи 0</span>'
            for g in sg) or '<span style="font-family:var(--sans);font-size:12px;color:var(--muted);">на этой неделе все группы получили прямую речь</span>'

        w2_html = f"""
<div class="sec-head"><h2>Волна 2: кто пишет и кто читает</h2><div class="line"></div>
<div class="badge"><a href="projects/plans.html#metrics" style="color:var(--accent);">план внедрения →</a> · реестр источников: {w2.get('registry_sources', 0)} · подключено 15.09</div></div>

<div class="card"><div class="card-pad">
<div class="side-head">Кто пишет: состав потока по типу производителя <span class="sub">неделя · {wn} сообщений</span></div>
<div class="side-body">
{type_bars}
<div style="margin:14px 0 8px;font-family:var(--sans);font-size:10.5px;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);">Кто формирует день · состав потока по дням</div>
{stack_rows}
<div style="font-family:var(--sans);font-size:11px;color:var(--muted);margin:8px 0 4px;">{legend}</div>
<div class="note">Типы — из реестра <code>sources_registry.json</code> (ручной справочник: пресс-служба / редакция / агрегатор / авторский канал / промо). Неатрибутированные RSS принимаются редакцией. Доля агрегаторов — мера конвейерности поля: оно воспроизводит повестку, а не производит её.</div>
</div></div></div>

<div class="grid2">
<div class="card"><div class="card-pad">
<div class="side-head">Внимание как ресурс <span class="sub">просмотры {at.get('n_sources', 0)} TG-источников за неделю</span></div>
<div class="side-body">
<div style="display:flex;gap:26px;align-items:baseline;margin-bottom:10px;flex-wrap:wrap;">
<div><span style="font-family:var(--serif-display);font-size:26px;font-weight:700;color:var(--accent);">{at.get('gini') if at.get('gini') is not None else '—'}</span> <span style="font-family:var(--sans);font-size:11.5px;color:var(--muted);">Gini концентрации внимания (0 — равенство, 1 — монополия)</span></div>
<div><span style="font-family:var(--serif-display);font-size:26px;font-weight:700;">{_pct2(at.get('top3_share'))}</span> <span style="font-family:var(--sans);font-size:11.5px;color:var(--muted);">всех просмотров — у топ-3 каналов</span></div>
</div>
{at_rows}
<div class="note">Всего {fmt_views(at.get('total_views', 0))} просмотров за неделю. Концентрация внимания означает: повестку региона видят через два-три «окна»; районные источники в топ не попадают — их повестка для области почти не существует.</div>
</div></div></div>
<div class="card"><div class="card-pad">
<div class="side-head">Голос и деньги <span class="sub">прямая речь · рекламная нагрузка · немые группы</span></div>
<div class="side-body">
<div style="display:flex;gap:26px;align-items:baseline;margin-bottom:8px;flex-wrap:wrap;">
<div><span style="font-family:var(--serif-display);font-size:26px;font-weight:700;">{sp.get('official', '—')}</span> <span style="font-family:var(--sans);font-size:11.5px;color:var(--muted);">цитат должностных лиц</span></div>
<div><span style="font-family:var(--serif-display);font-size:26px;font-weight:700;">{sp.get('citizen', '—')}</span> <span style="font-family:var(--sans);font-size:11.5px;color:var(--muted);">цитат жителей</span></div>
<div><span style="font-family:var(--serif-display);font-size:26px;font-weight:700;">{_pct2(plc.get('share') if plc else pl.get('share'))}</span> <span style="font-family:var(--sans);font-size:11.5px;color:var(--muted);">потока — коммерческая реклама ({plc.get('n', pl.get('n', 0))}{f", с маркировкой {plc.get('marked', 0)}" if plc else ""})</span></div>
<div><span style="font-family:var(--serif-display);font-size:26px;font-weight:700;">{_pct2(plx.get('share'))}</span> <span style="font-family:var(--sans);font-size:11.5px;color:var(--muted);">потока — кросс-промо в MAX ({plx.get('n', 0)})</span></div>
</div>
<div style="margin:12px 0 6px;font-family:var(--sans);font-size:10.5px;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);">Немые группы — упомянуты, но не процитированы</div>
{sg_chips}
<div class="note">Прямая речь — атрибуция цитат «в кавычках» по маркерам в ±150 знаках («губернатор/министерство/администрация…» против «житель/рабочий/врач…»), оценка ориентировочная. Немые группы — этическое ядро раздела: о них пишут, но их речь в поле не попадает. Реклама — классификатор, калиброванный по реальной базе (15.09): коммерческий класс = легальная маркировка (erid, «Реклама.» + ИНН, «на правах рекламы») или офертная рамка (промокод с кодом, «успей купить по … цене», «от N ₽», скидка N%, рекламные сокращатели ссылок); кросс-промо считается отдельно — это приписки каналов, уводящие аудиторию в MAX. Нативные интеграции без маркировки ловятся частично — оценка является нижней границей.</div>
</div></div></div>
</div>
"""

    def _pct2w(x):
        return "—" if x is None else f"{round(x * 100, 1)}%"

    # ── Волна 3 (owner_verification.md): деньги и собственность ──
    w3 = info.get("w3") or {}
    w3_html = ""
    if w3.get("hhi") is not None:
        FORM_COLORS = {"аноним": "var(--muted)", "частный бизнес": "#B4795A",
                       "государство": "var(--ink)", "официальные": "var(--ink-2)",
                       "не установлен": "var(--rule)", "вне реестра": "var(--accent)"}
        grp_bars = ""
        for gname, g in (w3.get("groups") or {}).items():
            wdt = max(2, round((g.get("share") or 0) * 100))
            col = FORM_COLORS.get(gname, "var(--muted)")
            grp_bars += (f'<div style="display:flex;gap:9px;align-items:center;margin-bottom:6px;font-family:var(--sans);font-size:12px;">'
                         f'<span style="width:150px;text-align:right;font-weight:600;color:var(--ink);flex-shrink:0;">{esc(gname)}</span>'
                         f'<span style="flex:1;background:var(--paper-2);border:1px solid var(--rule);height:14px;overflow:hidden;display:block;"><i style="display:block;height:100%;width:{wdt}%;background:{col};"></i></span>'
                         f'<span style="width:130px;font-size:11px;color:var(--muted);">{round((g.get("share") or 0) * 100, 1)}% · ист. {g.get("n", 0)}</span></div>')
        own_rows = ""
        for o in w3.get("top_owners") or []:
            own_rows += (f'<div style="display:flex;gap:12px;align-items:baseline;padding:5px 0;border-bottom:1px dashed var(--rule);font-size:13px;">'
                         f'<span style="flex:1;min-width:0;color:var(--ink);">{esc(o.get("name", ""))}</span>'
                         f'<span style="font-family:var(--sans);font-size:10.5px;color:var(--muted);white-space:nowrap;">{esc(o.get("form", ""))} · ист. {o.get("n_sources", 0)}</span>'
                         f'<span style="font-family:var(--sans);font-size:12px;font-weight:700;white-space:nowrap;">{round((o.get("share") or 0) * 100, 1)}%</span></div>')
        aff_lines = "".join(f'<div style="font-size:12.5px;padding:4px 0;border-bottom:1px dashed var(--rule);"><code>{esc(a.get("id", ""))}</code> — {esc(a.get("group", ""))}</div>'
                            for a in w3.get("affiliates") or []) or '<div class="note">Гипотез аффилированности пока нет.</div>'
        w3_html = f"""
<div class="sec-head"><h2>Волна 3: деньги и собственность</h2><div class="line"></div>
<div class="badge"><a href="projects/plans.html#metrics" style="color:var(--accent);">план внедрения →</a> · <a href="owner_verification.md" style="color:var(--accent);">верификация владельцев 15.09</a> · реестр: {w3.get('registry_sources', 0)}</div></div>
<div class="grid2">
<div class="card"><div class="card-pad">
<div class="side-head">Концентрация собственности <span class="sub">HHI по учредителям, взвешенный потоком недели</span></div>
<div class="side-body">
<div style="display:flex;gap:26px;align-items:baseline;margin-bottom:10px;flex-wrap:wrap;">
<div><span style="font-family:var(--serif-display);font-size:26px;font-weight:700;color:var(--accent);">{w3.get('hhi_confirmed') if w3.get('hhi_confirmed') is not None else '—'}</span> <span style="font-family:var(--sans);font-size:11.5px;color:var(--muted);">HHI атрибутируемой части — {esc(w3.get('verdict', '—'))} ({_pct2w(w3.get('confirmed_flow_share'))} потока)</span></div>
<div><span style="font-family:var(--serif-display);font-size:26px;font-weight:700;">{w3.get('hhi') if w3.get('hhi') is not None else '—'}</span> <span style="font-family:var(--sans);font-size:11.5px;color:var(--muted);">HHI всего поля — {esc(w3.get('verdict_all', '—'))} (с анонимами как отдельными владельцами — занижен)</span></div>
</div>
{grp_bars}
<div class="note">Индекс Херфиндаля–Хиршмана (0–10000, пороги: &lt;1500 низкая, 1500–2500 умеренная, &gt;2500 высокая) по учредителям источников; доля владельца = доля его источников в потоке недели, источники одного юрлица сливаются по ИНН. Анонимные каналы считаются отдельными неизвестными владельцами — общий HHI из-за этого занижен; честная картина — по атрибутируемой части (подтверждённые владельцы: {_pct2w(w3.get('confirmed_flow_share'))} потока). Государство и должностные лица: {_pct2w(w3.get('state_official_share'))} потока; юридически непрозрачные источники: {_pct2w(w3.get('anon_share'))}.</div>
</div></div></div>
<div class="card"><div class="card-pad">
<div class="side-head">Кто владеет полем <span class="sub">топ-6 владельцев по доле потока</span></div>
<div class="side-body">
{own_rows}
<div style="margin:12px 0 6px;font-family:var(--sans);font-size:10.5px;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);">Гипотезы аффилированности</div>
{aff_lines}
<div class="note">Доказательства владельцев — <code>owner_verification.md</code> (imprint-ы СМИ, реестр РКН, ЕГРЮЛ). «Платное освещение» (контракты ЕИС на информосвещение органов власти) — плейсхолдер: ЕИС из облачного контура недоступна, подключение через ручной экспорт в <code>data/goszakupki_eis.csv</code> (проект «Госзакупки»).</div>
</div></div></div>
</div>
"""

    # ── Волна 4 (план v0.9): язык, труд и методика — метрики на собранных данных ──
    w4 = info.get("w4") or {}
    w4_html = ""
    ag = w4.get("agency") or {}
    fr = w4.get("frames") or {}
    ait = w4.get("ai_trace") or {}
    dd = w4.get("dedup") or {}
    if ag.get("n") or fr.get("clusters") or ait.get("n") or dd.get("n_items"):
        def _p4(x):
            return "—" if x is None else f"{round(x * 100, 1)}%"

        def _num4(x, nd=2):
            return "—" if x is None else (f"{x:.{nd}f}" if isinstance(x, float) else str(x))

        def _seg4(pairs):
            """Сегмент-полоса: [(подпись, цвет, доля)] → (полоса, легенда)."""
            bar = legend = ""
            for lbl, col, val in pairs:
                if not val:
                    continue
                w = max(1, round(val * 100))
                bar += (f'<span title="{esc(lbl)}: {round(val * 100)}%" '
                        f'style="width:{w}%;background:{col};display:block;height:100%;"></span>')
                legend += (f'<span style="display:inline-flex;align-items:center;gap:5px;'
                           f'margin-right:14px;"><i style="width:10px;height:10px;background:{col};'
                           f'display:inline-block;"></i>{esc(lbl)} · {round(val * 100)}%</span>')
            return bar, legend

        def _bars4(rows, mx=None, color="var(--ink)"):
            """Строки-полосы: [(подпись, значение, подпись справа)] → HTML."""
            mx = mx or max([r[1] for r in rows] or [1]) or 1
            html = ""
            for lbl, val, right in rows:
                w = max(2, min(100, int(val / mx * 100)))
                html += (f'<div style="display:flex;gap:9px;align-items:center;margin-bottom:6px;'
                         f'font-family:var(--sans);font-size:12px;">'
                         f'<span style="width:150px;text-align:right;font-weight:600;color:var(--ink);'
                         f'flex-shrink:0;">{esc(str(lbl))}</span>'
                         f'<span style="flex:1;background:var(--paper-2);border:1px solid var(--rule);'
                         f'height:14px;overflow:hidden;display:block;"><i style="display:block;'
                         f'height:100%;width:{w}%;background:{color};"></i></span>'
                         f'<span style="width:110px;font-size:11px;color:var(--muted);'
                         f'white-space:nowrap;">{esc(str(right))}</span></div>')
            return html

        # ── 1) индекс агентности
        ag_html = ""
        if ag.get("n"):
            rs = ag.get("role_shares") or {}
            role_pairs = [("субъект действия", "var(--ink)", rs.get("субъект") or 0),
                          ("объект действия", "#B4795A", rs.get("объект") or 0),
                          ("актор назван, роль не ясна", "var(--ink-2)", rs.get("упоминание") or 0),
                          ("безличная конструкция", "#6D6079", rs.get("безличный") or 0),
                          ("актор не назван", "var(--rule)", rs.get("без актора") or 0)]
            ag_bar, ag_legend = _seg4(role_pairs)
            amix = ag.get("actor_mix") or {}
            asum = sum(amix.values()) or 1
            ACTOR_LABEL = {"власть": "власть и должностные лица", "контроль": "силовики и надзор",
                           "жители": "жители", "работники": "работники и профессии",
                           "военные": "военные", "бизнес": "бизнес", "учреждения": "учреждения",
                           "неизвестные": "неизвестные"}
            ag_rows = _bars4([(ACTOR_LABEL.get(k, k), v, f"{round(v / asum * 100)}% · n={v}")
                              for k, v in amix.items()], color="var(--accent)")
            omix = ag.get("object_mix") or {}
            osum = sum(omix.values()) or 1
            ag_obj_rows = _bars4([(ACTOR_LABEL.get(k, k), v, f"{round(v / osum * 100)}% · n={v}")
                                  for k, v in list(omix.items())[:5]], color="#B4795A")
            ag_tier_rows = ""
            for t in ("T1", "T2", "T3", "СМИ/подборка"):
                v = (ag.get("by_tier") or {}).get(t)
                if not v:
                    continue
                ag_tier_rows += (
                    f'<tr><td>{esc(t)}</td><td style="text-align:right;">{v.get("n", 0)}</td>'
                    f'<td style="text-align:right;">{_p4(v.get("subject_share"))}</td>'
                    f'<td style="text-align:right;">{v.get("people_subjects", 0)}</td>'
                    f'<td style="text-align:right;">{v.get("power_subjects", 0)}</td>'
                    f'<td style="text-align:right;">{v.get("people_objects", 0)}</td>'
                    f'<td style="text-align:right;">{_p4(v.get("impersonal_share"))}</td></tr>')
            ag_ex = ""
            for cls, exs in (ag.get("examples") or {}).items():
                for e in exs[:1]:
                    ag_ex += (f'<div style="display:flex;gap:12px;align-items:baseline;padding:5px 0;'
                              f'border-bottom:1px dashed var(--rule);font-size:13px;">'
                              f'<span style="width:104px;flex-shrink:0;font-family:var(--sans);'
                              f'font-size:10.5px;color:var(--muted);text-transform:uppercase;'
                              f'letter-spacing:.06em;">{esc(ACTOR_LABEL.get(cls, cls))}</span>'
                              f'<a href="{esc(e.get("url") or "#")}" target="_blank" rel="noopener" '
                              f'style="flex:1;min-width:0;color:var(--ink);">{esc(e.get("title", ""))}</a>'
                              f'<span style="font-family:var(--sans);font-size:11px;color:var(--muted);'
                              f'white-space:nowrap;">{esc(str(e.get("source", "")))}</span></div>')
            excl = ag.get("excluded_service") or {}
            excl_txt = ", ".join(f"{k} — {v}" for k, v in excl.items()) or "нет"
            fp = ag.get("first_person_by_tier") or {}
            fp_txt = " · ".join(f"{esc(k)}: {_p4(v)}" for k, v in sorted(fp.items())) or "—"
            ag_html = f"""
<div class="card"><div class="card-pad">
<div class="side-head">Индекс агентности <span class="sub">кому поле отдаёт действие · ось «язык»</span></div>
<div class="side-body">
<div style="display:flex;gap:26px;align-items:baseline;margin-bottom:10px;flex-wrap:wrap;">
<div><span style="font-family:var(--serif-display);font-size:26px;font-weight:700;color:var(--accent);">{_num4(ag.get('agency_index'))}</span> <span style="font-family:var(--sans);font-size:11.5px;color:var(--muted);">индекс агентности — {esc(ag.get('verdict', '—'))} (люди {ag.get('people_subjects', 0)} против власти и надзора {ag.get('power_subjects', 0)})</span></div>
<div><span style="font-family:var(--serif-display);font-size:26px;font-weight:700;">{_p4(ag.get('actor_density'))}</span> <span style="font-family:var(--sans);font-size:11.5px;color:var(--muted);">сообщений называют социального актора в лиде</span></div>
<div><span style="font-family:var(--serif-display);font-size:26px;font-weight:700;">{_p4(ag.get('objectification'))}</span> <span style="font-family:var(--sans);font-size:11.5px;color:var(--muted);">людей в поле — объекты действия, а не субъекты</span></div>
<div><span style="font-family:var(--serif-display);font-size:26px;font-weight:700;">{_p4(ag.get('impersonal_share'))}</span> <span style="font-family:var(--sans);font-size:11.5px;color:var(--muted);">сообщений без действующего лица (безлично или «о событии»)</span></div>
</div>
<div style="display:flex;height:16px;border:1px solid var(--rule);overflow:hidden;margin-bottom:6px;">{ag_bar}</div>
<div style="font-family:var(--sans);font-size:10.5px;color:var(--muted);margin-bottom:4px;">{ag_legend}</div>
<div class="grid2" style="margin-top:12px;">
<div><div style="margin:0 0 6px;font-family:var(--sans);font-size:10.5px;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);">Кто действует · субъекты</div>{ag_rows}</div>
<div><div style="margin:0 0 6px;font-family:var(--sans);font-size:10.5px;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);">Над кем совершают действие · объекты</div>{ag_obj_rows}
<div style="font-family:var(--sans);font-size:11.5px;color:var(--muted);margin-top:8px;">Авторское «я/мы» в лиде: {_p4(ag.get('first_person_share'))} потока ({fp_txt}).</div></div>
</div>
<div style="margin:12px 0 6px;font-family:var(--sans);font-size:10.5px;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);">По уровням источников</div>
<div style="overflow-x:auto;"><table class="tbl"><tr><th>Уровень</th><th style="text-align:right;">сообщ.</th><th style="text-align:right;">субъект</th><th style="text-align:right;">люди-субъекты</th><th style="text-align:right;">власть-субъекты</th><th style="text-align:right;">люди-объекты</th><th style="text-align:right;">безличность</th></tr>{ag_tier_rows}</table></div>
<div style="margin:12px 0 6px;font-family:var(--sans);font-size:10.5px;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);">Примеры разметки</div>
{ag_ex or '<div class="note">Примеров нет.</div>'}
<div class="note"><b>Метод.</b> Эвристика без морфологического разбора (внешние NLP-библиотеки отклонены принципом автономности): в первых предложениях лида ищется пара «класс актора ↔ агентивный глагол» в окне ±55 знаков; актор после предлога считается косвенным падежом и в субъекты не попадает; пассивный или виктимный маркер рядом («пострадали», «госпитализированы», «нашли тело») даёт роль объекта; адресатный глагол перед актором («жителей призвали…») — тоже объект. Классы: власть и должностные лица, силовики и надзор, жители, работники и профессии, военные, бизнес, учреждения, неизвестные. Служебные формуляры исключены ({esc(excl_txt)}): в них субъекта нет по определению. <b>Границы.</b> Без парсера омонимия падежей снимается не полностью: ручная проверка 32 сообщений с присвоенной ролью (20 «субъект» + 12 «объект») дала 27 верных — точность ≈85%; типичные ошибки: несклоняемые аббревиатуры («подала иск в Арбитражный суд», «на АЗС»), локативы места и прилагательные вместо существительных. Поэтому доля субъектов — нижняя оценка, а 45% сообщений попадают в «актор назван, роль не ясна»: их метрика не трактует. Калибровка по ручной разметке 200 сообщений — следующий шаг паспорта (пункт «аудит выборки»).</div>
</div></div></div>
"""

        # ── 2) фрейм-карта события
        fr_html = ""
        if fr.get("frame_mix"):
            fmix = fr.get("frame_mix") or {}
            ftot = sum(fmix.values()) or 1
            FRAME_LABEL = {"тревога": "тревога и режимы", "ЧП": "ЧП и происшествия",
                           "жалоба": "жалоба и проблема", "надзор": "надзор и наказание",
                           "работы": "плановые работы", "достижение": "достижение",
                           "ритуал": "ритуал и визит", "услуга": "услуга и инструкция",
                           "статистика": "статистика и опрос", "интерактив": "интерактив с аудиторией",
                           "лайв": "лайв-репортаж", "погода": "погода", "прочее": "нейтральная хроника"}
            fr_rows = _bars4([(FRAME_LABEL.get(k, k), v, f"{round(v / ftot * 100)}% · n={v}")
                              for k, v in fmix.items()], color="var(--ink-2)")
            tm = fr.get("tier_matrix") or {}
            fr_names = [k for k, _ in (fr.get("frame_mix") or {}).items()][:8]
            fr_thead = "".join(f'<th style="text-align:right;">{esc(FRAME_LABEL.get(f, f))}</th>' for f in fr_names)
            fr_trows = ""
            for t in ("T1", "T2", "T3", "СМИ/подборка"):
                v = tm.get(t)
                if not v:
                    continue
                cells = "".join(f'<td style="text-align:right;">{_p4((v.get("frames") or {}).get(f))}</td>'
                                for f in fr_names)
                fr_trows += f'<tr><td>{esc(t)} <span style="color:var(--muted);font-size:11px;">n={v.get("n")}</span></td>{cells}</tr>'
            fr_ex = ""
            for c in (fr.get("examples") or [])[:2]:
                fr_ex += (f'<div style="padding:8px 0;border-bottom:1px dashed var(--rule);">'
                          f'<div style="font-size:13.5px;font-weight:700;color:var(--ink);margin-bottom:4px;">'
                          f'×{c.get("size")} · фреймы: {esc(" / ".join(c.get("frames") or []))}'
                          f'{" · конфликт уровней" if c.get("tier_conflict") else ""}</div>')
                for m in c.get("members") or []:
                    tier_lbl = f"T{m.get('tier')}" if m.get("tier") else "СМИ"
                    fr_ex += (f'<div style="display:flex;gap:10px;align-items:baseline;padding:3px 0;'
                              f'font-family:var(--sans);font-size:11.5px;">'
                              f'<span style="width:96px;flex-shrink:0;text-align:right;color:var(--muted);">'
                              f'{esc(str(m.get("frame", "")))}</span>'
                              f'<span style="width:34px;flex-shrink:0;color:var(--muted);">{esc(tier_lbl)}</span>'
                              f'<span style="width:120px;flex-shrink:0;color:var(--ink);overflow:hidden;'
                              f'text-overflow:ellipsis;white-space:nowrap;">{esc(str(m.get("source", "")))}</span>'
                              f'<span style="flex:1;min-width:0;color:var(--ink-2);overflow:hidden;'
                              f'text-overflow:ellipsis;white-space:nowrap;">{esc(str(m.get("title", "")))}</span></div>')
                fr_ex += '</div>'
            fr_html = f"""
<div class="card"><div class="card-pad">
<div class="side-head">Фрейм-карта события <span class="sub">как поле называет одно и то же · ось «язык»</span></div>
<div class="side-body">
<div style="display:flex;gap:26px;align-items:baseline;margin-bottom:10px;flex-wrap:wrap;">
<div><span style="font-family:var(--serif-display);font-size:26px;font-weight:700;color:var(--accent);">{_p4(fr.get('divergence_share'))}</span> <span style="font-family:var(--sans);font-size:11.5px;color:var(--muted);">каскадов перепечаток названы в разных фреймах ({fr.get('divergent', 0)} из {fr.get('clusters', 0)})</span></div>
<div><span style="font-family:var(--serif-display);font-size:26px;font-weight:700;">{fr.get('tier_conflicts', 0)}</span> <span style="font-family:var(--sans);font-size:11.5px;color:var(--muted);">конфликтов уровней: официальный канал и агрегатор дали сюжету несовместимые фреймы</span></div>
<div><span style="font-family:var(--serif-display);font-size:26px;font-weight:700;">{fr.get('chp_vs_works', 0)}</span> <span style="font-family:var(--sans);font-size:11.5px;color:var(--muted);">контрастов «ЧП ↔ плановые работы»</span></div>
</div>
<div style="margin:0 0 6px;font-family:var(--sans);font-size:10.5px;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);">Фреймы недели · все сообщения</div>
{fr_rows}
<div style="margin:12px 0 6px;font-family:var(--sans);font-size:10.5px;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);">Кто в какой фрейм смотрит · доля внутри уровня</div>
<div style="overflow-x:auto;"><table class="tbl"><tr><th>Уровень</th>{fr_thead}</tr>{fr_trows}</table></div>
<div style="margin:12px 0 6px;font-family:var(--sans);font-size:10.5px;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);">Расхождения внутри каскадов</div>
{fr_ex or '<div class="note">Расходящихся каскадов за неделю нет.</div>'}
<div class="note"><b>Метод.</b> Фрейм — способ назвать событие: лексикон из 12 рамок (тревога, ЧП, жалоба, надзор, плановые работы, достижение, ритуал и визит, услуга и инструкция, статистика, интерактив, лайв, погода) плюс «нейтральная хроника» при отсутствии маркеров; доминанта — по числу совпадений в заголовке и лиде. Кластеры — уже посчитанная дедупликацией связность перепечаток, поэтому расхождение фреймов видно на одном и том же событии. <b>Что это значит.</b> Фреймы распределены по этажам поля: официальные каналы чаще подают сюжет как достижение или ритуал, агрегаторы — как ЧП и жалобу, редакции — как надзор и работы. Расхождение фреймов внутри одного каскада — измеримый след конфликта интересов; контраст «ЧП ↔ плановые работы» — его классическая форма{' (за неделю не зафиксирован)' if not fr.get('chp_vs_works') else f": {fr.get('chp_vs_works')} каскадов"}. <b>Границы.</b> Фрейм определяется лексиконом, а не смыслом: ирония и цитаты чужой рамки не распознаются; «нейтральная хроника» — остаточный класс, его доля показывает, сколько поля вообще не оценивает события.</div>
</div></div></div>
"""

        # ── 3) ИИ-след: шаблонность производства
        ai_html = ""
        if ait.get("n"):
            sig = ait.get("signals") or {}
            sig_rows = _bars4([(k, v, f"{v} сообщ. · {_p4(v / (ait.get('n') or 1))}")
                               for k, v in sig.items()], color="#6D6079")
            ai_tier_rows = ""
            for t in ("T1", "T2", "T3", "СМИ/подборка"):
                v = (ait.get("by_tier") or {}).get(t)
                if not v:
                    continue
                ai_tier_rows += (f'<tr><td>{esc(t)}</td><td style="text-align:right;">{v.get("n", 0)}</td>'
                                 f'<td style="text-align:right;">{_p4(v.get("any_share"))}</td>'
                                 f'<td style="text-align:right;">{_p4(v.get("strong_share"))}</td></tr>')
            ai_src_rows = "".join(
                f'<tr><td>{esc(s.get("source", ""))}</td><td style="text-align:right;">{s.get("n", 0)}</td>'
                f'<td style="text-align:right;">{_p4(s.get("share"))}</td></tr>'
                for s in (ait.get("by_source") or [])[:6])
            ai_ex = ""
            for e in (ait.get("examples") or [])[:3]:
                ai_ex += (f'<div style="display:flex;gap:12px;align-items:baseline;padding:5px 0;'
                          f'border-bottom:1px dashed var(--rule);font-size:13px;">'
                          f'<span style="flex:1;min-width:0;color:var(--ink);">{esc(e.get("title", ""))}</span>'
                          f'<span style="font-family:var(--sans);font-size:10.5px;color:var(--muted);'
                          f'white-space:nowrap;">{esc(str(e.get("source", "")))} · {esc(", ".join(e.get("signals") or []))}</span></div>')
            ai_html = f"""
<div class="card"><div class="card-pad">
<div class="side-head">ИИ-след и шаблонность производства <span class="sub">сколько текста собрано, а не написано · ось «труд»</span></div>
<div class="side-body">
<div style="display:flex;gap:26px;align-items:baseline;margin-bottom:10px;flex-wrap:wrap;">
<div><span style="font-family:var(--serif-display);font-size:26px;font-weight:700;color:var(--accent);">{_p4(ait.get('any_share'))}</span> <span style="font-family:var(--sans);font-size:11.5px;color:var(--muted);">потока несёт хотя бы один признак шаблона ({ait.get('any_n', 0)} из {ait.get('n', 0)}) — {esc(ait.get('share_any_verdict', '—'))}</span></div>
<div><span style="font-family:var(--serif-display);font-size:26px;font-weight:700;">{_p4(ait.get('strong_share'))}</span> <span style="font-family:var(--sans);font-size:11.5px;color:var(--muted);">с выраженным следом (два признака и более)</span></div>
<div><span style="font-family:var(--serif-display);font-size:26px;font-weight:700;">{ait.get('verbatim_items', 0)}</span> <span style="font-family:var(--sans);font-size:11.5px;color:var(--muted);">сообщений с дословными повторами чужого текста (общих групп предложений: {ait.get('verbatim_groups', 0)})</span></div>
</div>
{sig_rows}
<div class="grid2" style="margin-top:12px;">
<div><div style="margin:0 0 6px;font-family:var(--sans);font-size:10.5px;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);">По уровням</div>
<div style="overflow-x:auto;"><table class="tbl"><tr><th>Уровень</th><th style="text-align:right;">сообщ.</th><th style="text-align:right;">со следом</th><th style="text-align:right;">выраженный</th></tr>{ai_tier_rows}</table></div></div>
<div><div style="margin:0 0 6px;font-family:var(--sans);font-size:10.5px;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);">Источники с максимальной долей · n≥12</div>
<div style="overflow-x:auto;"><table class="tbl"><tr><th>Источник</th><th style="text-align:right;">сообщ.</th><th style="text-align:right;">со следом</th></tr>{ai_src_rows}</table></div></div>
</div>
<div style="margin:12px 0 6px;font-family:var(--sans);font-size:10.5px;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);">Примеры выраженного следа</div>
{ai_ex or '<div class="note">Примеров нет.</div>'}
<div class="note"><b>Метод.</b> Шесть независимых признаков: шаблонная концовка («Мы в Telegram | Мы в MAX», «Подписаться», ссылки t.me/max.ru), клише машинного текста («важно отметить», «в современном мире», «играет важную роль»), эмодзи-блок (≥5 эмодзи в лиде или ≥3 одинаковых), капс-заголовок, список-шаблон (≥3 маркера-буллета), дословный повтор (≥2 общих предложения длиной ≥40 знаков с другим источником — ловит копипаст пресс-релизов и синдицированный рерайт ниже порога дедупликации). Сообщение «со следом» — при одном признаке, «с выраженным» — при двух и более. <b>Важно.</b> Это не детектор авторства ИИ, а измерение шаблонности производства: признаки одинаково ловят машинную генерацию, потогонный рерайт и копипаст пресс-релизов. Клише машинного текста в региональном поле почти не встречаются — шаблонность здесь обеспечивает не генерация, а формуляр канала и дословное заимствование. Паспорт метрики требует ручной сверки с редакциями.</div>
</div></div></div>
"""

        # ── 4) устойчивость дедупликации
        dd_html = ""
        if dd.get("n_items"):
            sw = dd.get("sweep") or []
            sw_rows = ""
            for s in sw:
                cur = abs(s.get("threshold", 0) - (dd.get("threshold") or 0)) < 1e-9
                style = ' style="background:var(--paper-2);font-weight:700;"' if cur else ""
                sw_rows += (f'<tr{style}><td>{s.get("threshold"):.2f}{" ← текущий" if cur else ""}</td>'
                            f'<td style="text-align:right;">{s.get("clusters", 0)}</td>'
                            f'<td style="text-align:right;">{s.get("dups", 0)}</td>'
                            f'<td style="text-align:right;">{_p4(s.get("original_share"))}</td>'
                            f'<td style="text-align:right;">{s.get("max_size", 0)}</td></tr>')
            dd_smp = ""
            for s in (dd.get("sample") or [])[:6]:
                flags = []
                if s.get("antagonistic"):
                    flags.append("режим введён ↔ снят")
                if s.get("same_source"):
                    flags.append("один источник")
                flag_txt = f' <span style="color:var(--accent);">· {esc(", ".join(flags))}</span>' if flags else ""
                dd_smp += (f'<div style="padding:6px 0;border-bottom:1px dashed var(--rule);font-size:12.5px;">'
                           f'<div style="font-family:var(--sans);font-size:10.5px;color:var(--muted);margin-bottom:2px;">'
                           f'Жаккар {s.get("jaccard")}{" · склеены" if s.get("would_merge") else " · не склеены"}{flag_txt}</div>'
                           f'<div style="color:var(--ink);"><b>{esc((s.get("a") or {}).get("source", ""))}:</b> '
                           f'{esc((s.get("a") or {}).get("title", ""))}</div>'
                           f'<div style="color:var(--ink-2);"><b>{esc((s.get("b") or {}).get("source", ""))}:</b> '
                           f'{esc((s.get("b") or {}).get("title", ""))}</div></div>')
            ant_ex = ""
            for e in (dd.get("antagonistic_examples") or [])[:2]:
                ant_ex += (f'<div style="padding:6px 0;border-bottom:1px dashed var(--rule);font-size:12.5px;">'
                           f'<div style="color:var(--ink);"><b>{esc((e.get("a") or {}).get("source", ""))}:</b> '
                           f'{esc((e.get("a") or {}).get("title", ""))}</div>'
                           f'<div style="color:var(--accent);"><b>{esc((e.get("b") or {}).get("source", ""))}:</b> '
                           f'{esc((e.get("b") or {}).get("title", ""))}</div></div>')
            rng = dd.get("original_range") or [None, None]
            dd_dups = next((s.get("dups", 0) for s in sw
                            if abs(s.get("threshold", 0) - (dd.get("threshold") or 0)) < 1e-9), 0)
            dd_html = f"""
<div class="card"><div class="card-pad">
<div class="side-head">Устойчивость дедупликации <span class="sub">насколько можно верить цифре «оригинальности» · ось «методика»</span></div>
<div class="side-body">
<div style="display:flex;gap:26px;align-items:baseline;margin-bottom:10px;flex-wrap:wrap;">
<div><span style="font-family:var(--serif-display);font-size:26px;font-weight:700;">{_p4(dd.get('original_share'))}</span> <span style="font-family:var(--sans);font-size:11.5px;color:var(--muted);">оригинальность недели при пороге Жаккара {dd.get('threshold')} (пересчёт, {dd.get('n_items', 0)} сообщ.)</span></div>
<div><span style="font-family:var(--serif-display);font-size:26px;font-weight:700;color:var(--accent);">±{dd.get('spread_pp', 0) / 2:.1f} п.п.</span> <span style="font-family:var(--sans);font-size:11.5px;color:var(--muted);">чувствительность к порогу: {_p4(rng[0])}…{_p4(rng[1])} на порогах 0.30–0.60</span></div>
<div><span style="font-family:var(--serif-display);font-size:26px;font-weight:700;">{sum((dd.get('blocked_by_guards') or {}).values())}</span> <span style="font-family:var(--sans);font-size:11.5px;color:var(--muted);">склеек заблокировано охранными правилами; остаточных дефектов {dd.get('suspicious_dups', 0)} из {dd_dups} дублей</span></div>
<div><span style="font-family:var(--serif-display);font-size:26px;font-weight:700;">{_p4(dd.get('corrected_original_share'))}</span> <span style="font-family:var(--sans);font-size:11.5px;color:var(--muted);">оригинальность, если не склеивать и повторы своего канала</span></div>
</div>
<div class="grid2">
<div><div style="margin:0 0 6px;font-family:var(--sans);font-size:10.5px;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);">Пороговый эксперимент</div>
<div style="overflow-x:auto;"><table class="tbl"><tr><th>Порог</th><th style="text-align:right;">кластеров</th><th style="text-align:right;">дублей</th><th style="text-align:right;">оригинальность</th><th style="text-align:right;">макс. кластер</th></tr>{sw_rows}</table></div></div>
<div><div style="margin:0 0 6px;font-family:var(--sans);font-size:10.5px;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);">Охранные правила dedup.py: что заблокировано на этой неделе</div>
{_bars4([('заблокировано охранными правилами', sum((dd.get('blocked_by_guards') or {}).values()), ' · '.join(f'{k} {v}' for k, v in (dd.get('blocked_by_guards') or {}).items()) or 'нет'), ('остаточный брак (длинные кластеры)', dd.get('suspicious_dups', 0), f"{dd.get('suspicious_dups', 0)} дублей · дословных повторов {dd.get('episode_verbatim_dups', 0)}"), ('остаточный антагонизм', dd.get('antagonistic_dups', 0), f"{dd.get('antagonistic_dups', 0)} дублей"), ('повтор своего канала (склеен намеренно)', dd.get('same_source_dups', 0), f"{dd.get('same_source_dups', 0)} дублей · вне каскадов")], color='#B4795A')}
<div style="font-family:var(--sans);font-size:11.5px;color:var(--muted);margin-top:6px;">Медианная жизнь кластера — {dd.get('median_span_h')} ч; пограничных пар (±0.07 от порога) — {dd.get('borderline_pairs', 0)}.</div>
{ant_ex}</div>
</div>
<div style="margin:12px 0 6px;font-family:var(--sans);font-size:10.5px;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);">Контрольная выборка пограничных пар — на ручную верификацию</div>
{dd_smp or '<div class="note">Пограничных пар нет.</div>'}
<div class="note"><b>Метод.</b> Одни и те же пары недели пересчитаны при порогах Жаккара 0.30–0.60 (в конвейере — {dd.get('threshold')} из config.json), в двух режимах: с охранными правилами dedup.py и без них — видна и цена выбора порога, и эффект правил. <b>Охранные правила (включены 15.09 по итогам этой метрики).</b> (1) Антагонистичные формуляры не склеиваются никогда: «Ракетная опасность» и «Снят режим „Ракетная опасность“» — противоположные сообщения, а не перепечатки. (2) Служебные формуляры (оповещения о режимах, прогноз погоды) склеиваются только в пределах {(dd.get('policy') or {}).get('dedup_service_span_h', 6)} ч — текст у них идентичен сутки за сутками. (3) Обычные материалы — в пределах {(dd.get('policy') or {}).get('dedup_max_span_h', 24)} ч (медианная жизнь каскада — часы), кроме дословных повторов с Жаккаром ≥ {(dd.get('policy') or {}).get('dedup_verbatim_jaccard', 0.85)}. (4) Повтор внутри собственного <b>издания</b> остаётся склеенным ради чистоты ленты, но помечается <code>same_source</code> и не попадает ни в «🔁 также сообщили», ни в каскады: в метриках считается <code>cluster_src</code> — число независимых изданий. Издание — не канал: RSS ulpressa.ru и Telegram @ulpressa (одно юрлицо, ООО «Симбирск-Паблисити»), сайт администрации Ульяновска и @ulmeria (одна пресс-служба), @ulgovru и @Russkih_Aleksey (одна пресс-служба исполнительной власти) считаются одним источником — иначе перепечатка своего же релиза в свой же канал выглядела бы как независимое подтверждение. Карта изданий — поле <code>outlet</code> в <code>sources_registry.json</code> (outlets.py); конкурирующие каналы одного города («Типичный Димитровград» и «Информационный Димитровград» — разные админы) остаются разными источниками. <b>Вывод недели.</b> {esc(dd.get('verdict', '—'))}. Остаточные дефекты (длинные кластеры, антагонизм) после включения правил должны держаться около нуля — блок теперь работает как контроль качества, а не как описание брака. Контрольная выборка пограничных пар (±0.07 от порога) — для ручной верификации редакцией.</div>
</div></div></div>
"""

        w4_html = f"""
<div class="sec-head"><h2>Волна 4: язык, труд и методика</h2><div class="line"></div>
<div class="badge"><a href="projects/plans.html#metrics" style="color:var(--accent);">план внедрения →</a> · метрики подключены 15.09 · выборка: {ag.get('n') or ait.get('n') or 0} сообщения недели</div></div>
{ag_html}
<div class="grid2">
{fr_html}
{ai_html}
</div>
{dd_html}
"""

    ts = info.get("tone_series") or []
    tone_spark = sparkline([(t.get("score") or 0) for t in ts], w=300, h=56, color="#4a7fb5") if ts else ""
    tone_days = "".join(f"<span style='font-size:10px;color:var(--muted);'>{t['date'][8:10]}</span> " for t in ts[-7:])

    return f"""<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Инфопространство — сквозное исследование · {cfg['brand']}</title>
<link rel="icon" type="image/png" href="assets/logo_gudok.png"><style>{CSS}</style></head><body>
<header class="masthead"><div class="mast-inner">
<div class="mast-side">Информационно-аналитическое издание<br>марксистской группы «Победа»</div>
<div class="mast-title">ГУДОК<span>.</span></div>
<div class="mast-side mast-side--right">Исследование инфопространства<br>период: 7 дней
<div class="mast-actions">{THEME_BTN}</div></div>
</div></header>
{render_nav(cfg, "projects", "", subnav=subnav_projects("", "infospace"))}

<div class="page">

<div class="kpi-grid" style="grid-template-columns:repeat(5,1fr);margin-bottom:6px;">
<div class="kpi"><div class="num">{week}</div><div class="lbl">сообщений за 7 дней</div></div>
<div class="kpi green"><div class="num">{orig_pct}%</div><div class="lbl">оригинальных (не перепечаток)</div></div>
<div class="kpi violet"><div class="num">{len(cascades) and cascades[0]['size'] or 0}<small> макс.</small></div><div class="lbl">крупнейший каскад недели</div></div>
<div class="kpi gold"><div class="num">{fed_pct}%</div><div class="lbl">федеральное эхо (не про регион)</div></div>
<div class="kpi red"><div class="num">{len(silent)}<small> + {len(low)}</small></div><div class="lbl">молчащих и полунемых муниципалитетов</div></div>
</div>
<div class="note" style="margin-bottom:18px;">Раздел обновляется каждым прогоном конвейера — это не разовый отчёт, а непрерывное наблюдение за устройством регионального инфополя: кто производит новости, кто их тиражирует, какие сюжеты побеждают, кого не слышно. Данные — {esc(str(info.get('generated_local','')))}, база: {len(store)} записей.
<b>Что измерим дальше и как:</b> реестр из 32 метрик-кандидатов, паспорта метрик, волны внедрения
и открытые пункты плана развития — <a href="projects/plans.html#metrics" style="color:var(--accent);font-weight:700;">на странице «Планы и методы» →</a></div>

<div class="sec-head"><h2>Кто задаёт повестку</h2><div class="line"></div>
<div class="badge">первичность в каскадах перепечаток</div></div>
<div class="grid2">
<div class="card"><div class="card-pad">
{bar_rows(setters, color="#2f80ed")}
<div class="note">Считаются материалы, ставшие первичными в кластерах из 2+ <b>изданий</b> (дедупликация). Каналы одной редакции объединены: «Улпресса» — это RSS ulpressa.ru и Telegram @ulpressa (ООО «Симбирск-Паблисити»), «Губернатор и Правительство Ульяновской области» — @ulgovru и @Russkih_Aleksey (одна пресс-служба). Перепечатка своего материала в свой канал сеттером повестки не считается.</div></div></div>
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
{w1_html}{w2_html}{w3_html}{w4_html}
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
{footer.render_footer('')}
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
        side_html += f"""<div class="pm-item"><b>{esc(clip_words(m['title'],120))}</b>
<span>{esc(clip_sentences((m.get('text') or ''),220))}</span>
<i>{cats.get(m.get('category'), {}).get('name', '')} · {dt.strftime('%d.%m %H:%M') if dt else ''} · {esc(m.get('source', ''))}</i></div>"""

    by_cat = {}
    lead_ids = {m["id"] for m in leads}
    for it in window:
        if it["id"] in lead_ids:
            continue
        by_cat.setdefault(it.get("category", "society"), []).append(it)
    rubrics = ""
    for c in cfg["categories"]:
        items = [it for it in by_cat.get(c["id"], []) if not is_alert(it)]
        if not items:
            continue
        rows = "".join(
            f"""<div class="pm-item"><b>{esc(clip_words(it['title'],110))}</b>
<span>{esc(clip_sentences((it.get('text') or ''),160))}</span>
<i>{(local_dt(it.get('published')) or now):%H:%M} · {esc(it.get('source', ''))}</i></div>"""
            for it in items[:4])
        rubrics += f'<div class="pm-h3">{c["icon"]} {esc(c["name"])}</div>{rows}'

    tomorrow = day + timedelta(days=1)
    af = [e for e in (an.get("calendar") or []) if e.get("date") in (day.isoformat(), tomorrow.isoformat())][:8]
    af_html = "".join(
        f'<li><b>{e["date"][8:10]}.{e["date"][5:7]} {esc(e.get("time") or "—")}</b> — {esc(clip_words(e["title"],95))}</li>'
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
<style>{CSS}{PRINT_CSS}</style></head>
<body class="print-mode">
<div class="pm-toolbar">
<a href="{digest_link(date_str)}">← Электронный выпуск</a>
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
<div class="pm-deck">{esc(clip_sentences(lead.get('text') or '', 260)) if lead else ''}</div>

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
<div>Набрано и выпущено автоматически: мониторинг {sum(1 for c in cfg.get('telegram_channels', []) if c.get('enabled'))} Telegram-каналов и {sum(1 for c in cfg.get('rss_sources', []) if c.get('enabled', True))} RSS-лент, {sum(1 for c in cfg.get('web_sources', []) or [] if c.get('enabled', True))} сайт(ов) органов власти; колонку редактора готовит ассистент.</div>
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
        if is_alert(it) or is_promo(it):
            continue  # уведомления о режимах и анонсы — не сюжеты
        mem = members.get(it["id"], [])
        size = len(mem) + 1
        views = it.get("views") or 0
        if size < 2 and views < 3000:
            continue
        # сюжет = содержательная тема с независимым освещением:
        # ≥3 публикаций из ≥2 источников ИЛИ широкий охват. Репост-каскад
        # одного канала и уведомления о режимах сюжетом не считаются.
        _srcs = {outlets.outlet_key(it)} | {outlets.outlet_key(m) for m in mem}
        if (size < 3 or len(_srcs) < 2) and views < 8000:
            continue
        days = sorted([pdate(it)] + [pdate(m) for m in mem])
        cnt = {}
        for d in days:
            cnt[d] = cnt.get(d, 0) + 1
        peak = max(cnt, key=lambda d: cnt[d])
        srcs = {outlets.outlet(it)} | {outlets.outlet(m) for m in mem}
        t_first = sentiment_of(f"{it.get('title','')} {(it.get('text') or '')[:200]}")[0]
        last_m = sorted(mem, key=lambda m: pdate(m))[-1] if mem else it
        t_last = sentiment_of(f"{last_m.get('title','')} {(last_m.get('text') or '')[:200]}")[0]
        status = "затух" if days[-1] < end - timedelta(days=1) else ("в развитии" if days[-1] >= end else "пик пройден")
        arcs.append({
            "title": nice_title(it, 110), "url": it.get("url") or "", "src": outlets.outlet(it),
            "first": days[0], "peak": peak, "last": days[-1], "size": size, "views": views,
            "srcs": srcs, "t1": t_first, "t2": t_last, "status": status, "days": sorted(set(days)),
        })
    arcs.sort(key=lambda a: -((a["views"] or 0) + a["size"] * 2000))
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
            f'<div class="tl-txt"><a href="{esc(e.get("url") or "#")}" target="_blank" rel="noopener">{esc(clip_words(e["title"],80))}</a></div></div>'
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
        f'<div class="tl-txt"><a href="{esc(it.get("url") or "#")}" target="_blank" rel="noopener">{esc(clip_words(it["title"],80))}</a></div></div>'
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
<div class="now-line">{esc(clip_words((cfg.get("enterprise_note") or ""),220))}</div></div>
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
<header class="masthead"><div class="mast-inner">
<div class="mast-side">Информационно-аналитическое издание<br>марксистской группы «Победа»</div>
<div class="mast-title">ГУДОК<span>.</span></div>
<div class="mast-side mast-side--right">Аналитика недели<br>выпусков: {len(weeks)}
<div class="mast-actions">{THEME_BTN}</div></div>
</div></header>
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
{footer.render_footer('')}
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
    src_c = Counter(outlets.outlet(it) for it in all_m)
    top3 = sum(n for _, n in src_c.most_common(3))
    conc = round(top3 / volume * 100) if volume else 0
    def csrc(it):
        """Независимых источников в каскаде (cluster_src после правок dedup 15.09)."""
        return it.get("cluster_src") or it.get("cluster") or 0

    casc = sorted([it for it in prim if csrc(it) >= 2], key=lambda x: -csrc(x))[:6]
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
    muni_src = {outlets.norm(outlets.resolve_raw(x)) for x in (cfg.get("municipal_sources") or [])}
    for name, pat in (cfg.get("municipalities") or {}).items():
        rx = re.compile(pat, re.I)
        n = own = 0
        for it in all_m:
            if rx.search(it.get("title", "") or ""):
                n += 1
                if outlets.outlet_key(it) in muni_src:
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
        f'<div class="af-mini"><div class="cal-badge" style="background:var(--red);"><b>×{csrc(c)}</b><span>ист.</span></div>'
        f'<div style="flex:1;"><a href="{esc(c.get("url") or "#")}" target="_blank" rel="noopener" style="font-size:13px;font-weight:700;color:var(--navy);">{esc(clip_words(c["title"],100))}</a>'
        f'<div style="font-size:11.3px;color:var(--muted);">{(pdate(c) or now):%d.%m} · {esc(c.get("source",""))}</div></div></div>'
        for c in casc) or '<div class="now-line">Каскадов за месяц не зафиксировано.</div>'
    def _muni_own(own):
        return "✅ " + str(own) if own else '<span style="color:#b02a2f;font-weight:700;">нет</span>'

    muni_tbl = "".join(
        f'<tr><td><b>{esc(nm)}</b></td><td>{n}</td><td>{_muni_own(own)}</td></tr>'
        for nm, n, own in muni_rows[:14]) or '<tr><td colspan="3">Нет данных.</td></tr>'
    chron_rows = "".join(
        f'<div class="af-mini"><div class="cal-badge"><b>{(pdate(c) or now):%d}</b><span>{(pdate(c) or now):%b}</span></div>'
        f'<div style="flex:1;"><a href="{esc(c.get("url") or "#")}" target="_blank" rel="noopener" style="font-size:13px;font-weight:700;color:var(--navy);">{esc(clip_words(c["title"],100))}</a>'
        f'<div style="font-size:11.3px;color:var(--muted);">👁 {fmt_views(c["views"])} · {esc(c.get("source",""))}</div></div></div>'
        for c in chron)
    concl = [
        f"Объём инфопотока за месяц: {volume} сообщений, оригинальных {orig}%.",
        f"Концентрация источников: топ-3 дают {conc}% потока.",
        f"Средний тон месяца: {tone_avg:+.2f}." + (" Повестка эмоционально умеренная." if abs(tone_avg) < 0.2 else ""),
        f"Крупнейший каскад: ×{csrc(casc[0])} независимых источников («{casc[0]['title'][:60]}»)." if casc else "Каскадов нет.",
        f"Территорий с упоминаниями: {len(muni_rows)} из {len(cfg.get('municipalities') or {})}; "
        f"свой голос — у {sum(1 for _, _, o in muni_rows if o)}.",
    ]
    stamp = '<span class="wk-stamp">завершён</span>' if done else '<span class="wk-stamp wip">готовится</span>'
    return f"""<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Месячный отчёт {MONTHS_RU_GEN[mo-1]} {y} — {cfg['brand']}</title>
<link rel="icon" type="image/png" href="../assets/logo_gudok.png">
<style>{CSS}{INDEX_CSS}</style></head><body>
<header class="masthead"><div class="mast-inner">
<div class="mast-side">Информационно-аналитическое издание<br>марксистской группы «Победа»</div>
<div class="mast-title">ГУДОК<span>.</span></div>
<div class="mast-side mast-side--right">Месячный отчёт<br>период {start:%d.%m}–{end:%d.%m}.{end:%y}
<div class="mast-actions">{THEME_BTN}</div></div>
</div></header>
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
<div class="kpi red"><div class="num">{csrc(casc[0]) if casc else 0}</div><div class="lbl">макс. каскад (независимых источников)</div></div>
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
{footer.render_footer('../')}
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
<header class="masthead"><div class="mast-inner">
<div class="mast-side">Информационно-аналитическое издание<br>марксистской группы «Победа»</div>
<div class="mast-title">ГУДОК<span>.</span></div>
<div class="mast-side mast-side--right">Месячные отчёты<br>отчётов: {len(months)}
<div class="mast-actions">{THEME_BTN}</div></div>
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
{footer.render_footer('')}
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
<b style="font-size:14.5px;color:var(--navy);flex:1;">{esc(clip_words(a['title'],110))}</b>
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
<header class="masthead"><div class="mast-inner">
<div class="mast-side">Информационно-аналитическое издание<br>марксистской группы «Победа»</div>
<div class="mast-title">ГУДОК<span>.</span></div>
<div class="mast-side mast-side--right">Недельник {start:%d.%m}–{end:%d.%m}.{end:%y}<br>сюжетных дуг: {len(arcs)}
<div class="mast-actions">{THEME_BTN}</div></div>
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
{footer.render_footer('../')}
</body></html>"""


# ------------------------------------------------------------------ archive
def render_archive(cfg, trends, store, status):
    """Архив издания: календарь выпусков + реестр + недельники/месячные + проекты."""
    now = datetime.now(UTC4)
    today = now.date()
    nav_html = render_nav(cfg, "archive", "")
    digests = sorted(glob.glob(os.path.join(DIGESTS, "digest_*.html")))
    dset = {os.path.basename(d)[7:17] for d in digests}
    weeks = sorted(glob.glob(os.path.join(BASE, "weekly", "week_*.html")))
    month_files = sorted(glob.glob(os.path.join(BASE, "monthly", "month_*.html")))
    launch = None
    try:
        launch = datetime.strptime(cfg.get("launch_date", ""), "%Y-%m-%d").date()
    except ValueError:
        pass

    # материалов по дням (без дублей перепечаток)
    per_day = Counter()
    for it in store:
        if it.get("dup_of"):
            continue
        dt = local_dt(it.get("published"))
        if dt:
            per_day[dt.date().isoformat()] += 1

    MON_RU = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
              "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]
    WD_S = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
    WD_F = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]

    # ── календарь: по блоку на каждый месяц, где есть выпуски (новые сверху) ──
    months = sorted({d[:7] for d in dset} | {os.path.basename(m)[6:13] for m in month_files}, reverse=True)
    cal_html = ""
    for ym in months:
        y, mo = map(int, ym.split("-"))
        first = datetime(y, mo, 1, tzinfo=UTC4).date()
        last = (datetime(y + 1, 1, 1, tzinfo=UTC4).date() if mo == 12
                else datetime(y, mo + 1, 1, tzinfo=UTC4).date()) - timedelta(days=1)
        cells = "".join(f'<span class="cal-h">{w}</span>' for w in WD_S)
        d = first
        cells += '<span class="cal-cell empty"></span>' * first.weekday()
        while d <= last:
            iso = d.isoformat()
            if iso in dset:
                num, test = digest_number(cfg, iso)
                lbl = f"№{num}" + (" 🧪" if test else "")
                cls = "cal-cell has" + (" today" if d == today else "")
                cells += (f'<a class="{cls}" href="digests/digest_{iso}.html" '
                          f'title="Выпуск {lbl} от {d:%d.%m.%Y} · материалов: {per_day.get(iso, 0)}">'
                          f'<span class="cal-d">{d.day}</span><span class="cal-n">{lbl}</span></a>')
            elif launch and d < launch:
                cells += f'<span class="cal-cell pre" title="до запуска издания"><span class="cal-d">{d.day}</span></span>'
            elif d > today:
                cells += f'<span class="cal-cell off"><span class="cal-d">{d.day}</span></span>'
            else:
                cells += f'<span class="cal-cell miss" title="{d:%d.%m} — выпуска нет"><span class="cal-d">{d.day}</span></span>'
            d += timedelta(days=1)
        mlink = (f' · <a class="cal-mlink" href="monthly/month_{ym}.html">отчёт за месяц</a>'
                 if os.path.exists(os.path.join(BASE, f"monthly/month_{ym}.html")) else "")
        cal_html += (f'<div class="cal-month"><div class="cal-title">{MON_RU[mo - 1]} {y}{mlink}</div>'
                     f'<div class="cal">{cells}</div></div>')

    # ── реестр выпусков: новые сверху ──
    reg_rows = ""
    for iso in sorted(dset, reverse=True):
        d = datetime.strptime(iso, "%Y-%m-%d").date()
        num, test = digest_number(cfg, iso)
        n_items = per_day.get(iso, 0)
        ex = os.path.exists(os.path.join(DIGESTS, f"exec_{iso}.html"))
        pr = os.path.exists(os.path.join(DIGESTS, f"print_{iso}.html"))
        links = [f'<a href="digests/digest_{iso}.html">выпуск</a>']
        links.append(f'<a href="digests/exec_{iso}.html">руководителю</a>' if ex else '<span class="na">руководителю —</span>')
        links.append(f'<a href="digests/print_{iso}.html">печать</a>' if pr else '<span class="na">печать —</span>')
        badge = ' <span class="reg-test">🧪 тестовый</span>' if test else ""
        live = (' <a class="reg-live" href="digests/today.html">живая страница →</a>'
                if (iso == today.isoformat() and iso in dset) else "")
        reg_rows += (f'<tr><td class="num">№{num}{badge}</td>'
                     f'<td>{WD_F[d.weekday()]}, {d:%d.%m.%Y}{live}</td>'
                     f'<td class="cnt">{n_items}</td>'
                     f'<td class="lnk"> · '.join(links) + '</td></tr>')

    # ── недельники и месячные ──
    wk_items = ""
    for w in sorted(weeks, reverse=True):
        b = os.path.basename(w)[:-5]
        parts = b.split("_")
        if len(parts) >= 3:
            nn = parts[1].lstrip("0") or "0"
            st = datetime.strptime(parts[2], "%Y-%m-%d").date()
            en = datetime.strptime(parts[3], "%Y-%m-%d").date()
            wk_items += (f'<li><a href="weekly/{os.path.basename(w)}">Недельник №{nn}</a>'
                         f'<span class="per">{st:%d.%m}–{en:%d.%m.%Y}</span></li>')
    wk_items = wk_items or '<li class="na">недельники появятся после первой завершённой недели</li>'
    mo_items = ""
    for m in month_files:
        ym = os.path.basename(m)[6:13]
        y, mo = map(int, ym.split("-"))
        mo_items += f'<li><a href="monthly/month_{ym}.html">{MON_RU[mo - 1]} {y}</a><span class="per">все метрики месяца</span></li>'
    mo_items = mo_items or '<li class="na">первый отчёт — после завершения сентября</li>'

    # ── проекты и спецвыпуски ──
    proj = [("projects/elections_2026.html", "Выборы-2026", "спецвыпуск: губернатор, Госдума, довыборы в ЗСО"),
            ("projects/goszakupki.html", "Госзакупки", "аналитика закупок региона"),
            ("infospace.html", "Инфопространство", "сеттеры повестки, каскады, тон, территории"),
            ("methods.html", "Методы", "реестр из 36 методик с паспортами · идеология и гегемония · техконтур · стенд"),
            ("projects/dossier.html", "Досье (прототип)", "действующие лица инфополя: упоминания, тон, дуги сюжетов · демо-данные"),
            ("projects/plans.html", "Планы", "треки планов · реестр из 32 метрик · паспорта · конвейер внедрения"),
            ("afisha.html", "Афиша", "культурные события области, автоизвлечение")]
    proj_cards = "".join(
        f'<a class="proj-card" href="{href}"><b>{esc(name)}</b><span>{esc(desc)}</span></a>'
        for href, name, desc in proj if os.path.exists(os.path.join(BASE, href)))
    special_files = sorted(glob.glob(os.path.join(SPECIAL, "*.html")))
    proj_cards += "".join(
        f'<a class="proj-card" href="special/{os.path.basename(s)}"><b>{esc(os.path.basename(s)[:-5].replace("_", " "))}</b><span>ручной спецвыпуск</span></a>'
        for s in special_files)

    n_total = sum(per_day.values())
    launch_txt = f"{launch:%d.%m.%Y}" if launch else "11.09.2026"
    return f"""<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Архив — {cfg['brand']}</title>
<link rel="icon" type="image/png" href="assets/logo_gudok.png"><style>{CSS}{INDEX_CSS}
.cal-month{{margin-bottom:20px;}}
.cal-title{{font-family:var(--serif-display);font-weight:600;font-size:18px;color:var(--ink);margin-bottom:8px;}}
.cal-mlink{{font-family:var(--sans);font-size:11px;font-weight:500;color:var(--muted);border-bottom:1px solid var(--rule);}}
.cal-mlink:hover{{color:var(--accent);border-color:var(--accent);}}
.cal{{display:grid;grid-template-columns:repeat(7,minmax(38px,1fr));gap:4px;}}
.cal-h{{font-family:var(--sans);font-size:10px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);text-align:center;padding:2px 0 6px;}}
.cal-cell{{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:1px;min-height:50px;border:1px solid var(--rule);background:var(--paper-2);text-decoration:none;}}
.cal-d{{font-family:var(--serif-body);font-size:15px;font-weight:600;color:var(--ink);line-height:1.1;}}
.cal-n{{font-family:var(--sans);font-size:9.5px;font-weight:700;color:var(--accent);}}
a.cal-cell.has{{background:var(--paper);border-color:var(--ink);}}
a.cal-cell.has:hover{{border-color:var(--accent);}}
a.cal-cell.has:hover .cal-d{{color:var(--accent);}}
.cal-cell.today{{box-shadow:inset 0 0 0 2px var(--accent);}}
.cal-cell.pre{{border:none;background:none;opacity:.3;}}
.cal-cell.off{{opacity:.4;}}
.cal-cell.miss .cal-d{{color:var(--muted);}}
.cal-cell.empty{{border:none;background:none;}}
.reg{{width:100%;border-collapse:collapse;font-size:13px;}}
.reg th{{font-family:var(--sans);font-size:10px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);text-align:left;border-bottom:2px solid var(--ink);padding:6px 10px 6px 0;}}
.reg td{{border-bottom:1px solid var(--rule);padding:9px 10px 9px 0;vertical-align:baseline;}}
.reg .num{{font-family:var(--serif-display);font-size:17px;font-weight:700;white-space:nowrap;color:var(--ink);}}
.reg-test{{font-family:var(--sans);font-size:9.5px;font-weight:700;color:var(--muted);}}
.reg-live{{font-family:var(--sans);font-size:11px;color:var(--accent);white-space:nowrap;}}
.reg .cnt{{font-family:var(--sans);font-size:12.5px;color:var(--ink-2);white-space:nowrap;}}
.reg .lnk{{font-family:var(--sans);font-size:12px;white-space:nowrap;}}
.reg .lnk a{{color:var(--ink-2);border-bottom:1px solid var(--rule);}}
.reg .lnk a:hover{{color:var(--accent);border-color:var(--accent);}}
.reg .na{{color:var(--muted);opacity:.55;}}
.arch-grid{{display:grid;grid-template-columns:minmax(0,auto) minmax(0,1fr);gap:36px;align-items:start;}}
.per-list{{list-style:none;padding:0;margin:0;}}
.per-list li{{display:flex;justify-content:space-between;align-items:baseline;gap:12px;padding:8px 0;border-bottom:1px dashed var(--rule);font-size:14px;}}
.per-list li:last-child{{border-bottom:none;}}
.per-list a{{font-family:var(--serif-body);font-weight:600;color:var(--ink);}}
.per-list a:hover{{color:var(--accent);}}
.per-list .per{{font-family:var(--sans);font-size:11.5px;color:var(--muted);white-space:nowrap;}}
.per-list .na{{color:var(--muted);font-size:13px;}}
.proj-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px;}}
.proj-card{{border:1px solid var(--rule);border-top:2px solid var(--ink);background:var(--paper-2);padding:12px 14px;display:flex;flex-direction:column;gap:4px;}}
.proj-card:hover{{border-color:var(--accent);border-top-color:var(--accent);}}
.proj-card b{{font-family:var(--serif-body);font-size:15px;color:var(--ink);}}
.proj-card:hover b{{color:var(--accent);}}
.proj-card span{{font-family:var(--sans);font-size:11.5px;color:var(--muted);line-height:1.45;}}
@media (max-width:900px){{.arch-grid{{grid-template-columns:1fr;}}}}
</style></head><body>
<header class="masthead"><div class="mast-inner">
<div class="mast-side">Информационно-аналитическое издание<br>марксистской группы «Победа»</div>
<div class="mast-title">ГУДОК<span>.</span></div>
<div class="mast-side mast-side--right">Архив издания<br>выходит с {launch_txt}
<div class="mast-actions">{THEME_BTN}</div></div>
</div></header>
{nav_html}
<div class="page">

<div class="sec-head"><h2>Выпуски по дням</h2><div class="line"></div>
<div class="badge"><a href="digests/today.html">Живая страница «Сегодня» →</a></div></div>
<div class="arch-grid">
<div>{cal_html}
<div class="note" style="font-size:12px;color:var(--muted);max-width:420px;">Клик по дню — выпуск за закрытые сутки. 🧪 — тестовый номер. Обведённый день — текущие сутки (живая страница). Материалов в базе всего: {n_total}.</div>
</div>
<div>
<table class="reg"><tr><th>Выпуск</th><th>Сутки</th><th>Материалов</th><th>Смотреть</th></tr>
{reg_rows}</table>
</div>
</div>

<div class="sec-head"><h2>Периодические отчёты</h2><div class="line"></div>
<div class="badge"><a href="weekly.html">все недели</a> · <a href="monthly.html">все месяцы</a></div></div>
<div class="arch-grid">
<div><h3 style="font-family:var(--sans);font-size:11px;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);margin:0 0 6px;">Недельники · сюжетные дуги</h3>
<ul class="per-list">{wk_items}</ul></div>
<div><h3 style="font-family:var(--sans);font-size:11px;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);margin:0 0 6px;">Месячные отчёты · метрики</h3>
<ul class="per-list">{mo_items}</ul></div>
</div>

<div class="sec-head"><h2>Проекты и спецвыпуски</h2><div class="line"></div></div>
<div class="proj-grid">{proj_cards}</div>

</div>
{footer.render_footer('')}
</body></html>"""



# ------------------------------------------------------------------ index
def render_index(cfg, trends, store, status, digest_files, special_files):
    """Первая полоса v3: hero → самое читаемое → карточки → фича → мнения → периодичности."""
    now = datetime.now(UTC4)
    day = now.date()
    an = load_json(os.path.join(DATA, "analytics.json")) or {}
    nav_html = render_nav(cfg, "index", "", subnav="")
    cats = {c["id"]: c for c in cfg["categories"]}

    win_start = datetime.combine(day, datetime.min.time(), tzinfo=UTC4) - timedelta(hours=30)
    window = [it for it in store if not it.get("dup_of")
              and local_dt(it.get("published")) and local_dt(it["published"]) >= win_start]
    if len(window) < 6:
        win_start -= timedelta(days=2)
        window = [it for it in store if not it.get("dup_of")
                  and local_dt(it.get("published")) and win_start <= local_dt(it["published"])]
    pool = [it for it in window if is_regional(it) and it.get("category") != "security"
            and not is_alert(it)] or window
    shown = ShownIds()
    lead = pick_hero(pool, trends, now, cfg)
    if lead:
        shown.add(lead)
    n24 = (trends or {}).get("counts", {}).get("last24h", 0)
    dnum, dtest = digest_number(cfg, day)
    weather = fetch_weather()
    latest_digest = os.path.basename(digest_files[-1]) if digest_files else "today.html"
    if latest_digest != f"digest_{day:%Y-%m-%d}.html" and os.path.exists(os.path.join(DIGESTS, "today.html")):
        # текущие сутки ещё не закрыты: датированного выпуска нет, свежий — на живой странице
        latest_digest = "today.html"

    def take_first(candidates, k):
        """Блок набирается из ещё не показанных на полосе; при нехватке — дозаполнение."""
        out = []
        for it in candidates:
            if shown.first(it):
                out.append(it)
            if len(out) >= k:
                break
        for it in candidates:
            if len(out) >= k:
                break
            if it not in out:
                out.append(it)
                shown.add(it)
        return out

    # алерт-полоса: активные уведомления безопасности (tier-1/2)
    alert_pool = sorted([it for it in window if is_alert(it)
                         and it.get("tier") in (1, 2)],
                        key=lambda x: x.get("published") or "", reverse=True)
    alerts = []
    for it in alert_pool:
        pub = local_dt(it.get("published"))
        if not pub or (now - pub).total_seconds() / 3600 > 24:
            continue
        blob = (it.get("title") or "") + " " + (it.get("text") or "")[:200]
        if any(k in (blob or "").lower() for k in ("отмен", "снят", "заверш", "режим снят")):
            continue
        alerts.append(it)
        if len(alerts) >= 2:
            break
    alert_html = ""
    if alerts:
        rows = "".join(
            f'<div class="alert-row">'
            f'<span class="alert-dot" aria-hidden="true"></span>'
            f'<a href="{esc(a.get("url") or "#")}" target="_blank" rel="noopener" '
            f'title="{esc(present_title(a, 500))}">{esc(present_title(a, 170))}</a>'
            f'<span class="alert-time">{(local_dt(a.get("published")) or now):%H:%M}</span>'
            f'</div>' for a in alerts)
        alert_html = ('<section class="alertstrip" aria-label="Уведомление безопасности">'
                      f'<div class="alertstrip__inner">{rows}</div></section>')

    # самое читаемое за 7 дней
    week_ago = now - timedelta(days=7)
    viewed = sorted([it for it in store if it.get("views") and local_dt(it.get("published"))
                     and local_dt(it["published"]) >= week_ago and not it.get("dup_of") and gate(it)],
                    key=lambda x: -x["views"])
    viewed_top = take_first(viewed, 5)
    mostread = "".join(
        f'<li><span class="mostread__num" aria-hidden="true">{i:02d}</span>'
        f'<a href="{esc(it.get("url") or "#")}" target="_blank" rel="noopener" '
        f'title="{esc(present_title(it, 500))}">{esc(present_title(it, 90))}</a></li>'
        for i, it in enumerate(viewed_top, 1))

    # карточки последних материалов (#19/#20: чипы-рубрики + «Показать ещё 12»)
    media_var = ["a", "b", "c", "d"]
    pool_cards = [it for it in window if not is_alert(it) and gate(it)]
    rec = lambda x: x.get("published") or ""
    with_photo = sorted([it for it in pool_cards if photo_src(it)], key=rec, reverse=True)
    rest = sorted([it for it in pool_cards if not photo_src(it)], key=rec, reverse=True)
    cards_src = take_first(with_photo + rest, 36)
    cards = ""
    cat_order = cfg.get("categories") or []
    feed_cat_ids = [c.get("id") for c in cat_order
                    if any((it.get("category") == c.get("id")) for it in cards_src)]
    for i, it in enumerate(cards_src):
        cat = cats.get(it.get("category"), {})
        dt = local_dt(it.get("published"))
        mtype = it.get("material_type") or "news"
        cards += f"""<article class="card feed-card" data-cat="{esc(it.get('category',''))}" data-type="{esc(mtype)}">
<div class="card__media card__media--{media_var[i % 4]}" role="img" aria-label="{esc(cat.get('name',''))}">{photo_img(it, "", "position:absolute;inset:0;width:100%;height:100%;object-fit:cover;")}</div>
<span class="kicker card__kicker">{esc(kicker_text(it, cfg))}</span>
<h3 class="card__title"><a href="{esc(it.get('url') or '#')}" target="_blank" rel="noopener" title="{esc(present_title(it, 500))}">{esc(present_title(it, 100))}</a></h3>
{dek_p(it, 150, 'card__dek')}
<div class="card__meta">{esc(it.get('source',''))} · {fmt_time(it.get('published'), now) if dt else ''}</div>
<div class="card__badges">{card_badges(it)}</div>
</article>"""

    # чипы-рубрики ленты: категории + типы материалов, присутствующие в ленте
    feed_typ_ids = [t for t in MATERIAL_LABELS
                    if any((it.get("material_type") or "news") == t for it in cards_src)]
    chip = lambda group, val, label: (
        f'<button class="chip-f" data-group="{group}" data-val="{esc(val)}" aria-pressed="false">{esc(label)}</button>')
    chips = (chip("cat", "*", "Все")
             + "".join(chip("cat", c.get("id"), c.get("name") or c.get("id")) for c in cat_order
                       if c.get("id") in feed_cat_ids)
             + '<span class="chip-f-divider" aria-hidden="true"></span>'
             + chip("type", "*", "Все типы")
             + "".join(chip("type", t, MATERIAL_LABELS[t]) for t in feed_typ_ids))
    feed_total = len(cards_src)
    feed_bar = ('<div class="feed-bar">'
                f'<span id="feed-count">Материалов суток: {feed_total}</span>'
                '<button id="feed-more" class="feed-more" type="button">Показать ещё 12</button>'
                '<a href="archive.html">Архив-матрица →</a></div>')
    feed_empty = ('<p id="feed-empty" class="feed-empty" hidden>Ничего по этому фильтру в ленте нет — '
                  '<a href="#feed=*">показать все материалы</a>.</p>')

    # фича-полоса: колонка редактора или главная дуга
    ed_path = os.path.join(DATA, f"editorial_{day.isoformat()}.md")
    ed_text = ""
    if os.path.exists(ed_path):
        ed_text = open(ed_path, encoding="utf-8").read().strip()
    if ed_text:
        first = re.sub(r"\*\*(.+?)\*\*", r"\1", ed_text.split("\n\n")[0])
        feat_title = clip_words(first.split(".")[0], 110)
        feat_dek = clip_sentences(first[len(feat_title):].strip(" ."), 300) or clip_sentences(first, 300)
        feat_kicker = "Колонка редактора · Долгое чтение"
        feat_byline = "Редакция Гудка · внутренний выпуск"
    else:
        arcs = [a for a in week_arcs(store, day - timedelta(days=6), day)]
        if arcs:
            feat_title = arcs[0]["title"]
            _n = arcs[0]["size"]
            _held = (f'сюжет держал {_n} {plural_ru(_n, "источник", "источника", "источников")}'
                     if _n == 1 else
                     f'сюжет держали {_n} {plural_ru(_n, "источник", "источника", "источников")}')
            feat_dek = f'Возник {arcs[0]["first"]:%d.%m}, пик {arcs[0]["peak"]:%d.%m} — {_held}. Полная дуга — в недельнике.'
            feat_kicker = "Сюжет недели · Аналитика"
            feat_byline = "Инфопространство · автоматически"
        else:
            week_pool = [it for it in store if not it.get("dup_of") and not is_alert(it)
                         and it.get("views") and local_dt(it.get("published"))
                         and local_dt(it["published"]) >= datetime.combine(day - timedelta(days=6),
                                                                           datetime.min.time(),
                                                                           tzinfo=UTC4)]
            if week_pool:
                topw_filtered = take_first(week_pool, 1)
                topw = topw_filtered[0] if topw_filtered else week_pool[0]
                feat_title = present_title(topw, 110)
                feat_dek = clip_sentences(strip_title_lead(topw.get("text") or "", topw["title"]), 300) or topw["title"]
                feat_kicker = "Материал недели · по охвату"
                feat_byline = f'{topw.get("source", "")} · 👁 {fmt_views(topw["views"])}'
            else:
                feat_title, feat_dek = "Неделя в дугах", "Сюжетные дуги недели — в недельнике."
                feat_kicker, feat_byline = "Аналитика", "Гудок"

    # мнения: цитаты каналов tier-3
    ops = []
    av = ["1", "2", "3"]
    t3 = [it for it in store if it.get("tier") == 3 and not it.get("dup_of") and gate(it)
          and local_dt(it.get("published")) and local_dt(it["published"]) >= week_ago]
    t3s = take_first(t3, 3)
    for i, it in enumerate(t3s):
        ops.append(f"""<article class="op">
<p class="op__quote"><a href="{esc(it.get('url') or '#')}" target="_blank" rel="noopener" title="{esc(present_title(it, 500))}">«{esc(present_title(it, 110))}».</a></p>
<div class="op__author"><span class="op__avatar" aria-hidden="true">{av[i]}</span>
<span><div class="op__name">@{esc(it.get('channel') or '')}</div>
<div class="op__role">телеграм-канал, анонимный источник повестки</div></span></div></article>""")
    ops_html = "".join(ops) or '<div class="op"><p class="op__quote">Мнений за неделю не найдено.</p></div>'

    # «Коротко: 7 строк дня» — строки скорингового топа, не показанного выше
    ranked_win = sorted(pool_cards,
                        key=lambda x: hero_score(x, trends, now, cfg), reverse=True)
    brief_rows = short_brief(ranked_win, shown, 7)
    brief_html = ""
    if brief_rows:
        brows = "".join(
            f'<div class="brief-row"><span class="brief-t">'
            f'{fmt_time(it.get("published"), now, "rel")}</span>'
            f'<span class="brief-k">{esc(kicker_text(it, cfg))}</span>'
            f'<a href="{esc(it.get("url") or "#")}" target="_blank" rel="noopener" '
            f'title="{esc(present_title(it, 500))}">{esc(present_title(it, 110))}</a>'
            f'</div>' for it in brief_rows)
        brief_html = ('<section class="brief" aria-labelledby="brief-title">'
                      '<div class="brief__inner">'
                      '<div class="brief__label" id="brief-title">Коротко · 7 строк дня</div>'
                      f'{brows}</div></section>')

    # хроника сейчас
    live_items = take_first(sorted(window, key=lambda x: x.get("published") or "", reverse=True), 6)
    tl = "".join(
        f'<div class="tl-row"><div class="tl-time" title="{esc(fmt_time(it.get("published"), now))}">{esc(fmt_time(it.get("published"), now, "rel"))}</div>'
        f'<div class="tl-txt"><a href="{esc(it.get("url") or "#")}" target="_blank" rel="noopener" title="{esc(present_title(it, 500))}">{esc(present_title(it, 100))}</a>'
        f'<div class="tl-src">{esc(it.get("source",""))}</div></div></div>' for it in live_items)
    af_label, today_events, _af_day = pick_afisha(an, day)
    tev = "".join(
        f'<div class="tl-row"><div class="tl-time">{esc(e.get("time") or "—")}</div>'
        f'<div class="tl-txt"><a href="{esc(e.get("url") or "#")}" target="_blank" rel="noopener">{esc(clip_words(e["title"],90))}</a></div></div>'
        for e in today_events) or '<div class="now-line">Событий поблизости в афише нет — <a href="afisha.html">вся афиша</a>.</div>'

    lead_cat = cats.get(lead.get("category"), {}) if lead else {}
    lead_dt = local_dt(lead.get("published")) if lead else None
    lead_views = f' · 👁 {fmt_views(lead["views"])}' if lead and lead.get("views") else ""

    hero_extra = ""
    if lead:
        lines = []
        facts = hero_factors(lead, trends, now, cfg)
        if facts:
            why = "Почему это главное: " + "; ".join(f"{n} — {d}" for n, d in facts)
            lines.append(f'<div class="hero__why">{esc(why)}</div>')
        pp = fact_passport(lead, cfg, now)
        if pp:
            passp = " · ".join(f"<strong>{esc(k)}:</strong> {esc(v)}" for k, v in pp)
            lines.append(f'<div class="hero__passport">{passp}</div>')
        cl = lead.get("cluster")
        if cl:
            members = sorted((it for it in store if it.get("cluster") == cl),
                             key=lambda x: x.get("published") or "")
            also = also_reported(members, lead)
            if also:
                lines.append(f'<div class="hero__also">{esc(also)}</div>')
            if len(members) >= 2:
                tl2 = cluster_timeline(members, now)
                if tl2:
                    lines.append(f'<div class="hero__timeline">{esc(tl2)}</div>')
        hero_extra = "".join(lines)

    # #23: отчёт качества выпуска — три поля знает только генератор полосы
    quality = quality_report(store, cfg, day)
    quality["dups_on_page"] = sum(1 for it in store if it.get("dup_of"))
    alert_times = [local_dt(a.get("published")) for a in alerts if local_dt(a.get("published"))]
    quality["last_alert_lag_min"] = (int((now - max(alert_times)).total_seconds() // 60)
                                     if alert_times else None)
    empt = []
    if not alert_html:
        empt.append("алерт-полоса")
    if not mostread:
        empt.append("самое читаемое")
    if not brief_html:
        empt.append("коротко: 7 строк дня")
    if not ops_html.startswith('<article'):
        empt.append("мнения повестки")
    if not any(e.get("time") for e in today_events):
        empt.append("афиша на сегодня")
    if not live_items:
        empt.append("хроника сейчас")
    if not lead:
        empt.append("главный сюжет")
    quality["empty_blocks"] = empt
    save_json(os.path.join(DATA, "quality_report.json"), quality)

    # #24: A/B — флаг в config включает переключатель «версии B главной»
    ab_actions = ""
    if (cfg.get("settings") or {}).get("ab_front_v4"):
        ab_actions = ('<button class="ab-link" type="button" aria-pressed="false">'
                      'Версия B главной</button>')

    return f"""<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Гудок — информационно-аналитическое издание · Ульяновская область</title>
<link rel="icon" type="image/png" href="assets/logo_gudok.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,400;0,9..144,600;0,9..144,700;1,9..144,400&family=Inter:wght@400;500;600;700&family=Source+Serif+4:ital,opsz,wght@0,8..60,400;0,8..60,600;1,8..60,400&display=swap" rel="stylesheet">
<style>{CSS}</style></head><body>
<header class="masthead"><div class="mast-inner">
<div class="mast-side">Информационно-аналитическое издание<br>марксистской группы «Победа»</div>
<div class="mast-title">ГУДОК<span>.</span></div>
<div class="mast-side mast-side--right">Выпуск № {dnum}{' · тест' if dtest else ''}<br>выходит с 11.09.2026
<div class="mast-actions">{THEME_BTN}{ab_actions}</div></div>
</div></header>
{nav_html}
{alert_html}
<main>
<section class="hero"><div class="hero__inner">
<div>
<div class="hero__eyebrow"><span class="live" aria-hidden="true"></span>
<span class="kicker">{esc(lead_cat.get('name','Главное'))}</span></div>
<h1 class="hero__title"><a href="{esc(lead.get('url') or '#') if lead else '#'}" target="_blank" rel="noopener" title="{esc(present_title(lead, 500)) if lead else ''}">{esc(present_title(lead, 90)) if lead else '—'}</a></h1>
{dek_p(lead, 320, 'hero__dek') if lead else ''}
<div class="hero__byline"><span class="avatar" aria-hidden="true">Г</span>
<span><strong>{esc(lead.get('source','')) if lead else ''}</strong>
<span class="dot-sep">{fmt_time(lead.get('published'), now) if lead_dt else ''}</span>
<span class="dot-sep">{esc(str(n24)) + ' материалов за сутки'}</span>{lead_views}</span></div>
{hero_extra}
</div>
<figure class="hero__media">{photo_img(lead, "", "position:absolute;inset:0;width:100%;height:100%;object-fit:cover;")}<figcaption><span>Ульяновская область</span><span>Гудок · {day:%d.%m.%Y}</span></figcaption></figure>
</div></section>

<section class="mostread" aria-label="Самое читаемое"><div class="mostread__inner">
<div class="mostread__label">Самое читаемое</div>
<ol class="mostread__list">{mostread or '<li>Нет данных за неделю.</li>'}</ol>
</div></section>

{brief_html}

<section class="now-panel-wrap"><div class="page" style="padding-top:28px;">
<div class="now-panel"><div class="now-grid">
<div class="now-col"><div class="now-h">Сейчас</div>{tl}</div>
<div class="now-col"><div class="now-h">{esc(af_label)}</div>{tev}</div>
<div class="now-col"><div class="now-h">Справка</div>
<div class="now-line">Погода: {esc(weather) if weather else '—'}. Тон повестки и метрики инфополя —
в проекте <a href="infospace.html">«Инфопространство»</a>. Периоды: <a href="weekly.html">неделя</a>, <a href="monthly.html">месяц</a>.</div></div>
</div></div></div></section>

<section class="section" aria-labelledby="latest-title">
<div class="sec-head" style="margin-top:0;"><h2 id="latest-title">Последние материалы</h2>
<a href="digests/{latest_digest}">Весь выпуск № {dnum} →</a></div>
<div class="feed-chips" id="feed-chips" role="group" aria-label="Фильтр ленты">{chips}</div>
<div class="grid" id="feed-grid">{cards}</div>
{feed_bar}
{feed_empty}
</section>

<section class="feature" aria-labelledby="feature-title">
<div class="feature__inner">
<div class="feature__text">
<div class="feature__kicker">{esc(feat_kicker)}</div>
<h2 class="feature__title" id="feature-title">{esc(feat_title)}<em>.</em></h2>
<p class="feature__dek">{esc(feat_dek)}</p>
<div class="feature__byline"><strong>{esc(feat_byline.split(' · ')[0])}</strong> · {esc(feat_byline.split(' · ')[-1])}</div>
</div>
<figure class="feature__media"><figcaption>Архив · Гудок</figcaption></figure>
</div></section>

<section class="section" aria-labelledby="opinion-title">
<div class="sec-head"><h2 id="opinion-title">Мнения повестки</h2>
<a href="infospace.html">Инфопространство →</a></div>
<div class="opinion__grid">{ops_html}</div>
<div class="note" style="max-width:var(--maxw);margin:18px auto;padding:0 var(--gutter);">Цитаты анонимных каналов приводятся как материал исследования повестки, а не как редакционные оценки.</div>
</section>

<section class="newsletter" aria-labelledby="periods-title">
<div class="newsletter__inner">
<div class="newsletter__kicker">Периодичности</div>
<h2 class="newsletter__title" id="periods-title">День. Неделя. Месяц. <em>Одна редакция.</em></h2>
<p class="newsletter__dek">Ежедневный выпуск-хроника, недельник с сюжетными дугами, месячный отчёт со всеми метриками.</p>
<div class="period-links">
<a href="digests/{latest_digest}">Выпуск № {dnum}</a>
<a href="weekly.html">Недельник</a>
<a href="monthly.html">Месячный отчёт</a>
<a href="archive.html">Архив-матрица</a>
</div>
<div class="newsletter__fine">Издание внутреннее. Распространяется среди членов группы «Победа».</div>
</div></section>
</main>
{footer.render_footer('')}
{FEED_JS}
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

    # только реально существующие выпуски: раньше сюда дописывался файл текущих суток,
    # которого ещё нет (сутки не закрыты) — витрина получала битую ссылку на весь день
    digest_files = sorted(glob.glob(os.path.join(DIGESTS, "digest_*.html")))
    digest_no, _test = digest_number(cfg, date_str)

    def themed(html):
        now = datetime.now(UTC4)
        html = html.replace("</head>", THEME_HEAD + "</head>", 1)
        WD = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
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
        if "</main>" not in html:
            html = html.replace("</body>", "</main></body>", 1)
        return html.replace("</body>", THEME_FOOT + "</body>", 1)

    def with_utilbar(html, prefix=""):
        return html.replace("</body>", render_utilbar(prefix) + "</body>", 1)

    now_main = datetime.now(UTC4)
    today_str = now_main.strftime("%Y-%m-%d")
    today_no, _ = digest_number(cfg, today_str)
    today_html = with_utilbar(themed(render_digest(cfg, trends, store, status, today_str, today_no, mode="today")), "../")
    with open(os.path.join(DIGESTS, "today.html"), "w", encoding="utf-8") as f:
        f.write(today_html)
    print("[generate] живая страница: digests/today.html")

    def day_has_items(dstr):
        ds = datetime.strptime(dstr, "%Y-%m-%d").date()
        ws = datetime.combine(ds, datetime.min.time(), tzinfo=UTC4)
        we = ws + timedelta(days=1)
        return any(local_dt(it.get("published")) and ws <= local_dt(it["published"]) < we for it in store)

    for back in range(1, 4):
        dstr = (now_main.date() - timedelta(days=back)).isoformat()
        if not day_has_items(dstr):
            continue
        dno, _ = digest_number(cfg, dstr)
        dhtml = with_utilbar(themed(render_digest(cfg, trends, store, status, dstr, dno, mode="closed")), "../")
        with open(os.path.join(DIGESTS, f"digest_{dstr}.html"), "w", encoding="utf-8") as f:
            f.write(dhtml)
    print("[generate] закрытые сутки: пересобраны за последние 3 дня")

    if args.date and args.date != today_str:
        dno, _ = digest_number(cfg, args.date)
        dhtml = with_utilbar(themed(render_digest(cfg, trends, store, status, args.date, dno, mode="closed")), "../")
        with open(os.path.join(DIGESTS, f"digest_{args.date}.html"), "w", encoding="utf-8") as f:
            f.write(dhtml)

    # (выборы-2026 теперь живут в projects/elections_2026.html — см. выше)

    if args.weekly_new:
        now = datetime.now(UTC4)
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
    afw_html = render_afisha_print(cfg, load_json(os.path.join(DATA, "analytics.json")) or {})
    with open(os.path.join(BASE, "afisha_weekend.html"), "w", encoding="utf-8") as f:
        f.write(afw_html)
    print("[generate] листок выходных: afisha_weekend.html")

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

    plans_html = themed(render_plans(cfg, trends, store, status,
                                     load_json(os.path.join(DATA, "analytics.json")) or {}))
    with open(os.path.join(proj_dir, "plans.html"), "w", encoding="utf-8") as f:
        f.write(plans_html)
    print("[generate] планы: projects/plans.html")
    methods_html = themed(render_methods(cfg, trends, store, status))
    with open(os.path.join(BASE, "methods.html"), "w", encoding="utf-8") as f:
        f.write(methods_html)
    print("[generate] методы: methods.html (реестр методик v1.1)")
    dossier_html = themed(render_dossier(cfg, trends, store, status))
    with open(os.path.join(proj_dir, "dossier.html"), "w", encoding="utf-8") as f:
        f.write(dossier_html)
    print("[generate] досье: projects/dossier.html (прототип, демо-данные)")

    pressa_html = themed(render_pressa(cfg, trends, store, status))
    with open(os.path.join(proj_dir, "pressa.html"), "w", encoding="utf-8") as f:
        f.write(pressa_html)
    print("[generate] архив прессы: projects/pressa.html (реестр-справочник, ядро)")

    special_files = sorted(glob.glob(os.path.join(SPECIAL, "*.html")))
    index_html = themed(render_index(cfg, trends, store, status, digest_files, special_files))
    with open(os.path.join(BASE, "index.html"), "w", encoding="utf-8") as f:
        f.write(index_html)

    print(f"[generate] выпуск №{digest_no}: digests/digest_{date_str}.html")
    print(f"[generate] витрина: index.html (архив: {len(digest_files)} выпусков, спец: {len(special_files)})")


if __name__ == "__main__":
    main()
