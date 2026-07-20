# SPDX-License-Identifier: GPL-2.0-only

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Literal

EventCategory = Literal["lifecycle", "control", "input", "debug", "replay", "peripheral"]
EventSource = Literal["service", "user", "replay", "worker"]


@dataclass(frozen=True, slots=True)
class SessionEvent:
    sequence: int
    generation: int
    offset_ms: int
    category: EventCategory
    type: str
    source: EventSource
    data: dict[str, object]

    def public_dict(self) -> dict[str, object]:
        return {
            "sequence": self.sequence,
            "generation": self.generation,
            "offset_ms": self.offset_ms,
            "category": self.category,
            "type": self.type,
            "source": self.source,
            "data": self.data,
        }


@dataclass(frozen=True, slots=True)
class ReplayAction:
    offset_ms: int
    type: Literal[
        "key",
        "button",
        "imu",
        "power",
        "serial",
        "reset",
        "power_off",
        "power_on",
    ]
    payload: object


def serial_metadata(payload: bytes) -> dict[str, object]:
    """Describe UART data without retaining its contents in public diagnostics."""

    return {
        "byte_count": len(payload),
        "sha256": sha256(payload).hexdigest(),
        "content_included": False,
    }
