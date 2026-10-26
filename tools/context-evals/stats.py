"""Statistics shared by the dynamic harness and the improvement loop (issue #3, sections 5.2 and 6).

Cases are clustered (several per skill or domain) and repeated, so differences between two refs use a paired cluster
bootstrap: per case, average the repeats of each arm and take the difference; resample clusters with replacement and
average the case differences. Everything is deterministic for a given seed.
"""

from __future__ import annotations

import hashlib
import math
import random
from collections import defaultdict
from dataclasses import dataclass
from statistics import NormalDist, fmean, pstdev

HOLDOUT_MODULUS = 5
DEFAULT_RESAMPLES = 4000


def is_holdout(case_id: str) -> bool:
    """Deterministic tune/holdout split: sha256(id) % 5 == 0 is holdout."""
    return int(hashlib.sha256(case_id.encode()).hexdigest(), 16) % HOLDOUT_MODULUS == 0


@dataclass(frozen=True)
class Interval:
    mean: float
    lo: float
    hi: float
    se: float
    p_not_greater: float
    """One-sided bootstrap p-value for "the difference is > 0": the share of resamples at or below zero."""
    clusters: int
    cases: int

    @property
    def verdict(self) -> str:
        if self.lo > 0:
            return "better"
        if self.hi < 0:
            return "worse"
        return "inconclusive"

    def mde(self, alpha: float = 0.05, power: float = 0.8) -> float:
        """Cluster-aware minimum detectable effect from the bootstrap standard error (two-sided alpha)."""
        z = NormalDist().inv_cdf
        return (z(1 - alpha / 2) + z(power)) * self.se


def paired_cluster_bootstrap(
    base: dict[str, list[float]],
    arm: dict[str, list[float]],
    clusters: dict[str, str],
    *,
    alpha: float = 0.05,
    resamples: int = DEFAULT_RESAMPLES,
    seed: int = 0,
) -> Interval:
    """Interval for mean(arm - base) over the cases both arms ran, resampling clusters.

    `base` and `arm` map case id to the scores of its repeats; `clusters` maps case id to its cluster (skill or
    domain). Cases missing from either arm are dropped; a case without a cluster is its own cluster.
    """
    shared = sorted(set(base) & set(arm))
    shared = [c for c in shared if base[c] and arm[c]]
    if not shared:
        raise ValueError("no case was run by both arms")
    by_cluster: dict[str, list[float]] = defaultdict(list)
    for case in shared:
        by_cluster[clusters.get(case, case)].append(fmean(arm[case]) - fmean(base[case]))
    groups = [by_cluster[k] for k in sorted(by_cluster)]
    observed = fmean(d for g in groups for d in g)
    rng = random.Random(seed)
    stats = []
    for _ in range(resamples):
        drawn = [d for _ in groups for d in rng.choice(groups)]
        stats.append(fmean(drawn))
    stats.sort()
    lo = stats[int(math.floor(alpha / 2 * (resamples - 1)))]
    hi = stats[int(math.ceil((1 - alpha / 2) * (resamples - 1)))]
    p = sum(1 for s in stats if s <= 0) / resamples
    return Interval(observed, lo, hi, pstdev(stats), p, len(groups), len(shared))


def holm(pvalues: dict[str, float], alpha: float = 0.05) -> dict[str, bool]:
    """Holm step-down: which hypotheses are rejected at family-wise level `alpha`."""
    order = sorted(pvalues, key=pvalues.get)
    rejected: dict[str, bool] = {k: False for k in pvalues}
    for i, key in enumerate(order):
        if pvalues[key] > alpha / (len(order) - i):
            break
        rejected[key] = True
    return rejected


def cohen_kappa(a: list[bool], b: list[bool]) -> float:
    """Cohen's kappa for two raters' binary labels of the same items."""
    if len(a) != len(b) or not a:
        raise ValueError("kappa needs two equally long, non-empty label lists")
    n = len(a)
    observed = sum(x == y for x, y in zip(a, b, strict=True)) / n
    pa, pb = sum(a) / n, sum(b) / n
    expected = pa * pb + (1 - pa) * (1 - pb)
    if expected == 1:
        return 1.0 if observed == 1 else 0.0
    return (observed - expected) / (1 - expected)
