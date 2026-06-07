"""Explainable statistical anomaly detection.

A small, defensible detector — a rolling-window z-score — rather than an opaque
model. It learns each workload's own baseline from recent history and flags when
the latest calls deviate from *that* baseline, which a fixed threshold can't do
(a workload normally at 50ms jumping to 300ms is anomalous but well under a
1000ms ceiling). Every result carries the numbers behind it so an alert can
explain itself.
"""

from dataclasses import dataclass
from statistics import fmean, pstdev


@dataclass
class AnomalyResult:
    firing: bool
    z: float  # how many baseline std-devs the recent mean sits above the baseline
    recent_mean: float
    baseline_mean: float
    baseline_std: float
    baseline_n: int


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
