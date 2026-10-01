"""Muscle definitions for a Rigify human rig.

Offsets are fractions of the attach bone's length, in character directions
(see ``spec.DIRECTIONS``). They were placed against the stock Rigify "Human"
metarig in its default A-pose: the arm hangs ~30 degrees below horizontal with
the palm facing down/inward, so the outer (lateral) side of the upper arm is
roughly UP and the palm side of the hand is DOWN + IN.

Anatomy is simplified on purpose: one line of action per muscle (or per head
for the deltoid), chosen so the line shortens when the real muscle would
contract. That is what drives the bulge.
"""

from .spec import Attach, MuscleSet, MuscleSpec

UPPER_ARM = ("DEF-upper_arm{s}", "DEF-upper_arm{s}.001")
FOREARM = ("DEF-forearm{s}", "DEF-forearm{s}.001")

ARM = MuscleSet(
    name="arm",
    description="Deltoid (3 heads), biceps, triceps, brachioradialis, forearm flexors/extensors",
    muscles=(
        MuscleSpec(
            name="biceps",
            description="Elbow flexor on the front of the upper arm",
            origin=Attach("ORG-upper_arm{s}", 0.08, (("FRONT", 0.10),)),
            insertion=Attach("ORG-forearm{s}", 0.12, (("FRONT", 0.10),)),
            host="DEF-upper_arm{s}.001",
            belly=(0.38, 0.80),
            radius=0.20,
            region=UPPER_ARM,
            bulge=2.2, bulge_min=0.9, bulge_max=1.5,
            flex_gain=0.3, flex_group="arm", jiggle=1.0,
        ),
        MuscleSpec(
            name="triceps",
            description="Elbow extensor on the back of the upper arm; thins as the elbow bends",
            origin=Attach("ORG-upper_arm{s}", 0.10, (("BACK", 0.10),)),
            insertion=Attach("ORG-forearm{s}", 0.0, (("BACK", 0.12),)),
            host="DEF-upper_arm{s}.001",
            belly=(0.30, 0.75),
            radius=0.20,
            region=UPPER_ARM,
            bulge=1.0, bulge_min=0.88, bulge_max=1.3,
            flex_gain=0.2, flex_group="arm", jiggle=1.0,
        ),
        MuscleSpec(
            name="deltoid_front",
            description="Anterior deltoid; bunches when the arm swings forward",
            origin=Attach("ORG-shoulder{s}", 0.75, (("FRONT", 0.16), ("UP", 0.06))),
            insertion=Attach("ORG-upper_arm{s}", 0.42, (("UP", 0.06), ("FRONT", 0.06))),
            host="DEF-upper_arm{s}",
            belly=(0.20, 0.65),
            radius=0.30,
            region=("DEF-upper_arm{s}", "DEF-shoulder{s}"),
            bulge=1.5, bulge_min=0.9, bulge_max=1.4,
            flex_gain=0.2, flex_group="arm", jiggle=0.6,
        ),
        MuscleSpec(
            name="deltoid_mid",
            description="Lateral deltoid; bunches when the arm is raised sideways",
            origin=Attach("ORG-shoulder{s}", 1.0, (("UP", 0.16), ("OUT", 0.06))),
            insertion=Attach("ORG-upper_arm{s}", 0.42, (("UP", 0.12),)),
            host="DEF-upper_arm{s}",
            belly=(0.20, 0.65),
            radius=0.30,
            region=("DEF-upper_arm{s}", "DEF-shoulder{s}"),
            bulge=1.5, bulge_min=0.9, bulge_max=1.4,
            flex_gain=0.2, flex_group="arm", jiggle=0.6,
        ),
        MuscleSpec(
            name="deltoid_rear",
            description="Posterior deltoid; bunches when the arm swings back",
            origin=Attach("ORG-shoulder{s}", 0.85, (("BACK", 0.25), ("UP", 0.06))),
            insertion=Attach("ORG-upper_arm{s}", 0.42, (("UP", 0.06), ("BACK", 0.06))),
            host="DEF-upper_arm{s}",
            belly=(0.20, 0.65),
            radius=0.30,
            region=("DEF-upper_arm{s}", "DEF-shoulder{s}"),
            bulge=1.5, bulge_min=0.9, bulge_max=1.4,
            flex_gain=0.2, flex_group="arm", jiggle=0.6,
        ),
        MuscleSpec(
            name="brachioradialis",
            description="Thumb-side forearm muscle; bowstrings over the elbow when it bends",
            origin=Attach("ORG-upper_arm{s}", 0.72, (("UP", 0.06), ("FRONT", 0.06))),
            insertion=Attach("ORG-forearm{s}", 0.92, (("FRONT", 0.08),)),
            host="DEF-forearm{s}",
            belly=(0.32, 0.62),
            radius=0.16,
            region=FOREARM,
            bulge=1.0, bulge_min=0.9, bulge_max=1.25,
            flex_gain=0.2, flex_group="forearm", jiggle=0.4,
        ),
        MuscleSpec(
            name="forearm_flexors",
            description="Palm-side forearm mass; bunches when the wrist curls toward the palm",
            origin=Attach("ORG-upper_arm{s}", 0.95, (("DOWN", 0.12), ("FRONT", 0.04))),
            insertion=Attach("ORG-hand{s}", 0.40, (("DOWN", 0.25), ("IN", 0.20))),
            host="DEF-forearm{s}",
            belly=(0.12, 0.50),
            radius=0.16,
            region=FOREARM,
            bulge=1.3, bulge_min=0.9, bulge_max=1.35,
            flex_gain=0.2, flex_group="forearm", jiggle=0.3,
        ),
        MuscleSpec(
            name="forearm_extensors",
            description="Back-of-forearm mass; bunches when the wrist bends back",
            origin=Attach("ORG-upper_arm{s}", 0.95, (("UP", 0.10), ("BACK", 0.03))),
            insertion=Attach("ORG-hand{s}", 0.40, (("UP", 0.25), ("OUT", 0.20))),
            host="DEF-forearm{s}",
            belly=(0.12, 0.50),
            radius=0.16,
            region=FOREARM,
            bulge=1.3, bulge_min=0.9, bulge_max=1.35,
            flex_gain=0.2, flex_group="forearm", jiggle=0.3,
        ),
    ),
)

HAND = MuscleSet(
    name="hand",
    description="Thenar (thumb ball), hypothenar (pinky side), first dorsal interosseous",
    muscles=(
        MuscleSpec(
            name="thenar",
            description="Thumb ball; bulges when the thumb crosses toward the palm",
            origin=Attach("ORG-hand{s}", 0.20, (("DOWN", 0.20), ("IN", 0.15), ("FRONT", 0.10))),
            insertion=Attach("ORG-thumb.02{s}", 0.0, (("DOWN", 0.20), ("BACK", 0.20))),
            host="DEF-thumb.01{s}",
            belly=(0.25, 0.75),
            radius=0.35,
            region=("DEF-thumb.01{s}", "DEF-hand{s}", "DEF-palm.01{s}"),
            bulge=2.5, bulge_min=0.9, bulge_max=1.4,
            flex_gain=0.25, flex_group="hand", jiggle=0.0,
        ),
        MuscleSpec(
            name="hypothenar",
            description="Pinky-side heel of the palm",
            origin=Attach("ORG-hand{s}", 0.20, (("DOWN", 0.20), ("IN", 0.10), ("BACK", 0.25))),
            insertion=Attach("ORG-f_pinky.01{s}", 0.0, (("DOWN", 0.20), ("BACK", 0.20))),
            host="DEF-palm.04{s}",
            belly=(0.25, 0.75),
            radius=0.30,
            region=("DEF-palm.04{s}", "DEF-hand{s}"),
            bulge=1.2, bulge_min=0.9, bulge_max=1.3,
            flex_gain=0.2, flex_group="hand", jiggle=0.0,
        ),
        MuscleSpec(
            name="dorsal_interosseous",
            description="Web between thumb and index on the back of the hand; responds (weakly) to the index pulling toward the thumb",
            origin=Attach("ORG-thumb.01{s}", 0.40, (("UP", 0.25), ("OUT", 0.20))),
            insertion=Attach("ORG-f_index.01{s}", 0.10, (("UP", 0.20), ("FRONT", 0.15))),
            host="DEF-palm.01{s}",
            belly=(0.25, 0.75),
            radius=0.35,
            region=("DEF-palm.01{s}", "DEF-thumb.01{s}", "DEF-hand{s}"),
            bulge=2.0, bulge_min=0.9, bulge_max=1.4,
            flex_gain=0.25, flex_group="hand", jiggle=0.0,
        ),
    ),
)

CHEST = MuscleSet(
    name="chest",
    description="Pectoralis major; bunches when the arm crosses the body, flattens when raised",
    muscles=(
        MuscleSpec(
            name="pectoralis",
            origin=Attach("ORG-spine.003", 0.35, (("FRONT", 0.40), ("OUT", 0.25))),
            insertion=Attach("ORG-upper_arm{s}", 0.15, (("FRONT", 0.12),)),
            host="DEF-spine.003",
            belly=(0.15, 0.60),
            radius=0.30,
            region=("DEF-spine.003", "DEF-shoulder{s}", "DEF-breast{s}", "DEF-upper_arm{s}"),
            bulge=1.2, bulge_min=0.88, bulge_max=1.35,
            flex_gain=0.2, flex_group="chest", jiggle=0.5,
        ),
    ),
)

# Experimental: same mechanism on the Rigify face (Blender 4.x "skin" face).
# Faces are mostly sold by shape keys / face bones; these only add the
# secondary fleshy response. Verified for direction of activation only.
FACE_REGION = ("DEF-cheek.B{s}", "DEF-cheek.T{s}", "DEF-jaw{s}", "DEF-jaw{s}.001",
               "DEF-lip.T{s}", "DEF-lip.B{s}", "DEF-spine.006")
FACE = MuscleSet(
    name="face",
    description="EXPERIMENTAL: zygomaticus (smile cheek bulge), masseter (jaw clench)",
    muscles=(
        MuscleSpec(
            name="zygomaticus",
            description="Cheekbone to mouth corner; a smile shortens it and puffs the cheek",
            origin=Attach("ORG-cheek.T{s}", 0.2),
            insertion=Attach("lips{s}", 0.0),
            host="ORG-cheek.T{s}",
            belly=(0.30, 0.70),
            radius=0.35,
            region=FACE_REGION,
            bulge=2.0, bulge_min=0.9, bulge_max=1.4,
            flex_gain=0.25, flex_group="face", jiggle=0.3,
        ),
        MuscleSpec(
            name="masseter",
            description="Cheekbone arch to jaw angle; thins as the jaw opens, bulges on clench (flex)",
            origin=Attach("ORG-cheek.T{s}", 0.0, (("DOWN", 0.4),)),
            insertion=Attach("ORG-jaw{s}.001", 0.1),
            host="ORG-jaw{s}",
            belly=(0.30, 0.75),
            radius=0.35,
            region=FACE_REGION,
            bulge=1.0, bulge_min=0.9, bulge_max=1.3,
            flex_gain=0.3, flex_group="face", jiggle=0.0,
        ),
    ),
)

SETS = {s.name: s for s in (ARM, HAND, CHEST, FACE)}
