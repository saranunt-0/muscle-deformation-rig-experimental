# Architecture

## Data flow

```
Rigify pose (FK/IK controls)
   │
   ▼
ORG/DEF bones ──► MCH-MUS-<m>      (child of origin bone)
                  Stretch To → MCH-MUS-<m>_ins (child of insertion bone)
                  volume XZ, bulge = exponent, min/max = clamp²
                  ⇒ X scale = activation a_m  (1 rest, >1 contracted, <1 stretched)
                                         │
flex slider f_g (pose-bone custom prop) ─┤  driver (simple expression, no Python):
                                         ▼  input_m = (a_m − 1 + f_g·gain_m) · amp_m
Mesh: Armature ─► MUS Bulge (GN) ─► MUS Jiggle (GN, simulation zone) ─► rest of stack
                  offset = N · Σ_{k<3} mus_w{k} · input[mus_idx{k}] · Strength
                                      spring: v' = (v + dt(k(T−p) + c·v_T)) / (1 + c·dt)
                                      out = T + clamp(p − T) · mus_jiggle · Strength
```

## Key decisions

| Decision | Why | Evidence |
|---|---|---|
| Muscles are *sensors* (non-deforming bones); the skin is pushed after skinning | Rigid deform bones break Rigify's B-Bone twist distribution | 17.6 mm artifact on a pure 90° twist with rigid belly bones; < 1 mm with the push (tests) |
| Masks are vertex groups (editable) **plus** baked top-3 attributes (fast) | GN reads vertex groups slowly | ~7.9 → ~3 ms/frame bulge cost at 45k verts |
| Driver var uses `LOCAL_SPACE` | `TRANSFORM_SPACE` ignores the Stretch To scale | `test_driver_matches_bone_scale` on 4.5 + 5.0 |
| Jiggle damping relative to the target velocity | World-velocity damping drags flesh behind fast limbs | render_jiggle lag curve; `test_jiggle_lags_then_settles` |
| Muscle data is declarative (`library.py`) with `{s}` side placeholders and character-space offsets | One definition covers both sides and any metarig scale | `test_mirror_symmetry` |
| Rebuild via Rigify "Run Script" hook | Re-generating a Rigify rig wipes extra bones | `test_rigify_regenerate_rebuilds_muscles` |

## Module map

| File | Role |
|---|---|
| `muscle_rig/spec.py` | `Attach`, `MuscleSpec`, `MuscleSet`, direction vocabulary |
| `muscle_rig/library.py` | Arm / chest / hand / face definitions |
| `muscle_rig/build.py` | Edit-mode bone creation, Stretch To, flex props, removal |
| `muscle_rig/weights.py` | Procedural masks (dome around belly × region share), amplitude, compact bake |
| `muscle_rig/bulge.py` | Bulge node group (Index Switch per top-k slot), drivers, modifier placement |
| `muscle_rig/jiggle.py` | Simulation-zone spring node group (versioned), modifier |
| `muscle_rig/api.py` | `apply`, `rebind`, `strip`, `install_rigify_hook` |
| `muscle_rig/ui.py` | Sidebar panel + operators |
