# Research: a simple dynamic muscle rig for Blender (on top of Rigify)

**Goal (from the brief):** about 50% realism at about 70% efficiency. Start from a universal
rig (Rigify), focus on the obvious muscles (the arm), and treat hands and face as separate
modules.

**Status:** prototype working and tested on Blender **4.5.14 LTS** and **5.0.1**: 21/21
headless tests pass on both. Arm, chest and hand sets are usable. The face set is
experimental: only the direction of activation is verified.

---

## 1. The options, and how they fit the brief

| Approach | How it works | Realism | Runtime cost | Setup effort | Notes |
|---|---|---|---|---|---|
| **Corrective shape keys (pose-space deformation)** | Sculpt the shape at key poses and drive it from joint angles | High where sculpted | Very low | **High**: one sculpt per pose, combinations multiply | Best art control. Single-axis rotation drivers flip when a joint turns on several axes [5][6]. Blender Studio's *Pose Shape Keys* add-on helps [7]. |
| **Helper / "muscle" deform bones** | Extra deform bones scaled or moved by constraints | Low–medium | Very low | Medium | Game-engine friendly. **Tried and rejected here**, see §3.1. |
| **Stretch To volume preservation** | A bone from origin to insertion: when it shortens, it gets thicker | Gives a good *signal* | ~0 | Low | Blender's built-in squash and stretch (Volume Variation, Volume Min/Max) [1][2]. We use it as the **contraction sensor**. |
| **Mesh muscle systems (X-Muscle System)** | Real muscle meshes plus a tissue simulation drive the skin | High | High | High (paid) | Rigify-compatible; jiggle, auto-weights, flexor/extensor types [3][4]. The "full" answer, more than the brief asks for. |
| **Bone jiggle add-ons (Wiggle 2, jiggle-physics fork, Wiggle Bones)** | Spring physics on bones | — (secondary motion only) | Low–medium | Low | Real-time viewport dynamics [8][9][10]. Adds an add-on dependency. |
| **Geometry Nodes simulation-zone jiggle** | Per-vertex damped spring in a simulation zone | — (secondary motion only) | Low | Low | Native and bakeable, no add-on [11][12]. Needs sequential playback or a bake. |
| **Corrective Smooth (delta-mush style)** | Smooths skinning artifacts and restores rest-pose detail | — | Medium | Low | Helps joint collapse but also smooths away bulges. Optional, not used. |

**Takeaway:** nothing built into Blender, and no free add-on, gives "muscles" in one click.
The paid route (X-Muscle) is more than the 50% target needs. The cheapest approach that holds
up uses Blender's own pieces: **Stretch To as a sensor**, **a Geometry Nodes push as the
deformer**, and **a Geometry Nodes spring for dynamics**.

## 2. What we built

```
Rigify rig (unchanged skin weights)
 ├─ per muscle: MCH-MUS-<name>      origin → insertion line, Stretch To (volume XZ)
 │              MCH-MUS-<name>_ins  target bone on the insertion bone
 │              → X scale = activation (1 = rest, >1 contracted, <1 stretched)
 └─ flex sliders  muscle_flex_<group>.<side> on the arm/torso/jaw settings bones

Body mesh modifiers:  Armature → MUS Bulge (GN) → MUS Jiggle (GN sim) → (Subdivision…)
 MUS Bulge : offset = normal · Σ_k w_k · input[idx_k]       (k = 3 strongest muscles)
             input_i (driver) = (activation_i − 1 + flex · gain_i) · amplitude_i
 MUS Jiggle: per-vertex damped spring toward the skinned position, masked + clamped
```

* **Muscles in the library:** arm (8 per side: deltoid front/mid/rear, biceps, triceps,
  brachioradialis, forearm flexors, forearm extensors); chest (pectoralis); hand (thenar,
  hypothenar, first dorsal interosseous); face, experimental (zygomaticus major, masseter).
  Each one is a single line of action chosen so that it shortens when the real muscle would
  contract.
* **Masks** are editable `MUS-<muscle>.<side>` vertex groups: a smooth dome around the belly,
  limited to skin that belongs to the muscle's limb. They are baked into 3 compact attributes
  for speed.
* **Amplitude** is measured per mesh: the distance from the bone axis to the masked skin,
  capped at the muscle radius. So a thicker arm bulges more for the same contraction, which is
  what scaling the limb section would do.

## 3. Findings (measured, not assumed)

### 3.1 Rigid "belly bones" fight Rigify's twist. Rejected.
The first version used a deforming belly bone per muscle and took over part of the skin
weights. With **no bulge at all**, a 90° upper-arm twist still moved the biceps skin by
**17.6 mm**. The cause is that Rigify's DEF bones are 10-segment B-Bones, so twist varies
continuously along the arm, while a rigid bone can carry only one twist value. Blending the
belly across segments with an Armature constraint did not fix it. Moving the bulge to a
**post-skinning normal push** removed the problem: the twist-only test now measures
**< 1 mm**, and the bulge is identical with and without twist (`test_twist_alone_does_not_bulge_arm`,
`test_bulge_same_with_and_without_twist`).

### 3.2 Reading vertex groups inside Geometry Nodes is slow
With 24 masks read as vertex groups, the bulge cost **~7.9 ms/frame** at 47k vertices.
Blender converts each group to an attribute every frame. Baking the masks into
"top-3 muscles per vertex" index/weight attributes and picking inputs with an **Index
Switch** made the cost independent of how many muscles there are (§4).

### 3.3 Driver transform space: use `LOCAL_SPACE`
For a bone with a Stretch To, a `TRANSFORMS` driver variable in `TRANSFORM_SPACE` read
**1.0**, which ignores the constraint. `LOCAL_SPACE` and `WORLD_SPACE` return the constrained
scale. We use `LOCAL_SPACE` because it also ignores the rig object's scale. Verified on 4.5
and 5.0 by `test_driver_matches_bone_scale`.

### 3.4 Jiggle must be damped relative to the skin, not to the world
Damping against world velocity makes flesh trail behind any fast swing: steady-state lag is
about 2ζv/ω, roughly 4 cm at 1 m/s. Damping the velocity relative to the target (the skinned
position) means only acceleration causes wobble, which is how attached tissue behaves. The
default frequency was raised from 2.5 to 4 Hz so a normal quick arm raise stays inside the
3 cm safety clamp. Semi-implicit Euler with implicit damping is stable for
f < fps/π (7.6 Hz at 24 fps), so the UI caps it at 6 Hz.

### 3.5 Smaller things worth knowing
* Rigify's **Run Script** (finalize script) runs after generation with the new rig active.
  The add-on writes such a script, so **Re-Generate Rig rebuilds the muscles**
  (`test_rigify_regenerate_rebuilds_muscles`).
* Blender mirrors a pose by negating the Y and Z rotation channels on the `.R` side.
  Symmetric test poses must do the same (`test_mirror_symmetry`).
* The pip `bpy` module can hang at interpreter exit, especially after an exception. Scripts
  leave through `os._exit` (`scripts/_runner.py`).

## 4. Cost

Headless evaluation, 96-frame arm animation, min of 3 runs, 4 CPUs (`scripts/benchmark.py`).
Viewport drawing is not included, so in the real viewport the *relative* overhead is smaller.

| verts | clean Rigify | + muscle bones | + bulge | + bulge + jiggle |
|---:|---:|---:|---:|---:|
| 20,294 | 3.0 ms | 3.3 ms | 5.2 ms | 6.1 ms |
| 44,622 | 3.7 ms | 4.5 ms | 7.4 ms | 9.4 ms |
| 78,786 | 4.9 ms | 5.9 ms | 10.9 ms | 12.9 ms |

(Blender 4.5.14. Blender 5.0.1 is within noise: 5.5 / 9.3 / 12.4 ms for the full stack.)

**Honest reading:** the bones and drivers are nearly free (+0.3–1 ms). The bulge pass is
the main cost, about +2–5 ms. The full stack is about **2–2.5× the evaluation cost of plain
Rigify**, and still well over 100 evaluations per second at 45k vertices. To scrub faster
while blocking out animation, turn the modifiers off in the viewport and leave them on for
render.

## 5. Hands and face

* **Hands:** the same mechanism works. The thenar contracts to about 1.15 when the thumb
  swings across the palm, which gives +4 mm on the demo mannequin. Hand muscles are small,
  so the effect is subtle (as it is in life). The dorsal interosseous responds only weakly
  (index finger pulled toward the thumb: 1.02–1.04). It stays in the set but is labelled
  approximate.
* **Face:** faces are sold by expression shapes, not by muscle bulges. Production faces use
  FACS-style shape keys and/or face bones [13][14][15], and Rigify already ships a face rig.
  We recommend that, with the muscle layer adding only *secondary flesh*. The experimental
  face set shows two such cases with the same mechanism: **zygomaticus** contracts to 1.20 on
  a smile (cheek puff), and **masseter** thins when the jaw opens (0.93) and bulges from the
  `face` flex slider (clench). They are not rendered here because the mannequin has no face.

## 6. Limitations (known, not hidden)

* The push is **isotropic along the normal**. There is no skin sliding over muscle, no
  collision, and no volume exchange between neighbouring muscles.
* Muscle placement uses offsets measured on the **stock Rigify metarig (A-pose)**. A T-pose
  or unusual proportions need a look, and masks may need repainting. Repaint the `MUS-*`
  groups, then call `api.rebind(rig)`.
* Jiggle runs in **object space**. Moving the mesh *object* (rather than the rig's root bone)
  does not excite it. Scrubbing needs a bake (Physics tab → Simulation Nodes).
* Geometry Nodes and drivers **do not export to game engines**. For export, bake the bulge
  into corrective shape keys (a possible next step), or use bones only.
* Linking the rig through library overrides is **not tested**.
* Every number above comes from a procedural mannequin. Results on a real, sculpted
  character will differ.

## 7. Sources

1. Blender Manual, *Stretch To Constraint* (5.2 LTS / 3.6): https://docs.blender.org/manual/en/latest/animation/constraints/tracking/stretch_to.html
2. A. Madej, *Theory behind building a squash & stretch rig*: https://adammadej.com/posts/202403-squashstretch/
3. X-Muscle System on Superhive (Blender Market): https://superhivemarket.com/products/x-muscle-system
4. K44dev Studio, X-Muscle System: https://k44dev.com/xmuscle-system/
5. Blender Artists, *Corrective shape keys driven by bone rotation*: https://blenderartists.org/t/corrective-shape-keys-driven-by-bone-rotation/1118555
6. Wikipedia, *Pose space deformation*: https://en.wikipedia.org/wiki/Pose_space_deformation
7. Blender Studio, *Pose Shape Keys* add-on: https://studio.blender.org/tools/addons/pose_shape_keys
8. Wiggle 2 (shteeve3d): https://github.com/shteeve3d/blender-wiggle-2
9. blender-jiggle-physics (verlet fork of Wiggle 2): https://github.com/naelstrof/blender-jiggle-physics
10. Wiggle Bones on Blender Extensions: https://extensions.blender.org/add-ons/wiggle-bones/
11. BlenderNation, *Jiggle Physics With Geometry Nodes in Blender* (2025): https://www.blendernation.com/2025/03/23/jiggle-physics-with-geometry-nodes-in-blender/
12. 80.lv, *Custom Jiggle Setup Made with Geometry Nodes*: https://80.lv/articles/check-out-this-custom-jiggle-setup-made-with-geometry-nodes
13. Blender Studio, *Advanced Facial Rigging: Why shape keys*: https://studio.blender.org/training/facial-rigging/why-shape-keys/
14. Blender Artists, *Shape Keys or Bones in Facial Rig*: https://blenderartists.org/t/shape-keys-or-bones-in-facial-rig/485832
15. CG Dive, *Rig Anything with Rigify: rig types explained*: https://cgdive.com/rig-anything-with-rigify-05-rig-types-explained/

*Method note:* the Blender manual and developer docs were blocked by this environment's
network policy. Their content above comes from search-result summaries. Every API behaviour
we rely on was checked directly in Blender 4.5.14 and 5.0.1 (the pip `bpy` modules), and
the tests encode those checks.
