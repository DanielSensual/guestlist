import random
import shutil

import numpy as np
import pytest

from conftest import FIXTURES
from guestlist.meta import sam


def rle_to_string(counts: list[int]) -> str:
    """pycocotools' rleToString, to round-trip our decoder."""
    out = []
    for i, x in enumerate(counts):
        if i > 2:
            x -= counts[i - 2]
        more = True
        while more:
            c = x & 0x1F
            x >>= 5
            more = (x != -1) if (c & 0x10) else (x != 0)
            if more:
                c |= 0x20
            out.append(chr(c + 48))
    return "".join(out)


def test_rle_to_array_is_column_major():
    a = sam.rle_to_array({"size": [2, 3], "counts": [1, 2, 3]})
    assert a.tolist() == [[0, 1, 0], [1, 0, 0]]


def test_compressed_rle_round_trips():
    rng = random.Random(7)
    for _ in range(50):
        counts = [rng.randint(0, 400) for _ in range(rng.randint(1, 40))]
        assert sam.rle_counts(rle_to_string(counts)) == counts


@pytest.mark.skipif(shutil.which("node") is None or not sam.NODE_DECODER.parent.joinpath("node_modules").exists(),
                    reason="node decoder not installed (cd tools/sam-decode && npm ci)")
def test_node_bulk_decode_matches_python_decoder():
    dets, _ = sam.parse((FIXTURES / "sam_doc_sample.txt").read_text())
    bulk = sam.decode_masks(dets)
    for d in dets:
        assert np.array_equal(bulk[(d.frame, d.object_id)], d.mask_array())
