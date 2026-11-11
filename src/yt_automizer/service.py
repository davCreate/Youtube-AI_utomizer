"""Thin, testable wrapper around the YouTube Data API v3 and YouTube Analytics API v2."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import ledger
from .compliance import UploadPlan, check_upload
from .config import Settings
from .niche import score_videos


class PolicyBlocked(RuntimeError):
    def __init__(self, report: dict):
        super().__init__("Upload blocked by policy checks")
        self.report = report


def _rows(resp: dict) -> list[dict]:
    headers = [h["name"] for h in resp.get("columnHeaders", [])]
    return [dict(zip(headers, row)) for row in resp.get("rows", [])]


class YouTubeService:
    def __init__(self, youtube, analytics, settings: Settings):
        self.yt = youtube
        self.an = analytics
        self.settings = settings
        self._channel: dict | None = None

    # ------------------------------------------------------------------ channel
    def channel(self) -> dict:
        if self._channel is None:
            ledger.spend_quota("channels.list")
            resp = self.yt.channels().list(part="snippet,statistics,contentDetails,status", mine=True).execute()
            items = resp.get("items", [])
            if not items:
                raise RuntimeError("This Google account has no YouTube channel.")
            self._channel = items[0]
        return self._channel

    def channel_overview(self) -> dict:
        ch = self.channel()
        stats = ch.get("statistics", {})
        return {
            "id": ch["id"],
            "title": ch["snippet"]["title"],
            "custom_url": ch["snippet"].get("customUrl"),
            "subscribers": int(stats.get("subscriberCount", 0)),
            "subscribers_hidden": stats.get("hiddenSubscriberCount", False),
            "total_views": int(stats.get("viewCount", 0)),
            "video_count": int(stats.get("videoCount", 0)),
            "made_for_kids": ch.get("status", {}).get("madeForKids"),
            "ypp_progress_hint": "YPP needs 1,000 subs + 4,000 public watch hours (12 months) "
            "or 1,000 subs + 10M Shorts views (90 days). Check exact eligibility in YouTube Studio.",
        }

    def recent_uploads(self, limit: int = 25) -> list[dict]:
        uploads = self.channel()["contentDetails"]["relatedPlaylists"]["uploads"]
        ledger.spend_quota("playlistItems.list")
        resp = self.yt.playlistItems().list(part="contentDetails", playlistId=uploads, maxResults=min(limit, 50)).execute()
        ids = [i["contentDetails"]["videoId"] for i in resp.get("items", [])]
        return self.videos(ids)

    def videos(self, ids: list[str]) -> list[dict]:
        out = []
        for i in range(0, len(ids), 50):
            ledger.spend_quota("videos.list")
            resp = self.yt.videos().list(part="snippet,statistics,status,contentDetails", id=",".join(ids[i : i + 50])).execute()
            for v in resp.get("items", []):
                s = v.get("statistics", {})
                out.append({
                    "id": v["id"],
                    "title": v["snippet"]["title"],
                    "description": v["snippet"].get("description", ""),
                    "tags": v["snippet"].get("tags", []),
                    "published_at": v["snippet"].get("publishedAt"),
                    "duration": v.get("contentDetails", {}).get("duration"),
                    "privacy": v.get("status", {}).get("privacyStatus"),
                    "contains_synthetic_media": v.get("status", {}).get("containsSyntheticMedia"),
                    "views": int(s.get("viewCount", 0)),
                    "likes": int(s.get("likeCount", 0)),
                    "comments": int(s.get("commentCount", 0)),
                })
        return out

    # ---------------------------------------------------------------- analytics
    def analytics(self, start_date: str, end_date: str, metrics: str, dimensions: str | None = None,
                  sort: str | None = None, max_results: int | None = None, filters: str | None = None) -> list[dict]:
        params = {"ids": "channel==MINE", "startDate": start_date, "endDate": end_date, "metrics": metrics}
        if dimensions:
            params["dimensions"] = dimensions
        if sort:
            params["sort"] = sort
        if max_results:
            params["maxResults"] = max_results
        if filters:
            params["filters"] = filters
        return _rows(self.an.reports().query(**params).execute())

    def performance_summary(self, days: int = 28) -> dict:
        end = date.today()
        start = end - timedelta(days=days)
        s, e = start.isoformat(), end.isoformat()
        core = "views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,subscribersGained,subscribersLost,likes,shares"
        summary = {"period": {"start": s, "end": e}}
        totals = self.analytics(s, e, core)
        summary["totals"] = totals[0] if totals else {}
        try:
            summary["by_format"] = self.analytics(s, e, "views,estimatedMinutesWatched,averageViewPercentage,subscribersGained",
                                                  dimensions="creatorContentType")
        except Exception as exc:  # dimension not available for every channel
            summary["by_format"] = f"unavailable: {exc}"
        summary["top_videos"] = self.analytics(s, e, "views,estimatedMinutesWatched,averageViewPercentage,subscribersGained",
                                               dimensions="video", sort="-views", max_results=10)
        summary["traffic_sources"] = self.analytics(s, e, "views", dimensions="insightTrafficSourceType", sort="-views")
        summary["revenue"] = self.revenue(days)
        return summary

    def revenue(self, days: int = 28) -> dict | str:
        end = date.today()
        start = end - timedelta(days=days)
        try:
            rows = self.analytics(start.isoformat(), end.isoformat(),
                                  "estimatedRevenue,estimatedAdRevenue,estimatedRedPartnerRevenue,grossRevenue,cpm,playbackBasedCpm,monetizedPlaybacks")
            daily = self.analytics(start.isoformat(), end.isoformat(), "estimatedRevenue,views", dimensions="day", sort="day")
            total = rows[0] if rows else {}
            views = sum(r.get("views", 0) for r in daily)
            if views:
                total["rpm_estimate"] = round(1000 * total.get("estimatedRevenue", 0) / views, 2)
            return {"totals": total, "daily": daily}
        except Exception as exc:
            return f"Revenue unavailable (channel not in YPP yet, or monetary scope missing): {exc}"

    # ----------------------------------------------------------------- research
    def search(self, query: str, days: int = 30, max_results: int = 25, region: str | None = None,
               language: str | None = None, short_only: bool = False) -> list[dict]:
        after = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
        params = {"part": "id", "q": query, "type": "video", "order": "viewCount",
                  "publishedAfter": after, "maxResults": min(max_results, 50)}
        if region:
            params["regionCode"] = region
        if language:
            params["relevanceLanguage"] = language
        if short_only:
            params["videoDuration"] = "short"  # under 4 minutes
        ledger.spend_quota("search.list")
        ids = [i["id"]["videoId"] for i in self.yt.search().list(**params).execute().get("items", [])]
        if not ids:
            return []
        ledger.spend_quota("videos.list")
        vids = self.yt.videos().list(part="snippet,statistics,contentDetails", id=",".join(ids)).execute().get("items", [])
        ch_ids = sorted({v["snippet"]["channelId"] for v in vids})
        ledger.spend_quota("channels.list")
        chans = self.yt.channels().list(part="statistics", id=",".join(ch_ids[:50])).execute().get("items", [])
        subs = {c["id"]: int(c["statistics"].get("subscriberCount", 0)) for c in chans}
        return [{
            "id": v["id"],
            "title": v["snippet"]["title"],
            "channel": v["snippet"]["channelTitle"],
            "channel_id": v["snippet"]["channelId"],
            "channel_subs": subs.get(v["snippet"]["channelId"], 0),
            "published_at": v["snippet"]["publishedAt"],
            "duration": v["contentDetails"].get("duration"),
            "views": int(v["statistics"].get("viewCount", 0)),
        } for v in vids]

    def research_niches(self, keywords: list[str], days: int = 30, region: str | None = None,
                        language: str | None = None, short_only: bool = False) -> list[dict]:
        results = []
        for kw in keywords:
            vids = self.search(kw, days=days, region=region, language=language, short_only=short_only)
            scored = score_videos(vids)
            scored["keyword"] = kw
            scored["examples"] = sorted(vids, key=lambda v: v["views"] / max(v["channel_subs"], 100), reverse=True)[:5]
            results.append(scored)
        return sorted(results, key=lambda r: r["score"], reverse=True)

    # ------------------------------------------------------------------- writes
    def precheck(self, plan: UploadPlan) -> dict:
        recent = self.recent_uploads(25)
        return check_upload(plan, self.settings, recent, ledger.uploads_in_last_24h()).to_dict()

    def upload(self, file_path: str, plan: UploadPlan, category_id: str = "22",
               thumbnail_path: str | None = None, language: str | None = None) -> dict:
        from googleapiclient.http import MediaFileUpload

        path = Path(file_path).expanduser()
        if not path.is_file():
            raise FileNotFoundError(path)
        report = self.precheck(plan)
        if not report["ok"]:
            raise PolicyBlocked(report)

        description = plan.description
        if plan.is_short and "#shorts" not in (plan.title + description).lower():
            description = (description + "\n\n#Shorts").strip()
        snippet = {"title": plan.title, "description": description, "tags": plan.tags, "categoryId": category_id}
        if language:
            snippet["defaultLanguage"] = language
            snippet["defaultAudioLanguage"] = language
        body = {
            "snippet": snippet,
            # Always uploaded private: a human reviews it in Studio, then publish_video makes it public.
            "status": {
                "privacyStatus": "private",
                "selfDeclaredMadeForKids": plan.made_for_kids,
                "containsSyntheticMedia": plan.contains_synthetic_media,
                "embeddable": True,
            },
        }
        media = MediaFileUpload(str(path), chunksize=8 * 1024 * 1024, resumable=True)
        request = self.yt.videos().insert(part="snippet,status", body=body, media_body=media)
        response = None
        while response is None:
            _, response = request.next_chunk()
        ledger.spend_quota("videos.insert")
        video_id = response["id"]

        if thumbnail_path:
            ledger.spend_quota("thumbnails.set")
            self.yt.thumbnails().set(videoId=video_id, media_body=MediaFileUpload(str(Path(thumbnail_path).expanduser()))).execute()

        ledger.audit("upload", {
            "video_id": video_id, "title": plan.title, "is_short": plan.is_short,
            "contains_synthetic_media": plan.contains_synthetic_media, "made_for_kids": plan.made_for_kids,
            "ai_tools_used": plan.ai_tools_used, "human_contribution": plan.human_contribution,
            "warnings": [i for i in report["issues"] if i["level"] == "warn"],
        })
        return {"video_id": video_id, "privacy": "private", "studio_url": f"https://studio.youtube.com/video/{video_id}/edit",
                "warnings": [i for i in report["issues"] if i["level"] == "warn"]}

    def _get_video_parts(self, video_id: str) -> dict:
        ledger.spend_quota("videos.list")
        items = self.yt.videos().list(part="snippet,status", id=video_id).execute().get("items", [])
        if not items:
            raise ValueError(f"Video {video_id} not found on this channel.")
        return items[0]

    def publish(self, video_id: str, publish_at: str | None = None) -> dict:
        v = self._get_video_parts(video_id)
        status = {k: v["status"][k] for k in ("selfDeclaredMadeForKids", "containsSyntheticMedia", "embeddable", "license")
                  if k in v["status"]}
        if publish_at:
            status.update(privacyStatus="private", publishAt=publish_at)  # scheduled publishing
        else:
            status["privacyStatus"] = "public"
        ledger.spend_quota("videos.update")
        self.yt.videos().update(part="status", body={"id": video_id, "status": status}).execute()
        ledger.audit("publish", {"video_id": video_id, "publish_at": publish_at})
        return {"video_id": video_id, "status": "scheduled" if publish_at else "public", "publish_at": publish_at}

    def update_metadata(self, video_id: str, title: str | None = None, description: str | None = None,
                        tags: list[str] | None = None, contains_synthetic_media: bool | None = None) -> dict:
        v = self._get_video_parts(video_id)
        snippet = {k: v["snippet"][k] for k in ("title", "description", "tags", "categoryId", "defaultLanguage")
                   if k in v["snippet"]}
        before = {"title": snippet.get("title"), "description": snippet.get("description"), "tags": snippet.get("tags")}
        if title is not None:
            snippet["title"] = title
        if description is not None:
            snippet["description"] = description
        if tags is not None:
            snippet["tags"] = tags
        parts, body = ["snippet"], {"id": video_id, "snippet": snippet}
        if contains_synthetic_media is not None:
            status = {k: v["status"][k] for k in ("privacyStatus", "selfDeclaredMadeForKids", "embeddable", "license", "publishAt")
                      if k in v["status"]}
            status["containsSyntheticMedia"] = contains_synthetic_media
            body["status"] = status
            parts.append("status")
        ledger.spend_quota("videos.update")
        self.yt.videos().update(part=",".join(parts), body=body).execute()
        ledger.audit("update_metadata", {"video_id": video_id, "before": before,
                                         "after": {"title": title, "description": description, "tags": tags,
                                                   "contains_synthetic_media": contains_synthetic_media}})
        return {"video_id": video_id, "updated": parts}

    def comments(self, video_id: str, limit: int = 50) -> list[dict]:
        ledger.spend_quota("commentThreads.list")
        resp = self.yt.commentThreads().list(part="snippet", videoId=video_id, maxResults=min(limit, 100),
                                             order="relevance", textFormat="plainText").execute()
        return [{
            "comment_id": t["snippet"]["topLevelComment"]["id"],
            "author": t["snippet"]["topLevelComment"]["snippet"]["authorDisplayName"],
            "text": t["snippet"]["topLevelComment"]["snippet"]["textDisplay"],
            "likes": t["snippet"]["topLevelComment"]["snippet"].get("likeCount", 0),
            "replies": t["snippet"].get("totalReplyCount", 0),
        } for t in resp.get("items", [])]

    def reply(self, comment_id: str, text: str) -> dict:
        ledger.spend_quota("comments.insert")
        resp = self.yt.comments().insert(part="snippet", body={"snippet": {"parentId": comment_id, "textOriginal": text}}).execute()
        ledger.audit("reply", {"parent_id": comment_id, "text": text, "reply_id": resp["id"]})
        return {"reply_id": resp["id"]}
