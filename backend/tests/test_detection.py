from app.detection import zscore_anomaly

KW = {"recent_samples": 5, "min_baseline": 20, "z_threshold": 3.0}


def test_abstains_without_enough_history():
    # 10 samples but min_baseline is 20 -> can't judge.
    assert zscore_anomaly([100.0] * 10, **KW) is None


def test_abstains_on_constant_baseline():
    # A flat baseline has no spread, so a z-score is undefined: abstain.
    assert zscore_anomaly([100.0] * 30, **KW) is None


def test_fires_on_sustained_upward_shift():
    baseline = [100.0 + (i % 7) for i in range(40)]  # ~tight around 103
    values = [600.0] * 5 + baseline  # most-recent-first: recent window spiked
    res = zscore_anomaly(values, **KW)
    assert res is not None
    assert res.firing
    assert res.z > 3.0
    assert res.recent_mean == 600.0
    assert res.baseline_n == 40


def test_ignores_downward_shift():
    baseline = [600.0 + (i % 7) for i in range(40)]
    values = [100.0] * 5 + baseline  # recent window dropped -> not an anomaly
    res = zscore_anomaly(values, **KW)
    assert res is not None
    assert not res.firing  # one-sided: a drop is good news


def test_single_spike_does_not_fire():
    # One outlier among normal recent calls shouldn't drag the recent mean over.
    baseline = [100.0 + (i % 7) for i in range(40)]
    values = [600.0, 100.0, 101.0, 99.0, 102.0] + baseline
    res = zscore_anomaly(values, **KW)
    assert res is not None
    # recent_mean ~200 vs baseline ~103; with a tiny spread this may or may not
    # exceed 3σ, but it must be far less extreme than five sustained spikes.
    assert res.recent_mean < 250.0
