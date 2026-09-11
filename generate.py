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
:root{--navy:#0d2137;--navy2:#14314f;--navy3:#1d4066;--blue:#2f80ed;--sky:#dce9f8;
--gold:#f2b134;--red:#e5484d;--green:#2ea36b;--bg:#eef2f7;--card:#fff;--line:#dbe4ee;
--txt:#1c2733;--muted:#5b6b7c;--radius:14px;--shadow:0 2px 10px rgba(13,33,55,.08);}
*{margin:0;padding:0;box-sizing:border-box;}
html{scroll-behavior:smooth;}
body{font-family:"Segoe UI",Roboto,Arial,sans-serif;background:var(--bg);color:var(--txt);font-size:15px;line-height:1.5;}
a{color:var(--blue);text-decoration:none;} a:hover{text-decoration:underline;}
.topbar{background:linear-gradient(135deg,var(--navy),var(--navy2) 60%,var(--navy3));color:#fff;padding:14px 22px;box-shadow:0 2px 14px rgba(0,0,0,.25);}
.topbar-inner{max-width:1280px;margin:0 auto;display:flex;align-items:center;gap:14px;flex-wrap:wrap;}
.brand{align-items:center;}
.brand>div{display:flex;flex-direction:column;justify-content:center;}
.brand{display:flex;align-items:center;gap:12px;}
.brand-title{font-size:19px;font-weight:800;letter-spacing:.6px;}
.brand-title span{color:#fff;}
.brand-sub{font-size:11.5px;color:#a9c1d9;text-transform:uppercase;letter-spacing:.4px;}
.top-meta{margin-left:auto;display:flex;gap:9px;flex-wrap:wrap;align-items:center;}
.chip{background:rgba(255,255,255,.1);border:1px solid rgba(255,255,255,.18);border-radius:999px;padding:5px 13px;font-size:12.5px;color:#e7eef6;display:flex;gap:7px;align-items:center;white-space:nowrap;}
.chip b{color:var(--gold);}
.dot{width:8px;height:8px;border-radius:50%;background:#41d17a;display:inline-block;animation:p 1.6s infinite;}
.dot.err{background:#e5484d;}
@keyframes p{0%,100%{opacity:1}50%{opacity:.3}}
.nav{background:var(--navy);border-top:1px solid rgba(255,255,255,.12);}
.nav-inner{max-width:1280px;margin:0 auto;display:flex;gap:2px;overflow-x:auto;padding:0 14px;}
.nav a{color:#c9d8e8;font-size:13px;font-weight:600;padding:10px 13px;white-space:nowrap;border-bottom:3px solid transparent;}
.nav a:hover{color:#fff;background:rgba(255,255,255,.06);text-decoration:none;}
.page{max-width:1280px;margin:0 auto;padding:22px 18px 40px;}
.sec-head{display:flex;align-items:center;gap:12px;margin:30px 0 14px;}
.sec-head h2{font-size:20px;font-weight:800;color:var(--navy);}
.sec-head .line{flex:1;height:2px;background:linear-gradient(90deg,var(--line),transparent);}
.sec-head .badge{font-size:11px;font-weight:700;background:var(--sky);color:var(--navy3);padding:4px 10px;border-radius:999px;text-transform:uppercase;letter-spacing:.5px;}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:16px;}
.grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;}
.main-grid{display:grid;grid-template-columns:1fr 370px;gap:20px;align-items:start;}
.card{background:var(--card);border-radius:var(--radius);box-shadow:var(--shadow);border:1px solid var(--line);overflow:hidden;}
.card-pad{padding:16px 18px;}
.kpi-grid{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;}
.kpi{background:var(--card);border-radius:var(--radius);box-shadow:var(--shadow);padding:13px 15px;border-left:4px solid var(--blue);}
.kpi .num{font-size:22px;font-weight:800;color:var(--navy);line-height:1.1;}
.kpi .num small{font-size:12px;color:var(--muted);}
.kpi .lbl{font-size:11.8px;color:var(--muted);margin-top:4px;}
.kpi.gold{border-left-color:var(--gold);} .kpi.red{border-left-color:var(--red);}
.kpi.green{border-left-color:var(--green);} .kpi.violet{border-left-color:#7b5aa6;}
.topic-row{display:grid;grid-template-columns:210px 1fr 130px 90px;gap:10px;align-items:center;padding:8px 0;border-bottom:1px dashed var(--line);font-size:13px;}
.topic-row:last-child{border-bottom:none;}
.topic-name{font-weight:700;color:var(--navy);}
.topic-name small{display:block;font-weight:600;color:var(--muted);font-size:11px;}
.stchip{font-size:10.5px;font-weight:800;border-radius:999px;padding:3px 9px;white-space:nowrap;display:inline-block;}
.bar-wrap{background:#edf2f8;border-radius:6px;height:16px;overflow:hidden;}
.bar-fill{height:100%;border-radius:6px;background:linear-gradient(90deg,var(--blue),#5aa0f5);}
.bar-fill.hot{background:linear-gradient(90deg,#d5494e,#f08a8d);}
.bar-fill.warm{background:linear-gradient(90deg,#d99a1b,#f2c14e);}
.bar-fill.cool{background:linear-gradient(90deg,#218a58,#3ec27f);}
.tgpost{display:flex;gap:10px;padding:9px 0;border-bottom:1px dashed var(--line);}
.tgpost:last-child{border-bottom:none;}
.tgpost .views{flex-shrink:0;background:#e8f4ff;color:#1d4f9c;border-radius:8px;font-size:11px;font-weight:800;padding:3px 8px;height:fit-content;white-space:nowrap;}
.tgpost .t{font-size:12.8px;color:var(--txt);line-height:1.4;}
.tgpost .m{font-size:11px;color:var(--muted);margin-top:2px;}
.cat-block{margin-bottom:16px;}
.cat-head{display:flex;align-items:center;gap:10px;padding:11px 16px;border-bottom:1px solid var(--line);background:linear-gradient(90deg,#f8fbfe,#fff);}
.cat-ico{width:28px;height:28px;border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:14px;color:#fff;flex-shrink:0;}
.cat-head h3{font-size:15px;font-weight:800;color:var(--navy);}
.cat-head .count{margin-left:auto;font-size:11px;color:var(--muted);background:var(--bg);border-radius:999px;padding:3px 9px;font-weight:700;}
.news-item{padding:11px 16px;border-bottom:1px dashed var(--line);}
.news-item:last-child{border-bottom:none;}
.news-item h4{font-size:13.8px;font-weight:700;line-height:1.35;margin-bottom:3px;}
.news-item h4 a{color:var(--txt);} .news-item h4 a:hover{color:var(--blue);}
.news-item p{font-size:12.5px;color:var(--muted);line-height:1.45;}
.news-item .meta{font-size:10.8px;color:#8a99aa;margin-top:4px;font-weight:600;}
.news-item .meta .tg{color:#1d4f9c;}
.side-head{padding:12px 15px;background:var(--navy);color:#fff;font-size:13.5px;font-weight:800;display:flex;align-items:center;gap:8px;}
.side-head .sub{margin-left:auto;font-size:10.5px;font-weight:600;color:#9db6cf;}
.side-body{padding:13px 15px;}
.note{font-size:11.5px;color:var(--muted);background:#f7fafd;border:1px dashed var(--line);border-radius:9px;padding:8px 11px;margin-top:10px;line-height:1.45;}
.verdict{background:#f7fafd;border-left:3px solid var(--gold);border-radius:0 9px 9px 0;padding:9px 13px;font-size:12.6px;color:var(--navy3);margin-top:10px;}
.verdict b{color:#96690a;text-transform:uppercase;font-size:11px;letter-spacing:.8px;display:block;margin-bottom:3px;}
.tbl{width:100%;border-collapse:collapse;font-size:12.8px;}
.tbl th{background:var(--navy);color:#fff;text-align:left;padding:8px 11px;font-size:11px;text-transform:uppercase;letter-spacing:.5px;}
.tbl td{padding:8px 11px;border-bottom:1px solid var(--line);vertical-align:top;}
.tbl tr:nth-child(even) td{background:#f8fbfe;}
.ok{color:var(--green);font-weight:800;} .fail{color:var(--red);font-weight:800;}
.arch-item{display:flex;align-items:center;gap:12px;padding:10px 0;border-bottom:1px dashed var(--line);}
.arch-item:last-child{border-bottom:none;}
.arch-date{width:52px;height:46px;border-radius:10px;background:var(--navy);color:#fff;display:flex;flex-direction:column;align-items:center;justify-content:center;line-height:1;flex-shrink:0;}
.arch-date b{font-size:16px;} .arch-date span{font-size:9px;color:#9db6cf;margin-top:2px;text-transform:uppercase;}
.btn{display:inline-block;background:var(--navy);color:#fff;border-radius:9px;padding:8px 15px;font-size:12.5px;font-weight:700;}
.btn:hover{background:var(--navy3);text-decoration:none;}
.btn.gold{background:var(--gold);color:#3d2e04;}
.alert-banner{background:linear-gradient(90deg,#b02a2f,#e5484d);color:#fff;padding:12px 20px;font-size:14px;font-weight:700;display:flex;align-items:center;gap:12px;flex-wrap:wrap;}
.alert-banner a{color:#ffe3a8;}
.alert-banner .blink{animation:p 1s infinite;font-size:17px;}
.print-btn{background:var(--gold);border:none;color:#3d2e04;font-weight:800;font-size:12px;padding:7px 14px;border-radius:8px;cursor:pointer;}
.footer{background:var(--navy);color:#9db6cf;margin-top:36px;padding:24px 22px;font-size:12px;}
.footer-inner{max-width:1280px;margin:0 auto;display:flex;gap:30px;flex-wrap:wrap;}
.footer b{color:#fff;display:block;font-size:13px;margin-bottom:6px;}
.footer p{line-height:1.6;max-width:480px;}
code,pre{font-family:Consolas,Menlo,monospace;}
.codebox{background:#0d2137;color:#c9d8e8;border-radius:10px;padding:12px 14px;font-size:12px;overflow-x:auto;line-height:1.55;}
.codebox .c{color:#7fa3c7;}
.cal-ev{display:flex;gap:11px;padding:8px 0;border-bottom:1px dashed var(--line);align-items:flex-start;}
.cal-ev:last-child{border-bottom:none;}
.cal-badge{flex-shrink:0;width:44px;height:42px;border-radius:9px;background:var(--navy3);color:#fff;display:flex;flex-direction:column;align-items:center;justify-content:center;line-height:1;}
.cal-badge b{font-size:15px;} .cal-badge span{font-size:8.5px;text-transform:uppercase;color:#a9c1d9;margin-top:2px;}
.cal-badge.gold{background:var(--gold);color:#4d3a06;} .cal-badge.gold span{color:#7a5f10;}
.cal-txt{font-size:12.8px;line-height:1.4;}
.cal-txt .t2{color:var(--muted);font-size:11.3px;}
.cl-card{border:1px solid var(--line);border-radius:11px;padding:11px 14px;margin-bottom:10px;background:#fbfdff;}
.cl-card.gap{border-left:4px solid var(--gold);}
.cl-head{display:flex;align-items:center;gap:9px;flex-wrap:wrap;margin-bottom:6px;}
.cl-name{font-size:13.5px;font-weight:800;color:var(--navy);}
.cl-badge{font-size:10px;font-weight:800;border-radius:999px;padding:2px 9px;}
.cl-samples{font-size:12px;color:var(--muted);line-height:1.55;}
.cl-samples a{color:var(--txt);}
.tone-wrap{display:flex;gap:22px;align-items:center;flex-wrap:wrap;}
.tone-gauge{flex:1;min-width:250px;}
.tone-bar{height:20px;border-radius:10px;background:linear-gradient(90deg,#d5494e,#efe6cd 50%,#3ec27f);position:relative;}
.tone-pin{position:absolute;top:-4px;width:4px;height:28px;background:var(--navy);border-radius:2px;box-shadow:0 0 0 2px #fff;}
.tone-cats{display:flex;flex-wrap:wrap;gap:6px;margin-top:11px;}
.tone-cat{font-size:11px;border-radius:8px;padding:3px 9px;border:1px solid var(--line);background:#fff;font-weight:700;}
.fc-tbl{width:100%;border-collapse:collapse;font-size:12.5px;margin-top:10px;}
.fc-tbl th{text-align:left;padding:6px 10px;background:var(--bg);color:var(--muted);font-size:10.5px;text-transform:uppercase;letter-spacing:.5px;}
.fc-tbl td{padding:6px 10px;border-bottom:1px dashed var(--line);}
.fc-up{color:#b02a2f;font-weight:800;} .fc-down{color:#1d7a4d;font-weight:800;} .fc-flat{color:var(--muted);font-weight:800;}
.tchip{display:inline-block;font-size:10px;font-weight:700;background:#eef4fc;color:#3d5a7a;border:1px solid #d8e4f2;border-radius:999px;padding:1px 8px;margin:5px 4px 0 0;}
.hero-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;}
.hero-card{background:var(--card);border-radius:var(--radius);box-shadow:var(--shadow);border-top:4px solid var(--blue);padding:14px 16px;display:flex;flex-direction:column;}
.hero-card .hk{font-size:10.5px;font-weight:800;letter-spacing:1px;text-transform:uppercase;color:var(--blue);margin-bottom:7px;display:flex;justify-content:space-between;}
.hero-card .hk .w{color:var(--muted);letter-spacing:.2px;text-transform:none;font-weight:600;}
.hero-card h3{font-size:15.5px;font-weight:800;color:var(--navy);line-height:1.3;margin-bottom:7px;}
.hero-card h3 a{color:var(--navy);} .hero-card h3 a:hover{color:var(--blue);}
.hero-card p{font-size:12.8px;color:var(--muted);line-height:1.5;}
.hero-meta{margin-top:auto;padding-top:8px;font-size:11px;color:#8a99aa;font-weight:600;border-top:1px dashed var(--line);}
.chrono{border-left:3px solid var(--red);padding-left:15px;margin-top:6px;}
.chrono-item{position:relative;padding:7px 0;border-bottom:1px dashed var(--line);font-size:12.8px;line-height:1.4;}
.chrono-item:last-child{border-bottom:none;}
.chrono-item::before{content:"";position:absolute;left:-22px;top:12px;width:9px;height:9px;border-radius:50%;background:var(--red);border:2px solid #fff;}
.chrono-time{font-weight:800;color:var(--red);font-size:11.5px;margin-right:6px;white-space:nowrap;}
@media (max-width:1080px){.main-grid,.grid2,.hero-grid{grid-template-columns:1fr;}.kpi-grid{grid-template-columns:repeat(2,1fr);}.grid3{grid-template-columns:1fr;}.topic-row{grid-template-columns:150px 1fr 110px;}.topic-row .sparkcell{display:none;}}
@media print{.nav,.print-btn,.top-meta .chip{display:none!important;}body{background:#fff;}.card,.kpi{box-shadow:none;break-inside:avoid;}}

.nav a.active{color:#fff;border-bottom-color:var(--gold);}
.nav a.nav-util{color:#8fa9c4;font-weight:600;}
.nav a.nav-util:hover{color:#fff;}
.nav-util-first{margin-left:auto;}
.subnav{background:var(--card);border-bottom:1px solid var(--line);}
.subnav-inner{max-width:1280px;margin:0 auto;padding:7px 18px;display:flex;gap:15px;flex-wrap:wrap;font-size:12.2px;align-items:center;}
.subnav-inner a{color:var(--muted);font-weight:700;}
.subnav-inner a:hover{color:var(--blue);}
.subnav .lbl{color:var(--navy);font-weight:800;text-transform:uppercase;font-size:10px;letter-spacing:.9px;}
/* ===== ТЁМНАЯ ТЕМА ===== */
:root[data-theme="dark"]{
  --bg:#0b1622; --card:#12202f; --line:#24384e; --txt:#dfe9f4; --muted:#93a7bc;
  --sky:#1c3350; --navy:#dce9f8; --navy3:#a9c9e8; --shadow:0 2px 12px rgba(0,0,0,.45);
}
:root[data-theme="dark"] .topbar{background:linear-gradient(135deg,#0a1826,#0f2033 60%,#14314f);}
:root[data-theme="dark"] .nav{background:#0a1826;}
:root[data-theme="dark"] .ticker-wrap{background:#060d16;border-color:#1d3550;}
:root[data-theme="dark"] .side-head,
:root[data-theme="dark"] .tbl th,
:root[data-theme="dark"] .cal-badge,
:root[data-theme="dark"] .arch-date,
:root[data-theme="dark"] .dist-head,
:root[data-theme="dark"] .exec-sec h2{background:#16283c;}
:root[data-theme="dark"] .cal-badge.gold{background:var(--gold);color:#4d3a06;}
:root[data-theme="dark"] .cal-badge.gold span{color:#7a5f10;}
:root[data-theme="dark"] .cat-head{background:linear-gradient(90deg,#15263a,#12202f);border-color:var(--line);}
:root[data-theme="dark"] .note{background:#101e2d;border-color:#24384e;}
:root[data-theme="dark"] .verdict,:root[data-theme="dark"] .an-verdict{background:#101e2d;color:#c9d8e8;}
:root[data-theme="dark"] .verdict b,:root[data-theme="dark"] .an-verdict b{color:#e8b64c;}
:root[data-theme="dark"] .tbl tr:nth-child(even) td{background:#14243a;}
:root[data-theme="dark"] .tbl td{border-color:var(--line);}
:root[data-theme="dark"] .bar-wrap,:root[data-theme="dark"] .bar-row .bt{background:#1c3049;}
:root[data-theme="dark"] .btn{background:#1d4066;color:#fff;}
:root[data-theme="dark"] .btn:hover{background:#2a5580;}
:root[data-theme="dark"] .footer{background:#0a1826;}
:root[data-theme="dark"] .fbtn{background:#12202f;border-color:#24384e;color:var(--muted);}
:root[data-theme="dark"] .fbtn.active{background:#2f80ed;border-color:#2f80ed;color:#fff;}
:root[data-theme="dark"] .wx{background:linear-gradient(160deg,#15263a,#101e2d);border-color:#24384e;}
:root[data-theme="dark"] .wx.alert{background:linear-gradient(160deg,#2a1c1c,#201414);border-color:#4e3030;}
:root[data-theme="dark"] .wx .t{color:var(--txt);}
:root[data-theme="dark"] .hero-src{background:#101e2d;border-color:var(--line);}
:root[data-theme="dark"] .drone{background:#251616;border-color:#4e3030;}
:root[data-theme="dark"] .codebox{background:#060d16;}
:root[data-theme="dark"] .cl-card{background:#101e2d;border-color:var(--line);}
:root[data-theme="dark"] .person{background:#101e2d;border-color:var(--line);}
:root[data-theme="dark"] .reserved{background:repeating-linear-gradient(45deg,#101e2d,#101e2d 12px,#0d1926 12px,#0d1926 24px);border-color:#2c4258;}
:root[data-theme="dark"] .tone-cat{background:#101e2d;border-color:var(--line);}
:root[data-theme="dark"] .tgpost .views{background:#16283c;color:#8ab4e8;}
:root[data-theme="dark"] .exec-wrap{background:var(--bg);}
:root[data-theme="dark"] .news-item .meta .tg{color:#7fa8d9;}
:root[data-theme="dark"] .fc-up{color:#ff8a8e;}
:root[data-theme="dark"] .fc-down{color:#6fd39b;}
:root[data-theme="dark"] .hl{color:#3d2e04;}
:root[data-theme="dark"] .okrug-title .no{background:#1c3350;color:#cfe2f7;}
:root[data-theme="dark"] .chipC{background:#101e2d;border-color:#24384e;color:var(--txt);}
:root[data-theme="dark"] .timeline::before{background:linear-gradient(180deg,#2ea36b,#2f80ed 30%,#9a7cc9 60%,#d99a1b);}
:root[data-theme="dark"] .phase::before{background:#0b1622;}
:root[data-theme="dark"] .sprint{background:linear-gradient(135deg,#0f2033,#16283c);}
:root[data-theme="dark"] .mission{background:var(--card);}
:root[data-theme="dark"] .src-card{background:var(--card);border-color:var(--line);}
.logo{width:42px;height:42px;object-fit:contain;border-radius:10px;background:#fff;box-shadow:0 1px 6px rgba(0,0,0,.3);flex-shrink:0;}
.mast-logo{width:68px;height:68px;object-fit:contain;border-radius:16px;background:#fff;box-shadow:0 3px 14px rgba(0,0,0,.45);flex-shrink:0;}
.theme-btn{border:1px solid rgba(255,255,255,.22);font-size:13px;padding:6px 12px;border-radius:8px;cursor:pointer;background:rgba(255,255,255,.12);color:#ffe9b8;font-weight:800;}
.theme-btn:hover{background:rgba(255,255,255,.22);}
@media print{
  :root[data-theme="dark"]{--bg:#fff;--card:#fff;--line:#dbe4ee;--txt:#1c2733;--muted:#5b6b7c;--navy:#0d2137;--navy3:#1d4066;--sky:#dce9f8;}
  :root[data-theme="dark"] .exec-wrap{background:#fff;}
  .theme-btn{display:none!important;}
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
        ("digest", f"📰 Выпуск {label_num}", f"{prefix}digests/{latest}" if latest else ""),
        ("exec", "📋 Руководителю", f"{prefix}digests/{ex}" if ex_exists else ""),
        ("afisha", "🎭 Афиша", f"{prefix}afisha.html"),
        ("elections", "🗳 Выборы-2026", f"{prefix}special/elections_2026.html"),
        ("infospace", "🔬 Инфопространство", f"{prefix}infospace.html"),
        ("archive", "🗄 Архив", f"{prefix}index.html#archive"),
    ]
    utils = [
        ("analytics", "Аналитика недели", f"{prefix}special/analytics_2026-09-11.html"),
        ("roadmap", "🧭 Роадмап", f"{prefix}roadmap.html"),
        ("status", "🩺 Статус", f"{prefix}status.html"),
    ]
    html_items = []
    for key, txt, href in items:
        if not href:
            continue
        cls = "active" if key == current else ""
        html_items.append(f'<a class="{cls}" href="{href}">{txt}</a>')
    for i, (key, txt, href) in enumerate(utils):
        cls = ("nav-util nav-util-first" if i == 0 else "nav-util") + (" active" if key == current else "")
        html_items.append(f'<a class="{cls}" href="{href}">{txt}</a>')
    return f'<nav class="nav"><div class="nav-inner">{"".join(html_items)}</div></nav>' + subnav


# ------------------------------------------------------------------ digest
def render_digest(cfg, trends, store, status, date_str, digest_no):
    now = datetime.now(UTC4)
    an = load_json(os.path.join(DATA, "analytics.json")) or {}
    nav_html = render_nav(cfg, "digest", "../", subnav=SUBNAV_DIGEST)
    day = datetime.strptime(date_str, "%Y-%m-%d").date()
    cats = {c["id"]: c for c in cfg["categories"]}
    tg_channels = {c["username"]: c for c in cfg["telegram_channels"] if c.get("enabled", True)}

    # окно выборки: сутки вокруг даты дайджеста (+6 ч запас)
    win_start = datetime.combine(day, datetime.min.time(), tzinfo=UTC4) - timedelta(hours=6)
    win_end = win_start + timedelta(hours=cfg["settings"].get("digest_window_hours", 26))
    window = []
    for it in store:
        if it.get("dup_of"):
            continue  # перепечатки скрыты — показан первичный материал с also_in
        dt = local_dt(it.get("published"))
        if dt and win_start <= dt < win_end:
            window.append(it)
    # если материалов мало — расширяем до 3 суток
    if len(window) < 8:
        win_start -= timedelta(days=2)
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
<div class="brand-sub">Информационно-аналитическое издание · выпуск № {digest_no}{' · 🧪 ТЕСТОВЫЙ' if digest_no == 0 else ''}</div>
</div></div>
<div class="top-meta">
<div class="chip">{'🧪 тестовый номер · ' if digest_no == 0 else ''}<span class="dot"></span> Выпуск от <b>{day:%d.%m.%Y}</b></div>
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
        parts.append(f"""<div class="sec-head" id="heroes"><h2>🔥 Главные события дня</h2><div class="line"></div>
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
        parts.append(f"""<div class="sec-head"><h2>⚡ Оперативная хроника: безопасность</h2><div class="line"></div>
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
        parts.append(f"""<div class="sec-head" id="pulse"><h2>📊 Пульс информационной повестки</h2><div class="line"></div>
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
            parts.append(f"""<div class="sec-head"><h2>👁 Самое читаемое в Telegram за 7 дней</h2><div class="line"></div></div>
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
        parts.append(f"""<div class="sec-head" id="afisha"><h2>📅 Автоафиша: ближайшие события</h2><div class="line"></div>
<div class="badge">извлечено из новостей · {len(cal)} дат</div></div>
<div class="card"><div class="card-pad">{''.join(rows)}
<div class="note">Даты извлекаются из текстов автоматически (analytics.py): одиночные дни, диапазоны, время и площадки 📍. Погода и исторические даты отсеиваются. Перед визитом сверяйтесь с первоисточником.</div></div></div>""")

    # ---- Лента дня
    parts.append(f"""<div class="sec-head" id="feed"><h2>📰 Лента дня</h2><div class="line"></div>
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
                items_html.append(f"""<div class="news-item">
{thumb}<h4><a href="{link}" target="_blank" rel="noopener">{esc(it['title'])}</a></h4>
<p>{esc(it.get('text') or '')}</p>
<div class="meta">{dt.strftime('%d.%m %H:%M') if dt else ''} · {esc(it.get('source',''))}{tg_badge}</div>
{chips}</div>""")
            block = (f"""<div class="card cat-block"><div class="cat-head">
<div class="cat-ico" style="background:{c['color']};">{c['icon']}</div>
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
    parts.append(f"""<div class="sec-head" id="tg"><h2>📡 Telegram-монитор</h2><div class="line"></div>
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
        parts.append(f"""<div class="sec-head" id="clusters"><h2>🧩 Сюжеты последних 72 часов</h2><div class="line"></div>
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
        parts.append(f"""<div class="sec-head" id="tone"><h2>🎭 Тон повестки дня</h2><div class="line"></div>
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
        parts.append(f"""<div class="sec-head" id="forecast"><h2>🔮 Прогноз повестки</h2><div class="line"></div>
<div class="badge">автоматические выводы</div></div>
<div class="card"><div class="card-pad"><div class="verdict"><b>Сводка трекера</b>{' '.join(lines)}</div>{fc_rows}
<div class="note">Выводы — правила trends.py; прогноз — наклон ряда + EMA (analytics.py), уверенность по разбросу остатков. При накоплении истории точность растёт.</div></div></div>""")

    meta = (status or {}).get("_meta", {})
    parts.append(f"""</div>
<footer class="footer"><div class="footer-inner">
<div><b>{cfg['brand']}</b><p>{esc(cfg['tagline_full'])}</p><p style="margin-top:6px;">Выпуск №{digest_no} от {day:%d.%m.%Y}. Собрано автоматически: {esc(meta.get('last_run_local','—'))} (UTC+4).</p></div>
<div><b>Методика</b><p>Мониторинг RSS ({', '.join(s['name'] for s in cfg['rss_sources'] if s.get('enabled', True))}) и публичных превью Telegram-каналов (t.me/s/…). Классификация — по словарю config.json; тренды — сравнение 3-дневного окна с недельной базой.</p></div>
<div><b>Навигация</b><p><a href="../index.html" style="color:#ffd47e;">← Первая полоса</a> · <a href="../special/analytics_2026-09-11.html" style="color:#ffd47e;">Аналитический спецвыпуск 11.09</a></p></div>
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

<div class="sec-head" style="margin-top:8px;"><h2>🏛 Кандидаты на пост губернатора</h2><div class="line"></div>
<div class="badge">избран на 5 лет · назначает сенатора</div></div>
<div class="grid2" style="margin-bottom:8px;">{cand_cards}</div>
<div class="note" style="margin-bottom:22px;">Порога явки нет — выборы состоятся при любой активности. Профили составлены по данным Википедии, «Ведомостей» и региональных СМИ (проверено 11.09.2026).</div>

<div class="sec-head"><h2>🗳 Государственная Дума: одномандатные округа</h2><div class="line"></div>
<div class="badge">по данным gogov.ru, 23.08.2026</div></div>
<div class="grid2" style="margin-bottom:6px;">{dist_blocks}</div>
<div class="note" style="margin-bottom:22px;">Всего по округам выдвигались 20 человек: 1 снялся, 2 выбыли после регистрации (Д. Гондаренко, «Яблоко», № 185; Е. Скрипкин, «Яблоко», № 186). Также 20 сентября — довыборы депутата Законодательного Собрания VII созыва по Вешкаймскому одномандатному округу № 2.</div>

<div class="sec-head"><h2>📈 Выборная повестка в мониторинге</h2><div class="line"></div>
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

<div class="sec-head"><h2>📰 Выборная лента из базы центра</h2><div class="line"></div>
<div class="badge">топ-10 по просмотрам и свежести</div></div>
<div class="card" style="margin-bottom:22px;">{feed}</div>

<div class="sec-head"><h2>👀 Что будем отслеживать 18–20 сентября</h2><div class="line"></div></div>
<div class="card"><div class="card-pad"><ul class="watch" style="padding-left:20px;">
<li><b>Явка по дням</b> — трёхдневное голосование без ДЭГ делает мобилизацию в Ульяновске (52,6% избирателей) ключевым фактором; сравним с 2021 годом (губернаторские: ~48% на трёх днях).</li>
<li><b>Результаты губернаторской кампании</b> — интрига не в победе фаворита, а в распределении мест 2–4 (Ким vs Маринин vs Ясайтис) и проценте ЕР/КПРФ по партспискам.</li>
<li><b>Округа № 185 и № 186</b> — Камеко (ЕР) и Кононов (ЕР) против сильных коммунистов (Шилов, Султашов); Маринин тянет ЛДПР сразу в двух кампаниях.</li>
<li><b>Сообщения о нарушениях</b> — мониторинг Ulnovosti.ru, «Компромат Ульяновск», tier-3 каналов с обязательной верификацией по tier-1.</li>
<li><b>Первые шаги избранного губернатора</b> — назначение сенатора из трёх заявленных протеже, кадровые решения в правительстве области.</li>
</ul></div></div>

<div class="sec-head"><h2>📊 Итоги голосования</h2><div class="line"></div>
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

<div class="sec-head"><h2>🎟 Анонсы культурных каналов</h2><div class="line"></div>
<div class="badge">Telegram, последние посты</div></div>
<div class="grid2">{''.join(chan_html)}</div>

<div class="note" style="margin-top:16px;">Афиша собирается автоматически (analytics.py → extract_calendar) из текстов всех
мониторируемых источников: даты, время, площадки. Типы событий определяются по ключевым словам; районные мероприятия
помечены бейджем. Культурных событий в выборке: {n_culture}. <b>Перед визитом сверяйте время и билеты у организаторов</b> —
данные извлечены из публикаций автоматически и могут содержать неточности.</div>

</div>
<footer class="footer"><div class="footer-inner">
<div><b>{cfg['brand']} · Афиша</b><p>Автономная страница, обновляется каждым прогоном run.sh. Источники: Telegram-каналы (@culturnik, @ulpromo, @ProNovosty73 и др.) и RSS СМИ региона.</p></div>
<div><b>Навигация</b><p><a href="index.html" style="color:#ffd47e;">Первая полоса</a> · <a href="digests/digest_{today.isoformat()}.html" style="color:#ffd47e;">Свежий дайджест</a> · <a href="status.html" style="color:#ffd47e;">Статус системы</a></p></div>
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

<div class="sec-head"><h2>🎯 Кто задаёт повестку</h2><div class="line"></div>
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

<div class="sec-head"><h2>🌊 Каскады недели</h2><div class="line"></div>
<div class="badge">как сюжеты расходятся по каналам</div></div>
<div class="card"><div class="card-pad">{casc_html}
<div class="note">Каскад — одно событие, разошедшееся перепечатками по нескольким источникам. Ширина каскада = резонанс сюжета в инфополе.</div></div></div>

<div class="sec-head"><h2>🎭 Тон информационного пространства</h2><div class="line"></div>
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

<div class="sec-head"><h2>🗺 Карта муниципалитетов: кого слышно</h2><div class="line"></div>
<div class="badge">по упоминаниям за 7 дней</div></div>
<div class="card"><div class="card-pad">{muni_html}{silence_html}
<div class="note">Ульяновск не участвует в подсчёте (он заведомо доминирует). Красным — муниципалитеты, полностью выпавшие из инфополя за неделю; жёлтым — 1–2 упоминания. Это измеримый признак информационного неравенства территорий: жизнь районов существует для областного читателя только через происшествия или визиты чиновников.</div></div></div>

<div class="sec-head"><h2>📌 Выводы наблюдения</h2><div class="line"></div>
<div class="badge">автоматические</div></div>
<div class="card"><div class="card-pad"><div class="verdict"><b>Сводка недели</b>
<ul style="padding-left:20px;margin-top:4px;line-height:1.7;font-size:13px;">{concl_html}</ul></div>
<div class="note">Выводы формируются правилами analytics.py; по мере накопления истории добавятся сравнения неделя-к-неделе и сезонность.</div></div></div>

</div>
<footer class="footer"><div class="footer-inner">
<div><b>Гудок</b><p>{esc(cfg['tagline_full'])}</p></div>
<div><b>Методика</b><p>Дедупликация (Жаккар + вложенность заголовков), TF-IDF-кластеризация, лексикон тональности (±110 маркеров), географические маркеры муниципалитетов. Всё — на открытых данных мониторинга; воспроизводится из data/store.jsonl.</p></div>
<div><b>Навигация</b><p><a href="index.html" style="color:#ffd47e;">Первая полоса</a> · <a href="special/analytics_2026-09-11.html" style="color:#ffd47e;">Аналитика недели</a> · <a href="roadmap.html" style="color:#ffd47e;">Роадмап</a></p></div>
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
        lead_html = f"""<div class="lead-main" style="border-top-color:{cat.get('color','var(--gold)')};">
<div class="lead-kicker" style="color:{cat.get('color','var(--gold)')};">{cat.get('icon','📌')} {esc(cat.get('name','Главное'))} · сюжет дня</div>
<h2><a href="{url}" target="_blank" rel="noopener">{esc(m['title'])}</a></h2>
<p>{esc((m.get('text') or '')[:340])}</p>
<div class="lead-meta">{meta} · <a href="{url}" target="_blank" rel="noopener">читать полностью →</a></div></div>"""
        side = ""
        for m in leads[1:3]:
            cat = cats.get(m.get("category"), {})
            url, meta = lead_meta(m)
            side += f"""<div class="lead-card" style="border-top-color:{cat.get('color','var(--blue)')};">
<div class="lead-kicker" style="color:{cat.get('color','var(--blue)')};">{cat.get('icon','📌')} {esc(cat.get('name',''))}</div>
<h3><a href="{url}" target="_blank" rel="noopener">{esc(m['title'][:120])}</a></h3>
<p>{esc((m.get('text') or '')[:150])}</p>
<div class="lead-meta">{meta}</div></div>"""
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
        ("📰", f"Выпуск № {dnum}{' (тестовый)' if dtest else ''}", f"{n24} <small>материалов за 24 ч</small>",
         "Лента дня по девяти рубрикам, пульс повестки, сюжеты 72 часов, тон дня и прогноз на завтра.",
         f"digests/{latest_digest}" if latest_digest else "", "var(--blue)"),
        ("📋", "Дайджест руководителя", "1 <small>страница A4</small>",
         "Пять событий, три риска, два решения — для быстрого чтения руководством организации.",
         f"digests/{ex}" if ex_ok else "", "#1d7a4d"),
        ("🎭", "Афиша", f"{af_n} <small>событий на 45 дней</small>",
         "Культурные события области: фестивали, театр, концерты, выставки; фильтры по дням и районам.",
         "afisha.html", "#9a4d8f"),
        ("🗳", "Выборы-2026", f"{d_vote} <small>дн. до голосования</small>" if d_vote > 0 else "голосование",
         "Спецвыпуск: кандидаты в губернаторы, округа Госдумы № 185/186, довыборы в ЗСО, предвыборные тренды.",
         "special/elections_2026.html", "#b02a2f"),
        ("🔬", "Инфопространство", f"{n_week} <small>сообщений за неделю</small>",
         "Сквозное исследование: кто задаёт повестку, каскады перепечаток, тон по уровням, федеральное эхо, карта районов.",
         "infospace.html", "#0f9b8e"),
        ("📕", "Аналитика недели", "спецвыпуск",
         "Глубокий ручной разбор повестки: политика, экономика, бюджет, безопасность — с верификацией фактов.",
         "special/analytics_2026-09-11.html", "#96690a"),
        ("🗄", "Архив", f"{len(digest_files)} <small>выпусков · {len(special_files)} спец.</small>",
         "Все ежедневные выпуски и специальные материалы издания с первого дня.",
         "#archive", "var(--muted)"),
        ("🧭", "Роадмап", "v2.4",
         "Куда движется издание: фазы развития, инфраструктура, риски и метрики проекта.",
         "roadmap.html", "#1d4066"),
        ("🩺", "Статус системы", "служебная",
         "Здоровье конвейера, доступность источников, алерт-монитор, бэкапы. Реестр источников — там же.",
         "status.html", "#5b6b7c"),
    ]
    sec_cards = ""
    for ic, t, fig, dsc, href, color in cards:
        inner = f"""<div class="ic">{ic}</div><b>{esc(t)}</b><div class="fig">{fig}</div>
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
<style>{CSS}{INDEX_CSS}</style></head><body>

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
<a class="chip" href="digests/{latest_digest}" style="color:#ffe9b8;">Свежий выпуск →</a>
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
<div class="now-h">📅 Сегодня в области</div>
{tev}
</div>
<div class="now-col">
<div class="now-h">📊 Картина момента</div>
<div class="now-num">{n24} <small>публикаций за 24 ч</small></div>
<div class="now-line">тема часа: <b>{esc(top_topic[1]['name']) if top_topic else '—'}</b> ({top_topic[1]['today'] if top_topic else 0} упом.)</div>
<div class="now-line">тон повестки: <b>{tone:+.2f}</b> — {tone_txt}</div>
<div class="now-line">до дня голосования: <b>{d_vote} дн.</b></div>
<div class="now-line">погода: {esc(weather) if weather else '—'}</div>
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

<footer class="footer"><div class="footer-inner">
<div><b>Гудок</b><p>{esc(cfg['tagline_full'])} Выходит ежедневно в 07:30 (UTC+4).</p></div>
<div><b>Разделы</b><p><a href="digests/{latest_digest}" style="color:#ffd47e;">Свежий выпуск</a> · <a href="afisha.html" style="color:#ffd47e;">Афиша</a> · <a href="special/elections_2026.html" style="color:#ffd47e;">Выборы-2026</a> · <a href="infospace.html" style="color:#ffd47e;">Инфопространство</a> · <a href="roadmap.html" style="color:#ffd47e;">Роадмап</a> · <a href="status.html" style="color:#ffd47e;">Статус</a></p></div>
<div><b>Редакция</b><p>Мониторинг {sum(1 for c in cfg.get('telegram_channels',[]) if c.get('enabled'))} Telegram-каналов и {sum(1 for c in cfg.get('rss_sources',[]) if c.get('enabled',True))} RSS-лент. Колонку редактора и аналитику готовит ассистент. Реестр источников и здоровье конвейера — на <a href="status.html" style="color:#ffd47e;">status-странице</a>.</p></div>
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
        html = html.replace("</head>", THEME_HEAD + "</head>", 1)
        return html.replace("</body>", THEME_FOOT + "</body>", 1)

    digest_html = themed(render_digest(cfg, trends, store, status, date_str, digest_no))
    with open(target, "w", encoding="utf-8") as f:
        f.write(digest_html)

    if args.elections:
        os.makedirs(SPECIAL, exist_ok=True)
        el_html = themed(render_elections(cfg, trends, store, status))
        with open(os.path.join(SPECIAL, "elections_2026.html"), "w", encoding="utf-8") as f:
            f.write(el_html)
        print("[generate] спецвыпуск: special/elections_2026.html")

    if args.exec_mode:
        exec_html = themed(render_exec(cfg, trends, store, status, date_str))
        exec_path = os.path.join(DIGESTS, f"exec_{date_str}.html")
        with open(exec_path, "w", encoding="utf-8") as f:
            f.write(exec_html)
        print(f"[generate] дайджест руководителя: digests/exec_{date_str}.html")

    afisha_html = themed(render_afisha(cfg, trends, store, status,
                                        load_json(os.path.join(DATA, "analytics.json")) or {}))
    infospace_html = themed(render_infospace(cfg, trends, store, status,
                                             load_json(os.path.join(DATA, "infospace.json")) or {}))
    with open(os.path.join(BASE, "infospace.html"), "w", encoding="utf-8") as f:
        f.write(infospace_html)
    print("[generate] инфопространство: infospace.html")
    with open(os.path.join(BASE, "afisha.html"), "w", encoding="utf-8") as f:
        f.write(afisha_html)
    print("[generate] афиша: afisha.html")

    special_files = sorted(glob.glob(os.path.join(SPECIAL, "*.html")))
    index_html = themed(render_index(cfg, trends, store, status, digest_files, special_files))
    with open(os.path.join(BASE, "index.html"), "w", encoding="utf-8") as f:
        f.write(index_html)

    print(f"[generate] выпуск №{digest_no}: digests/digest_{date_str}.html")
    print(f"[generate] витрина: index.html (архив: {len(digest_files)} выпусков, спец: {len(special_files)})")


if __name__ == "__main__":
    main()
