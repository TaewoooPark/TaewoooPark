#!/usr/bin/env bash
#
# Run ccusage and @ccusage/codex --json and upload each result to a private Gist.
# Invoked manually or by launchd every 4 hours.
#
# Required env:
#   CCUSAGE_GIST_ID   ID of the private Gist that holds usage.json (Claude Code)
#   CODEX_GIST_ID     ID of the private Gist that holds usage-codex.json (Codex)
#
# Depends on: npx (Node), gh CLI authenticated as the repo owner.

set -euo pipefail

log() { printf '[ccusage-upload %s] %s\n' "$(date -u +%FT%TZ)" "$*"; }

: "${CCUSAGE_GIST_ID:?error: CCUSAGE_GIST_ID is not set}"
: "${CODEX_GIST_ID:?error: CODEX_GIST_ID is not set}"

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
assert "totals" in d and "totalTokens" in d["totals"], "missing totals.totalTokens"
print(f"ok: {len(d['daily'])} days, {d['totals']['totalTokens']:,} tokens")
PY
}

upload_one() {
  local label="$1" cmd="$2" filename="$3" gist_id="$4"
  local out="$TMPDIR_RUN/$filename"

  log "running $label"
  # shellcheck disable=SC2086
  npx --yes $cmd --json > "$out"

  log "validating $label JSON"
  validate_json "$out"

  log "uploading $label to gist $gist_id"
  gh gist edit "$gist_id" "$out"
}

upload_one "ccusage"        "ccusage@latest"         "usage.json"       "$CCUSAGE_GIST_ID"
upload_one "@ccusage/codex" "@ccusage/codex@latest"  "usage-codex.json" "$CODEX_GIST_ID"

log "done"
