"""
SentinelVision - Track Continuity Manager

Converts unstable ByteTrack IDs into stable canonical vehicle IDs.
When ByteTrack temporarily loses a vehicle and later assigns a new ID,
this manager reconnects the new ID to the original canonical vehicle
using multi-signal weighted matching.

Phase 3: Track Continuity

Matching Signals (weighted)
--------------------------
  spatial_distance      - gap between last known and new center
  predicted_position    - gap from velocity-predicted position
  time_gap              - decays as the track stays lost
  size_similarity       - bbox area ratio
  direction_compat      - alignment of movement vs. last velocity
  class_compat          - exact (1.0), motorcycle<->car (0.5), else 0.0

A hard class incompatibility (score 0.0) immediately rejects a candidate.
The weighted total must meet the acceptance threshold to confirm a match.

Public API
----------
  TrackContinuityManager.update(observations, frame_number) -> list[CanonicalObservation]
  TrackContinuityManager.mark_counted(canonical_id) -> bool
  TrackContinuityManager.get_canonical_id(bytetrack_id) -> int | None
  TrackContinuityManager.cleanup() -> int
  TrackContinuityManager.reset()
"""

from dataclasses import dataclass
from math import hypot
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Minimal observation type - duck-type compatible with Phase 1 VehicleObservation
# ---------------------------------------------------------------------------
@dataclass
class TrackObservation:
    """A single tracked vehicle observation in one frame.

    This mirrors the fields of :class:`backend.ai.vehicle_tracker.VehicleObservation`
    needed by the continuity manager, defined here to avoid importing torch-
    dependent Phase 1 code.  Any object with the same public attributes can be
    passed to :meth:`TrackContinuityManager.update`.
    """

    raw_track_id: int
    class_name: str
    bbox: tuple  # (x1, y1, x2, y2)
    center: tuple  # (cx, cy)
    frame_number: int


# ---------------------------------------------------------------------------
# Output type
# ---------------------------------------------------------------------------
@dataclass
class CanonicalObservation:
    """A vehicle observation annotated with a stable canonical ID."""

    canonical_id: int
    bytetrack_id: int
    class_name: str
    bbox: tuple  # (x1, y1, x2, y2)
    center: tuple  # (cx, cy)
    frame_number: int
    counted: bool
    is_reconnected: bool


# ---------------------------------------------------------------------------
# Internal state types
# ---------------------------------------------------------------------------
@dataclass
class _ActiveTrack:
    """State for a currently-visible canonical vehicle."""

    canonical_id: int
    bytetrack_id: int
    center: tuple  # (cx, cy)
    bbox: tuple  # (x1, y1, x2, y2)
    velocity: tuple  # (vx, vy) per-frame displacement
    stabilized_class: str
    counted: bool
    last_frame: int


@dataclass
class _LostTrack:
    """State for a recently-lost track held in the grace-period buffer."""

    canonical_id: int
    center: tuple
    bbox: tuple
    velocity: tuple
    stabilized_class: str
    counted: bool
    last_frame: int
    frames_since_lost: int


# ---------------------------------------------------------------------------
# Default configuration
# ---------------------------------------------------------------------------
_DEFAULT_WEIGHTS: Dict[str, float] = {
    "spatial": 0.25,
    "predicted": 0.20,
    "time": 0.15,
    "size": 0.15,
    "direction": 0.15,
    "class": 0.10,
}

# Class-compatibility scores.  Any pair not listed is hard-incompatible (0.0).
_CLASS_COMPAT: Dict[Tuple[str, str], float] = {
    ("car", "car"): 1.0,
    ("motorcycle", "motorcycle"): 1.0,
    ("bus", "bus"): 1.0,
    ("truck", "truck"): 1.0,
    ("car", "motorcycle"): 0.5,
    ("motorcycle", "car"): 0.5,
}


class TrackContinuityManager:
    """Convert unstable ByteTrack IDs into stable canonical vehicle IDs.

    Parameters
    ----------
    grace_period : int
        Number of frames a lost track is held for possible reconnection.
        Default 15 (~0.5 s at 30 fps).
    acceptance_threshold : float
        Minimum weighted match score (0-1) to accept a reconnection.
        Default 0.55.
    max_spatial_distance : float
        Pixel distance beyond which spatial_score drops to 0.
        Default 250.
    max_pred_distance : float
        Pixel distance beyond which predicted_position score drops to 0.
        Default 350.
    weights : dict[str, float] | None
        Signal weights. Keys: spatial, predicted, time, size, direction, class.
        Must sum to ~1.0.  None uses defaults.
    canonical_id_start : int
        First canonical ID to assign.  Default 100.
    """

    def __init__(
        self,
        grace_period: int = 15,
        acceptance_threshold: float = 0.55,
        max_spatial_distance: float = 250.0,
        max_pred_distance: float = 350.0,
        weights: Optional[Dict[str, float]] = None,
        canonical_id_start: int = 100,
    ) -> None:
        if grace_period < 1:
            raise ValueError(f"grace_period must be >= 1, got {grace_period}")
        if not (0.0 < acceptance_threshold <= 1.0):
            raise ValueError(
                f"acceptance_threshold must be in (0, 1], got {acceptance_threshold}"
            )
        if max_spatial_distance <= 0:
            raise ValueError(
                f"max_spatial_distance must be > 0, got {max_spatial_distance}"
            )
        if max_pred_distance <= 0:
            raise ValueError(
                f"max_pred_distance must be > 0, got {max_pred_distance}"
            )

        self.grace_period: int = grace_period
        self.acceptance_threshold: float = acceptance_threshold
        self.max_spatial_distance: float = max_spatial_distance
        self.max_pred_distance: float = max_pred_distance
        self.weights: Dict[str, float] = (
            dict(weights) if weights is not None else dict(_DEFAULT_WEIGHTS)
        )
        self._canonical_id_start: int = canonical_id_start

        # --- mutable state ---
        self._next_canonical_id: int = canonical_id_start
        # bytetrack_id -> _ActiveTrack
        self._active: Dict[int, _ActiveTrack] = {}
        # canonical_id -> _LostTrack
        self._lost: Dict[int, _LostTrack] = {}


    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def update(
        self,
        observations: List[TrackObservation],
        frame_number: int,
    ) -> List[CanonicalObservation]:
        """Process one frame of observations and return canonical observations.

        Parameters
        ----------
        observations : list[TrackObservation]
            Current frame's tracked vehicles.
        frame_number : int
            Monotonic frame counter.

        Returns
        -------
        list[CanonicalObservation]
            Observations annotated with stable canonical IDs.
        """
        current_ids = {obs.raw_track_id for obs in observations}
        previous_ids = set(self._active.keys())

        # --- move disappeared tracks into the lost buffer ---
        for bt_id in previous_ids - current_ids:
            active = self._active.pop(bt_id)
            self._lost[active.canonical_id] = _LostTrack(
                canonical_id=active.canonical_id,
                center=active.center,
                bbox=active.bbox,
                velocity=active.velocity,
                stabilized_class=active.stabilized_class,
                counted=active.counted,
                last_frame=active.last_frame,
                frames_since_lost=0,
            )

        # --- process current observations ---
        results: List[CanonicalObservation] = []

        for obs in observations:
            bt_id = obs.raw_track_id

            if bt_id in self._active:
                # Existing active track - update state, same canonical ID
                old = self._active[bt_id]
                new_velocity = (
                    obs.center[0] - old.center[0],
                    obs.center[1] - old.center[1],
                )
                self._active[bt_id] = _ActiveTrack(
                    canonical_id=old.canonical_id,
                    bytetrack_id=bt_id,
                    center=obs.center,
                    bbox=obs.bbox,
                    velocity=new_velocity,
                    stabilized_class=obs.class_name,
                    counted=old.counted,
                    last_frame=frame_number,
                )
                results.append(
                    CanonicalObservation(
                        canonical_id=old.canonical_id,
                        bytetrack_id=bt_id,
                        class_name=obs.class_name,
                        bbox=obs.bbox,
                        center=obs.center,
                        frame_number=frame_number,
                        counted=old.counted,
                        is_reconnected=False,
                    )
                )
            else:
                # New ByteTrack ID - attempt reconnection to a lost track
                match_id = self._attempt_reconnection(obs)

                if match_id is not None:
                    lost = self._lost.pop(match_id)
                    self._active[bt_id] = _ActiveTrack(
                        canonical_id=lost.canonical_id,
                        bytetrack_id=bt_id,
                        center=obs.center,
                        bbox=obs.bbox,
                        velocity=(
                            obs.center[0] - lost.center[0],
                            obs.center[1] - lost.center[1],
                        ),
                        stabilized_class=obs.class_name,
                        counted=lost.counted,
                        last_frame=frame_number,
                    )
                    results.append(
                        CanonicalObservation(
                            canonical_id=lost.canonical_id,
                            bytetrack_id=bt_id,
                            class_name=obs.class_name,
                            bbox=obs.bbox,
                            center=obs.center,
                            frame_number=frame_number,
                            counted=lost.counted,
                            is_reconnected=True,
                        )
                    )
                else:
                    # Genuinely new vehicle - allocate fresh canonical ID
                    canonical_id = self._next_canonical_id
                    self._next_canonical_id += 1
                    self._active[bt_id] = _ActiveTrack(
                        canonical_id=canonical_id,
                        bytetrack_id=bt_id,
                        center=obs.center,
                        bbox=obs.bbox,
                        velocity=(0.0, 0.0),
                        stabilized_class=obs.class_name,
                        counted=False,
                        last_frame=frame_number,
                    )
                    results.append(
                        CanonicalObservation(
                            canonical_id=canonical_id,
                            bytetrack_id=bt_id,
                            class_name=obs.class_name,
                            bbox=obs.bbox,
                            center=obs.center,
                            frame_number=frame_number,
                            counted=False,
                            is_reconnected=False,
                        )
                    )

        # --- age and expire lost tracks ---
        self._age_lost_tracks()
        self._expire_lost_tracks()

        return results


    def mark_counted(self, canonical_id: int) -> bool:
        """Mark a canonical vehicle as counted.

        Returns True if the active track was found and updated.
        """
        for bt_id, track in self._active.items():
            if track.canonical_id == canonical_id:
                track.counted = True
                return True
        return False

    def get_canonical_id(self, bytetrack_id: int) -> Optional[int]:
        """Return the canonical ID for an active ByteTrack ID, or None."""
        track = self._active.get(bytetrack_id)
        return track.canonical_id if track is not None else None

    def cleanup(self) -> int:
        """Remove expired lost tracks.  Returns number removed."""
        return self._expire_lost_tracks()

    def reset(self) -> None:
        """Clear all state."""
        self._active.clear()
        self._lost.clear()
        self._next_canonical_id = self._canonical_id_start

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _attempt_reconnection(self, obs: TrackObservation) -> Optional[int]:
        """Find the best matching lost track for *obs*.

        Returns the canonical_id of the best match, or None if no lost
        track scores above the acceptance threshold.
        """
        best_score = 0.0
        best_id: Optional[int] = None

        for canonical_id, lost in self._lost.items():
            score = self._match_score(obs, lost)
            if score > best_score:
                best_score = score
                best_id = canonical_id

        if best_score >= self.acceptance_threshold and best_id is not None:
            return best_id
        return None

    def _match_score(self, obs: TrackObservation, lost: _LostTrack) -> float:
        """Compute weighted match score in [0, 1] between obs and lost track."""
        # --- class compatibility (hard gate) ---
        class_score = _CLASS_COMPAT.get(
            (lost.stabilized_class, obs.class_name), 0.0
        )
        if class_score == 0.0:
            return 0.0  # hard incompatibility - immediate reject

        # --- spatial distance score ---
        dx = obs.center[0] - lost.center[0]
        dy = obs.center[1] - lost.center[1]
        dist = hypot(dx, dy)
        spatial_score = max(0.0, 1.0 - dist / self.max_spatial_distance)

        # --- predicted position score ---
        frames = lost.frames_since_lost
        pred_cx = lost.center[0] + lost.velocity[0] * frames
        pred_cy = lost.center[1] + lost.velocity[1] * frames
        pred_dist = hypot(obs.center[0] - pred_cx, obs.center[1] - pred_cy)
        predicted_score = max(0.0, 1.0 - pred_dist / self.max_pred_distance)

        # --- time gap score ---
        time_score = max(0.0, 1.0 - frames / self.grace_period)

        # --- size similarity score ---
        lw = lost.bbox[2] - lost.bbox[0]
        lh = lost.bbox[3] - lost.bbox[1]
        lost_area = lw * lh
        ow = obs.bbox[2] - obs.bbox[0]
        oh = obs.bbox[3] - obs.bbox[1]
        obs_area = ow * oh
        max_area = max(lost_area, obs_area)
        size_score = min(lost_area, obs_area) / max_area if max_area > 0 else 0.0

        # --- direction compatibility score ---
        if dist > 1e-6:
            move_dx = dx / dist
            move_dy = dy / dist
            vel_mag = hypot(lost.velocity[0], lost.velocity[1])
            if vel_mag > 1e-6:
                vel_dx = lost.velocity[0] / vel_mag
                vel_dy = lost.velocity[1] / vel_mag
                dot = move_dx * vel_dx + move_dy * vel_dy
                direction_score = max(0.0, dot)  # map [-1,1] -> [0,1]
            else:
                direction_score = 0.5  # no velocity info - neutral
        else:
            direction_score = 1.0  # same position - perfect

        # --- weighted sum ---
        total = (
            self.weights["spatial"] * spatial_score
            + self.weights["predicted"] * predicted_score
            + self.weights["time"] * time_score
            + self.weights["size"] * size_score
            + self.weights["direction"] * direction_score
            + self.weights["class"] * class_score
        )
        return total

    def _age_lost_tracks(self) -> None:
        """Increment frames_since_lost for every buffered lost track."""
        for cid, lost in self._lost.items():
            lost.frames_since_lost += 1

    def _expire_lost_tracks(self) -> int:
        """Remove lost tracks that exceeded the grace period.

        Returns the number of removed tracks.
        """
        expired = [
            cid for cid, lt in self._lost.items()
            if lt.frames_since_lost >= self.grace_period
        ]
        for cid in expired:
            del self._lost[cid]
        return len(expired)

    # ------------------------------------------------------------------
    def __repr__(self) -> str:
        return (
            f"TrackContinuityManager("
            f"active={len(self._active)}, "
            f"lost={len(self._lost)}, "
            f"grace_period={self.grace_period})"
        )
