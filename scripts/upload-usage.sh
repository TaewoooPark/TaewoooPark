#!/usr/bin/env bash
#
# Run ccusage JSON reports and upload the combined agent usage to a private Gist.
# Invoked manually or by launchd every 4 hours.
#
# Required env:
#   CCUSAGE_GIST_ID   ID of the private Gist that holds usage.json
#
# Depends on: npx (Node), gh CLI authenticated as the repo owner.

set -euo pipefail

log() { printf '[ccusage-upload %s] %s\n' "$(date -u +%FT%TZ)" "$*"; }

: "${CCUSAGE_GIST_ID:?error: CCUSAGE_GIST_ID is not set}"
for bin in npx gh python3; do
  if ! command -v "$bin" >/dev/null 2>&1; then
    echo "error: $bin not found in PATH ($PATH)" >&2
    exit 127
  fi
done

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

upload_one() {
  local label="$1" filename="$2" gist_id="$3"
  local out="$TMPDIR_RUN/$filename"

  log "running $label"
  npx --yes ccusage@latest --timezone "${CCUSAGE_TIMEZONE:-Asia/Seoul}" --json > "$out"

  log "validating $label JSON"
  validate_json "$out"

  log "uploading $label to gist $gist_id"
  gh gist edit "$gist_id" "$out"
}

upload_one "agent usage" "usage.json" "$CCUSAGE_GIST_ID"

log "done"
