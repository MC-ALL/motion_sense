from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
import math

from app.models.ingest import EnvTelemetryAggregateRecord, MetricAggregate, TelemetryRecord


EXCLUDED_METRIC_KEYS = {"ts"}


def aggregate_env_records(
    records: list[TelemetryRecord],
    interval: str,
    *,
    limit: int = 1000,
    offset: int = 0,
) -> list[EnvTelemetryAggregateRecord]:
    interval_seconds = parse_interval_seconds(interval)
    buckets: dict[datetime, list[TelemetryRecord]] = defaultdict(list)

    for record in records:
        timestamp = datetime.fromisoformat(record.ts.replace("Z", "+00:00"))
        bucket_start = _bucket_floor(timestamp, interval_seconds)
        buckets[bucket_start].append(record)

    aggregated: list[EnvTelemetryAggregateRecord] = []
    for bucket_start in sorted(buckets.keys(), reverse=True):
        bucket_records = buckets[bucket_start]
        metric_samples: dict[str, list[float]] = defaultdict(list)

        for record in bucket_records:
            for key, value in record.payload.items():
                if key not in EXCLUDED_METRIC_KEYS and _is_numeric(value):
                    metric_samples[key].append(float(value))

        metrics = {
            key: MetricAggregate(
                min=min(values),
                max=max(values),
                avg=sum(values) / len(values),
            )
            for key, values in metric_samples.items()
        }

        aggregated.append(
            EnvTelemetryAggregateRecord(
                bucket_start=bucket_start.isoformat(),
                bucket_end=(bucket_start + timedelta(seconds=interval_seconds)).isoformat(),
                count=len(bucket_records),
                metrics=metrics,
            )
        )

    return aggregated[offset : offset + limit]


def parse_interval_seconds(interval: str) -> int:
    if not interval:
        raise ValueError("interval is required")

    unit = interval[-1]
    value = int(interval[:-1])
    if value <= 0:
        raise ValueError("interval must be positive")

    if unit == "s":
        return value
    if unit == "m":
        return value * 60
    if unit == "h":
        return value * 3600
    if unit == "d":
        return value * 86400
    raise ValueError(f"unsupported interval: {interval}")


def _bucket_floor(timestamp: datetime, interval_seconds: int) -> datetime:
    epoch = timestamp.astimezone(UTC).timestamp()
    bucket_epoch = math.floor(epoch / interval_seconds) * interval_seconds
    return datetime.fromtimestamp(bucket_epoch, tz=UTC)


def _is_numeric(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)
