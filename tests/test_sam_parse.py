import json

import numpy as np
import pytest

from conftest import FIXTURES
from guestlist.meta import sam


def test_doc_sample_parses_into_two_objects_with_box_local_masks():
    dets, size = sam.parse((FIXTURES / "sam_doc_sample.txt").read_text().strip())
    assert size == (320, 334)
    by_id = {d.object_id: d for d in dets}
    assert set(by_id) == {"0", "1"}
    d0 = by_id["0"]
    # x2/y2 are inclusive on the wire; boxes are stored right/bottom-exclusive
    assert d0.box == (211, 228, 271, 255)
    m = d0.mask_array()
    assert m.shape == (27, 60)  # height, width = the box, not the frame
    assert set(m.flatten().tolist()) <= {0, 1}
    assert 0.5 < m.mean() <= 1.0


def test_tracks_group_by_object_and_sort_by_frame():
    text = (FIXTURES / "sam_doc_sample.txt").read_text().strip()
    later = text.replace("<0f>", "<5f>", 1)
    dets, _ = sam.parse(later + "\n" + text)
    result = sam.SamResult(text, dets, (320, 334), 0, 0.0, 0.0, True)
    tracks = result.tracks()
    assert [d.frame for d in tracks["0"]] == [0, 5]


def test_box_prompt_builder_matches_wire_grammar():
    prompt = sam.build_objects_prompt((1800, 1200), {1: (0, (444, 626, 676, 850))})
    # builder writes x2 = right - 1, y2 = bottom - 1
    assert prompt == "<0f>1<|box;x1=444;y1=626;x2=675;y2=849;w=1800;h=1200|>"


@pytest.mark.skipif(not (FIXTURES / "sam_concept_spike.json").exists(), reason="spike fixture not recorded")
def test_real_spike_output_parses_with_confidence_and_one_bit_masks():
    rec = json.loads((FIXTURES / "sam_concept_spike.json").read_text())
    dets, size = sam.parse(rec["text"])
    assert size == tuple(rec["frame_size"])
    assert dets, "expected at least one person"
    assert all(d.confidence is not None and 0 <= d.confidence <= 1 for d in dets)
    assert all(d.mask.encoding == "one_bit" for d in dets)
    # raster long side is capped by the API; fit_to_box scales it back over the full box
    big = max(dets, key=lambda d: d.box[3] - d.box[1])
    assert max(big.mask.height, big.mask.width) <= 1024
    m = sam.fit_to_box(np.zeros((big.mask.height, big.mask.width), np.uint8), big.box)
    assert m.shape == (big.box[3] - big.box[1], big.box[2] - big.box[0])
    assert {d.frame for d in dets} <= set(range(rec["frames_in_fixture"]))
