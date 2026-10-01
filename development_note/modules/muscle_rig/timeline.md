# Module: muscle_rig
<!-- Blender add-on that layers pose-driven muscle bulge + jiggle on a Rigify rig -->

---

## [2026-10-01] Prototype v0.1: arm, chest, hand, experimental face

**Type**: `feature`
**Status**: `resolved` (prototype; see open items)

### Context
Brief: simple dynamic muscle rig for an animation project, ~50% realism / ~70%
efficiency, start from Rigify, arm first, hand/face as separate parts. Empty repo.

### Work Done
1. Surveyed options (shape-key PSD, helper bones, Stretch To volume, X-Muscle,
   Wiggle-type bone dynamics, GN simulation jiggle). See docs/research.md.
2. v1 design: per muscle an MCH Stretch To line + a **deforming belly bone** that
   borrowed skin weight. Measured: biceps skin moved 25 mm in a twisted flex pose but only
   7 mm untwisted with the same contraction.
   - Hypothesis A: twist mismatch → confirmed: a pure 90° twist (no bulge) moved the skin
     17.6 mm. Root cause: Rigify DEF bones are 10-segment B-Bones (continuous twist),
     a rigid belly carries one twist value.
   - Tried blending the belly over DEF segments with an Armature constraint: still 17.6 mm.
   - Fix: belly bones removed. Bulge became a Geometry Nodes push along normals after the
     Armature modifier, driven per muscle. Twist-only now < 1 mm.
3. Drivers read 0: `TRANSFORMS` variable in `TRANSFORM_SPACE` ignores Stretch To scale;
   `LOCAL_SPACE` works (verified 4.5/5.0).
4. Perf: 24 vertex-group reads in GN cost ~4.5 ms at 47k verts → bake top-3
   (index, weight) attributes + Index Switch; also Set Position limited to masked verts.
5. Visual tuning from renders: bell-shaped masks (dome, not tube); amplitude capped at the
   mask radius (pectoralis host = spine was 19 cm away); biceps bulge 2.2; brachioradialis
   softened (it formed an elbow lump).
6. Jiggle: world-velocity damping caused drag-lag proportional to speed → target-relative
   damping; default 4 Hz; clamp 3 cm; optional `mus_jiggle_lag` debug attribute.
7. Hand set: probed thumb axes → thumb.01 Z+40/X+20 contracts thenar to ~1.15. DI only
   responds (weakly) to index abduction; kept, labelled approximate.
8. Face set (experimental): zygomaticus 1.20 on smile; masseter 0.93 when the jaw opens.
9. Rigify hook (finalize script) + extension manifest (validated with blender_ext.py).

### Checklist
- [x] 21/21 headless tests pass on Blender 4.5.14 LTS and 5.0.1 (`tests/test_muscle_rig.py`)
- [x] Add-on enables, operator runs, panel draw() executes (stub layout)
- [x] Extension zip builds and validates (bl_pkg/cli/blender_ext.py)
- [x] Benchmarks recorded (docs/research.md §4)
- [ ] Interactive viewport use in the Blender UI (no GUI here)
- [ ] A real sculpted character (only the procedural mannequin was used)

### Unverified Items
> Need a desktop Blender session.
- [ ] Install the extension zip, build muscles on your character, scrub the timeline.
  Expected: Muscle tab in the sidebar, biceps rises on elbow flex, no errors in the console.
- [ ] Viewport fps with and without the two MUS modifiers on your character.
- [ ] Library-override linking of the rig (flex props are marked overridable; untested).

### Root Cause / Outcome
Final architecture: non-deforming sensor bones + GN push + GN spring (development_note/architecture.md).

### Assumptions Made
- The user's rig is a Rigify *Human* (stock bone names); offsets were placed on the stock
  metarig in its A-pose.
- Target is rendering inside Blender (GN + drivers do not export to game engines).
