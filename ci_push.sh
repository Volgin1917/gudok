#!/usr/bin/env bash
# ci_push.sh — коммит и публикация результата прогона без гонок с ручным push.
#
# Зачем: workflow гоняют конвейер и пушат в main. Если за время прогона в main
# успел запушить человек (или соседний workflow), обычный `git push` падает с
# «! [rejected] … (fetch first)» и выпуск теряется (кейс 15.09.2026: прогон
# на 7a50309 упал на шаге «Коммит», Pages не опубликовался).
#
# Стратегия:
#   1) закоммитить изменения (по умолчанию ВСЕ — git add -A; CI передаёт явный
#      список сгенерированных путей) и проверить, что рабочее дерево чистое:
#      незамеченные правки кода — это потерянная работа (кейс 15.09.2026 №2);
#   2) fetch + rebase поверх свежего origin/<ветка> — быстрый путь, чужие
#      коммиты (данные и код) сохраняются;
#   3) если rebase упёрся в конфликт — решение зависит от того, ЧТО в наших
#      локальных коммитах:
#        • только сгенерированное (data/, digests/, *.html …) — типичный прогон
#          бота: берём состояние origin/<ветка> и пересобираем конвейер заново;
#        • есть код/конфиги/доки — reset --hard НЕЛЬЗЯ (сотрёт работу):
#          делаем merge -X ours (наш код остаётся, чужие неконфликтующие правки
#          подтягиваются), печатаем список конфликтов и пересобираем артефакты;
#   4) push с несколькими попытками: между rebase и push снова может прилететь
#      чужой коммит — тогда цикл повторяется.
#
# Использование:
#   bash ci_push.sh "<сообщение коммита>" [пути для git add …]
# Переменные окружения:
#   REBUILD_CMD      — команда пересборки для шага 3 (по умолчанию «bash run.sh»)
#   GIT_BOT_NAME / GIT_BOT_EMAIL — автор коммита (по умолчанию gudok-bot)
#   CI_PUSH_ATTEMPTS — число попыток push (по умолчанию 4)
set -uo pipefail

MSG="${1:-Выпуск $(date -u +%F)}"
shift || true

BRANCH="${GITHUB_REF_NAME:-$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo main)}"
REBUILD="${REBUILD_CMD:-bash run.sh}"
ATTEMPTS="${CI_PUSH_ATTEMPTS:-4}"

# сгенерированные пути: их не жалко пересобрать из чужого состояния ветки
GENERATED_RE='^(data/|digests/|weekly/|monthly/|projects/|special/|assets/|[^/]*\.html$)'

git config user.name  "${GIT_BOT_NAME:-gudok-bot}"
git config user.email "${GIT_BOT_EMAIL:-gudok-bot@users.noreply.github.com}"

# ── 1) коммит ────────────────────────────────────────────────────────────
if [ "$#" -gt 0 ]; then
  git add -- "$@" 2>/dev/null || true
else
  git add -A
fi
if git diff --cached --quiet; then
  echo "[ci_push] изменений нет — коммит не создаётся"
else
  git commit -q -m "$MSG"
  echo "[ci_push] коммит: $(git log -1 --format='%h %s' | cut -c1-90)"
fi

# страховка: если в дереве остались неотданные правки — они НЕ попадут в историю
DIRTY="$(git status --porcelain 2>/dev/null)"
if [ -n "$DIRTY" ]; then
  echo "[ci_push] ⚠️ в рабочем дереве остались незакоммиченные файлы (в push не попадут):"
  echo "$DIRTY" | head -20 | sed 's/^/[ci_push]     /'
fi

# ── 2–4) fetch → rebase/merge (или пересборка) → push, с повторами ───────
for i in $(seq 1 "$ATTEMPTS"); do
  if ! git fetch -q origin "$BRANCH"; then
    echo "[ci_push] fetch не удался (попытка $i/$ATTEMPTS), ждём 15 с"
    sleep 15
    continue
  fi

  if [ "$(git rev-parse HEAD)" != "$(git rev-parse "origin/$BRANCH")" ]; then
    # --autostash: незакоммиченное/неотслеживаемое (новые фото, archive.html) не должно
    # ронять rebase и отправлять прогон в дорогую пересборку
    if git rebase --autostash "origin/$BRANCH" >/dev/null 2>&1; then
      echo "[ci_push] rebase поверх origin/$BRANCH — ок"
    else
      git rebase --abort >/dev/null 2>&1 || true
      # что именно в наших локальных коммитах?
      LOCAL_FILES="$(git diff --name-only "origin/$BRANCH...HEAD" 2>/dev/null)"
      CODE_FILES="$(printf '%s\n' "$LOCAL_FILES" | grep -Ev "$GENERATED_RE" | grep -v '^$' || true)"
      if [ -z "$CODE_FILES" ]; then
        echo "[ci_push] конфликт, но локально только сгенерированное — берём origin/$BRANCH и пересобираем"
        git reset --hard -q "origin/$BRANCH"
      else
        echo "[ci_push] ⚠️ конфликт при наличии кода — reset --hard отменён, делаем merge -X ours"
        printf '%s\n' "$CODE_FILES" | head -20 | sed 's/^/[ci_push]     код: /'
        if ! git merge -X ours --no-edit "origin/$BRANCH" \
              -m "Слияние с origin/$BRANCH (код наш, сгенерированное пересобирается)" >/dev/null 2>&1; then
          echo "[ci_push] ✖ слияние не удалось — требуется ручное разрешение"
          git merge --abort >/dev/null 2>&1 || true
          git status -sb | head -20
          exit 1
        fi
      fi
      if ! eval "$REBUILD" >/dev/null 2>&1; then
        echo "[ci_push] ⚠️ пересборка завершилась с ошибкой — публикуем как есть"
      fi
      if [ "$#" -gt 0 ]; then
        git add -- "$@" 2>/dev/null || true
      else
        git add -A
      fi
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
