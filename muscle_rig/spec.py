"""Data model for muscle definitions.

A muscle is described by two attachment points (origin, insertion) on rig
bones, a host bone that carries the visible belly, and a few tuning numbers.
All lengths are fractions of a bone length, so a definition works on any
character scale as long as the metarig was fitted to the body.
"""

from dataclasses import dataclass, field
from typing import Tuple

# Character-space directions. Rigify metarigs face -Y with +Z up and the
# character's left side on +X. "OUT" is lateral (away from the midline) and is
# mirrored per side, so one definition covers both arms.
DIRECTIONS = {
    "FRONT": (0.0, -1.0, 0.0),
    "BACK": (0.0, 1.0, 0.0),
    "UP": (0.0, 0.0, 1.0),
    "DOWN": (0.0, 0.0, -1.0),
    "OUT": (1.0, 0.0, 0.0),
    "IN": (-1.0, 0.0, 0.0),
}

SIDES = (".L", ".R")


@dataclass(frozen=True)
class Attach:
    """A point fixed to a bone.

    ``bone`` is a bone name with ``{s}`` where the side suffix goes, e.g.
    ``"ORG-upper_arm{s}"`` or ``"DEF-upper_arm{s}.001"`` (Rigify puts the side
    before the segment number). Center bones simply omit ``{s}``.
    ``t`` is the position along the bone (0 = head, 1 = tail). ``offset`` is a
    tuple of ``(direction, amount)`` pairs where amount is a fraction of the
    bone length, e.g. ``(("FRONT", 0.12),)``.
    """

    bone: str
    t: float = 0.0
    offset: Tuple[Tuple[str, float], ...] = ()


@dataclass(frozen=True)
class MuscleSpec:
    name: str
    origin: Attach
    insertion: Attach
    # Bone under the belly: the push amplitude is measured from its axis.
    host: str
    # Belly span along the origin -> insertion line (0..1).
    belly: Tuple[float, float] = (0.3, 0.7)
    # Mask falloff radius as a fraction of the origin -> insertion length.
    radius: float = 0.12
    # Mask value at the belly core (0..1).
    weight: float = 1.0
    # Deform bones whose skin the muscle may affect ("{s}" placeholders).
    region: Tuple[str, ...] = ()
    # Stretch To "Volume Variation": >1 exaggerates the bulge.
    bulge: float = 1.0
    # Clamp of the resulting thickness factor.
    bulge_min: float = 0.85
    bulge_max: float = 1.6
    # Multiplier on the outward push (1 = skin moves as if the limb section
    # under the belly were scaled by the thickness factor).
    push: float = 1.0
    # Extra thickness factor per unit of the manual flex slider.
    flex_gain: float = 0.25
    flex_group: str = "arm"
    # 0..1 share of the jiggle effect this muscle receives.
    jiggle: float = 1.0
    description: str = ""

    def bone_names(self, side: str):
        """Names of the two generated bones for one side."""
        return (
            f"MCH-MUS-{self.name}{side}",       # line of action: origin -> insertion
            f"MCH-MUS-{self.name}_ins{side}",   # insertion target
        )

    def mask_name(self, side: str) -> str:
        return f"MUS-{self.name}{side}"


def sided(name: str, side: str) -> str:
    return name.replace("{s}", side)


@dataclass
class MuscleSet:
    """A named group of muscles that can be built independently."""

    name: str
    muscles: Tuple[MuscleSpec, ...]
    description: str = ""
    sides: Tuple[str, ...] = field(default=SIDES)
