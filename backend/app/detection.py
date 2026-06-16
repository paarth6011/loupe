"""Explainable statistical anomaly detection.

A small, defensible detector — a rolling-window z-score — rather than an opaque
model. It learns each workload's own baseline from recent history and flags when
the latest calls deviate from *that* baseline, which a fixed threshold can't do
(a workload normally at 50ms jumping to 300ms is anomalous but well under a
1000ms ceiling). Every result carries the numbers behind it so an alert can
explain itself.
"""

from dataclasses import dataclass
from statistics import fmean, median, pstdev

# MAD → standard-deviation conversion for a normal distribution. Multiplying the
# median absolute deviation by this makes the robust `scale` directly comparable
# to a classic std-dev, so the same z-thresholds carry over between detectors.
_MAD_TO_STD = 1.4826


@dataclass
class AnomalyResult:
    firing: bool
    z: float  # how many baseline std-devs the recent mean sits above the baseline
    recent_mean: float
    baseline_mean: float
    baseline_std: float
    baseline_n: int


@dataclass
class SeasonalResult:
    firing: bool
    z: float  # robust std-devs the recent median sits above the seasonal baseline
    recent_center: float  # median of the recent window
    baseline_center: float  # the bucket's learned median
    baseline_scale: float  # the bucket's robust std-equivalent (MAD×1.4826)
    baseline_n: int


def mad_scale(values: list[float], center: float) -> float:
    """Robust std-equivalent: the median absolute deviation, scaled to match a
    normal std-dev (see ``_MAD_TO_STD``). Returns 0.0 for an empty input.

    Robust where ``pstdev`` is not: a single slow GC pause or one runaway call
    barely moves the MAD, so it doesn't inflate the baseline's spread and mask
    real regressions (nor get dragged by an outlier into a false alarm).
    """
    if not values:
        return 0.0
    return median([abs(v - center) for v in values]) * _MAD_TO_STD


def seasonal_anomaly(
    recent_values: list[float],
    *,
    baseline_center: float,
    baseline_scale: float,
    baseline_n: int,
    z_threshold: float,
) -> SeasonalResult | None:
    """One-sided robust z-score against a *precomputed seasonal baseline*.

    Unlike ``zscore_anomaly``, the baseline here isn't the immediately-preceding
    samples — it's the median/MAD learned for this workload's current time bucket
    (e.g. "9am"), so a predictably-slow hour is judged against its own normal
    rather than against the quieter calls just before it. Compares the *median*
    of ``recent_values`` (robust to a lone spike) to the bucket's median.

    Returns ``None`` when there's nothing recent to judge or the baseline has no
    spread, so the caller can fall back to the rolling-window detector.
    """
    if not recent_values:
        return None
    if baseline_scale <= 0:
        return None  # flat bucket: a z-score is undefined, so abstain
    recent_center = median(recent_values)
    z = (recent_center - baseline_center) / baseline_scale
    return SeasonalResult(
        firing=z >= z_threshold,
        z=z,
        recent_center=recent_center,
        baseline_center=baseline_center,
        baseline_scale=baseline_scale,
        baseline_n=baseline_n,
    )


def zscore_anomaly(
    values: list[float],
    *,
    recent_samples: int,
    min_baseline: int,
    z_threshold: float,
) -> AnomalyResult | None:
    """One-sided rolling z-score: is the recent mean abnormally HIGH vs baseline?

    ``values`` is ordered most-recent-first. The newest ``recent_samples`` form
    the "recent" window; everything older is the baseline. Only upward
    deviations fire (a latency/cost *drop* is good news).

    Returns ``None`` when there isn't enough history, or the baseline has no
    spread to measure against — the detector abstains rather than guess, leaving
    the absolute-threshold rules to catch those cases.
    """
    if recent_samples < 1:
        return None
    baseline = values[recent_samples:]
    if len(baseline) < min_baseline:
        return None
    std = pstdev(baseline)
    if std <= 0:
        return None  # constant baseline: a z-score is undefined, so abstain
    mean = fmean(baseline)
    recent_mean = fmean(values[:recent_samples])
    z = (recent_mean - mean) / std
    return AnomalyResult(
        firing=z >= z_threshold,
        z=z,
        recent_mean=recent_mean,
        baseline_mean=mean,
        baseline_std=std,
        baseline_n=len(baseline),
    )
