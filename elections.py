#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""elections.py — проект «Выборы»: реестр избирательных кампаний Ульяновской области.

Страница projects/elections.html строится из этого реестра — указателя кампаний
архива выборов и референдумов Избирательной комиссии Ульяновской области:
http://www.ulyanovsk.izbirkom.ru/arkhiv-vyborov-i-referendumov/

v0.1 — РЕЕСТР-УКАЗАТЕЛЬ (по образцу pressa.py, plans.py): каждая карточка —
кампания: дата, уровень, тип, состав, ссылка на раздел архива, статус и метка
сверки с архивом. Цифры (кандидаты, явка, результаты, протоколы УИК) в этой
версии НЕ собираются: полноценная коллекция — серверная фаза (см. ROADMAP.md),
после переезда с GitHub Pages. Здесь страница даёт вёрстку раздела и каркас
для будущего коллектора (elections_collector.py, задержка опроса из
config.json → settings/izbirkom_delay_sec).

Каталог правится редакцией вручную, как plans.py/pressa.py. Даты и составы
сверены с архивом ИКУО по состоянию на 24.09.2026.
"""

SOURCE_URL = "http://www.ulyanovsk.izbirkom.ru/arkhiv-vyborov-i-referendumov/"
ARCHIVE_ROOT = "http://www.ulyanovsk.izbirkom.ru"
CHECK_DATE = "24.09.2026"

LEVELS = (
    ("federal", "Федеральные"),
    ("region", "Региональные"),
    ("muni", "Муниципальные"),
)

KINDS = (
    ("president", "президент РФ"),
    ("gd", "Государственная Дума"),
    ("gubernator", "губернатор"),
    ("zso", "Законодательное Собрание"),
    ("muni", "муниципальные депутаты"),
    ("ref", "референдум / общероссийское голосование"),
)

STATUS = (("reg", "реестр"),)

# level ->  краткое описание группы для страницы
LEVEL_DESC = {
    "federal": "Президент РФ, Государственная Дума, общероссийское голосование — кампании федерального уровня, проходившие в регионе.",
    "region": "Губернатор области, депутаты Законодательного Собрания, включая довыборы по округам.",
    "muni": "Городская дума Ульяновска, советы поселений и районов, довыборы по муниципальным округам.",
}

CAMPAIGNS = [
    # --------------------------------------------------------------- 2009–2012
    {
        "id": "e20091110",
        "date": "2009-10-11",
        "label": "11 октября 2009",
        "level": "muni",
        "kind": "muni",
        "title": "Муниципальные выборы",
        "desc": "Выборы депутатов представительных органов муниципальных образований области.",
        "arch": "/11-10-2009-munitsipalnye-vybory/index.php",
        "extra": False,
        "status": "реестр",
        "verify": "архив ИКУО · " + CHECK_DATE,
    },
    {
        "id": "e20100314_u",
        "date": "2010-03-14",
        "label": "14 марта 2010",
        "level": "muni",
        "kind": "muni",
        "title": "Муниципальные выборы в МО «город Ульяновск»",
        "desc": "Городская избирательная кампания 2010 года.",
        "arch": "/14-03-2010-munitsipalnye-vybory-v-mo-gorod-ulyanovsk/index.php",
        "extra": False,
        "status": "реестр",
        "verify": "архив ИКУО · " + CHECK_DATE,
    },
    {
        "id": "e20100314_v",
        "date": "2010-03-14",
        "label": "14 марта 2010",
        "level": "muni",
        "kind": "muni",
        "title": "Муниципальные выборы в МО «Вешкаймский район»",
        "desc": "Выборы в представительные органы Вешкаймского района.",
        "arch": "/14-03-2010-munitsipalnye-vybory-v-mo-veshkaymskiy-rayon/index.php",
        "extra": False,
        "status": "реестр",
        "verify": "архив ИКУО · " + CHECK_DATE,
    },
    {
        "id": "e20110313",
        "date": "2011-03-13",
        "label": "13 марта 2011",
        "level": "muni",
        "kind": "muni",
        "title": "Муниципальные выборы в МО «Ульяновский район»",
        "desc": "Выборы в представительные органы Ульяновского района.",
        "arch": "/13-03-2011-munitsipalnye-vybory-v-mo-ulyanovskiy-rayon/index.php",
        "extra": False,
        "status": "реестр",
        "verify": "архив ИКУО · " + CHECK_DATE,
    },
    {
        "id": "e20111204_gd",
        "date": "2011-12-04",
        "label": "4 декабря 2011",
        "level": "federal",
        "kind": "gd",
        "title": "Выборы депутатов Государственной Думы VI созыва",
        "desc": "Выборы по федеральному округу и одномандатным округам региона.",
        "arch": "/04-12-2011-vybory-deputatov-gosudarstvennoy-dumy-federalnogo-sobraniya-rossiyskoy-federatsii-shestog/index.php",
        "extra": False,
        "status": "реестр",
        "verify": "архив ИКУО · " + CHECK_DATE,
    },
    {
        "id": "e20111204_edg",
        "date": "2011-12-04",
        "label": "4 декабря 2011",
        "level": "region",
        "kind": "zso",
        "title": "Единый день голосования 4 декабря 2011 года",
        "desc": "Региональные и муниципальные кампании дня голосования.",
        "arch": "/04-12-2011-edinyy-den-golosovaniya/index.php",
        "extra": False,
        "status": "реестр",
        "verify": "архив ИКУО · " + CHECK_DATE,
    },
    {
        "id": "e20120304",
        "date": "2012-03-04",
        "label": "4 марта 2012",
        "level": "federal",
        "kind": "president",
        "title": "Выборы Президента Российской Федерации",
        "desc": "Федеральная кампания, голосование на участках региона.",
        "arch": "/04-03-2012-v-bory-prezidenta-rossiyskoy-federatsi/index.php",
        "extra": False,
        "status": "реестр",
        "verify": "архив ИКУО · " + CHECK_DATE,
    },
    {
        "id": "e20121014",
        "date": "2012-10-14",
        "label": "14 октября 2012",
        "level": "region",
        "kind": "zso",
        "title": "Единый день голосования 14 октября 2012 года",
        "desc": "Региональные и муниципальные кампании дня голосования.",
        "arch": "/14-10-2012-edinyy-den-golosovaniya/index.php",
        "extra": False,
        "status": "реестр",
        "verify": "архив ИКУО · " + CHECK_DATE,
    },
    # --------------------------------------------------------------- 2013–2016
    {
        "id": "e20130317",
        "date": "2013-03-17",
        "label": "17 марта 2013",
        "level": "muni",
        "kind": "muni",
        "title": "Дополнительные выборы в Ульяновскую городскую думу",
        "desc": "Довыборы депутатов по одномандатным округам городской думы.",
        "arch": "/17-03-2013-dopolnitelnye-vybory-v-ulyanovskuyu-gorodskuyu-dumu/index.php",
        "extra": True,
        "status": "реестр",
        "verify": "архив ИКУО · " + CHECK_DATE,
    },
    {
        "id": "e20130908",
        "date": "2013-09-08",
        "label": "8 сентября 2013",
        "level": "region",
        "kind": "zso",
        "title": "Единый день голосования 8 сентября 2013 года",
        "desc": "Региональные и муниципальные кампании дня голосования.",
        "arch": "/08-09-2013-edinyy-den-golosovaniya/index.php",
        "extra": False,
        "status": "реестр",
        "verify": "архив ИКУО · " + CHECK_DATE,
    },
    {
        "id": "e20140427",
        "date": "2014-04-27",
        "label": "27 апреля 2014",
        "level": "muni",
        "kind": "muni",
        "title": "Дополнительные выборы в Ульяновскую городскую думу",
        "desc": "Довыборы депутатов по одномандатным округам городской думы.",
        "arch": "/27-04-2014-dopolnitelnye-vybory-v-ulyanovskuyu-gorodskuyu-dumu/index.php",
        "extra": True,
        "status": "реестр",
        "verify": "архив ИКУО · " + CHECK_DATE,
    },
    {
        "id": "e20140914",
        "date": "2014-09-14",
        "label": "14 сентября 2014",
        "level": "region",
        "kind": "zso",
        "title": "Единый день голосования 14 сентября 2014 года",
        "desc": "Региональные и муниципальные кампании дня голосования.",
        "arch": "/14-09-2014-edinyy-den-golosovaniya-/index.php",
        "extra": False,
        "status": "реестр",
        "verify": "архив ИКУО · " + CHECK_DATE,
    },
    {
        "id": "e20150419",
        "date": "2015-04-19",
        "label": "19 апреля 2015",
        "level": "muni",
        "kind": "muni",
        "title": "Дополнительные выборы в МО «Ульяновский район»",
        "desc": "Довыборы в представительные органы Ульяновского района.",
        "arch": "/19-04-2015-dopolnitelnye-vybory-v-mo-ulyanovskiy-rayon/index.php",
        "extra": True,
        "status": "реестр",
        "verify": "архив ИКУО · " + CHECK_DATE,
    },
    {
        "id": "e20150621",
        "date": "2015-06-21",
        "label": "21 июня 2015",
        "level": "muni",
        "kind": "muni",
        "title": "Муниципальные выборы в МО «Чердаклинский район»",
        "desc": "Выборы в представительные органы Чердаклинского района.",
        "arch": "/21-06-2015-munitsipalnye-vybory-v-mo-cherdaklinskiy-rayon/index.php",
        "extra": False,
        "status": "реестр",
        "verify": "архив ИКУО · " + CHECK_DATE,
    },
    {
        "id": "e20150913",
        "date": "2015-09-13",
        "label": "13 сентября 2015",
        "level": "region",
        "kind": "gubernator",
        "title": "Единый день голосования 13 сентября 2015 года",
        "desc": "Выборы Губернатора Ульяновской области и муниципальные кампании.",
        "arch": "/13-09-2015-edinyy-den-golosovaniya/index.php",
        "extra": False,
        "status": "реестр",
        "verify": "архив ИКУО · " + CHECK_DATE,
    },
    {
        "id": "e20160417",
        "date": "2016-04-17",
        "label": "17 апреля 2016",
        "level": "muni",
        "kind": "muni",
        "title": "Дополнительные выборы в МО «Вешкаймский район»",
        "desc": "Довыборы в представительные органы Вешкаймского района.",
        "arch": "/17-04-2016-dopolnitelnye-vybory-v-mo-veshkaymskiy-rayon/index.php",
        "extra": True,
        "status": "реестр",
        "verify": "архив ИКУО · " + CHECK_DATE,
    },
    {
        "id": "e20160918",
        "date": "2016-09-18",
        "label": "18 сентября 2016",
        "level": "federal",
        "kind": "gd",
        "title": "Единый день голосования 18 сентября 2016 года",
        "desc": "Выборы депутатов Государственной Думы VII созыва, ЗСО и муниципальные кампании.",
        "arch": "/18-09-2016-edinyy-den-golosovaniya/index.php",
        "extra": False,
        "status": "реестр",
        "verify": "архив ИКУО · " + CHECK_DATE,
    },
    # --------------------------------------------------------------- 2016–2020
    {
        "id": "e20161225",
        "date": "2016-12-25",
        "label": "25 декабря 2016",
        "level": "region",
        "kind": "zso",
        "title": "Дополнительные выборы депутата Законодательного Собрания пятого созыва",
        "desc": "Довыборы по одномандатному округу ЗСО.",
        "arch": "/25-12-2016-dopolnitelnye-vybory-deputata-zakonodatelnogo-sobraniya-ulyanovskoy-oblasti-pyatogo-sozyv/index.php",
        "extra": True,
        "status": "реестр",
        "verify": "архив ИКУО · " + CHECK_DATE,
    },
    {
        "id": "e20170409",
        "date": "2017-04-09",
        "label": "9 апреля 2017",
        "level": "muni",
        "kind": "muni",
        "title": "Дополнительные муниципальные выборы",
        "desc": "Довыборы в представительные органы муниципалитетов области.",
        "arch": "/09-04-2017-dopolnitelnye-munitsipalnye-vybory/index.php",
        "extra": True,
        "status": "реестр",
        "verify": "архив ИКУО · " + CHECK_DATE,
    },
    {
        "id": "e20170730",
        "date": "2017-07-30",
        "label": "30 июля 2017",
        "level": "muni",
        "kind": "muni",
        "title": "Дополнительные выборы в МО «Цильнинский район»",
        "desc": "Довыборы в представительные органы Цильнинского района.",
        "arch": "/30-07-2017-dopolnitelnye-vybory-v-mo-tsilninskiy-rayon/index.php",
        "extra": True,
        "status": "реестр",
        "verify": "архив ИКУО · " + CHECK_DATE,
    },
    {
        "id": "e20170813",
        "date": "2017-08-13",
        "label": "13 августа 2017",
        "level": "muni",
        "kind": "muni",
        "title": "Дополнительные выборы в МО «Инзенский район»",
        "desc": "Довыборы в представительные органы Инзенского района.",
        "arch": "/13-08-2017-dopolnitelnye-vybory-v-mo-inzenskiy-rayon/index.php",
        "extra": True,
        "status": "реестр",
        "verify": "архив ИКУО · " + CHECK_DATE,
    },
    {
        "id": "e20170910",
        "date": "2017-09-10",
        "label": "10 сентября 2017",
        "level": "region",
        "kind": "zso",
        "title": "Единый день голосования 10 сентября 2017 года",
        "desc": "Региональные и муниципальные кампании дня голосования.",
        "arch": "/10-09-2017-edinyy-den-golosovaniya/index.php",
        "extra": False,
        "status": "реестр",
        "verify": "архив ИКУО · " + CHECK_DATE,
    },
    {
        "id": "e20180318",
        "date": "2018-03-18",
        "label": "18 марта 2018",
        "level": "federal",
        "kind": "president",
        "title": "Выборы Президента Российской Федерации",
        "desc": "Федеральная кампания, голосование на участках региона.",
        "arch": "/18-03-2018-vybory-prezidenta-rossiyskoy-federatsii/index.php",
        "extra": False,
        "status": "реестр",
        "verify": "архив ИКУО · " + CHECK_DATE,
    },
    {
        "id": "e20180909",
        "date": "2018-09-09",
        "label": "9 сентября 2018",
        "level": "region",
        "kind": "zso",
        "title": "Единый день голосования 9 сентября 2018 года",
        "desc": "Региональные и муниципальные кампании дня голосования.",
        "arch": "/09-09-2018-edinyy-den-golosovaniya/index.php",
        "extra": False,
        "status": "реестр",
        "verify": "архив ИКУО · " + CHECK_DATE,
    },
    {
        "id": "e20190908",
        "date": "2019-09-08",
        "label": "8 сентября 2019",
        "level": "region",
        "kind": "zso",
        "title": "Единый день голосования 8 сентября 2019 года",
        "desc": "Региональные и муниципальные кампании дня голосования.",
        "arch": "/08-09-2019-edinyy-den-golosovaniya/index.php",
        "extra": False,
        "status": "реестр",
        "verify": "архив ИКУО · " + CHECK_DATE,
    },
    {
        "id": "e20200701",
        "date": "2020-07-01",
        "label": "25 июня – 1 июля 2020",
        "level": "federal",
        "kind": "ref",
        "title": "Общероссийское голосование по поправкам к Конституции Российской Федерации",
        "desc": "Голосование в регионе 25.06–01.07.2020, раздел архива датирован 22.04.2020.",
        "arch": "/22-04-2020-konstitutsiya/index.php",
        "extra": False,
        "status": "реестр",
        "verify": "архив ИКУО · " + CHECK_DATE,
    },
    {
        "id": "e20200913",
        "date": "2020-09-13",
        "label": "13 сентября 2020",
        "level": "region",
        "kind": "zso",
        "title": "Единый день голосования 13 сентября 2020 года",
        "desc": "Региональные и муниципальные кампании дня голосования.",
        "arch": "/13-09-2020-edg/index.php",
        "extra": False,
        "status": "реестр",
        "verify": "архив ИКУО · " + CHECK_DATE,
    },
    # --------------------------------------------------------------- 2021–2026
    {
        "id": "e20210919",
        "date": "2021-09-19",
        "label": "17–19 сентября 2021",
        "level": "federal",
        "kind": "gd",
        "title": "Единый день голосования 19 сентября 2021 года",
        "desc": "Выборы депутатов Государственной Думы VIII созыва, Губернатора Ульяновской области, ЗСО и муниципальные кампании.",
        "arch": "/19-09-2021-edinyy-den-golosovaniya/index.php",
        "extra": False,
        "status": "реестр",
        "verify": "архив ИКУО · " + CHECK_DATE,
    },
    {
        "id": "e20220911",
        "date": "2022-09-11",
        "label": "9–11 сентября 2022",
        "level": "region",
        "kind": "zso",
        "title": "Единый день голосования 11 сентября 2022 года",
        "desc": "Региональные и муниципальные кампании дня голосования.",
        "arch": "/11-09-2022-edinyy-den-golosovaniya/index.php",
        "extra": False,
        "status": "реестр",
        "verify": "архив ИКУО · " + CHECK_DATE,
    },
    {
        "id": "e20230910",
        "date": "2023-09-10",
        "label": "8–10 сентября 2023",
        "level": "region",
        "kind": "zso",
        "title": "Единый день голосования 10 сентября 2023 года",
        "desc": "Региональные и муниципальные кампании дня голосования.",
        "arch": "/10-09-2023-edinyy-den-golosovaniya/index.php",
        "extra": False,
        "status": "реестр",
        "verify": "архив ИКУО · " + CHECK_DATE,
    },
    {
        "id": "e20240317",
        "date": "2024-03-17",
        "label": "15–17 марта 2024",
        "level": "federal",
        "kind": "president",
        "title": "Выборы Президента Российской Федерации",
        "desc": "Трёхдневное голосование на участках региона.",
        "arch": "/17-03-2024-vybory-prezidenta-rf/index.php",
        "extra": False,
        "status": "реестр",
        "verify": "архив ИКУО · " + CHECK_DATE,
    },
    {
        "id": "e20240908",
        "date": "2024-09-08",
        "label": "6–8 сентября 2024",
        "level": "federal",
        "kind": "gd",
        "title": "Дополнительные выборы депутатов Государственной Думы",
        "desc": "Довыборы по одномандатному избирательному округу на территории области.",
        "arch": "/08-09-2024-dopolnitelnye-vybory-gd/index.php",
        "extra": True,
        "status": "реестр",
        "verify": "архив ИКУО · " + CHECK_DATE,
    },
    {
        "id": "e20250914",
        "date": "2025-09-14",
        "label": "13–14 сентября 2025",
        "level": "muni",
        "kind": "muni",
        "title": "Выборы депутатов Ульяновской городской думы",
        "desc": "Основная муниципальная кампания года в областном центре.",
        "arch": "/14-09-2025-vybory-gorodskaya-duma/index.php",
        "extra": False,
        "status": "реестр",
        "verify": "архив ИКУО · " + CHECK_DATE,
    },
    {
        "id": "e20260918",
        "date": "2026-09-18",
        "label": "18–20 сентября 2026",
        "level": "region",
        "kind": "gubernator",
        "title": "Единый день голосования 20 сентября 2026 года",
        "desc": "Выборы Губернатора Ульяновской области, депутатов Государственной Думы по округам № 185 и 186, кандидата в депутаты ЗСО по двухмандатному Вешкаймскому округу № 2, муниципальные кампании.",
        "arch": "/arkhiv-vyborov-i-referendumov/20-09-2026-vybory-gubernatora-i-gd/",
        "extra": False,
        "status": "реестр",
        "verify": "архив ИКУО · " + CHECK_DATE,
    },
]


def by_kind(kind):
    """Кампании одного типа."""
    return [c for c in CAMPAIGNS if c["kind"] == kind]


def by_level(level):
    """Кампании одного уровня ('federal' | 'region' | 'muni')."""
    return [c for c in CAMPAIGNS if c["level"] == level]


def counts_levels():
    """Число кампаний по уровням (порядок как в LEVELS)."""
    return {lv: len(by_level(lv)) for lv, _ in LEVELS}


def counts_kinds():
    """Число кампаний по типам."""
    return {kind: len(by_kind(kind)) for kind, _ in KINDS}


def years_span():
    """Диапазон лет охвата реестра, например '2009–2026'."""
    years = sorted(c["date"][:4] for c in CAMPAIGNS)
    return f"{years[0]}–{years[-1]}"


def total():
    """Число кампаний в реестре."""
    return len(CAMPAIGNS)


if __name__ == "__main__":
    print("Кампаний в реестре:", total(), "(годы", years_span() + ")")
    for lvl, _ in LEVELS:
        print(" ", lvl, counts_levels()[lvl])
    for kind, _ in KINDS:
        n = counts_kinds()[kind]
        if n:
            print("  ·", kind, n)