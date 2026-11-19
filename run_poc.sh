#!/usr/bin/env bash
# End-to-end driver for the PR #314 linkability PoC.
# Starts the clearnet collector and the I2P eepsite, performs two automated
# "browser" visits, then prints the correlation. No external dependencies;
# Python 3 standard library only.
set -euo pipefail

cd "$(dirname "$0")"

EEPSITE_PORT="${EEPSITE_PORT:-8631}"
COLLECTOR_PORT="${COLLECTOR_PORT:-8632}"

rm -f logs/eepsite_log.jsonl logs/collector_log.jsonl
mkdir -p logs

pids=()
cleanup() { for p in "${pids[@]:-}"; do kill "$p" 2>/dev/null || true; done; }
trap cleanup EXIT

wait_port() {  # wait_port <port>
  python3 - "$1" <<'PY'
import socket, sys, time
port = int(sys.argv[1])
for _ in range(100):
    s = socket.socket(); s.settimeout(0.2)
    if s.connect_ex(("127.0.0.1", port)) == 0:
        s.close(); sys.exit(0)
    s.close(); time.sleep(0.05)
sys.exit(1)
PY
}

echo ">> starting clearnet collector on :$COLLECTOR_PORT"
python3 collector.py --port "$COLLECTOR_PORT" --log logs/collector_log.jsonl &
pids+=($!)

echo ">> starting I2P eepsite on :$EEPSITE_PORT"
python3 eepsite.py --port "$EEPSITE_PORT" \
  --collector "http://127.0.0.1:$COLLECTOR_PORT" \
  --log logs/eepsite_log.jsonl &
pids+=($!)

wait_port "$COLLECTOR_PORT" || { echo "collector did not start"; exit 1; }
wait_port "$EEPSITE_PORT"   || { echo "eepsite did not start";   exit 1; }

echo ">> visit 1: a user reads http://linkability-demo.i2p/article/42"
python3 visit.py --eepsite "http://127.0.0.1:$EEPSITE_PORT" --path /article/42

echo ">> visit 2: the same (or another) user reads /forum/thread/7"
python3 visit.py --eepsite "http://127.0.0.1:$EEPSITE_PORT" --path /forum/thread/7

echo
python3 correlate.py \
  --i2p-log logs/eepsite_log.jsonl \
  --clearnet-log logs/collector_log.jsonl
