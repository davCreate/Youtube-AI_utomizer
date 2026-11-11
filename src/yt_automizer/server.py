"""MCP server exposing the channel to Claude Code (stdio transport)."""

from __future__ import annotations

from datetime import date, timedelta

from mcp.server.mcpserver import MCPServer

from . import auth, ledger
from .compliance import UploadPlan, check_upload
from .config import load_settings
from .service import PolicyBlocked, YouTubeService

INSTRUCTIONS = """\
Tools for running a YouTube channel together with a human creator.
Rules you must follow:
- Uploads always land as PRIVATE. Only call publish_video after the human has watched the
  video and explicitly said to publish it.
- Disclose realistic AI people/voices/footage with contains_synthetic_media=true.
- Every upload needs a real human contribution (idea, footage, voice, edit, fact-check).
  Do not mass-produce near-identical videos: that is demonetized as "inauthentic content".
- research_niches costs ~100 quota units per keyword (10,000/day). Batch wisely.
"""

mcp = MCPServer("youtube-automizer", instructions=INSTRUCTIONS)
_service: YouTubeService | None = None


def svc() -> YouTubeService:
    global _service
    if _service is None:
        yt, an = auth.build_clients()
        _service = YouTubeService(yt, an, load_settings())
    return _service


# ------------------------------------------------------------------ read tools
@mcp.tool()
def channel_overview() -> dict:
    """Channel name, subscribers, total views, video count and YPP thresholds."""
    return svc().channel_overview()


@mcp.tool()
def list_recent_videos(limit: int = 20) -> list[dict]:
    """Latest uploads with views, likes, comments, privacy and AI-disclosure flag."""
    return svc().recent_uploads(limit)


@mcp.tool()
def performance_summary(days: int = 28) -> dict:
    """Views, watch time, retention, subs, Shorts vs long-form split, top videos, traffic sources and revenue."""
    return svc().performance_summary(days)


@mcp.tool()
def revenue_report(days: int = 28) -> dict | str:
    """Estimated revenue, ad revenue, CPM, RPM and daily revenue. Needs YPP membership."""
    return svc().revenue(days)


@mcp.tool()
def analytics_query(metrics: str, start_date: str | None = None, end_date: str | None = None,
                    dimensions: str | None = None, sort: str | None = None, max_results: int | None = None,
                    filters: str | None = None) -> list[dict]:
    """Raw YouTube Analytics API v2 query for channel==MINE.

    Examples: metrics="views,averageViewPercentage", dimensions="video", sort="-views";
    metrics="audienceWatchRatio", dimensions="elapsedVideoTimeRatio", filters="video==VIDEO_ID" (retention curve);
    metrics="viewerPercentage", dimensions="ageGroup,gender". Dates are YYYY-MM-DD (default last 28 days).
    """
    end_date = end_date or date.today().isoformat()
    start_date = start_date or (date.today() - timedelta(days=28)).isoformat()
    return svc().analytics(start_date, end_date, metrics, dimensions, sort, max_results, filters)


@mcp.tool()
def search_youtube(query: str, days: int = 30, max_results: int = 25, region: str | None = None,
                   language: str | None = None, short_only: bool = False) -> list[dict]:
    """Most-viewed recent videos for a query, with channel size. Costs ~102 quota units."""
    return svc().search(query, days, max_results, region, language, short_only)


@mcp.tool()
def research_niches(keywords: list[str], days: int = 30, region: str | None = None,
                    language: str | None = None, short_only: bool = False) -> list[dict]:
    """Rank candidate niches/keywords by demand (views/day) and opportunity (small channels winning).

    Returns a 0-100 relative score plus outlier example videos. ~102 quota units per keyword.
    """
    return svc().research_niches(keywords, days, region, language, short_only)


@mcp.tool()
def list_comments(video_id: str, limit: int = 50) -> list[dict]:
    """Top comments on a video, to mine feedback and new video ideas."""
    return svc().comments(video_id, limit)


@mcp.tool()
def quota_status() -> dict:
    """Estimated YouTube Data API units used today (local count) and upload volume in the last 24h."""
    s = svc().settings
    used = ledger.quota_used()
    return {"used": used, "daily_quota": s.daily_quota, "remaining": s.daily_quota - used,
            "uploads_last_24h": ledger.uploads_in_last_24h(), "max_uploads_per_day": s.max_uploads_per_day}


@mcp.tool()
def audit_log(limit: int = 30) -> list[dict]:
    """Every upload, publish, metadata edit and comment reply made through this server."""
    return ledger.read_audit(limit)


# ---------------------------------------------------------- compliance + writes
@mcp.tool()
def compliance_check(title: str, made_for_kids: bool | None, contains_synthetic_media: bool | None,
                     human_contribution: str, description: str = "", tags: list[str] | None = None,
                     ai_tools_used: list[str] | None = None, script: str = "", is_short: bool = False,
                     duration_seconds: float | None = None) -> dict:
    """Dry-run the policy checks for a planned video (disclosure, inauthentic content, COPPA, limits)."""
    plan = UploadPlan(title=title, description=description, tags=tags or [], made_for_kids=made_for_kids,
                 contains_synthetic_media=contains_synthetic_media, ai_tools_used=ai_tools_used or [],
                 human_contribution=human_contribution, script=script, is_short=is_short,
                 duration_seconds=duration_seconds)
    try:
        return svc().precheck(plan)
    except auth.NotAuthenticated:
        return check_upload(plan, load_settings()).to_dict() | {"note": "offline check, no duplicate detection"}


@mcp.tool()
def upload_video(file_path: str, title: str, made_for_kids: bool, contains_synthetic_media: bool,
                 human_contribution: str, description: str = "", tags: list[str] | None = None,
                 ai_tools_used: list[str] | None = None, script: str = "", is_short: bool = False,
                 duration_seconds: float | None = None, category_id: str = "22",
                 thumbnail_path: str | None = None, language: str | None = None) -> dict:
    """Upload a local video file as PRIVATE after passing policy checks. Costs ~1600 quota units.

    contains_synthetic_media: true if realistic AI people/voices/places/events appear.
    human_contribution: what the human creator did on this video. category_id 22 = People & Blogs,
    2 = Autos & Vehicles, 17 = Sports, 27 = Education, 28 = Science & Technology.
    """
    plan = UploadPlan(title=title, description=description, tags=tags or [], made_for_kids=made_for_kids,
                 contains_synthetic_media=contains_synthetic_media, ai_tools_used=ai_tools_used or [],
                 human_contribution=human_contribution, script=script, is_short=is_short,
                 duration_seconds=duration_seconds)
    try:
        return svc().upload(file_path, plan, category_id, thumbnail_path, language)
    except PolicyBlocked as exc:
        return {"uploaded": False, "reason": "blocked by policy checks", **exc.report}


@mcp.tool()
def publish_video(video_id: str, human_approved: bool, publish_at: str | None = None) -> dict:
    """Make a private video public now, or schedule it (publish_at = ISO 8601 UTC, e.g. 2026-11-20T17:00:00Z).

    Set human_approved=true ONLY if the human explicitly approved publishing this video in this conversation.
    """
    if not human_approved:
        return {"published": False, "reason": "Ask the creator to review the private video in Studio and approve first."}
    return svc().publish(video_id, publish_at)


@mcp.tool()
def update_video_metadata(video_id: str, title: str | None = None, description: str | None = None,
                          tags: list[str] | None = None, contains_synthetic_media: bool | None = None) -> dict:
    """Change title/description/tags (e.g. A/B-style title iteration) or fix the AI-disclosure flag.

    The previous values are saved in the audit log so changes can be reverted.
    """
    if title is not None and len(title) > 100:
        return {"updated": False, "reason": "Title over 100 characters."}
    return svc().update_metadata(video_id, title, description, tags, contains_synthetic_media)


@mcp.tool()
def reply_to_comment(comment_id: str, text: str) -> dict:
    """Reply publicly to a comment as the channel. Draft it with the creator first; keep it genuine."""
    return svc().reply(comment_id, text)


# --------------------------------------------------------------------- prompts
@mcp.prompt()
def weekly_review() -> str:
    """Weekly growth review: stats, what worked, next videos."""
    return (
        "Run a weekly review of my channel: call performance_summary(days=7) and performance_summary(days=28), "
        "list_recent_videos, and revenue_report. Compare Shorts vs long-form, find the 3 best and 3 worst videos by "
        "averageViewPercentage and subs gained, explain why, and propose 5 next video ideas that fit what worked. "
        "For each idea say what I (the human) contribute and what AI does. Check quota_status before any research."
    )


@mcp.prompt()
def find_niche(interests: str) -> str:
    """Find a profitable niche from the creator's interests."""
    return (
        f"My interests: {interests}. Brainstorm 15 specific sub-niche keywords (mix of Shorts-friendly and long-form, "
        "favouring higher-RPM themes like tech, engineering, automotive, education), pick the 8 most promising, then call "
        "research_niches on them. Rank the results, explain demand vs competition, show outlier videos to learn from, "
        "and recommend 1-2 niches where my own knowledge gives an authentic edge YouTube will reward."
    )


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
