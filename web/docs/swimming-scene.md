# Layered landing-page swimming scene

A vertical underwater background and three transparent shrimp poses form a Canvas animation. Scrolling down pans from surface to bed while the shrimp crosses right-to-left; scrolling up reverses the scene, and stopping freezes it. Background/shrimp size does not grow with progress: camera movement, animal position and stroke pose are calculated separately.

This is **layered animation of AI-generated images**, not generated video, recorded footage, a biological motion simulation or model output.

## Implementation

| File | Responsibility |
| --- | --- |
| [hero-scene.tsx](../frontend/src/components/hero-scene.tsx) | Hero, Canvas, poster, actions, skip control and scroll subscription |
| [swim-scene.ts](../frontend/src/lib/swim-scene.ts) | Geometry in `getScenePose()`; loading/drawing/cleanup in `createSwimScene()` |
| [landing-refinement.css](../frontend/src/app/landing-refinement.css) | Sticky region, clipping, masks, responsive/reduced-motion styles |
| [use-reduced-motion.ts](../frontend/src/lib/use-reduced-motion.ts) | Consistent SSR/first-client output and preference subscription |
| [swim-scene.test.cjs](../frontend/tests/swim-scene.test.cjs) | Geometry, alpha blending, failure, reverse and lifecycle tests |

The track is `270dvh` on desktop and `240dvh` on mobile, with a `100dvh` sticky stage. Progress is clamped to 0–1 from `track.offsetHeight - stage.offsetHeight`. No wheel interception, page locking or timed autoplay is used. `.landing { overflow: clip }` avoids an ancestor scrolling container breaking sticky positioning.

Copy/actions fade during progress 0.12–0.32, then become `inert` so invisible controls cannot receive focus/clicks. Reverse scrolling restores them; teardown and reduced-motion changes restore attributes. The skip control stays outside the fading copy, jumps to features and moves keyboard focus.

## Assets

Runtime files under `web/frontend/public/images/swim/` total **883,224 bytes (about 863 KiB)**:

| File | Dimensions | Alpha |
| --- | --- | --- |
| `ocean-depth.webp` | 1024 × 1536 | Opaque surface, water column and bed |
| `shrimp-01.webp` | 1536 × 1024 | Real alpha, pose 1 |
| `shrimp-02.webp` | 1536 × 1024 | Real alpha, pose 2 |
| `shrimp-03.webp` | 1536 × 1024 | Real alpha, pose 3 |

Original PNGs are under `web/docs/assets/swim/`; the site loads only public WebP files. See [provenance](assets.md) and [prompts](landing-image-prompts.md). URLs use `/images/swim/...`, never drive letters or user directories.

Before readiness, on failure, or with reduced motion, the hero uses `/images/hero-poster.webp`. The feature section uses `/images/shrimp-observation.webp`; these are additional to the four animation assets. Originals are `web/docs/assets/hero-poster.png` and `shrimp-observation.png`.

## Replacing images

1. Replace the background with an opaque portrait image containing surface above and bed below, without text, panels or precomposited shrimp. Aspect ratio is preserved with at least 2.4 canvas heights for camera travel.
2. Replace all three shrimp poses with equal-size, left-facing images of the same animal, aligned head/body scale and transparent margins. Keep antennae, legs and tail fully inside the canvas. Real alpha is required; white/checkerboard backgrounds are unsuitable. Current size is 1536 × 1024.
3. Update the hero fallback if appearance changes, including first-load and reduced-motion states.
4. Renamed assets require updating `paths` in `swim-scene.ts`, retaining site-root-relative URLs.

The background and shrimp cannot be the same full photograph: one must be opaque and the other transparent. Three poses are currently assumed. Changing that count also requires updating `pose.from`, `pose.to`, `pose.blend` and tests.

Refresh/check cache after replacing assets. TypeScript/CSS changes require `npm run build` in `web/frontend/` and a frontend restart for production preview. API, worker and PostgreSQL need no restart for scene changes.

## Motion parameters

`getScenePose(progress, viewport, background, shrimp)` is DOM-free geometry:

| Calculation | Effect |
| --- | --- |
| `travel` start/range | Scroll interval for shrimp movement |
| `camera`, background `x/y` | Depth-pan timing and horizontal offset |
| Background `scale` | Pan area; must always cover the canvas |
| Shrimp `x/y` | Right-to-left path and entry/exit, separately tuned for mobile/desktop |
| Shrimp `width/height/rotation` | Fixed display size and angle; scaling is not a substitute for swimming |
| `stroke`, `pose` | Pose-blend count, order and weight |
| `label` | Surface/submerging/swimming/bed cues |

The shrimp center travels more than one canvas width and its rotated bounds fully exit left. Recheck desktop, phone and landscape visibility after geometry/aspect-ratio changes. Copy fading lives in `createSwimScene()`; zero opacity must coincide with `inert`, with reverse/teardown restoration.

Canvas `data-target-progress` records target progress. `data-progress`, `data-camera-y`, `data-shrimp-x` and `data-pose` update only after a successful draw, helping verify reverse movement, freezing and actual displacement.

## Drawing and failure handling

Each redraw fully covers the old frame with the opaque background, then blends adjacent poses in a transparent buffer using `source-over` and `lighter` to avoid excessive mid-blend transparency. Position/rotation are applied before drawing the buffer onto the main Canvas.

Only four assets load. Main Canvas DPR is capped at 1.5; pose buffer width at 1200px. RAF coalesces changes rather than running a continuous loop; identical progress/size does not redraw. Resize recalculates crop and resolution.

Partial pose failure uses available poses. Background failure or loss of all poses retains the poster and shortens the scroll region. Hidden tabs/offscreen scenes do not draw; visibility resumes at the latest progress. Teardown cancels RAF, observers and listeners, removes image callbacks and clears buffers. In-flight image requests may finish but cannot modify an unmounted scene.

Reduced motion creates no scene controller, loads none of the four layers, removes the extended scroll track and displays the poster with normal content.

## Historical verification and future checks

Historical desktop/mobile review covered scrolling, poster, feature image, skip and dashboard navigation without normal-operation console errors/warnings. Current historical suite counts are consolidated in [validation](validation.md), not repeated here.

The scene tests cover independent camera/animal displacement, fixed sizes, coverage, reverse motion, alpha blending, RAF, resize, image failures, remount recovery, visibility pause, teardown, full exit and copy/focus restoration. From `web/frontend/`:

```powershell
npm.cmd test
npm.cmd run lint
npm.cmd run typecheck
npm.cmd run build
```

After changing assets/geometry, recheck desktop/mobile forward/reverse scroll, fading/focus, skip, no redraw while stopped, reduced motion, asset failure and revisiting the page. Scene changes do not alter inference, API behavior or measurements.
