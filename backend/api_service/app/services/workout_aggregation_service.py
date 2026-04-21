from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.models.ingest import TelemetryRecord
from app.models.workout import (
    WorkoutSessionAggregateResult,
    WorkoutSessionMetrics,
    WorkoutSessionSegment,
)
from app.storage.store import Store


DEFAULT_SESSION_GAP_S = 15 * 60
DEFAULT_TRIGGER_LOOKBACK_S = 6 * 60 * 60
MAX_QUERY_LIMIT = 5000


@dataclass(slots=True)
class ClosedSegment:
    equipment_id: str
    started_at: datetime
    ended_at: datetime
    duration_s: int


@dataclass(slots=True)
class SessionCandidate:
    started_at: datetime
    ended_at: datetime
    equipment_ids: list[str]
    segments: list[WorkoutSessionSegment]


class WorkoutAggregationService:
    def __init__(self, store: Store) -> None:
        self._store = store

    async def aggregate_sessions(
        self,
        *,
        username: str | None = None,
        wristband_id: str | None = None,
        gym_id: str | None = None,
        start: str | None = None,
        end: str | None = None,
        gap_threshold_s: int = DEFAULT_SESSION_GAP_S,
    ) -> WorkoutSessionAggregateResult:
        bindings = await self._store.list_user_wristband_bindings(
            username=username,
            wristband_id=wristband_id,
            gym_id=gym_id,
            active_only=None,
            limit=MAX_QUERY_LIMIT,
            offset=0,
        )

        result = WorkoutSessionAggregateResult()
        query_start = _parse_iso(start) if start is not None else None
        query_end = _parse_iso(end) if end is not None else None

        for binding in bindings:
            binding_start = _parse_iso(binding.bound_at)
            binding_end = _parse_iso(binding.unbound_at) if binding.unbound_at is not None else query_end

            window_start = binding_start if query_start is None else max(binding_start, query_start)
            if binding_end is None:
                window_end = query_end or _utc_now()
            elif query_end is None:
                window_end = binding_end
            else:
                window_end = min(binding_end, query_end)

            if window_end <= window_start:
                continue

            segments = await self._load_closed_segments(
                wristband_id=binding.wristband_id,
                start=window_start,
                end=window_end,
            )
            eligible_segments = [
                item
                for item in segments
                if item.started_at >= binding_start
                and item.ended_at <= (binding_end or item.ended_at)
                and item.duration_s > 0
            ]
            if not eligible_segments:
                continue

            result.processed_bindings += 1
            candidates = self._group_segments(eligible_segments, gap_threshold_s=gap_threshold_s)
            existing_items = await self._store.list_workout_sessions(
                username=binding.username,
                wristband_id=binding.wristband_id,
                gym_id=binding.gym_id,
                start=_format_iso(window_start),
                end=_format_iso(window_end),
                limit=MAX_QUERY_LIMIT,
                offset=0,
            )
            existing_by_started_at = {
                _parse_iso(item.started_at): item
                for item in existing_items
                if item.source == "aggregated"
            }

            for candidate in candidates:
                metrics = await self._build_metrics(
                    wristband_id=binding.wristband_id,
                    session_start=candidate.started_at,
                    session_end=candidate.ended_at,
                    segments=candidate.segments,
                )
                notes = "aggregated from equipment binding events"
                existing = existing_by_started_at.get(candidate.started_at)
                if existing is None:
                    created = await self._store.create_workout_session(
                        username=binding.username,
                        wristband_id=binding.wristband_id,
                        gym_id=binding.gym_id,
                        status="completed",
                        source="aggregated",
                        started_at=_format_iso(candidate.started_at),
                        ended_at=_format_iso(candidate.ended_at),
                        equipment_ids=candidate.equipment_ids,
                        segments=candidate.segments,
                        metrics=metrics,
                        notes=notes,
                    )
                    result.created_sessions += 1
                    result.sessions.append(created)
                    continue

                updated = await self._store.update_workout_session(
                    session_id=existing.session_id,
                    status="completed",
                    ended_at=_format_iso(candidate.ended_at),
                    equipment_ids=candidate.equipment_ids,
                    segments=candidate.segments,
                    metrics=metrics,
                    notes=notes,
                )
                if updated is not None:
                    result.updated_sessions += 1
                    result.sessions.append(updated)

        result.sessions.sort(key=lambda item: (item.started_at, item.session_id), reverse=True)
        return result

    async def aggregate_recent_wristband_activity(
        self,
        *,
        wristband_id: str,
        gym_id: str,
        end: str,
        lookback_s: int = DEFAULT_TRIGGER_LOOKBACK_S,
        gap_threshold_s: int = DEFAULT_SESSION_GAP_S,
    ) -> WorkoutSessionAggregateResult:
        end_dt = _parse_iso(end)
        start_dt = end_dt - timedelta(seconds=lookback_s)
        return await self.aggregate_sessions(
            wristband_id=wristband_id,
            gym_id=gym_id,
            start=_format_iso(start_dt),
            end=end,
            gap_threshold_s=gap_threshold_s,
        )

    async def _load_closed_segments(
        self,
        *,
        wristband_id: str,
        start: datetime,
        end: datetime,
    ) -> list[ClosedSegment]:
        events = await self._store.list_binding_events(
            wristband_id=wristband_id,
            start=_format_iso(start),
            end=_format_iso(end),
            limit=MAX_QUERY_LIMIT,
            offset=0,
        )
        segments: list[ClosedSegment] = []
        for event in sorted(events, key=lambda item: (item.ts, item.id)):
            if event.action != "unbind" or not event.equipment_id or not event.duration_s:
                continue
            ended_at = _parse_iso(event.ts)
            started_at = ended_at - timedelta(seconds=event.duration_s)
            if ended_at <= start or started_at >= end:
                continue
            clipped_start = max(started_at, start)
            clipped_end = min(ended_at, end)
            duration_s = int((clipped_end - clipped_start).total_seconds())
            if duration_s <= 0:
                continue
            segments.append(
                ClosedSegment(
                    equipment_id=event.equipment_id,
                    started_at=clipped_start,
                    ended_at=clipped_end,
                    duration_s=duration_s,
                )
            )
        return segments

    def _group_segments(
        self,
        segments: list[ClosedSegment],
        *,
        gap_threshold_s: int,
    ) -> list[SessionCandidate]:
        if not segments:
            return []

        ordered = sorted(segments, key=lambda item: (item.started_at, item.ended_at, item.equipment_id))
        groups: list[list[ClosedSegment]] = [[ordered[0]]]

        for item in ordered[1:]:
            current_group = groups[-1]
            previous = current_group[-1]
            gap_s = int((item.started_at - previous.ended_at).total_seconds())
            if gap_s <= gap_threshold_s:
                current_group.append(item)
                continue
            groups.append([item])

        candidates: list[SessionCandidate] = []
        for group in groups:
            workout_segments = [
                WorkoutSessionSegment(
                    equipment_id=item.equipment_id,
                    started_at=_format_iso(item.started_at),
                    ended_at=_format_iso(item.ended_at),
                    duration_s=item.duration_s,
                )
                for item in group
            ]
            candidates.append(
                SessionCandidate(
                    started_at=group[0].started_at,
                    ended_at=group[-1].ended_at,
                    equipment_ids=_dedupe_equipment_ids(workout_segments),
                    segments=workout_segments,
                )
            )
        return candidates

    async def _build_metrics(
        self,
        *,
        wristband_id: str,
        session_start: datetime,
        session_end: datetime,
        segments: list[WorkoutSessionSegment],
    ) -> WorkoutSessionMetrics:
        wristband_telemetry = await self._store.list_telemetry(
            device_type="wristband",
            device_id=wristband_id,
            start=_format_iso(session_start),
            end=_format_iso(session_end),
            limit=MAX_QUERY_LIMIT,
            offset=0,
        )
        avg_heart_rate, max_heart_rate, total_steps = _summarize_wristband_metrics(wristband_telemetry)

        total_rep_count = 0
        total_energy_wh = 0.0
        normalized_segments: list[WorkoutSessionSegment] = []
        for segment in segments:
            segment_start = _parse_iso(segment.started_at)
            segment_end = _parse_iso(segment.ended_at or segment.started_at)
            equipment_telemetry = await self._store.list_telemetry(
                device_type="equipment",
                device_id=segment.equipment_id,
                start=segment.started_at,
                end=segment.ended_at,
                limit=MAX_QUERY_LIMIT,
                offset=0,
            )
            rep_count, energy_wh = _summarize_equipment_metrics(equipment_telemetry)
            total_rep_count += rep_count
            total_energy_wh += energy_wh
            normalized_segments.append(
                WorkoutSessionSegment(
                    equipment_id=segment.equipment_id,
                    started_at=_format_iso(segment_start),
                    ended_at=_format_iso(segment_end),
                    duration_s=segment.duration_s,
                    rep_count=rep_count,
                    energy_wh=round(energy_wh, 2),
                )
            )

        segments[:] = normalized_segments
        return WorkoutSessionMetrics(
            avg_heart_rate=avg_heart_rate,
            max_heart_rate=max_heart_rate,
            total_steps=total_steps,
            total_rep_count=total_rep_count,
            total_energy_wh=round(total_energy_wh, 2),
        )


def _summarize_wristband_metrics(records: list[TelemetryRecord]) -> tuple[float | None, int | None, int | None]:
    heart_rates: list[float] = []
    step_counts: list[int] = []
    for record in sorted(records, key=lambda item: item.ts):
        heart_rate = _coerce_float(record.payload.get("heart_rate"))
        if heart_rate is not None and heart_rate > 0:
            heart_rates.append(heart_rate)
        step_count = _coerce_int(record.payload.get("step_count"))
        if step_count is not None and step_count >= 0:
            step_counts.append(step_count)

    avg_heart_rate = round(sum(heart_rates) / len(heart_rates), 1) if heart_rates else None
    max_heart_rate = int(max(heart_rates)) if heart_rates else None
    total_steps = _counter_delta(step_counts)
    return avg_heart_rate, max_heart_rate, total_steps



def _summarize_equipment_metrics(records: list[TelemetryRecord]) -> tuple[int, float]:
    rep_counts: list[int] = []
    energy_values: list[float] = []
    for record in sorted(records, key=lambda item: item.ts):
        rep_count = _coerce_int(record.payload.get("rep_count"))
        if rep_count is not None and rep_count >= 0:
            rep_counts.append(rep_count)
        energy_wh = _coerce_float(record.payload.get("energy_wh"))
        if energy_wh is not None and energy_wh >= 0:
            energy_values.append(energy_wh)
    return _counter_delta(rep_counts), round(_counter_delta_float(energy_values), 2)



def _dedupe_equipment_ids(segments: list[WorkoutSessionSegment]) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for segment in segments:
        if segment.equipment_id in seen:
            continue
        seen.add(segment.equipment_id)
        values.append(segment.equipment_id)
    return values



def _counter_delta(values: list[int]) -> int | None:
    if not values:
        return None
    total = 0
    previous = values[0]
    for value in values[1:]:
        if value >= previous:
            total += value - previous
        else:
            total += value
        previous = value
    return total



def _counter_delta_float(values: list[float]) -> float:
    if not values:
        return 0.0
    total = 0.0
    previous = values[0]
    for value in values[1:]:
        if value >= previous:
            total += value - previous
        else:
            total += value
        previous = value
    return total



def _parse_iso(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)



def _format_iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")



def _utc_now() -> datetime:
    return datetime.now(tz=UTC)



def _coerce_int(value) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip():
        try:
            return int(float(value))
        except ValueError:
            return None
    return None



def _coerce_float(value) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str) and value.strip():
        try:
            return float(value)
        except ValueError:
            return None
    return None
