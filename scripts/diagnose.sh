#!/usr/bin/env bash
# Диагностика проекта одним запуском: гоняет группы команд, складывает вывод в .diagnose/*.log.
# Дальше достаточно сказать Claude «готово» — он сам прочитает логи (summary.log — сводка).
#
#   bash scripts/diagnose.sh                       # группы 0–4: окружение, install, proto, проверки
#   bash scripts/diagnose.sh --mock                # + Prism по openapi.yaml (нужен npx и интернет)
#   bash scripts/diagnose.sh --docker              # + docker compose up --build, health, make smoke, down
#   SPIKE_URLS="https://ok.ru/group/<id>/topics https://max.ru/<канал>" bash scripts/diagnose.sh
#                                                  # + проба страниц OK/MAX для spike B1-01
#
# Что меняет: создаёт .env, если его нет; ставит зависимости (uv sync); `make proto`
# перегенерирует packages/platform_contracts и docs/ (это нужно для TL-02).
# Секреты не печатаются: .env сравнивается только по именам переменных, значения в логах маскируются.

cd "$(dirname "$0")/.." || exit 1
LOG=.diagnose
rm -rf "$LOG" && mkdir -p "$LOG"
SUMMARY="$LOG/summary.log"
WITH_MOCK=0; WITH_DOCKER=0
for arg in "$@"; do
  case "$arg" in
    --mock) WITH_MOCK=1 ;;
    --docker) WITH_DOCKER=1 ;;
    *) echo "неизвестный аргумент: $arg"; exit 2 ;;
  esac
done

# run <имя-лога> <таймаут-сек> <команда...> — вывод в лог, код и время в summary
run() {
  local name=$1 limit=$2; shift 2
  local file="$LOG/$name.log" start=$SECONDS
  { echo "\$ $*"; echo "── $(date '+%F %T')"; } > "$file"
  timeout "$limit" "$@" >> "$file" 2>&1
  local code=$?
  [ "$code" = 124 ] && echo "!! таймаут ${limit}с" >> "$file"
  echo "── код выхода: $code, $((SECONDS - start)) с" >> "$file"
  printf '%-34s код=%-3s %4ss\n' "$name" "$code" "$((SECONDS - start))" | tee -a "$SUMMARY"
}
# runsh — то же для строки shell (пайпы, циклы)
runsh() { local name=$1 limit=$2 cmd=$3; run "$name" "$limit" bash -c "$cmd"; }

echo "Диагностика $(date '+%F %T'), папка: $(pwd)" | tee "$SUMMARY"

# ── 0. окружение ─────────────────────────────────────────────
runsh 00-versions 60 '
  uname -a; echo; cat .python-version 2>/dev/null | sed "s/^/.python-version: /"
  for c in "uv --version" "python3 --version" "docker --version" "docker compose version" \
           "node --version" "npm --version" "make --version | head -1" "git --version"; do
    printf "%-28s" "$c"; (eval "$c" 2>&1 | head -1) || echo "нет"
  done'
runsh 01-git 60 '
  git branch --show-current; git log -3 --oneline; echo; git status --short | head -80'
runsh 02-network 120 '
  for u in https://pypi.org https://files.pythonhosted.org https://github.com https://registry.npmjs.org \
           https://ok.ru https://m.ok.ru https://max.ru https://api.vk.com/method/utils.getServerTime \
           https://searchapi.api.cloud.yandex.net https://api.max.ru; do
    printf "%-60s" "$u"; curl -s -o /dev/null -m 8 -w "%{http_code}\n" "$u"
  done'
runsh 03-env-keys 30 '
  test -f .env || { echo ".env нет"; exit 0; }
  keys() { grep -E "^[A-Za-z_][A-Za-z0-9_]*=" "$1" | cut -d= -f1 | sort -u; }
  echo "в .env.example, но нет в .env:"; comm -23 <(keys .env.example) <(keys .env) | sed "s/^/  /"
  echo "в .env, но нет в .env.example:"; comm -13 <(keys .env.example) <(keys .env) | sed "s/^/  /"
  echo "пустые значения в .env (имена):"
  grep -E "^[A-Za-z_][A-Za-z0-9_]*=\s*$" .env | cut -d= -f1 | sed "s/^/  /"'

# ── 1. install ───────────────────────────────────────────────
run 10-make-install 900 make install

# ── 2. proto + справочники ───────────────────────────────────
run 20-make-proto 600 make proto
runsh 21-after-proto 60 '
  git status --short -- packages contracts docs | head -60; echo
  git diff --stat -- packages contracts docs | tail -25; echo
  ls packages/platform_contracts/src; ls packages/platform_contracts/src/*/v1 2>/dev/null | head -40'

# ── 3. проверки по сервисам (не останавливаемся на первой ошибке) ──
for s in $(ls services); do
  [ -d "services/$s" ] || continue
  run "30-ruff-$s" 300 bash -c "cd services/$s && uv run ruff check . && uv run ruff format --check ."
  run "31-mypy-$s" 600 bash -c "cd services/$s && uv run mypy src"
  run "32-pytest-$s" 600 bash -c "cd services/$s && uv run pytest -q"
done

# ── 4. опционально ───────────────────────────────────────────
if [ -n "${SPIKE_URLS:-}" ]; then
  run 50-spike-probe 300 python3 services/collector_service/scripts/spike_probe.py --save $SPIKE_URLS
fi

if [ "$WITH_MOCK" = 1 ]; then
  runsh 60-prism 180 '
    (npx --yes @stoplight/prism-cli@5 mock contracts/http/openapi.yaml -p 4010 >.diagnose/prism-server.out 2>&1 &) ; sleep 25
    for p in /api/v1/platforms /api/v1/sources "/api/v1/searches?limit=2"; do
      echo "GET $p"; curl -s -m 10 -w "\n[%{http_code}]\n" "http://localhost:4010$p" | head -c 700; echo
    done
    echo "POST /api/v1/query/analyze"
    curl -s -m 10 -X POST -H "content-type: application/json" -d "{\"query\":\"ДТП Красноярск\"}" \
      -w "\n[%{http_code}]\n" http://localhost:4010/api/v1/query/analyze | head -c 700
    pkill -f "prism-cli.*mock" ; echo; tail -20 .diagnose/prism-server.out'
fi

if [ "$WITH_DOCKER" = 1 ]; then
  run 70-compose-services 60 docker compose config --services
  run 71-compose-up 1500 docker compose up -d --build
  runsh 72-wait-health 200 '
    for i in $(seq 1 30); do
      code=$(curl -s -o /dev/null -m 5 -w "%{http_code}" http://localhost:8000/health/ready)
      echo "попытка $i: $code"; [ "$code" = 200 ] && break; sleep 6
    done
    curl -s -m 10 http://localhost:8000/health/ready; echo'
  run 73-compose-ps 60 docker compose ps -a
  runsh 74-compose-logs 120 'for s in $(docker compose config --services); do echo "══ $s"; docker compose logs --tail=40 "$s" 2>&1; done'
  run 75-smoke 300 make smoke
  run 76-compose-down 300 docker compose down
fi

# ── маскируем секреты в логах и закрываем ────────────────────
sed -i -E 's/((TOKEN|KEY|PASSWORD|SECRET)[A-Za-z0-9_]*[=:] *"?)[^ "]+/\1***/Ig' "$LOG"/*.log 2>/dev/null
echo
echo "Готово. Сводка: $SUMMARY — скажите Claude «готово», он прочитает логи в $LOG/."
