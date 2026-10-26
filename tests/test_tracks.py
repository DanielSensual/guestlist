import numpy as np

from guestlist import draw, moments, thumbs, tracks
from guestlist.meta import sam, spark

SIZE = (720, 1280)


def dets(oid, frames, box=(300, 300, 500, 900), conf=0.9):
    return [sam.Detection(f, oid, box, conf) for f in frames]


def build(*groups, fps=12.0):
    return tracks.build_tracks([d for g in groups for d in g], clip="t", fps=fps, frame_size=SIZE)


def test_guest_vs_crowd_and_labels_by_first_appearance():
    ts = build(dets("0", range(10, 60)), dets("1", range(0, 12)), dets("2", range(5, 50), box=(0, 0, 40, 60)),
               dets("3", range(0, 40)))
    by_id = {t.track_id: t for t in ts}
    assert by_id["0"].kind == "guest" and by_id["3"].kind == "guest"
    assert by_id["1"].kind == "crowd"       # 1 s on screen
    assert by_id["2"].kind == "crowd"       # 0.3% of the frame
    assert by_id["3"].label == "#1" and by_id["0"].label == "#2"
    assert by_id["1"].label == "c1" and by_id["2"].label == "c2"
    assert [t.kind for t in ts] == ["guest", "guest", "crowd", "crowd"]


def test_gaps_presence_and_flags():
    t = build(dets("0", [*range(0, 24), *range(36, 48)], conf=0.6))[0]
    assert t.gaps() == [(24, 35)]
    assert round(t.missing_frac, 3) == round(12 / 48, 3)
    assert t.presence(0, 2) == 1.0 and t.presence(2, 3) == 0.0 and t.presence(1.5, 2.5) == 0.5
    assert {"low_confidence", "gappy"} <= set(t.flags())
    assert t.box_at(30) is None and t.box_at(40) == (300, 300, 500, 900)


def test_jumps_catch_teleports_and_size_flips_but_not_steady_motion():
    steady = [sam.Detection(f, "0", (300 + 2 * f, 300, 500 + 2 * f, 900)) for f in range(24)]
    t = build(steady)[0]
    assert t.jumps() == [] and "unstable" not in t.flags()
    leap = steady[:12] + [sam.Detection(f, "0", (0, 300, 100, 600)) for f in range(12, 24)]
    assert build(leap)[0].jumps() == [12]


def test_fill_sample_and_sparse_masks():
    ds = dets("0", range(30)) + dets("1", range(30))
    sample = tracks.fill_sample(ds, every=6)
    assert sorted(d.frame for d in sample if d.object_id == "0") == [0, 6, 12, 18, 24]
    t = tracks.build_tracks(ds, clip="t", fps=12, frame_size=SIZE,
                            fills={(d.frame, d.object_id): 0.05 for d in sample})[0]
    assert "sparse_mask" in t.flags()


def test_rle_area():
    assert sam.rle_area({"size": [2, 3], "counts": [1, 2, 3]}) == 2 / 6


def test_thumbnail_candidates_are_spread_out_and_prefer_big_central_boxes():
    small = [sam.Detection(f, "0", (300, 600, 360, 700)) for f in range(0, 30)]
    big = [sam.Detection(f, "0", (200, 200, 520, 1100)) for f in range(30, 60)]
    t = build(small + big)[0]
    picks = thumbs.candidates(t, k=3, min_sep_s=1.0)
    assert picks[0] >= 30
    assert all(abs(a - b) >= 12 for i, a in enumerate(picks) for b in picks[i + 1:])
    img = np.zeros((1280, 720, 3), np.uint8)
    c, origin = thumbs.crop(img, (0, 0, 100, 200))
    assert origin == (0, 0) and c.shape[:2] == (224, 112)


def test_tag_sits_above_the_box_or_inside_when_there_is_no_room():
    assert draw.tag_rect((100, 200, 300, 600), (40, 30), SIZE, 4)[3] <= 200
    x0, y0, x1, y1 = draw.tag_rect((700, 0, 720, 600), (40, 30), SIZE, 4)
    assert y0 >= 0 and x1 <= SIZE[0]
    assert draw.color_for("#9") == draw.color_for("#1") and draw.color_for("c3") == draw.CROWD


def test_moment_checks_against_tracks():
    ts = {t.label: t for t in build(dets("0", range(0, 120)), dets("1", range(0, 30)))}
    assert set(ts) == {"#1", "#2"}
    ok = moments.check_event({"t_start": 0, "t_end": 4, "people": ["#1", "#2"]}, ts)
    assert ok["status"] == "supported" and ok["people"]["#2"]["on_screen_s"] == 2.5
    weak = moments.check_event({"t_start": 2, "t_end": 6, "people": ["#2"]}, ts)
    assert weak["people"]["#2"]["status"] == "weak" and weak["status"] == "review"
    bad = moments.check_event({"t_start": 5, "t_end": 8, "people": ["#2", "#9", spark.UNMARKED]}, ts)
    assert bad["people"]["#2"]["status"] == "unsupported" and bad["people"]["#9"]["status"] == "unknown_tag"
    assert bad["people"][spark.UNMARKED]["status"] == "unmarked" and bad["status"] == "contradicted"
    log = {"people": [{"label": "#2", "first_seen_s": 0.4, "appearance": ""}],
           "events": [{"t_start": 0, "t_end": 4, "people": ["#1", "#2"]}]}
    checked = moments.check_log(log, ts)
    assert checked["people"][0]["first_seen_error_s"] == 0.4
    assert checked["tags_never_mentioned"] == ["#1"]
