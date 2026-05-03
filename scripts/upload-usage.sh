#!/usr/bin/env bash
#
# Run ccusage (Claude) + @ccusage/codex (Codex), merge per-day token totals,
# and upload the combined snapshot to a private Gist. Invoked manually or
# by launchd twice a day.
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
CLAUDE_RAW="$TMPDIR_RUN/claude.json"
CODEX_RAW="$TMPDIR_RUN/codex.json"

log "running ccusage (claude)"
npx --yes ccusage@latest --json > "$CLAUDE_RAW"

log "running ccusage codex"
if ! npx --yes @ccusage/codex@latest --json > "$CODEX_RAW" 2>/dev/null; then
  log "codex usage unavailable; treating as zero"
  echo '{"daily":[],"totals":{"totalTokens":0}}' > "$CODEX_RAW"
fi

log "merging claude + codex daily totals"
python3 - "$CLAUDE_RAW" "$CODEX_RAW" "$OUT" <<'PY'
import json, sys
from collections import defaultdict

claude_p, codex_p, out_p = sys.argv[1:4]

merged = defaultdict(int)
for p in (claude_p, codex_p):
    with open(p) as f:
        d = json.load(f)
    for row in d.get("daily", []):
        date = row.get("date")
        if not date:
            continue
        merged[date] += int(row.get("totalTokens", 0))

daily = [{"date": d, "totalTokens": t} for d, t in sorted(merged.items())]
total = sum(r["totalTokens"] for r in daily)

with open(out_p, "w") as f:
    json.dump({"daily": daily, "totals": {"totalTokens": total}}, f)
print(f"merged {len(daily)} days, {total:,} tokens")
PY

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
