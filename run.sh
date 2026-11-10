#!/usr/bin/env bash
# run.sh — полный цикл выпуска дайджеста издание «Гудок»
# сбор (RSS+TG) -> обогащение -> дедупликация -> тренды -> генерация (дайджест + для руководителя)
# run.sh [YYYY-MM-DD] [--publish] — --publish дополнительно отправит дайджест в Telegram
set -e
cd "$(dirname "$0")"

DATE=""   # необязательный аргумент: дата выпуска YYYY-MM-DD
PUBLISH=0 # --publish: отправить дайджест в Telegram после сборки (иначе только локально)
for a in "$@"; do
  case "$a" in
    --publish) PUBLISH=1 ;;
    *) [ -z "$DATE" ] && DATE="$a" ;;
  esac
done

python3 collector.py --quiet
python3 enrich.py --max 40 --quiet || true
python3 photos.py --quiet || true || echo "⚠️ enrich: часть источников недоступна — использованы RSS-тексты"
python3 dedup.py --quiet
python3 trends.py
python3 backup.py --quiet
python3 status.py >/dev/null
if [ -n "$DATE" ]; then
  python3 generate.py --exec --date "$DATE"
else
  python3 generate.py --exec
fi

if [ "$PUBLISH" = "1" ]; then
  if [ -n "$DATE" ]; then
    python3 tg_publish.py --digest --date "$DATE" || true
  else
    python3 tg_publish.py --digest || true
  fi
  # «Картина дня» (Yandex ART) — отдельный модуль; без ключа мягко пропускается
  python3 picture_of_day.py --publish || true
fi

echo "✅ Готово: index.html и digests/ обновлены ($(date '+%d.%m.%Y %H:%M'))"
