# Agent Usage Widget — Setup

End-to-end wiring so that `assets/agent-usage.svg` refreshes every 4 hours
without you touching anything.

## Pipeline

```
┌─ your Mac (launchd, every 4 h KST) ─────┐       ┌── GitHub ─────────────────────────────┐
│  ccusage --all --json → upload-usage.sh ──►   │  private Gist (usage.json)            │
└─────────────────────────────────────────┘       │                  │                    │
                                                  │                  ▼                    │
                                                  │  Actions (every 4 h, +5 min)          │
                                                  │  generate_svg.py                      │
                                                  │  commits agent-usage.svg              │
                                                  └───────────────────────────────────────┘
```

## One-time setup

### 1. Create a private Gist

```bash
# anything non-empty as placeholder — will be overwritten immediately
echo '{}' > /tmp/usage.json

gh gist create --desc "ccusage agent daily snapshot" /tmp/usage.json
# copy the hash at the end of the printed URL → GIST_ID
```

### 2. Add the repo secrets

Secret (unlisted) Gists are readable via the public API without auth, so the
Actions workflow needs only the IDs — no PAT.

```bash
gh secret set GIST_ID --body "<hash from gist>" -R TaewoooPark/TaewoooPark
```

Or via UI: repo → Settings → Secrets and variables → Actions → New repository secret.

### 3. Prime the Gist (first manual run)

```bash
export CCUSAGE_GIST_ID=<hash from gist>
scripts/upload-usage.sh
```

Verify the Gist now contains populated JSON.

### 4. Trigger Actions once manually

```bash
gh workflow run update-usage-svg.yml -R TaewoooPark/TaewoooPark
gh run list --workflow update-usage-svg.yml -R TaewoooPark/TaewoooPark -L 1
```

Confirm it commits `assets/agent-usage.svg`.

### 5. Install the launchd agent

```bash
# a) edit the plist: set the absolute path to upload-usage.sh on your machine
#    and replace REPLACE_WITH_CCUSAGE_GIST_ID
$EDITOR launchd/com.me.ccusage-upload.plist

# b) install
cp launchd/com.me.ccusage-upload.plist ~/Library/LaunchAgents/
launchctl load  ~/Library/LaunchAgents/com.me.ccusage-upload.plist

# c) test it right now
launchctl start com.me.ccusage-upload
tail -n 20 /tmp/ccusage-upload.log /tmp/ccusage-upload.err

# d) inspect schedule
launchctl list | grep ccusage-upload
```

To uninstall:

```bash
launchctl unload ~/Library/LaunchAgents/com.me.ccusage-upload.plist
rm           ~/Library/LaunchAgents/com.me.ccusage-upload.plist
```

## Total Stars Badge

`assets/total-stars.json` is refreshed by GitHub Actions once a day. It sums
every public repository owned by `TaewoooPark` plus every public repository in
the `OPTIMETA` organization. Forks are included here because the badge is an
all-repository total; the Featured Projects table can still exclude forks.

## Schedule reference

| When                              | Who runs it             | What happens                          |
| --------------------------------- | ----------------------- | ------------------------------------- |
| every 4 h (00/04/08/12/16/20 KST) | launchd on your Mac     | ccusage agent usage → Gist            |
| 5 min later (UTC 03/07/11/15/19/23 :05) | GitHub Actions cron | Gist → SVG → commit                   |
| any time                          | Actions → Run workflow  | manual refresh (uses latest Gist)     |

GitHub cron can drift by several minutes under load; that's fine.
The `concurrency` block in the workflow prevents overlapping runs.

## Troubleshooting

- **Actions fails on `curl gists/...`**: a GIST_ID is wrong, or the Gist was
  deleted. Re-create and update the secret.
- **launchd silently not firing**: `log show --predicate 'subsystem == "com.apple.xpc.launchd"' --last 1h | grep ccusage`.
- **Mac was asleep at 00:00**: launchd will fire as soon as the Mac wakes
  (default catch-up behavior for `StartCalendarInterval`).
- **SVG didn't change but Gist did**: check `totals.totalTokens` in the new
  Gist content — identical JSON produces identical SVG, and the "no change"
  step skips the commit.
