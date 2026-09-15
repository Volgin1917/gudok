#!/usr/bin/env bash
# ci_push.sh — коммит и публикация результата прогона без гонок с ручным push.
#
# Зачем: workflow гоняют конвейер и пушат в main. Если за время прогона в main
# успел запушить человек (или соседний workflow), обычный `git push` падает с
# «! [rejected] … (fetch first)» и выпуск теряется (кейс 15.09.2026: прогон
# на 7a50309 упал на шаге «Коммит», Pages не опубликовался).
#
# Стратегия (та же, что вручную при слиянии с бот-выпуском):
#   1) закоммитить сгенерированное;
#   2) fetch + rebase поверх свежего origin/<ветка> — быстрый путь, чужие
#      коммиты (данные и код) сохраняются;
#   3) если rebase упёрся в конфликт (обе стороны пересобрали одни и те же
#      файлы) — берём состояние origin/<ветка> как есть и ПЕРЕСОБИРАЕМ
#      конвейер заново: так не теряются ни чужие данные (data/store.jsonl),
#      ни чужой код (generate.py/analytics.py);
#   4) push с несколькими попытками: между rebase и push снова может прилететь
#      чужой коммит — тогда цикл повторяется.
#
# Использование:
#   bash ci_push.sh "<сообщение коммита>" [пути для git add …]
# Переменные окружения:
#   REBUILD_CMD   — команда пересборки для шага 3 (по умолчанию «bash run.sh»);
#                   для недельника: «bash run.sh && python3 generate.py --weekly-new»
#   GIT_BOT_NAME / GIT_BOT_EMAIL — автор коммита (по умолчанию gudok-bot)
#   CI_PUSH_ATTEMPTS — число попыток push (по умолчанию 4)
set -uo pipefail

MSG="${1:-Выпуск $(date -u +%F)}"
shift || true
if [ "$#" -gt 0 ]; then
  PATHS=("$@")
else
  PATHS=(data digests index.html afisha.html infospace.html status.html
         weekly.html monthly.html projects.html projects weekly monthly)
fi

BRANCH="${GITHUB_REF_NAME:-$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo main)}"
REBUILD="${REBUILD_CMD:-bash run.sh}"
ATTEMPTS="${CI_PUSH_ATTEMPTS:-4}"

git config user.name  "${GIT_BOT_NAME:-gudok-bot}"
git config user.email "${GIT_BOT_EMAIL:-gudok-bot@users.noreply.github.com}"

# ── 1) коммит ────────────────────────────────────────────────────────────
git add -- "${PATHS[@]}" 2>/dev/null || true
if git diff --cached --quiet; then
  echo "[ci_push] изменений нет — коммит не создаётся"
else
  git commit -q -m "$MSG"
  echo "[ci_push] коммит: $(git log -1 --format='%h %s' | cut -c1-90)"
fi

# ── 2–4) fetch → rebase (или пересборка) → push, с повторами ─────────────
for i in $(seq 1 "$ATTEMPTS"); do
  if ! git fetch -q origin "$BRANCH"; then
    echo "[ci_push] fetch не удался (попытка $i/$ATTEMPTS), ждём 15 с"
    sleep 15
    continue
  fi

  if [ "$(git rev-parse HEAD)" != "$(git rev-parse "origin/$BRANCH")" ]; then
    if git rebase "origin/$BRANCH" >/dev/null 2>&1; then
      echo "[ci_push] rebase поверх origin/$BRANCH — ок"
    else
      git rebase --abort >/dev/null 2>&1 || true
      echo "[ci_push] rebase с конфликтом: берём origin/$BRANCH и пересобираем"
      git reset --hard -q "origin/$BRANCH"
      if ! eval "$REBUILD" >/dev/null 2>&1; then
        echo "[ci_push] ⚠️ пересборка завершилась с ошибкой — публикуем как есть"
      fi
      git add -- "${PATHS[@]}" 2>/dev/null || true
      if git diff --cached --quiet; then
        echo "[ci_push] после пересборки изменений нет"
      else
        git commit -q -m "$MSG (пересборка после слияния с origin/$BRANCH)"
        echo "[ci_push] коммит пересборки: $(git log -1 --format='%h %s' | cut -c1-90)"
      fi
    fi
  fi

  if git push origin "HEAD:$BRANCH"; then
    echo "[ci_push] запушено: $(git log -1 --format='%h %s' | cut -c1-90)"
    exit 0
  fi

  echo "[ci_push] push отклонён (попытка $i/$ATTEMPTS) — повторяем через 15 с"
  sleep 15
done

echo "[ci_push] ✖ не удалось запушить за $ATTEMPTS попыток"
git status -sb | head -20
exit 1
