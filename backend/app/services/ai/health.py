"""
Per-provider health tracking (Section 6.7).

Section 6.7: "the gateway tracks rolling error rate and latency per
provider; a provider is marked degraded after a defined threshold of
consecutive failures or elevated latency (e.g. 3 consecutive timeouts or
>2x normal p95 latency) within a short window."

In-process state, like interview_ws_registry — correct at this project's
single-backend-process scale. A multi-instance deployment would move this to
Redis so all instances share one view of provider health; flagged rather
than silently assumed, since a per-instance view means each instance
independently rediscovers an outage.
"""
import statistics
import time
from dataclasses import dataclass, field

# Rolling window of recent latencies used for the p95 comparison. Small
# enough to react within a session, large enough that one slow call doesn't
# read as degradation.
_LATENCY_WINDOW = 20
_MIN_SAMPLES_FOR_LATENCY_CHECK = 8
_LATENCY_DEGRADATION_MULTIPLIER = 2.0


@dataclass
class ProviderHealth:
    name: str
    consecutive_failures: int = 0
    total_calls: int = 0
    total_failures: int = 0
    degraded_until: float = 0.0
    recent_latencies_ms: list[float] = field(default_factory=list)
    baseline_p95_ms: float | None = None

    @property
    def error_rate(self) -> float:
        return (self.total_failures / self.total_calls) if self.total_calls else 0.0


class ProviderHealthTracker:
    def __init__(self, *, degraded_after: int = 3, cooldown_seconds: float = 60.0):
        self._degraded_after = degraded_after
        self._cooldown_seconds = cooldown_seconds
        self._health: dict[str, ProviderHealth] = {}

    def _get(self, provider: str) -> ProviderHealth:
        if provider not in self._health:
            self._health[provider] = ProviderHealth(name=provider)
        return self._health[provider]

    def is_degraded(self, provider: str) -> bool:
        """
        True while a provider is in its cooldown window. The gateway skips
        degraded providers on the way down the chain, but still tries them as
        a last resort rather than failing the turn outright (see gateway.py).
        """
        return self._get(provider).degraded_until > time.monotonic()

    def record_success(self, provider: str, latency_ms: float) -> None:
        health = self._get(provider)
        health.total_calls += 1
        health.consecutive_failures = 0

        health.recent_latencies_ms.append(latency_ms)
        if len(health.recent_latencies_ms) > _LATENCY_WINDOW:
            health.recent_latencies_ms.pop(0)

        # Establish a baseline once there's enough signal, then treat
        # sustained >2x p95 as degradation per Section 6.7.
        if len(health.recent_latencies_ms) >= _MIN_SAMPLES_FOR_LATENCY_CHECK:
            current_p95 = self._p95(health.recent_latencies_ms)
            if health.baseline_p95_ms is None:
                health.baseline_p95_ms = current_p95
            elif current_p95 > health.baseline_p95_ms * _LATENCY_DEGRADATION_MULTIPLIER:
                self.mark_degraded(provider)
            else:
                # Slow drift downward keeps the baseline honest as real
                # provider performance changes, without letting one fast
                # burst reset it so low that normal latency reads as 2x.
                health.baseline_p95_ms = min(health.baseline_p95_ms, current_p95)

    def record_failure(self, provider: str) -> None:
        health = self._get(provider)
        health.total_calls += 1
        health.total_failures += 1
        health.consecutive_failures += 1
        if health.consecutive_failures >= self._degraded_after:
            self.mark_degraded(provider)

    def mark_degraded(self, provider: str) -> None:
        self._get(provider).degraded_until = time.monotonic() + self._cooldown_seconds

    def snapshot(self) -> dict[str, dict]:
        """For the admin/ops observability view (Section 6.7, Section 16)."""
        now = time.monotonic()
        return {
            name: {
                "degraded": health.degraded_until > now,
                "consecutiveFailures": health.consecutive_failures,
                "totalCalls": health.total_calls,
                "totalFailures": health.total_failures,
                "errorRate": round(health.error_rate, 4),
                "baselineP95Ms": round(health.baseline_p95_ms, 1) if health.baseline_p95_ms else None,
            }
            for name, health in self._health.items()
        }

    def reset(self) -> None:
        """Test-only: clears all tracked health so cases don't leak into each other."""
        self._health.clear()

    @staticmethod
    def _p95(values: list[float]) -> float:
        if len(values) < 2:
            return values[0] if values else 0.0
        # `n=20` quantiles -> index 18 is the 95th percentile boundary.
        return statistics.quantiles(values, n=20)[18]
