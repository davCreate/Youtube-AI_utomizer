# YouTube AI-utomizer

An MCP server that connects **Claude Code** to **your YouTube channel**. Claude can read your
stats and revenue, research niches, prepare and upload videos (private), and publish them
when you approve. Policy guardrails are built in so an AI-assisted channel stays eligible for
monetization.

> Monetization depends on YouTube, not on this tool. What it does is keep the process within
> YouTube's rules: AI disclosure, no mass-produced "inauthentic content", COPPA, and human approval before anything goes public.

## What Claude can do

| Area | Tools |
|---|---|
| Stats | `channel_overview`, `list_recent_videos`, `performance_summary` (views, watch time, retention, Shorts vs long-form, traffic sources), `analytics_query` (any YouTube Analytics query: retention curves, demographics...) |
| Money | `revenue_report` (estimated revenue, ad revenue, CPM, RPM, daily). Available once the channel is in YPP. |
| Research | `search_youtube`, `research_niches` (0-100 score: demand × small channels winning × diversity, with outlier videos) |
| Publishing | `compliance_check`, `upload_video` (always **private**), `publish_video` (needs `human_approved`, can schedule), `update_video_metadata` |
| Community | `list_comments`, `reply_to_comment` |
| Safety | `quota_status`, `audit_log` (every write, including previous metadata for rollback) |
| Prompts | `weekly_review`, `find_niche` |

Recommended: copy `docs/claude-settings.example.json` to `.claude/settings.json`. Then read-only
tools run without prompts, and research (uses quota), uploads, publishing, edits and replies
always ask for your confirmation.

## Built-in policy checks (`src/yt_automizer/compliance.py`)
- **Altered or synthetic content:** every upload must declare `contains_synthetic_media`. It is sent as
  `status.containsSyntheticMedia` (YouTube Data API, since Oct 2024). It warns when the listed tools
  (voice clones, AI video) suggest the content is realistic.
- **Inauthentic content (YPP):** blocks uploads with no stated human contribution, uploads that are
  near-duplicates of recent ones (3-gram similarity), and more than N uploads per 24h (default 3).
- **Sensitive topics** (health, finance, news, elections) with AI involvement: warns to fact-check and cite sources.
- **COPPA:** `made_for_kids` must be explicit.
- **API limits:** title ≤ 100 chars, description ≤ 5000 bytes, tags ≤ 500 chars, Shorts ≤ 3 min.

You can change the thresholds in `~/.yt-automizer/settings.json`.

## Setup (about 10 minutes)

1. **Google Cloud project**: at <https://console.cloud.google.com/> create a project and enable
   **YouTube Data API v3** and **YouTube Analytics API**.
2. **OAuth consent screen**: External, add your Google account as a *test user*.
3. **Credentials → Create OAuth client ID → Desktop app**. Download the JSON to
   `~/.yt-automizer/client_secret.json`.
4. Install and log in:
   ```bash
   python3 -m venv .venv
   .venv/bin/pip install -e .
   .venv/bin/yt-automizer auth      # opens the browser, choose the channel's account
   .venv/bin/yt-automizer whoami    # check the right channel is connected
   ```
5. Open Claude Code in this folder. The `youtube` server in `.mcp.json` starts automatically
   (run `/mcp` to check it). Try: *"Run the weekly review"* or *"Find me a niche: F1, aerodynamics, sports cars"*.

On Windows, change `.mcp.json` `command` to `.venv\\Scripts\\yt-automizer.exe`.

**Notes**
- While the OAuth app is in "Testing" mode, refresh tokens expire after 7 days; run `yt-automizer auth` again,
  or publish the app (personal use doesn't need Google verification for your own account).
- Videos uploaded through an **unverified** API project may be locked as private by YouTube until the
  project passes the [API compliance audit](https://support.google.com/youtube/contact/yt_api_form).
  Request it early. Until then, upload with this tool and publish from Studio.
- Data stays local: token, audit log and quota counter live in `~/.yt-automizer/` (override with `YT_AUTOMIZER_HOME`).

## Development
```bash
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest -q
```
