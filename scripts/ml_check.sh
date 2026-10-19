#!/usr/bin/env bash
# Проверка ML с локальными моделями и стенда целиком. Вывод — в .ml_check/*.log, сводка —
# .ml_check/summary.log. Дальше достаточно сказать Claude «готово» (или прислать summary.log).
#
#   bash scripts/ml_check.sh            # 0–5: окружение, Ollama, проверки ml_service, eval,
#                                       #      ml_service вживую по gRPC, make check всех сервисов
#   bash scripts/ml_check.sh --pull     # + скачать модели, если их нет (~6 ГБ)
#   bash scripts/ml_check.sh --stack    # + 6: стенд без Docker (collector fake, ml на моделях,
#                                       #      search, gateway) и make smoke; нужен Postgres
#
# Переменные: OLLAMA_URL (http://127.0.0.1:11434), OLLAMA_LLM_MODEL, OLLAMA_EMBED_MODEL,
# OLLAMA_JUDGE_MODEL, PG_DSN (postgresql+asyncpg://search:search_local@127.0.0.1:5435/search).
# Ничего не коммитит. Меняет: uv sync, eval/report.md и eval/report_baseline_heuristic.md.

cd "$(dirname "$0")/.." || exit 1
LOG=.ml_check
rm -rf "$LOG" && mkdir -p "$LOG"
SUMMARY="$LOG/summary.log"
WITH_PULL=0; WITH_STACK=0
for arg in "$@"; do
  case "$arg" in
    --pull) WITH_PULL=1 ;;
    --stack) WITH_STACK=1 ;;
    *) echo "неизвестный аргумент: $arg"; exit 2 ;;
  esac
done

export OLLAMA_URL=${OLLAMA_URL:-http://127.0.0.1:11434}
export OLLAMA_LLM_MODEL=${OLLAMA_LLM_MODEL:-qwen2.5:7b-instruct}
export OLLAMA_EMBED_MODEL=${OLLAMA_EMBED_MODEL:-bge-m3}
export OLLAMA_JUDGE_MODEL=${OLLAMA_JUDGE_MODEL:-}
PG_DSN=${PG_DSN:-postgresql+asyncpg://search:search_local@127.0.0.1:5435/search}
PIDS=()
cleanup() { for p in "${PIDS[@]}"; do kill "$p" 2>/dev/null; done; wait 2>/dev/null; }
trap cleanup EXIT

# run <имя-лога> <таймаут-сек> <команда...> — вывод в лог, код и время в summary
run() {
  local name=$1 limit=$2; shift 2
  local file="$LOG/$name.log" start=$SECONDS
  { echo "\$ $*"; echo "── $(date '+%F %T')"; } > "$file"
  timeout "$limit" "$@" >> "$file" 2>&1
  local code=$?
  [ "$code" = 124 ] && echo "!! таймаут ${limit}с" >> "$file"
  echo "── код выхода: $code, $((SECONDS - start)) с" >> "$file"
  printf '%-30s код=%-3s %4ss\n' "$name" "$code" "$((SECONDS - start))" | tee -a "$SUMMARY"
  return "$code"
}
runsh() { local name=$1 limit=$2 cmd=$3; run "$name" "$limit" bash -c "$cmd"; }
note() { echo "$*" | tee -a "$SUMMARY"; }

# wait_port <host:port> <сек>
wait_port() {
  local host=${1%:*} port=${1##*:} limit=$2 i
  for ((i = 0; i < limit; i++)); do
    (echo > "/dev/tcp/$host/$port") 2>/dev/null && return 0
    sleep 1
  done
  return 1
}

# start <имя> <каталог> <команда> — фоном, лог в .ml_check/<имя>.server.log
start() {
  local name=$1 dir=$2 cmd=$3
  (cd "$dir" && exec bash -c "$cmd") > "$LOG/$name.server.log" 2>&1 &
  PIDS+=("$!")
}

note "== ML check $(date '+%F %T'), OLLAMA_URL=$OLLAMA_URL"

# ── 0. окружение
runsh 00-env 30 'uname -a; uv --version; python3 --version; git log --oneline -1;
  command -v nvidia-smi >/dev/null && nvidia-smi --query-gpu=name,memory.used,memory.total --format=csv;
  command -v ollama >/dev/null && ollama --version; true'

# ── 1. Ollama и модели
MODELS=0
if runsh 01-ollama 15 "curl -sf $OLLAMA_URL/api/tags"; then
  have() { grep -q "\"name\":\"$1" "$LOG/01-ollama.log" || grep -q "\"name\": *\"$1" "$LOG/01-ollama.log"; }
  missing=()
  for m in "$OLLAMA_LLM_MODEL" "$OLLAMA_EMBED_MODEL" ${OLLAMA_JUDGE_MODEL:+"$OLLAMA_JUDGE_MODEL"}; do
    have "$m" || missing+=("$m")
  done
  if [ ${#missing[@]} -gt 0 ] && [ "$WITH_PULL" = 1 ]; then
    for m in "${missing[@]}"; do
      runsh "01-pull-${m//[:\/]/_}" 3600 "curl -sf $OLLAMA_URL/api/pull -d '{\"model\":\"$m\",\"stream\":false}'"
    done
    missing=()
  fi
  if [ ${#missing[@]} -gt 0 ]; then
    note "!! нет моделей: ${missing[*]} → ollama pull ${missing[*]} (или запусти с --pull)"
  else
    MODELS=1
    note "   модели на месте: $OLLAMA_LLM_MODEL, $OLLAMA_EMBED_MODEL ${OLLAMA_JUDGE_MODEL}"
  fi
else
  note "!! Ollama не отвечает на $OLLAMA_URL → ollama serve (или docker compose --profile llm-local up -d ollama)"
fi

# ── 2. проверки ml_service (как CI)
ML=services/ml_service
runsh 02-ml-sync 600 "cd $ML && uv sync"
runsh 02-ml-ruff 120 "cd $ML && uv run ruff check . && uv run ruff format --check ."
runsh 02-ml-mypy 300 "cd $ML && uv run mypy src"
runsh 02-ml-pytest 300 "cd $ML && uv run pytest -q"

# ── 3. качество: eval на эвристиках (базовая линия) и на моделях
runsh 03-eval-heuristic 300 "LLM_PROVIDER=stub EMBED_PROVIDER=stub uv run --project $ML python eval/run_eval.py --details --report eval/report_baseline_heuristic.md"
if [ "$MODELS" = 1 ]; then
  runsh 03-eval-models 1800 "LLM_PROVIDER=ollama EMBED_PROVIDER=ollama uv run --project $ML python eval/run_eval.py --details"
  grep -E '^\| \*\*Всего|^\| ' eval/report.md | head -8 >> "$SUMMARY"
fi

# ── 4. ml_service вживую по gRPC (порт 50155, чтобы не мешать стенду)
PROVIDER=stub; [ "$MODELS" = 1 ] && PROVIDER=ollama
start ml-grpc "$ML" "GRPC_ADDRESS=127.0.0.1:50155 LLM_PROVIDER=$PROVIDER EMBED_PROVIDER=$PROVIDER exec uv run ml-service"
if wait_port 127.0.0.1:50155 60; then
  sleep 3  # прогрев модели идёт в фоне
  runsh 04-ml-grpc 600 "uv run --project $ML python scripts/ml_grpc_check.py 127.0.0.1:50155"
  grep -E 'degraded|за [0-9.]+ с|FAIL|All good|классы' "$LOG/04-ml-grpc.log" | head -12 >> "$SUMMARY"
else
  note "!! ml_service не поднялся на 50155 — см. $LOG/ml-grpc.server.log"
fi
cleanup; PIDS=()

# ── 5. make check всех сервисов (как CI)
runsh 05-make-check 1800 "make check"

# ── 6. стенд без Docker и smoke (по флагу --stack)
if [ "$WITH_STACK" = 1 ]; then
  start collector services/collector_service "GRPC_ADDRESS=127.0.0.1:50054 COLLECTOR_FAKE=true exec uv run collector-service"
  start ml services/ml_service "GRPC_ADDRESS=127.0.0.1:50055 LLM_PROVIDER=$PROVIDER EMBED_PROVIDER=$PROVIDER exec uv run ml-service"
  start search services/search_service "DATABASE_URL=$PG_DSN GRPC_ADDRESS=127.0.0.1:50053 COLLECTOR_GRPC_TARGET=127.0.0.1:50054 ML_GRPC_TARGET=127.0.0.1:50055 uv run alembic upgrade head && exec uv run search-service"
  start gateway services/gateway "SEARCH_GRPC_TARGET=127.0.0.1:50053 COLLECTOR_GRPC_TARGET=127.0.0.1:50054 ML_GRPC_TARGET=127.0.0.1:50055 exec uv run uvicorn gateway.main:app --host 127.0.0.1 --port 8000"
  if wait_port 127.0.0.1:8000 120 && wait_port 127.0.0.1:50053 60; then
    sleep 5
    runsh 06-health 30 "curl -sf http://127.0.0.1:8000/health/ready"
    runsh 06-smoke 900 "uv run --project services/gateway python scripts/smoke.py http://127.0.0.1:8000"
    grep -E 'FAIL|All good|ML:|отбор:|поиск:' "$LOG/06-smoke.log" >> "$SUMMARY"
  else
    note "!! стенд не поднялся — см. $LOG/*.server.log (Postgres на ${PG_DSN##*@}?)"
  fi
fi

note "== готово. Логи: $LOG/, сводка: $SUMMARY"
