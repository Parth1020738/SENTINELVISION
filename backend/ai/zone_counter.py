"""
SentinelVision - Zone / Line Vehicle Counter

Counts vehicles entering and exiting a rectangular zone using stable
canonical vehicle IDs produced by the Track Continuity Manager (Phase 3).

Phase 4: Zone / Line Vehicle Counting

The counter operates on canonical vehicle IDs, not raw ByteTrack IDs,
so it survives temporary disappearances and ID switches.

Design
------
- Rectangular zone defined by (x1, y1, x2, y2).
- Per-vehicle state machine with hysteresis for jitter handling.
- Directional counting: IN (outside -> inside), OUT (inside -> outside).
- One-time counting per direction with reversal support.
- No dependencies on YOLO, PyTorch, OpenCV, GPU, database, or FastAPI.

State Machine
-------------
Each tracked vehicle is in exactly one of these states:

  OUTSIDE     - confirmed outside the zone.
  INSIDE      - confirmed inside the zone but never counted IN
                (vehicle was born inside the zone).
  COUNTED_IN  - confirmed inside the zone and already counted IN.
  COUNTED_OUT - confirmed outside the zone and already counted OUT.

Transitions (after hysteresis confirmation):

  OUTSIDE     -> inside  => COUNTED_IN   (emit IN event)
  OUTSIDE     => outside => OUTSIDE     (no change)
  INSIDE      -> outside => COUNTED_OUT  (emit OUT event)
  INSIDE      => inside  => INSIDE       (no change)
  COUNTED_IN  -> outside => COUNTED_OUT  (emit OUT event)
  COUNTED_IN  => inside  => COUNTED_IN   (no change)
  COUNTED_OUT -> inside  => COUNTED_IN   (emit IN event)
  COUNTED_OUT => outside => COUNTED_OUT  (no change)

Hysteresis
----------
A transition is only confirmed after the vehicle has been observed in
the new position for `confirmation_frames` consecutive frames. This
prevents jitter around the zone boundary from producing multiple
spurious counts.

Counting Events
---------------
Each confirmed IN/OUT transition produces a CountingEvent containing
canonical_vehicle_id, vehicle_class, direction, frame_number, and
position. Events are retained for later database / API integration.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

# Vehicle classes - mirrors Phase 1 CLASS_NAMES values
VEHICLE_CLASSES = frozenset({"car", "motorcycle", "bus", "truck"})

# State machine states
STATE_OUTSIDE = "OUTSIDE"
STATE_INSIDE = "INSIDE"
STATE_COUNTED_IN = "COUNTED_IN"
STATE_COUNTED_OUT = "COUNTED_OUT"

# Directions
DIRECTION_IN = "IN"
DIRECTION_OUT = "OUT"


@dataclass
class ZoneObservation:
    """A single vehicle observation to be processed by the zone counter.

    This is the generic input type. It intentionally does not depend on
    YOLO, PyTorch, OpenCV, or any other tracking-specific type. Any
    upstream pipeline (Phase 1-3) can construct a ZoneObservation from
    its own observation type.

    Attributes
    ----------
    canonical_id : int
        Stable canonical vehicle ID from the Track Continuity Manager.
    vehicle_class : str
        Stabilized vehicle class name (car, motorcycle, bus, or truck).
    center : tuple[float, float]
        (x, y) of the vehicle reference point (e.g. bounding-box center).
    frame_number : int
        Frame number or timestamp for temporal ordering.
    """

    canonical_id: int
    vehicle_class: str
    center: Tuple[float, float]
    frame_number: int


@dataclass
class CountingEvent:
    """A single confirmed IN or OUT counting event.

    Attributes
    ----------
    canonical_vehicle_id : int
        Stable canonical vehicle ID.
    vehicle_class : str
        Stabilized vehicle class at the time of the event.
    direction : str
        "IN" or "OUT".
    frame_number : int
        Frame number at which the event was confirmed.
    position : tuple[float, float]
        (x, y) of the vehicle at the time of the event.
    """

    canonical_vehicle_id: int
    vehicle_class: str
    direction: str
    frame_number: int
    position: Tuple[float, float]


@dataclass
class _VehicleState:
    """Internal mutable state for one canonical vehicle.

    Attributes
    ----------
    state : str
        Current state machine state.
    vehicle_class : str
        Latest stabilized vehicle class.
    last_frame : int
        Frame number of the most recent observation.
    last_position : tuple[float, float]
        (x, y) of the most recent observation.
    candidate : Optional[str]
        Candidate position (INSIDE / OUTSIDE) being evaluated, or None.
    candidate_count : int
        Number of consecutive frames the candidate has been observed.
    """

    state: str
    vehicle_class: str
    last_frame: int
    last_position: Tuple[float, float]
    candidate: Optional[str] = None
    candidate_count: int = 0


class ZoneCounter:
    """Counts vehicles entering and exiting a rectangular zone.

    Parameters
    ----------
    zone : tuple[float, float, float, float]
        Rectangular zone as (x1, y1, x2, y2). The coordinates may be in
        any order - they are normalised on construction.
    confirmation_frames : int
        Number of consecutive frames a vehicle must be observed in a new
        position before a transition is confirmed. Higher values reduce
        jitter false positives but increase latency. Default: 2.
    stale_threshold : int
        Number of frames after which an unseen vehicle state is eligible
        for cleanup. Default: 30.

    Notes
    -----
    The counter uses **canonical vehicle IDs** for identity. ByteTrack IDs
    must never be passed as canonical_id.
    """

    def __init__(
        self,
        zone: Tuple[float, float, float, float],
        confirmation_frames: int = 2,
        stale_threshold: int = 30,
    ) -> None:
        if confirmation_frames < 1:
            raise ValueError(
                f"confirmation_frames must be >= 1, got {confirmation_frames}"
            )
        if stale_threshold < 1:
            raise ValueError(
                f"stale_threshold must be >= 1, got {stale_threshold}"
            )

        # Normalise zone so (x1, y1) is top-left and (x2, y2) bottom-right
        x1, y1, x2, y2 = zone
        self._zone: Tuple[float, float, float, float] = (
            min(x1, x2),
            min(y1, y2),
            max(x1, x2),
            max(y1, y2),
        )

        self._confirmation_frames: int = confirmation_frames
        self._stale_threshold: int = stale_threshold

        # Internal state
        self._vehicle_states: Dict[int, _VehicleState] = {}
        self._events: List[CountingEvent] = []

        # Aggregated counts
        self._total_in: int = 0
        self._total_out: int = 0
        self._class_in: Dict[str, int] = {c: 0 for c in sorted(VEHICLE_CLASSES)}
        self._class_out: Dict[str, int] = {c: 0 for c in sorted(VEHICLE_CLASSES)}

    def update(self, observation: ZoneObservation) -> Optional[CountingEvent]:
        """Process a single vehicle observation.

        Parameters
        ----------
        observation : ZoneObservation
            The vehicle observation.

        Returns
        -------
        CountingEvent or None
            A counting event if a transition was confirmed, else None.
        """
        cid = observation.canonical_id
        cls = observation.vehicle_class

        if cls not in VEHICLE_CLASSES:
            raise ValueError(
                f"Invalid vehicle class '{cls}'. "
                f"Valid classes: {sorted(VEHICLE_CLASSES)}"
            )

        # Determine inside / outside for this observation
        position = self._classify_position(observation.center)

        # First time we see this canonical vehicle
        if cid not in self._vehicle_states:
            initial_state = STATE_INSIDE if position == STATE_INSIDE else STATE_OUTSIDE
            self._vehicle_states[cid] = _VehicleState(
                state=initial_state,
                vehicle_class=cls,
                last_frame=observation.frame_number,
                last_position=observation.center,
            )
            # No event - we did not observe a transition
            return None

        # Existing vehicle - update state machine
        vs = self._vehicle_states[cid]
        vs.last_frame = observation.frame_number
        vs.last_position = observation.center
        # Always adopt the latest stabilized class
        vs.vehicle_class = cls

        # Determine the position implied by the current state
        current_position = self._state_position(vs.state)

        if position == current_position:
            # Still in the same position - reset any candidate
            vs.candidate = None
            vs.candidate_count = 0
            return None

        # Position differs from current state - potential transition
        if position == vs.candidate:
            vs.candidate_count += 1
        else:
            vs.candidate = position
            vs.candidate_count = 1

        # Check if we have enough consecutive frames to confirm
        if vs.candidate_count >= self._confirmation_frames:
            return self._confirm_transition(cid, vs, position, observation)

        return None

    def process_frame(
        self, observations: List[ZoneObservation]
    ) -> List[CountingEvent]:
        """Process all observations from a single frame.

        Parameters
        ----------
        observations : list[ZoneObservation]
            All vehicle observations for the current frame.

        Returns
        -------
        list[CountingEvent]
            Counting events generated while processing this frame.
        """
        events: List[CountingEvent] = []
        for obs in observations:
            event = self.update(obs)
            if event is not None:
                events.append(event)
        return events

    def get_total_in(self) -> int:
        """Return total number of confirmed IN counts."""
        return self._total_in

    def get_total_out(self) -> int:
        """Return total number of confirmed OUT counts."""
        return self._total_out

    def get_class_in(self, vehicle_class: str) -> int:
        """Return confirmed IN count for a specific vehicle class.

        Parameters
        ----------
        vehicle_class : str
            One of "car", "motorcycle", "bus", "truck".
        """
        if vehicle_class not in VEHICLE_CLASSES:
            raise ValueError(
                f"Invalid vehicle class '{vehicle_class}'. "
                f"Valid classes: {sorted(VEHICLE_CLASSES)}"
            )
        return self._class_in[vehicle_class]

    def get_class_out(self, vehicle_class: str) -> int:
        """Return confirmed OUT count for a specific vehicle class.

        Parameters
        ----------
        vehicle_class : str
            One of "car", "motorcycle", "bus", "truck".
        """
        if vehicle_class not in VEHICLE_CLASSES:
            raise ValueError(
                f"Invalid vehicle class '{vehicle_class}'. "
                f"Valid classes: {sorted(VEHICLE_CLASSES)}"
            )
        return self._class_out[vehicle_class]

    def get_counts(self) -> Dict[str, Dict[str, int]]:
        """Return a snapshot of all counts.

        Returns
        -------
        dict
            {"total": {"IN": ..., "OUT": ...}, "car": {"IN": ..., "OUT": ...}, ...}
        """
        return {
            "total": {DIRECTION_IN: self._total_in, DIRECTION_OUT: self._total_out},
            **{
                c: {DIRECTION_IN: self._class_in[c], DIRECTION_OUT: self._class_out[c]}
                for c in sorted(VEHICLE_CLASSES)
            },
        }

    def get_events(self) -> List[CountingEvent]:
        """Return a copy of all recorded counting events."""
        return list(self._events)

    def cleanup(self, current_frame: int) -> int:
        """Remove stale vehicle states.

        A vehicle state is considered stale if it has not been observed
        for more than stale_threshold frames.

        Parameters
        ----------
        current_frame : int
            The current frame number.

        Returns
        -------
        int
            Number of vehicle states removed.
        """
        stale_ids = [
            cid
            for cid, vs in self._vehicle_states.items()
            if current_frame - vs.last_frame > self._stale_threshold
        ]
        for cid in stale_ids:
            del self._vehicle_states[cid]
        return len(stale_ids)

    def reset(self) -> None:
        """Reset all counts, events, and vehicle states."""
        self._vehicle_states.clear()
        self._events.clear()
        self._total_in = 0
        self._total_out = 0
        self._class_in = {c: 0 for c in sorted(VEHICLE_CLASSES)}
        self._class_out = {c: 0 for c in sorted(VEHICLE_CLASSES)}

    def _classify_position(self, center: Tuple[float, float]) -> str:
        """Return STATE_INSIDE or STATE_OUTSIDE for a point."""
        x, y = center
        x1, y1, x2, y2 = self._zone
        if x1 <= x <= x2 and y1 <= y <= y2:
            return STATE_INSIDE
        return STATE_OUTSIDE

    @staticmethod
    def _state_position(state: str) -> str:
        """Map a state machine state to its implied position."""
        if state in (STATE_INSIDE, STATE_COUNTED_IN):
            return STATE_INSIDE
        return STATE_OUTSIDE

    def _confirm_transition(
        self,
        cid: int,
        vs: _VehicleState,
        new_position: str,
        observation: ZoneObservation,
    ) -> CountingEvent:
        """Confirm a position transition, emit event, update counts."""
        # Determine new state and direction
        if new_position == STATE_INSIDE:
            # Moving (or re-entering) inside
            vs.state = STATE_COUNTED_IN
            direction = DIRECTION_IN
        else:
            # Moving outside
            vs.state = STATE_COUNTED_OUT
            direction = DIRECTION_OUT

        # Reset candidate
        vs.candidate = None
        vs.candidate_count = 0

        # Build event
        event = CountingEvent(
            canonical_vehicle_id=cid,
            vehicle_class=vs.vehicle_class,
            direction=direction,
            frame_number=observation.frame_number,
            position=observation.center,
        )
        self._events.append(event)

        # Update aggregated counts
        if direction == DIRECTION_IN:
            self._total_in += 1
            self._class_in[vs.vehicle_class] += 1
        else:
            self._total_out += 1
            self._class_out[vs.vehicle_class] += 1

        return event

    def __repr__(self) -> str:
        return (
            f"ZoneCounter(zone={self._zone}, "
            f"vehicles={len(self._vehicle_states)}, "
            f"IN={self._total_in}, OUT={self._total_out})"
        )
