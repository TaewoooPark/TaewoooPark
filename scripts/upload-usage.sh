#!/usr/bin/env bash
#
# Run ccusage --json and upload the result to a private Gist.
# Invoked manually or by launchd twice a day.
#
# Required env:
#   CCUSAGE_GIST_ID   ID of the private Gist that holds usage.json
#
# Depends on: npx (Node), gh CLI authenticated as the repo owner.

set -euo pipefail

log() { printf '[ccusage-upload %s] %s\n' "$(date -u +%FT%TZ)" "$*"; }

if [[ -z "${CCUSAGE_GIST_ID:-}" ]]; then
  echo "error: CCUSAGE_GIST_ID is not set" >&2
  exit 64
fi

for bin in npx gh python3; do
  if ! command -v "$bin" >/dev/null 2>&1; then
    echo "error: $bin not found in PATH ($PATH)" >&2
    exit 127
  fi
done

TMPDIR_RUN="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_RUN"' EXIT

OUT="$TMPDIR_RUN/usage.json"

log "running ccusage"
npx --yes ccusage@latest --json > "$OUT"

log "validating JSON"
python3 - "$OUT" <<'PY'
import json, sys
p = sys.argv[1]
d = json.load(open(p))
assert isinstance(d, dict), "root must be object"
assert "daily" in d and isinstance(d["daily"], list), "missing daily[]"
assert "totals" in d and "totalTokens" in d["totals"], "missing totals.totalTokens"
print(f"ok: {len(d['daily'])} days, {d['totals']['totalTokens']:,} tokens")
PY

log "uploading to gist $CCUSAGE_GIST_ID"
gh gist edit "$CCUSAGE_GIST_ID" "$OUT"

log "done"
