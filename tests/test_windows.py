from guestlist import windows
from guestlist.meta import sam


def result(dets):
    return sam.SamResult("", dets, (100, 100), len({d.frame for d in dets}), 0.0, 0.0, True)


def test_plan_covers_every_frame_with_overlap_and_folds_a_short_tail():
    spans = windows.plan_windows(720, 12, window_s=10, overlap_s=1)
    assert spans[0][0] == 0 and spans[-1][1] == 720
    for (a0, a1), (b0, b1) in zip(spans, spans[1:]):
        assert b0 == a1 - 12  # one second shared, for stitching
    assert windows.plan_windows(100, 12) == [(0, 100)]
    # a 30-frame tail would be a wasteful request: it joins the last window instead
    assert windows.plan_windows(246, 12, window_s=10, overlap_s=1)[-1] == (108, 246)


def test_split_halves_still_overlap():
    a, b = windows.split_span(0, 120, 12)
    assert a[0] == 0 and b[1] == 120 and a[1] - b[0] == 12


def test_stitch_joins_the_same_person_across_a_seam_and_keeps_strangers_apart():
    # window A frames 0-9, window B frames 8-17 (local 0-9); person "a0" == "b5"; "a1" leaves before the seam
    wa = [sam.Detection(f, "0", (10 + f, 10, 40 + f, 80)) for f in range(10)] + \
         [sam.Detection(f, "1", (60, 10, 90, 80)) for f in range(5)]
    wb = [sam.Detection(f, "5", (18 + f, 10, 48 + f, 80)) for f in range(10)] + \
         [sam.Detection(f, "2", (60, 60, 90, 99)) for f in range(4, 10)]
    dets, links = windows.stitch([windows.Window(0, 10, result(wa)), windows.Window(8, 18, result(wb))])
    tracks = {}
    for d in dets:
        tracks.setdefault(d.object_id, []).append(d.frame)
    assert len(links) == 1 and links[0]["from"] == "w0:0" and links[0]["to"] == "w1:5"
    assert tracks["0"] == list(range(18))      # one clip-wide id, overlap frames emitted once
    assert tracks["1"] == list(range(5))
    assert tracks["2"] == list(range(12, 18))  # global frames, ids ordered by first appearance
    assert sorted(tracks) == ["0", "1", "2"]


def test_saturation_is_sixteen_ids():
    full = [sam.Detection(0, str(i), (0, 0, 5, 5)) for i in range(sam.MAX_IDS)]
    assert windows.Window(0, 60, result(full)).saturated
    assert not windows.Window(0, 60, result(full[:-1])).saturated


def test_iou():
    assert windows.iou((0, 0, 10, 10), (0, 0, 10, 10)) == 1.0
    assert windows.iou((0, 0, 10, 10), (10, 0, 20, 10)) == 0.0
    assert abs(windows.iou((0, 0, 10, 10), (5, 0, 15, 10)) - 1 / 3) < 1e-9
