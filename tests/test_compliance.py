from yt_automizer.compliance import UploadPlan, check_upload, similarity
from yt_automizer.config import Settings

GOOD = dict(
    title="How F1 floors make downforce: ground effect explained",
    description="I break down venturi tunnels with my own CFD runs. Sources: FIA 2026 technical regulations.",
    made_for_kids=False,
    contains_synthetic_media=False,
    human_contribution="My own idea, CFD simulations I ran, my voice narration and my edit of the footage.",
    ai_tools_used=["Claude for script draft"],
)


def rules(report):
    return {(i.level, i.rule) for i in report.issues}


def test_good_plan_passes():
    r = check_upload(UploadPlan(**GOOD), Settings())
    assert r.ok, r.issues


def test_missing_declarations_block():
    plan = UploadPlan(**{**GOOD, "made_for_kids": None, "contains_synthetic_media": None})
    r = check_upload(plan, Settings())
    assert not r.ok
    assert ("block", "made_for_kids") in rules(r)
    assert ("block", "ai_disclosure") in rules(r)


def test_no_human_contribution_blocks():
    r = check_upload(UploadPlan(**{**GOOD, "human_contribution": "auto"}), Settings())
    assert ("block", "inauthentic_content") in rules(r)


def test_realistic_tool_without_disclosure_warns():
    r = check_upload(UploadPlan(**{**GOOD, "ai_tools_used": ["ElevenLabs voice clone"]}), Settings())
    assert r.ok
    assert ("warn", "ai_disclosure") in rules(r)


def test_near_duplicate_blocks():
    recent = [{"title": GOOD["title"], "description": GOOD["description"]}]
    r = check_upload(UploadPlan(**GOOD), Settings(), recent_uploads=recent)
    assert not r.ok


def test_daily_cap_blocks():
    r = check_upload(UploadPlan(**GOOD), Settings(max_uploads_per_day=2), uploads_last_24h=2)
    assert not r.ok


def test_limits():
    r = check_upload(UploadPlan(**{**GOOD, "title": "x" * 101, "tags": ["a" * 200] * 3}), Settings())
    assert not r.ok
    assert sum(1 for i in r.issues if i.rule == "metadata") == 2


def test_sensitive_topic_warns():
    plan = UploadPlan(**{**GOOD, "title": "Best crypto investing strategy for 2027"})
    assert ("warn", "sensitive_topic") in rules(check_upload(plan, Settings()))


def test_long_short_blocks():
    plan = UploadPlan(**{**GOOD, "is_short": True, "duration_seconds": 240})
    assert ("block", "shorts") in rules(check_upload(plan, Settings()))


def test_similarity_bounds():
    assert similarity("a b c d", "a b c d") == 1.0
    assert similarity("a b c d", "w x y z") == 0.0
    assert similarity("", "a b c") == 0.0
