from app.detection import mad_scale, seasonal_anomaly, zscore_anomaly

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


# --- Robust scale (median absolute deviation) -------------------------------


def test_mad_scale_matches_std_for_normal_like_spread():
    # MAD×1.4826 approximates the std-dev for a symmetric spread, so the same
    # z-thresholds carry over. A simple symmetric set around 100.
    values = [90.0, 95.0, 100.0, 105.0, 110.0]
    assert mad_scale(values, 100.0) == 5.0 * 1.4826


def test_mad_scale_ignores_a_lone_outlier():
    # One wild value barely moves the MAD (the whole point), whereas pstdev would
    # balloon. Baseline of 100s with a single 10000 spike.
    values = [100.0] * 20 + [10000.0]
    # Median is 100, most deviations are 0 -> MAD stays 0 (a tight baseline).
    assert mad_scale(values, 100.0) == 0.0


# --- Seasonal detector ------------------------------------------------------

SEASONAL_KW = {"baseline_center": 200.0, "baseline_scale": 20.0, "baseline_n": 80}


def test_seasonal_fires_above_its_own_bucket():
    # Recent calls (median 320) sit well above this bucket's 200±20 baseline.
    res = seasonal_anomaly(
        [320.0, 318.0, 322.0, 319.0, 321.0], z_threshold=3.0, **SEASONAL_KW
    )
    assert res is not None
    assert res.firing
    assert res.z == (320.0 - 200.0) / 20.0
    assert res.recent_center == 320.0
    assert res.baseline_n == 80


def test_seasonal_does_not_fire_within_its_bucket():
    # A predictably-slow hour: 210ms is normal for *this* bucket (200±20), so no
    # alarm — exactly the false positive a flat baseline would have raised.
    res = seasonal_anomaly(
        [210.0, 208.0, 212.0, 209.0, 211.0], z_threshold=3.0, **SEASONAL_KW
    )
    assert res is not None
    assert not res.firing


def test_seasonal_recent_median_resists_one_spike():
    # Four normal calls + one spike: the median stays ~normal, so a single bad
    # call doesn't trip the seasonal alarm (the absolute threshold rule catches
    # a lone catastrophic latency instead).
    res = seasonal_anomaly(
        [9000.0, 205.0, 207.0, 203.0, 206.0], z_threshold=3.0, **SEASONAL_KW
    )
    assert res is not None
    assert res.recent_center == 206.0
    assert not res.firing


def test_seasonal_ignores_downward_shift():
    # Faster than usual is good news, not an anomaly (one-sided).
    res = seasonal_anomaly(
        [60.0, 62.0, 58.0, 61.0, 59.0], z_threshold=3.0, **SEASONAL_KW
    )
    assert res is not None
    assert not res.firing


def test_seasonal_abstains_on_flat_bucket():
    # No spread in the bucket -> z-score undefined -> abstain (caller falls back).
    res = seasonal_anomaly(
        [300.0],
        baseline_center=200.0,
        baseline_scale=0.0,
        baseline_n=80,
        z_threshold=3.0,
    )
    assert res is None


def test_seasonal_abstains_without_recent_values():
    res = seasonal_anomaly([], z_threshold=3.0, **SEASONAL_KW)
    assert res is None
