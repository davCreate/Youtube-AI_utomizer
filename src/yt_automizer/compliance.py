"""Pre-upload policy checks.

These encode YouTube rules that matter for an AI-assisted channel that wants to be
monetized. They are guardrails, not legal advice: YouTube's own pages are the source
of truth and they change. Rules covered:

* Altered or synthetic content disclosure: realistic AI people, voices, places or
  events must be disclosed (API field ``status.containsSyntheticMedia``).
* YPP "inauthentic content" (formerly "repetitious content"): mass-produced,
  template-based or near-identical videos are not monetizable. AI tools are allowed;
  low-effort volume is not. So every upload must state the human's contribution and
  must not be a near-copy of recent uploads, and daily volume is capped.
* Extra care for AI narration/personas on health, finance, news and elections.
* COPPA: "made for kids" must be declared explicitly on every upload.
* Hard API limits on titles, descriptions and tags.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

from .config import Settings

BLOCK = "block"
WARN = "warn"


@dataclass
class Issue:
    level: str  # "block" or "warn"
    rule: str
    message: str


@dataclass
class UploadPlan:
    title: str
    description: str = ""
    tags: list[str] = field(default_factory=list)
    made_for_kids: bool | None = None
    # True when the video shows realistic AI-made or AI-altered people, voices, places or events.
    contains_synthetic_media: bool | None = None
    # Which AI tools were used for what (script, voice, footage, thumbnail...).
    ai_tools_used: list[str] = field(default_factory=list)
    # What the human did: idea, own footage, voice, editing choices, fact-checking...
    human_contribution: str = ""
    script: str = ""
    is_short: bool = False
    duration_seconds: float | None = None


@dataclass
class Report:
    ok: bool
    issues: list[Issue]

    def to_dict(self) -> dict:
        return {"ok": self.ok, "issues": [asdict(i) for i in self.issues]}


_WORD = re.compile(r"[\wáéíóúñü]+", re.IGNORECASE)
_REALISTIC_AI_TOOLS = ("voice", "clone", "tts", "elevenlabs", "avatar", "face", "deepfake",
                       "veo", "sora", "runway", "kling", "lip", "synthesia", "heygen")


def _shingles(text: str, n: int = 3) -> set[tuple[str, ...]]:
    words = [w.lower() for w in _WORD.findall(text)]
    if len(words) < n:
        return {tuple(words)} if words else set()
    return {tuple(words[i : i + n]) for i in range(len(words) - n + 1)}


def similarity(a: str, b: str) -> float:
    """Jaccard similarity of word 3-grams, 0 (different) to 1 (identical)."""
    sa, sb = _shingles(a), _shingles(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def check_upload(
    plan: UploadPlan,
    settings: Settings,
    recent_uploads: list[dict] | None = None,
    uploads_last_24h: int = 0,
) -> Report:
    """``recent_uploads``: dicts with ``title``, ``description`` and optionally ``script``."""
    issues: list[Issue] = []
    recent_uploads = recent_uploads or []

    # --- Hard API limits -------------------------------------------------------
    if not plan.title.strip():
        issues.append(Issue(BLOCK, "metadata", "Title is empty."))
    if len(plan.title) > 100:
        issues.append(Issue(BLOCK, "metadata", f"Title is {len(plan.title)} chars; the limit is 100."))
    if len(plan.description.encode("utf-8")) > 5000:
        issues.append(Issue(BLOCK, "metadata", "Description is over 5000 bytes."))
    if any(c in plan.title + plan.description for c in "<>"):
        issues.append(Issue(BLOCK, "metadata", "Title/description cannot contain '<' or '>'."))
    tag_chars = sum(len(t) + (2 if " " in t else 0) for t in plan.tags) + max(len(plan.tags) - 1, 0)
    if tag_chars > 500:
        issues.append(Issue(BLOCK, "metadata", f"Tags total {tag_chars} chars; the limit is 500."))
    hashtags = re.findall(r"#\w+", plan.title + " " + plan.description)
    if len(hashtags) > 15:
        issues.append(Issue(WARN, "metadata",
                            f"{len(hashtags)} hashtags: YouTube ignores hashtags above 60 and treats many as spam; keep it to 3-5."))

    # --- COPPA -------------------------------------------------------------------
    if plan.made_for_kids is None:
        issues.append(Issue(BLOCK, "made_for_kids",
                            "Declare made_for_kids explicitly (true/false). Required by YouTube/COPPA."))

    # --- AI disclosure -----------------------------------------------------------
    tools_text = " ".join(plan.ai_tools_used).lower()
    looks_realistic = any(k in tools_text for k in _REALISTIC_AI_TOOLS)
    if plan.contains_synthetic_media is None:
        issues.append(Issue(BLOCK, "ai_disclosure",
                            "Set contains_synthetic_media: true if the video has realistic AI-generated or "
                            "AI-altered people, voices, places or events that viewers could mistake for real."))
    elif plan.contains_synthetic_media is False and looks_realistic:
        issues.append(Issue(WARN, "ai_disclosure",
                            f"AI tools listed ({', '.join(plan.ai_tools_used)}) often produce realistic voices/footage. "
                            "If any of it could pass as real, set contains_synthetic_media=true."))

    # --- Inauthentic / mass-produced content ------------------------------------
    contribution = plan.human_contribution.strip()
    if len(contribution) < settings.min_human_contribution_chars:
        issues.append(Issue(BLOCK, "inauthentic_content",
                            "Describe the human's creative contribution (idea, own footage/voice, editing, "
                            f"fact-checking...) in at least {settings.min_human_contribution_chars} characters. "
                            "Fully automated, template-based videos are not monetizable in YPP."))

    if uploads_last_24h >= settings.max_uploads_per_day:
        issues.append(Issue(BLOCK, "inauthentic_content",
                            f"Already {uploads_last_24h} uploads in 24h (cap {settings.max_uploads_per_day}). "
                            "High volume of similar AI videos is the main trigger for channel-level demonetization."))

    candidate = " ".join([plan.title, plan.description, plan.script])
    worst, worst_title = 0.0, ""
    for prev in recent_uploads:
        prev_text = " ".join([prev.get("title", ""), prev.get("description", ""), prev.get("script", "")])
        s = similarity(candidate, prev_text)
        if s > worst:
            worst, worst_title = s, prev.get("title", "")
    if worst >= settings.similarity_block:
        issues.append(Issue(BLOCK, "inauthentic_content",
                            f"{worst:.0%} similar to recent upload '{worst_title}'. Near-duplicates get demonetized."))
    elif worst >= settings.similarity_warn:
        issues.append(Issue(WARN, "inauthentic_content",
                            f"{worst:.0%} similar to '{worst_title}'. Change the angle, structure or script, not just words."))

    # --- Sensitive topics ----------------------------------------------------------
    words = {w.lower() for w in _WORD.findall(candidate)}
    hits = sorted(words & set(settings.sensitive_topics))
    if hits and plan.ai_tools_used:
        issues.append(Issue(WARN, "sensitive_topic",
                            f"Touches {', '.join(hits)} with AI involvement. Fact-check, cite sources in the "
                            "description, and avoid an AI persona presenting itself as an expert."))

    # --- Shorts --------------------------------------------------------------------
    if plan.is_short and plan.duration_seconds is not None and plan.duration_seconds > 180:
        issues.append(Issue(BLOCK, "shorts", "Shorts can be at most 3 minutes (and should be vertical or square)."))

    return Report(ok=not any(i.level == BLOCK for i in issues), issues=issues)
