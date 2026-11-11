"""Niche scoring from public search results.

For a keyword we look at the top recent videos and ask three questions:

* demand: are recent videos getting views quickly? (median views per day)
* opportunity: are small channels getting those views? (share of top results from
  channels under 50k subscribers, and median views / subscribers "outlier" ratio)
* saturation: how many of the results come from a few big channels?

The score is relative: use it to rank keywords against each other, not as an absolute truth.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from statistics import median


def _age_days(published_at: str, now: datetime) -> float:
    dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
    return max((now - dt).total_seconds() / 86400, 0.5)


def score_videos(videos: list[dict], now: datetime | None = None, small_channel_subs: int = 50_000) -> dict:
    """``videos``: dicts with ``views``, ``published_at`` (ISO), ``channel_id``, ``channel_subs``."""
    now = now or datetime.now(timezone.utc)
    if not videos:
        return {"score": 0.0, "videos_analyzed": 0}

    vpd = [v["views"] / _age_days(v["published_at"], now) for v in videos]
    outlier = [v["views"] / max(v.get("channel_subs") or 0, 100) for v in videos]
    small = [v for v in videos if (v.get("channel_subs") or 0) < small_channel_subs]
    channels = {v["channel_id"] for v in videos}

    median_vpd = median(vpd)
    small_share = len(small) / len(videos)
    median_outlier = median(outlier)
    diversity = len(channels) / len(videos)  # 1.0 = every result from a different channel

    # Demand on a log scale: 100 views/day -> ~0.33, 10k/day -> ~0.67, 1M/day -> 1.0
    demand = min(math.log10(median_vpd + 1) / 6, 1.0)
    opportunity = 0.5 * small_share + 0.5 * min(math.log10(median_outlier + 1) / 2, 1.0)
    score = round(100 * (0.45 * demand + 0.40 * opportunity + 0.15 * diversity), 1)

    return {
        "score": score,
        "videos_analyzed": len(videos),
        "median_views_per_day": round(median_vpd),
        "small_channel_share": round(small_share, 2),
        "median_views_to_subs": round(median_outlier, 2),
        "channel_diversity": round(diversity, 2),
        "components": {"demand": round(demand, 3), "opportunity": round(opportunity, 3)},
    }
