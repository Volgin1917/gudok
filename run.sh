#!/usr/bin/env bash
# run.sh — полный цикл выпуска дайджеста издание «Гудок»
# сбор (RSS+TG) -> обогащение -> дедупликация -> тренды -> генерация (дайджест + для руководителя)
set -e
cd "$(dirname "$0")"

DATE="${1:-}"   # необязательный аргумент: дата выпуска YYYY-MM-DD

python3 collector.py --quiet
python3 enrich.py --max 40 --quiet || true
python3 photos.py --quiet || true || echo "⚠️ enrich: часть источников недоступна — использованы RSS-тексты"
python3 dedup.py --quiet
python3 trends.py
python3 backup.py --quiet
python3 status.py >/dev/null
# спецвыпуск «Выборы-2026» обновляется ежедневно, пока существует
if [ -f special/elections_2026.html ] || [ "$(date +%Y%m%d)" -le 20260921 ]; then
  python3 generate.py --elections >/dev/null 2>&1 || true
fi
if [ -n "$DATE" ]; then
  python3 generate.py --exec --date "$DATE"
else
  python3 generate.py --exec
fi

echo "✅ Готово: index.html и digests/ обновлены ($(date '+%d.%m.%Y %H:%M'))"
