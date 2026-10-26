import json

import numpy as np
import pytest
from fastapi.testclient import TestClient

from guestlist import roster, tracks
from guestlist.app import create_app
from guestlist.meta import sam, spark

SIZE = (720, 1280)


def track(oid, frames, box, clip="c"):
    return tracks.build_tracks([sam.Detection(f, oid, box, 0.9) for f in frames], clip=clip, fps=12,
                               frame_size=SIZE)[0]


def test_link_geometry_accepts_a_handover_and_rules_out_the_impossible():
    a = track("0", range(0, 60), (300, 300, 420, 700))
    b = track("1", range(66, 120), (310, 300, 430, 700))
    g = roster.link_geometry(a, b)
    assert g and g["gap_s"] == 0.58 and g["covisible_frames"] == 0
    together = track("2", range(30, 90), (310, 300, 430, 700))
    assert roster.link_geometry(a, together) is None            # on screen together for 30 frames
    far = track("3", range(66, 120), (0, 0, 60, 120))
    assert roster.link_geometry(a, far) is None                 # wrong place, wrong size
    late = track("4", range(140, 200), (310, 300, 430, 700))
    assert roster.link_geometry(a, late) is None                # 6.7 s later
    assert roster.link_geometry(b, a) is None                   # only forward in time


def test_split_track_and_eval_cases_use_provably_different_distractors():
    t = track("0", range(0, 120), (300, 300, 420, 700))
    a, b = roster.split_track(t, gap_s=1.0)
    assert a.last < b.first and b.first - a.last >= 12 and a.track_id == "0:a"
    other = track("1", range(60, 120), (500, 300, 620, 700))
    cases = roster.eval_cases([t, other], min_seconds=4.0)
    assert cases[0][0].track_id == "0:a" and cases[0][2] == [other]  # `other` is long enough to be a case too


def test_brighten_lifts_dark_crops_but_never_darkens():
    dark = np.full((10, 10, 3), 40, np.uint8)
    assert roster.brighten(dark).mean() > 100
    bright = np.full((10, 10, 3), 230, np.uint8)
    assert np.array_equal(roster.brighten(bright), bright)


def test_proposals_follow_the_measured_thresholds():
    letters = {"A": "c/1", "B": "c/2"}
    strong = roster.proposals_from_answer("c/0", letters, {"match": "A", "also_same": ["B"], "confidence": 0.93,
                                                           "evidence": "e"}, "within")
    assert [(p.b, p.status) for p in strong] == [("c/1", "suggested"), ("c/2", "pending")]
    weak = roster.proposals_from_answer("c/0", letters, {"match": "A", "also_same": [], "confidence": 0.6,
                                                         "evidence": "e"}, "within")
    assert weak == []
    none = roster.proposals_from_answer("c/0", letters, {"match": spark.NONE, "also_same": [], "confidence": 0.9,
                                                         "evidence": "e"}, "within")
    assert none == []


def test_conflicts_when_two_people_seen_together_match_one():
    ps = [roster.Proposal("a/1", "b/9", "across", status="suggested"),
          roster.Proposal("a/2", "b/9", "across", status="pending")]
    roster.flag_conflicts(ps, {frozenset(("a/1", "a/2"))})
    assert [p.status for p in ps] == ["conflict", "conflict"]
    assert ps[0].conflicts_with == ["a/2~b/9"]
    r = roster.Roster("/nonexistent/roster.json")
    r.proposals = ps
    r.decide("a/1~b/9", accept=True)
    assert [(p.status, p.decided_by) for p in ps] == [("accepted", "human"), ("rejected", "rule")]
    with pytest.raises(ValueError):
        r.decide("a/2~b/9", accept=True)  # its rival is already accepted


def _roster_file(tmp_path):
    def t(clip, tid, first, secs, area=0.05):
        return {"clip": clip, "first_s": first, "last_s": first + secs, "seconds_on_screen": secs,
                "median_area": area, "thumb": f"thumbs/{clip}/{tid}.jpg", "label": "", "kind": ""}
    data = {"clips": {"a": {}, "b": {}},
            "tracks": {"a/0": t("a", "0", 0, 5), "a/1": t("a", "1", 6, 3), "a/2": t("a", "2", 1, 0.5, 0.005),
                       "b/0": t("b", "0", 0, 4)},
            "proposals": [{"a": "a/0", "b": "a/1", "scope": "within", "status": "suggested",
                           "spark": {"via": "match", "confidence": 0.95, "evidence": "same red jacket", "sheet": ""}},
                          {"a": "a/0", "b": "b/0", "scope": "across", "status": "pending",
                           "spark": {"via": "match", "confidence": 0.8, "evidence": "maybe", "sheet": ""}}],
            "names": {}, "confirmed": []}
    p = tmp_path / "roster.json"
    p.write_text(json.dumps(data))
    return p


def test_people_are_derived_from_accepted_merges_only(tmp_path):
    r = roster.Roster(_roster_file(tmp_path))
    assert len(r.people()) == 4
    assert r.accept_suggested() == 1
    people = r.people()
    first = people[0]
    assert first["tracks"] == ["a/0", "a/1"] and first["seconds"] == 8 and first["label"] == "#1"
    assert [p["kind"] for p in people].count("crowd") == 1
    r.set_name("a/1", "  Maria ")
    r.confirm("a/0")
    r.save()
    again = roster.Roster(r.path)
    assert again.person("a/0")["name"] == "Maria" and again.person("a/1")["confirmed"]
    again.decide("a/0~b/0", True)  # a new fragment joins: what the human confirmed is no longer the whole person
    assert again.person("b/0")["tracks"] == ["a/0", "a/1", "b/0"] and not again.person("b/0")["confirmed"]


def test_review_page_and_one_click_decisions(tmp_path):
    path = _roster_file(tmp_path)
    client = TestClient(create_app(tmp_path))
    page = client.get("/")
    assert page.status_code == 200 and "Accept all 1 suggested" in page.text and "same red jacket" in page.text
    frag = client.post("/proposals/decide", data={"pid": "a/0~b/0", "accept": "true"})
    assert frag.status_code == 200 and frag.text.lstrip().startswith("<main") and "across clips" not in frag.text
    assert json.loads(path.read_text())["proposals"][1]["decided_by"] == "human"
    client.post("/proposals/accept-suggested")
    r = roster.Roster(path)
    assert r.person("b/0")["tracks"] == ["a/0", "a/1", "b/0"]
    client.post("/people/name", data={"pid": "b/0", "name": "Maria"})
    assert "Maria" in client.get("/").text
