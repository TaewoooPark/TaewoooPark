#!/usr/bin/env bash
#
# Run ccusage JSON reports and upload the combined agent usage to a private Gist.
# Invoked manually or by launchd every 4 hours.
#
# Required env:
#   CCUSAGE_GIST_ID   ID of the private Gist that holds usage.json
#
# Depends on: ccusage (preferred) or npx (fallback), gh CLI authenticated as
# the repo owner.

set -euo pipefail

log() { printf '[ccusage-upload %s] %s\n' "$(date -u +%FT%TZ)" "$*"; }

: "${CCUSAGE_GIST_ID:?error: CCUSAGE_GIST_ID is not set}"
for bin in gh python3; do
  if ! command -v "$bin" >/dev/null 2>&1; then
    echo "error: $bin not found in PATH ($PATH)" >&2
    exit 127
  fi
done

if [[ -n "${CCUSAGE_BIN:-}" ]]; then
  CCUSAGE_CMD=("$CCUSAGE_BIN")
elif command -v ccusage >/dev/null 2>&1; then
  CCUSAGE_CMD=(ccusage)
elif command -v npx >/dev/null 2>&1; then
  CCUSAGE_CMD=(npx --yes ccusage@latest)
else
  echo "error: neither ccusage nor npx found in PATH ($PATH)" >&2
  exit 127
fi

TMPDIR_RUN="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_RUN"' EXIT

validate_json() {
  local path="$1"
  python3 - "$path" <<'PY'
import json, sys
p = sys.argv[1]
d = json.load(open(p))
assert isinstance(d, dict), "root must be object"
assert "daily" in d and isinstance(d["daily"], list), "missing daily[]"
assert all("date" in e or "period" in e for e in d["daily"]), "daily entry missing date/period key"
assert "totals" in d and "totalTokens" in d["totals"], "missing totals.totalTokens"
print(f"ok: {len(d['daily'])} days, {d['totals']['totalTokens']:,} tokens")
PY
}

retry() {
  local attempts="$1"
  shift

  local delay=10
  local status=0
  for ((i = 1; i <= attempts; i++)); do
    "$@" && return 0
    status=$?
    if (( i == attempts )); then
      return "$status"
    fi
    log "attempt $i failed with exit $status; retrying in ${delay}s"
    sleep "$delay"
    delay=$((delay * 2))
  done
}

upload_one() {
  local label="$1" filename="$2" gist_id="$3"
  local out="$TMPDIR_RUN/$filename"
  local tmp="$out.tmp"

  log "running $label via ${CCUSAGE_CMD[*]} --all"
  "${CCUSAGE_CMD[@]}" --all --timezone "${CCUSAGE_TIMEZONE:-Asia/Seoul}" --json > "$tmp"
  mv "$tmp" "$out"

  log "validating $label JSON"
  validate_json "$out"

  log "uploading $label to gist $gist_id"
  retry 3 gh gist edit "$gist_id" --filename "$filename" "$out"
}

upload_one "agent usage" "usage.json" "$CCUSAGE_GIST_ID"

log "done"
