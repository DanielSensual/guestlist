import json

import jsonschema
import pytest

from conftest import FIXTURES
from guestlist.meta import spark


def test_schema_is_strict_mode_compatible():
    """Strict structured output needs additionalProperties:false and every key required, at every level."""
    def walk(node):
        if node.get("type") == "object":
            assert node.get("additionalProperties") is False
            assert set(node["required"]) == set(node["properties"])
            for child in node["properties"].values():
                walk(child)
        if node.get("type") == "array":
            walk(node["items"])
    walk(spark.EVENT_LOG_SCHEMA)


def test_schema_rejects_missing_fields():
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"clip_summary": "x", "people": []}, spark.EVENT_LOG_SCHEMA)


@pytest.mark.skipif(not (FIXTURES / "spark_event_log_spike.json").exists(), reason="spike fixture not recorded")
def test_real_spike_event_log_matches_schema_and_clip_bounds():
    rec = json.loads((FIXTURES / "spark_event_log_spike.json").read_text())
    data = rec["data"]
    jsonschema.validate(data, spark.EVENT_LOG_SCHEMA)
    labels = {p["label"] for p in data["people"]}
    for ev in data["events"]:
        assert 0 <= ev["t_start"] <= ev["t_end"] <= rec["clip_seconds"] + 1
        assert set(ev["people"]) <= labels
        assert 0 <= ev["confidence"] <= 1
