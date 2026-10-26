import importlib

import pytest

from guestlist.meta import client, pricing


def test_token_cost_uses_cached_rate_for_cached_tokens():
    # 1M fresh in + 1M out on Spark = 1.25 + 4.25
    assert pricing.token_cost("muse-spark-1.3", 1_000_000, 0, 1_000_000) == pytest.approx(5.50)
    # half the input cached
    assert pricing.token_cost("muse-spark-1.3", 1_000_000, 500_000, 0) == pytest.approx(0.625 + 0.075)


def test_sam_video_cost_has_a_50_frame_minimum():
    assert pricing.sam_video_cost(10) == pytest.approx(0.01)
    assert pricing.sam_video_cost(720) == pytest.approx(0.144)


def test_contributor_models_are_refused():
    with pytest.raises(ValueError):
        client.check_model("muse-spark-1.3-contributor")
    assert client.check_model("muse-spark-1.3") == "muse-spark-1.3"


def test_cache_keys_are_deterministic_and_budget_guard_stops(tmp_path, monkeypatch):
    monkeypatch.setenv("GUESTLIST_CACHE", str(tmp_path))
    monkeypatch.setenv("GUESTLIST_BUDGET_USD", "1.00")
    from guestlist.meta import cache
    cache = importlib.reload(cache)
    assert cache.key("a", {"x": 1, "y": 2}) == cache.key("a", {"y": 2, "x": 1})
    cache.charge("test", "sam-3.1", 0.75)
    assert cache.spent() == pytest.approx(0.75)
    cache.guard(0.2)
    with pytest.raises(cache.BudgetExceeded):
        cache.guard(0.3)
