#!/usr/bin/env bash
# TG Glance journey soak: N consecutive E2E runs (default 10, per the
# Nov 24 plan: "automation journey test in CI-style loop, 10 consecutive
# runs, no console errors").
#
# Backend on :8787 and vite on :5173 must already be running (they stay
# up across runs; each run issues a fresh pairing code, read from the
# backend log). The simulator is restarted per run: it has no shutdown
# endpoint and a fresh launch is the only way to get a clean app state
# (pairing screen, empty console) for the next run.
#
# Usage: bash scripts/soak_e2e.sh [runs] [backend_log]
#   SIM_BIN env override for the simulator binary; XVFB_DISPLAY default :99.
set -u
cd "$(dirname "$0")/.."
RUNS="${1:-10}"
BACKEND_LOG="${2:-/tmp/tgglance-backend.log}"
SIM_BIN="${SIM_BIN:-$HOME/workspace/.npm-global/bin/evenhub-simulator}"
DISPLAY_NUM="${XVFB_DISPLAY:-:99}"
STAMP="$(date +%Y%m%d-%H%M%S)"
LOG="scripts/soak-${STAMP}.log"

pass=0; fail=0
echo "soak start $(date -Iseconds) runs=$RUNS log=$LOG" | tee "$LOG"

# X display for the simulator window (headless LVGL window).
if ! xdpyinfo -display "$DISPLAY_NUM" >/dev/null 2>&1; then
  Xvfb "$DISPLAY_NUM" -screen 0 1280x800x24 >>"scripts/xvfb-${STAMP}.log" 2>&1 &
  echo "xvfb pid $!" | tee -a "$LOG"
  sleep 2
fi

for i in $(seq 1 "$RUNS"); do
  pkill -f "evenhub-simulator http://localhost:5173" 2>/dev/null || true
  sleep 1
  DISPLAY="$DISPLAY_NUM" "$SIM_BIN" http://localhost:5173 --automation-port 9898 \
    >>"scripts/sim-${STAMP}.log" 2>&1 &
  simpid=$!
  ok=1
  for _ in $(seq 1 40); do
    if curl -sf http://127.0.0.1:9898/api/ping >/dev/null 2>&1; then ok=0; break; fi
    sleep 1
  done
  if [ "$ok" -ne 0 ]; then
    echo "run $i FAIL (simulator never answered /api/ping)" | tee -a "$LOG"
    fail=$((fail+1)); kill "$simpid" 2>/dev/null || true; continue
  fi
  if python3 scripts/e2e_sim.py "$BACKEND_LOG" >>"$LOG" 2>&1; then
    echo "run $i PASS" | tee -a "$LOG"; pass=$((pass+1))
  else
    echo "run $i FAIL (see above in $LOG)" | tee -a "$LOG"; fail=$((fail+1))
  fi
  kill "$simpid" 2>/dev/null || true
  wait "$simpid" 2>/dev/null || true
  sleep 1
done

pkill -f "evenhub-simulator http://localhost:5173" 2>/dev/null || true
echo "soak done $(date -Iseconds): PASS=$pass FAIL=$fail" | tee -a "$LOG"
[ "$fail" -eq 0 ]
