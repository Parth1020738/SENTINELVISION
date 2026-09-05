"""
SentinelVision - Vehicle Class Stabilizer

Stabilizes vehicle class predictions over time using confidence-weighted,
recency-biased evidence accumulation. Prevents single-frame class flickers
while allowing genuine class transitions after persistent evidence.

Phase 2: Vehicle Class Stabilization

Algorithm
---------
For each track ID, maintain a bounded history of (class_name, confidence)
observations. To compute the stable class:

  1. For observation i (0 = oldest, n-1 = newest) in a history of size n:
         position_weight = (i + 1) / n          # linear recency bias
         evidence       = confidence * position_weight
  2. Sum evidence per class across all observations.
  3. The class with the highest total evidence is the stable class.
  4. stability_score = winner_evidence / total_evidence  (clamped 0..1)

Properties
----------
- A single low-confidence flicker contributes little evidence.
- Recent observations matter more than old ones (linear ramp).
- High-confidence observations dominate low-confidence ones.
- Genuine transitions occur once new-class evidence accumulates enough
  to overcome the recency-weighted history of the old class.
- No GPU, no OpenCV, no third-party dependencies.
"""

from collections import defaultdict, deque
from typing import Dict, FrozenSet, Optional, Set, Tuple

# ---------------------------------------------------------------------------
# Default supported classes -- mirrors Phase 1 CLASS_NAMES values.
# ---------------------------------------------------------------------------
DEFAULT_VALID_CLASSES: FrozenSet[str] = frozenset({"car", "motorcycle", "bus", "truck"})


class VehicleClassStabilizer:
    """
    Stabilizes vehicle class predictions per ByteTrack track ID.

    Parameters
    ----------
    history_size : int
        Maximum number of recent observations retained per track.
        Default 12 provides ~0.4 s of history at 30 fps.
    valid_classes : set[str] | frozenset[str] | None
        Set of valid class name strings. None defaults to the four
        SentinelVision vehicle classes (car, motorcycle, bus, truck).
    """

    def __init__(
        self,
        history_size: int = 12,
        valid_classes: Optional[Set[str]] = None,
    ) -> None:
        if history_size < 1:
            raise ValueError(f"history_size must be >= 1, got {history_size}")

        self.history_size: int = history_size
        self.valid_classes: FrozenSet[str] = (
            frozenset(valid_classes) if valid_classes is not None else DEFAULT_VALID_CLASSES
        )

        # Per-track observation history: track_id -> deque[(class_name, confidence)]
        self._history: Dict[int, deque] = defaultdict(
            lambda: deque(maxlen=history_size)
        )

    # ------------------------------------------------------------------
    def update(
        self,
        track_id: int,
        class_name: str,
        confidence: float,
    ) -> Tuple[str, float]:
        """
        Add a new observation for track_id and return the stabilized class.

        Parameters
        ----------
        track_id : int
            ByteTrack track ID.
        class_name : str
            Detected class name (e.g. "car", "motorcycle").
        confidence : float
            Detection confidence in the range [0.0, 1.0].

        Returns
        -------
        tuple[str, float]
            (stable_class, stability_score) where stability_score
            is in [0.0, 1.0].
        """
        self._validate(class_name, confidence)
        self._history[track_id].append((class_name, float(confidence)))
        return self._compute_stable_class(track_id)

    # ------------------------------------------------------------------
    def get_stable_class(self, track_id: int) -> Tuple[Optional[str], float]:
        """
        Query the stable class for track_id without adding an observation.

        Returns
        -------
        tuple[str | None, float]
            (stable_class, stability_score) or (None, 0.0) if the
            track has no history.
        """
        if track_id not in self._history or len(self._history[track_id]) == 0:
            return (None, 0.0)
        return self._compute_stable_class(track_id)

    # ------------------------------------------------------------------
    def cleanup(self, active_track_ids: Set[int]) -> None:
        """
        Remove history for tracks not present in active_track_ids.

        Call once per frame with the set of track IDs observed in that
        frame. Prevents unbounded memory growth from stale tracks.

        Parameters
        ----------
        active_track_ids : set[int]
            Track IDs observed in the current frame.
        """
        stale_ids = set(self._history.keys()) - set(active_track_ids)
        for tid in stale_ids:
            del self._history[tid]

    # ------------------------------------------------------------------
    def remove(self, track_id: int) -> bool:
        """
        Remove a specific track's history.

        Returns
        -------
        bool
            True if the track existed and was removed, False otherwise.
        """
        if track_id in self._history:
            del self._history[track_id]
            return True
        return False

    # ------------------------------------------------------------------
    def reset(self) -> None:
        """Clear all track history."""
        self._history.clear()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _validate(self, class_name: str, confidence: float) -> None:
        """Raise ValueError for invalid class or confidence."""
        if class_name not in self.valid_classes:
            raise ValueError(
                f"Invalid class '{class_name}'. Valid: {sorted(self.valid_classes)}"
            )
        if not isinstance(confidence, (int, float)):
            raise ValueError(
                f"Confidence must be numeric, got {type(confidence).__name__}"
            )
        if not (0.0 <= confidence <= 1.0):
            raise ValueError(
                f"Confidence must be in [0.0, 1.0], got {confidence}"
            )

    def _compute_stable_class(self, track_id: int) -> Tuple[str, float]:
        """
        Compute confidence-weighted, recency-biased stable class.

        See module docstring for the full algorithm description.
        """
        history = self._history[track_id]
        n = len(history)

        # Accumulate weighted evidence per class
        evidence: Dict[str, float] = defaultdict(float)
        for i, (cls, conf) in enumerate(history):
            position_weight = (i + 1) / n  # linear recency ramp: 1/n .. 1.0
            evidence[cls] += conf * position_weight

        total_evidence = sum(evidence.values())
        best_class = max(evidence, key=evidence.get)
        best_evidence = evidence[best_class]

        stability = best_evidence / total_evidence if total_evidence > 0 else 0.0
        return (best_class, stability)

    # ------------------------------------------------------------------
    def __repr__(self) -> str:
        return (
            f"VehicleClassStabilizer("
            f"history_size={self.history_size}, "
            f"tracks={len(self._history)})"
        )
