#!/usr/bin/env bash
# Rebuild the plugin and restart the DSH web dev runtime that serves it.
#
# The model only sees the built bundle (lib/index.js), and the web profile
# loads plugins at startup (patchReload: startup), so every src/ change needs
# exactly this sequence: build, stop the old server, start a new one.
#
# Usage: scripts/dev-restart.sh [--no-build] [--fg] [dsh web flags...]
#   --no-build   skip `pnpm build` (docs-only or Python-only changes)
#   --fg         run `dsh web` in the foreground instead of detached with a log
#   anything else is passed to `dsh web` (e.g. --no-open, --port 3099)
#
# Environment: DSH_HARNESS_DIR (default: ../deepseek-harness next to this repo),
#              DSH_WEB_LOG (default: ~/.dsh/dsh-web.log, created mode 600).
# Credentials are read by DSH itself from ~/.dsh/.env; this script never prints them.
set -euo pipefail

PLUGIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HARNESS_DIR="${DSH_HARNESS_DIR:-$PLUGIN_DIR/../deepseek-harness}"
LOG="${DSH_WEB_LOG:-$HOME/.dsh/dsh-web.log}"
NODE_VERSION=22.19.0
# Matches the tsx launcher of every `dsh web` started from a source checkout,
# whatever its port. Bracketing the last character keeps pgrep from matching itself.
WEB_PATTERN='apps/cli/src/bin.ts we[b]'

build=1
foreground=0
port=3080
passthrough=()
while [ $# -gt 0 ]; do
  case "$1" in
    --no-build) build=0 ;;
    --fg) foreground=1 ;;
    --port) port="$2"; passthrough+=("$1" "$2"); shift ;;
    --port=*) port="${1#--port=}"; passthrough+=("$1") ;;
    -h|--help) sed -n '2,15p' "$0"; exit 0 ;;
    *) passthrough+=("$1") ;;
  esac
  shift
done

[ -d "$HARNESS_DIR/apps/cli" ] || { echo "harness checkout not found at $HARNESS_DIR (set DSH_HARNESS_DIR)" >&2; exit 1; }

# shellcheck disable=SC1090
source "$HOME/.nvm/nvm.sh"
nvm use "$NODE_VERSION" >/dev/null

if [ "$build" = 1 ]; then
  echo "building plugin bundle in $PLUGIN_DIR"
  (cd "$PLUGIN_DIR" && pnpm build >/dev/null)
fi

if pgrep -f "$WEB_PATTERN" >/dev/null; then
  echo "stopping running dsh web"
  pkill -f "$WEB_PATTERN" || true
  for _ in $(seq 1 25); do
    pgrep -f "$WEB_PATTERN" >/dev/null || break
    sleep 0.2
  done
  pgrep -f "$WEB_PATTERN" >/dev/null && pkill -9 -f "$WEB_PATTERN" || true
fi

cd "$HARNESS_DIR"
if [ "$foreground" = 1 ]; then
  exec pnpm dsh web "${passthrough[@]}"
fi

install -m 600 /dev/null "$LOG"
nohup pnpm dsh web "${passthrough[@]}" >>"$LOG" 2>&1 &
pid=$!

# Ready when the port answers anything at all (401 without the token is fine).
# A cold tsx boot of the harness checkout takes 3 to 4 minutes on this host.
for _ in $(seq 1 1500); do
  if ! kill -0 "$pid" 2>/dev/null; then
    echo "dsh web exited early; last log lines:" >&2
    tail -n 20 "$LOG" >&2
    exit 1
  fi
  # 404 = socket open, tree still composing; anything else = routes are live.
  code=$(curl -s --max-time 2 -o /dev/null -w '%{http_code}' "http://127.0.0.1:$port/" || true)
  if [ -n "$code" ] && [ "$code" != "000" ] && [ "$code" != "404" ]; then
    echo "dsh web up on port $port (pid $pid); log: $LOG"
    echo "the browser opens with the token URL unless --no-open was given; the URL is in the log, do not paste it into chat"
    exit 0
  fi
  sleep 0.3
done
echo "dsh web did not answer on port $port within 450 s; see $LOG" >&2
exit 1
