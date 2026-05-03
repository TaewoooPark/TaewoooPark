# Claude Code Usage Widget — Setup

End-to-end wiring so that `assets/claude-usage.svg` refreshes twice a day
without you touching anything.

## Pipeline

```
┌─ your Mac (launchd, 00:00 / 12:00 KST) ─┐       ┌── GitHub ─────────────────┐
│  ccusage --json  →  upload-usage.sh     │  ──►  │  private Gist (usage.json)│
└─────────────────────────────────────────┘       │              │            │
                                                  │              ▼            │
                                                  │  Actions (03:05/15:05 UTC)│
                                                  │  generate_svg.py          │
                                                  │  commits claude-usage.svg │
                                                  └───────────────────────────┘
```

## One-time setup

### 1. Create a private Gist

```bash
# anything non-empty as placeholder — will be overwritten immediately
echo '{}' > /tmp/usage.json
gh gist create --desc "ccusage daily snapshot" /tmp/usage.json
# copy the hash at the end of the printed URL → this is GIST_ID
```

### 2. Add the GIST_ID repo secret

Secret (unlisted) Gists are readable via the public API without auth, so the
Actions workflow needs only `GIST_ID` — no PAT.

```bash
gh secret set GIST_ID --body "<hash from step 1>" -R TaewoooPark/TaewoooPark
```

Or via UI: repo → Settings → Secrets and variables → Actions → New repository secret.

### 3. Prime the Gist (first manual run)

```bash
export CCUSAGE_GIST_ID=<hash from step 1>
scripts/upload-usage.sh
```

Verify the Gist now contains a populated `usage.json`.

### 4. Trigger Actions once manually

```bash
gh workflow run update-usage-svg.yml -R TaewoooPark/TaewoooPark
gh run list --workflow update-usage-svg.yml -R TaewoooPark/TaewoooPark -L 1
```

Confirm it commits `assets/claude-usage.svg`.

### 5. Install the launchd agent

```bash
# a) edit the plist: set the absolute path to upload-usage.sh on your machine
#    and replace REPLACE_WITH_GIST_ID with your GIST_ID
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

## Schedule reference

| When                              | Who runs it             | What happens                          |
| --------------------------------- | ----------------------- | ------------------------------------- |
| every 4 h (00/04/08/12/16/20 KST) | launchd on your Mac     | ccusage → Gist                        |
| 5 min later (UTC 03/07/11/15/19/23 :05) | GitHub Actions cron | Gist → SVG → commit                   |
| any time                          | Actions → Run workflow  | manual refresh (uses latest Gist)     |

GitHub cron can drift by several minutes under load; that's fine.
The `concurrency` block in the workflow prevents overlapping runs.

## Troubleshooting

- **Actions fails on `curl gists/...`**: GIST_ID is wrong, or the Gist was
  deleted. Re-create and update the secret.
- **launchd silently not firing**: `log show --predicate 'subsystem == "com.apple.xpc.launchd"' --last 1h | grep ccusage`.
- **Mac was asleep at 00:00**: launchd will fire as soon as the Mac wakes
  (default catch-up behavior for `StartCalendarInterval`).
- **SVG didn't change but Gist did**: check `totals.totalTokens` in the new
  Gist content — identical JSON produces identical SVG, and the "no change"
  step skips the commit.
