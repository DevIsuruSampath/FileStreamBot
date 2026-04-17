from __future__ import annotations

import time

from FileStream.bot import work_loads


client_stats: dict[int, dict] = {}
EWMA_ALPHA = 0.35


def _ewma(current: float, new_value: float, alpha: float = EWMA_ALPHA) -> float:
    if current <= 0:
        return float(new_value)
    return (current * (1.0 - alpha)) + (float(new_value) * alpha)


def ensure_client_stat(index: int) -> dict:
    stat = client_stats.get(index)
    if stat is None:
        stat = {
            "avg_first_byte_ms": 0.0,
            "avg_throughput_bps": 0.0,
            "completed_streams": 0,
            "consecutive_failures": 0,
            "last_completed_at": 0.0,
            "last_error_at": 0.0,
        }
        client_stats[index] = stat
    return stat


def choose_best_client(available_indexes) -> int:
    best_index = None
    best_score = None

    for index in sorted(available_indexes):
        stat = ensure_client_stat(index)
        score = (
            int(work_loads.get(index, 0)),
            int(stat.get("consecutive_failures", 0)),
            float(stat.get("avg_first_byte_ms", 0.0)),
            -float(stat.get("avg_throughput_bps", 0.0)),
            index,
        )
        if best_score is None or score < best_score:
            best_score = score
            best_index = index

    if best_index is None:
        raise RuntimeError("No available clients")
    return best_index


def record_stream_completed(index: int, *, bytes_sent: int, duration_s: float, first_byte_s: float | None = None) -> None:
    stat = ensure_client_stat(index)
    stat["completed_streams"] = int(stat.get("completed_streams", 0)) + 1
    stat["consecutive_failures"] = 0
    stat["last_completed_at"] = time.time()

    if first_byte_s is not None and first_byte_s >= 0:
        first_byte_ms = float(first_byte_s) * 1000.0
        stat["avg_first_byte_ms"] = _ewma(float(stat.get("avg_first_byte_ms", 0.0)), first_byte_ms)

    if duration_s > 0 and bytes_sent > 0:
        throughput_bps = float(bytes_sent) / float(duration_s)
        stat["avg_throughput_bps"] = _ewma(float(stat.get("avg_throughput_bps", 0.0)), throughput_bps)


def record_stream_failed(index: int) -> None:
    stat = ensure_client_stat(index)
    stat["consecutive_failures"] = int(stat.get("consecutive_failures", 0)) + 1
    stat["last_error_at"] = time.time()
