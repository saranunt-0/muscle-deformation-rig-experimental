# Module: validation
<!-- Demo scene, tests, renders, benchmark and environment quirks -->

---

## [2026-10-01] Headless test and render pipeline

**Type**: `investigation`
**Status**: `resolved`

### Context
No desktop Blender in the cloud container. PyPI `bpy` 4.5.14 and 5.0.1 (Python 3.11)
installed into two venvs; download.blender.org and the Blender docs sites are blocked by
the network policy.

### Work Done
- `scripts/demo_scene.py`: Rigify human metarig → generate → mannequin
  (metaball torso/head/hands + tapered limb tubes, voxel remesh 8 mm, ~45k verts, separate
  finger tubes) → inverse-distance DEF weights → muscle layer.
  - Fixed: metaball capsule chains made lumpy limbs → replaced by tubes.
  - Fixed: thumb base blob weighted to the palm, so it tore from the thumb → allow DEF-thumb.01.
- `tests/test_muscle_rig.py`: 21 tests (structure, rest neutrality, contraction
  direction per joint, outward/inward push, twist immunity, driver value, flex, mirror,
  face direction, jiggle lag/settle/clamp/unmasked-untouched, idempotent rebuild, strip,
  Rigify regenerate hook, add-on operator + panel draw).
  - Test-helper bug found: `.R` poses must negate Y/Z rotations (Blender mirror convention).
- `scripts/render_compare.py`: Cycles CPU sheets with a signed push heat map.
  - Bug found: camera up-axis/sign → renders upside-down from behind; fixed.
- `scripts/render_jiggle.py`: GIF + strip + per-frame lag CSV.
- `scripts/benchmark.py`: clean Rigify vs + bones vs + bulge vs + jiggle at 3 densities.

### Environment quirks (root-caused)
- The pip `bpy` module hangs at interpreter exit, notably after an exception (seen as
  "hangs" with ~0% CPU) → `scripts/_runner.py` exits with `os._exit`.
- `pkill -f <script>` from the tool shell kills the shell itself (pattern matches its own
  command line); use explicit PIDs.

### Unverified Items
- [ ] `blender -b --factory-startup -P tests/test_muscle_rig.py` with a real Blender binary
  (only the pip modules were available). Expected: `21/21 passed`.
