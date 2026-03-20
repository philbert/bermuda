# Anisotropic Room Classification Plan

Date drafted: 2026-03-20

Related documents:
- `docs/room-wander-analysis.md`
- `docs/trapped-floor-recovery-plan.md`
- `docs/topology-gated-floor-inference-design.md`

## Purpose

This document proposes a room-classification improvement for a different class of failure than the
trapped-floor problem:

- the device remains on the correct floor,
- the solved trilateration point has directionally weak geometry,
- room assignment wanders between nearby rooms on that same floor,
- the current classifier trusts isotropic XY geometry more than it should.

The goal is to make room allocation less sensitive to biased `x/y` geometry and more willing to
lean on fingerprint evidence when the live solve is anisotropic.

The plan should also acknowledge a second reality from `docs/room-wander-analysis.md`:

- some false room challengers appear to be fingerprint-led before geometry makes them look
  plausible.

That means geometry scoring is only part of the fix. Early implementation phases should focus on
room-switch guardrails and fingerprint confidence before the more mathematically demanding
covariance work.

## Problem Summary

The current room pipeline treats the solved trilat point as if its XY uncertainty were roughly
circular.

That is often false in this house.

The scanner layout is anisotropic:

- the house is much longer in `x` than in `y`,
- scanners are naturally spread more strongly along `x`,
- many locations therefore have better `x` observability than `y` observability.

The result is:

- room geometry can be trustworthy in `x`,
- weak in `y`,
- but the current room score still uses a symmetric radial kernel.

That creates a bias toward false room movement when nearby rooms are mainly separated along the
weak axis.

## Current Behavior

The current classifier does three important things:

1. Scores room geometry from the solved position using an isotropic kernel.
2. Scores room fingerprints from per-sample RSSI medians.
3. Blends the two with a fixed fingerprint weight.

Relevant current details:

- geometry kernel uses `dx^2 + dy^2 + 0.15 * dz^2` in `room_classifier.py`
- fingerprint blend uses a fixed `FINGERPRINT_WEIGHT = 0.65`
- room switching then uses dwell and learned transition strength in `coordinator.py`

This means the classifier has no way to express:

- "`x` is well constrained but `y` is not"
- "geometry is currently less trustworthy than fingerprinting"
- "this room change is mostly along the weak axis, so require stronger evidence"

## Fingerprint Limitations Today

The current room fingerprints are already richer than a single room prototype:

- each accepted calibration sample becomes its own fingerprint,
- each fingerprint stores per-scanner median RSSI.

However, the classifier currently ignores other stored sample features that would be useful:

- `rssi_mad`
- `packet_count`
- `rssi_min`
- `rssi_max`
- scanner visibility asymmetry

This leaves useful signal on the table, especially for weak scanners that are poor trilat anchors
but still have room-specific fingerprint value.

It also means the current system gives too little penalty to under-sampled rooms. A room with only
one calibration sample can currently challenge too easily if that single sample happens to match a
noisy live observation.

## Operational Definitions

The following runtime terms are used throughout the plan, including Phase 2:

- `fingerprint_coverage(room)` =
  fraction of that room's accepted calibration samples for which at least one scanner recorded in
  the sample is currently reporting a live RSSI observation
- `fingerprint_confidence` =
  the margin between the highest and second-highest room fingerprint scores among rooms with
  non-zero coverage
- if only one room has non-zero fingerprint coverage, treat `fingerprint_confidence` as high
  rather than undefined because there is no competing fingerprint candidate
- `fingerprint_confidence_decisive_threshold = 0.05` as a provisional starting value
- current room fingerprint scores are expected to stay roughly in the `0.0 - 1.0` range, so a
  `0.05` margin is meant as a modest but non-trivial lead

This means the Phase 2 guardrail should read the fingerprint ranking like this:

- if the challenger does not hold the highest room fingerprint score, fingerprint is not decisive
  for the challenger
- if the challenger does hold the highest room fingerprint score but
  `fingerprint_confidence < 0.05`, fingerprint is still not clearly decisive

## Core Proposal

Improve room classification in two coordinated ways:

1. **Make geometry anisotropy-aware**
2. **Make fingerprinting richer and more reliability-aware**

These changes should work together.

Anisotropy-aware geometry prevents weak-axis wander from being over-interpreted.
Stronger fingerprinting gives the classifier something better to trust when geometry is weak.

## Part 1: Anisotropy-Aware Geometry

### Static observation

The scanner-anchor layout can be used to identify areas where geometry is naturally softer in
`y` than `x`, or vice versa.

This is useful for diagnosis and planning.

### Live observation

For room classification, static anchor geometry is not enough.
The relevant quantity is the live uncertainty of the current solve under the **active weighted
anchor set**.

That should be represented as a local XY covariance or equivalent anisotropy measure.

### Future room geometry scoring

Replace the isotropic room kernel with an uncertainty-aware one.

Instead of:

`d^2 = dx^2 + dy^2 + weighted_dz^2`

use a covariance-aware distance:

`d^2 = (p - sample)^T * inv(Sigma_solve + Sigma_room) * (p - sample)`

Where:

- `Sigma_solve` is the live XY uncertainty from trilat geometry
- `Sigma_room = r^2 * I`, where `r` is the sample support radius and `I` is the 2x2 identity
  matrix

This means:

- separation along a weak axis counts less as geometry evidence
- separation along a strong axis still counts strongly

That is exactly what is needed when `Guest Room`, `Ana's Office`, and `Sophia's room` are being
distinguished partly by coordinates along a weak axis.

Important implementation note:

- this is a later-phase improvement,
- the current solver does not yet expose a full `Sigma_solve`,
- computing it will require explicit design from the live Jacobian / Fisher information or an
  equivalent approximation.

### Lightweight fallback

The initial implementation should not wait for full covariance propagation.

Use a simpler live anisotropy scalar first, computed directly from the active weighted anchors:

- `sigma_x^2 = sum(w_i * (x_anchor_i - x_solve)^2) / sum(w_i)`
- `sigma_y^2 = sum(w_i * (y_anchor_i - y_solve)^2) / sum(w_i)`
- `anisotropy_ratio = max(sigma_x, sigma_y) / min(sigma_x, sigma_y)`
- the weak axis is the axis with the smaller `sigma`
- when anisotropy is large, reduce geometry influence and increase fingerprint influence

This is weaker than full Mahalanobis scoring, but it is computable from existing state and gives
both a scalar ratio and a runtime weak-axis direction for guardrails.

Known limitation of this proxy:

- it measures weighted anchor spread from the solve point, not full GDOP / Fisher-information
  uncertainty
- that makes it a reasonable first-pass observability proxy
- but it can overestimate confidence on an axis when anchors are well-separated yet mostly
  co-directional relative to the solve point
- Phase 1 diagnostics should explicitly validate whether this proxy tracks the actual wander cases

## Part 2: Stronger Fingerprinting Without Reintroducing Buckets

The recommended direction is **not** to bring back `buckets_1s`.

Instead, strengthen the existing compact sample representation.

### Proposed fingerprint features

Continue using per-sample RSSI medians as the primary center values, but also use:

- `rssi_mad` as a per-scanner reliability / expected spread term
- `packet_count` or a better visibility-derived count as a confidence weight
- optional use of `rssi_min` / `rssi_max` or span as a coarse stability signal
- explicit missing-feature handling when a calibration-visible weak scanner is absent live

Recommended missing-feature behavior:

- do not treat absence as a giant negative RSSI,
- do not ignore it completely,
- apply a bounded missing-feature penalty scaled by the scanner's calibration visibility /
  reliability weight,
- cap that penalty at the equivalent of a 6 dB RSSI mismatch or one `rssi_mad`, whichever is
  larger.

This would allow:

- stable scanners to contribute more strongly
- flaky scanners to contribute more softly
- weak scanners with repeatable room-specific behavior to still help room identity

### Important distinction

A scanner can be:

- poor for trilat geometry
- but still useful for fingerprinting

Those should not be treated as the same decision.

For room classification, weak non-trilat scanners may still carry distinctive signal.

### Minimum-sample rule

Fingerprint enrichment is not enough for under-calibrated rooms.

Add an explicit challenger penalty for rooms with too few accepted calibration samples:

- if a room has 1 accepted sample, require `2x` normal room-challenger dwell and an extra `0.10`
  blended-score margin
- if a room has 2 accepted samples, require `1.5x` normal room-challenger dwell and an extra
  `0.05` blended-score margin
- if a room has 3 or more accepted samples, do not apply this penalty

Apply this multiplier after the existing learned transition-strength dwell adjustment so that weak
learned transitions and sparse room calibration compound in the conservative direction.

Cap the resulting total room-challenger dwell after all multipliers:

- provisional maximum dwell ceiling: `180 seconds`
- if the multiplied dwell would exceed that value, clamp to the ceiling rather than continuing to
  grow

This penalty applies only to challengers, not to the stable room.

- the intent is to penalize movement into under-calibrated rooms
- not to destabilize a room assignment that is already holding steady

## Part 3: Adaptive Geometry vs Fingerprint Blending

The fixed fingerprint weight should be replaced by a dynamic blend.

The first implementation should be intentionally simple:

- primary input: live geometry quality
- required guard input: fingerprint coverage / confidence
- optional later input: live anisotropy ratio from the diagnostics phase

The room-blend thresholds should be tuned independently from the floor gate threshold. Do not
assume they are numerically the same as the `geometry_quality >= 0.30` floor-confidence rule.

Example behavior:

- good geometry: geometry retains meaningful influence
- poor geometry with good fingerprint coverage: fingerprint weight rises substantially
- poor geometry with weak fingerprint coverage: keep the stable room and require stronger
  challenger evidence

Start with a piecewise rule instead of a multi-input tuning problem, for example:

- if geometry quality <= low threshold: use high fingerprint weight
- if geometry quality >= high threshold: use normal fingerprint weight
- interpolate between those thresholds
- if the challenging room's fingerprint coverage is below its floor: do not raise fingerprint
  weight, hold the stable room instead

Provisional starting values:

- `low_threshold = 0.15`
- `high_threshold = 0.40`
- challenging-room fingerprint coverage floor = `0.50`

The `0.50` coverage floor may prove too conservative for rooms that are already under the
minimum-sample challenger penalty. If those two mechanisms stack too aggressively, lower the
coverage floor for under-calibrated rooms before weakening the minimum-sample rule itself.

This is better than globally increasing fingerprint weight, because it adapts to the live solve
without turning the first implementation into a research problem.

## Part 4: Room-Switch Gating

The room-switch logic should also use anisotropy and geometry quality.

Recommended changes:

- require stronger evidence when the candidate room differs mostly along the weak axis
- do not advance a room challenger when geometry quality is poor and the challenger's geometry
  support is weak
- if fingerprint is driving the challenger while geometry is low-quality, require extra dwell or
  a larger score margin
- treat fingerprint as decisive for the challenger only if:
  - the challenger has the highest room fingerprint score, and
  - `fingerprint_confidence >= fingerprint_confidence_decisive_threshold`

For the first implementation, define "mostly along the weak axis" as:

- the absolute room displacement component on the weak axis is greater than the component on the
  strong axis, using the lightweight runtime weak-axis calculation above

This is the highest-value early behavior change because it directly addresses the symptom observed
in `docs/room-wander-analysis.md`: a challenger being allowed to form and persist while geometry
was weak.

This directly addresses same-floor room wander.

## Part 5: Static Risk Maps

The scanner-anchor file can be used to generate a static anisotropy map for each floor.

This is useful for:

- diagnostics
- calibration planning
- anchor-placement decisions
- understanding which rooms are naturally at risk of axis-biased wander

However, static maps should be treated as a planning aid, not the live scoring input.

Live room scoring should use the current weighted anchor geometry.

Static anisotropy maps must never be fed directly into live room scoring.

## Why This Should Help `room-wander-analysis.md`

The `Living Room -> Sophia's room -> Living Room` failure described in
`docs/room-wander-analysis.md` is a strong match for this proposal.

That analysis already identified:

- stable floor
- poor same-floor geometry
- relatively high position confidence despite poor geometry quality
- a room switch that the pipeline accepted while geometry was weak

This proposal would help in two ways:

1. The room-switch guardrails would make it harder for a weakly supported challenger to become
   stable while geometry is poor.
2. The geometry score for `Sophia's room` would eventually be reduced if the room separation was
   mostly along the weak local axis.
3. The classifier would be more willing to favor fingerprint evidence or simply hold the stable
   room when geometry quality is poor.

So yes, this proposal is likely to help resolve that issue class.

### Important caveat

It may not be sufficient by itself.

If the fingerprint evidence itself is wrong or undersampled, anisotropy-aware geometry will reduce
bad geometry influence but may still leave the classifier with weak evidence overall.

That is why this plan pairs:

- anisotropy-aware geometry
- stronger fingerprints
- better room-switch gating

## Proposed Implementation Phases

### Phase 1: Diagnostics only

- Add a live XY anisotropy diagnostic to trilat output.
- Add a static floor anisotropy map generator from `bermuda.scanner_anchors`.
- Log whether room candidates differ mainly along the current weak axis.
- Log room fingerprint coverage and sample-count diagnostics for each challenger.

Goal:

- validate that the observed room-jump cases line up with high anisotropy.
- validate whether the first bad challenger is geometry-led, fingerprint-led, or both.

Decision gate after Phase 1:

- if the reference wander events do not show a clear correlation with elevated anisotropy,
  deprioritize the anisotropy-heavy parts of this plan
- continue with Phase 2 guardrails and Phase 3 fingerprint enrichment
- defer Phase 4 anisotropy use and Phase 5 covariance-aware geometry until the failure is
  re-diagnosed

### Phase 2: Room-switch guardrails first

- Increase dwell or margin requirements when the candidate switch is aligned with the weak axis.
- Prevent same-floor room switches when:
  - geometry quality is poor,
  - challenger geometry score is weak,
  - and the challenger either does not lead by fingerprint score or leads with
    `fingerprint_confidence < fingerprint_confidence_decisive_threshold`.
- Add the minimum-sample challenger penalty for under-calibrated rooms.

Goal:

- stop room wander from becoming a stable room assignment before changing the scoring math.
- accept that these guardrails will need re-tuning after Phase 3 changes the fingerprint score
  baseline.

### Phase 3: Fingerprint enrichment

- Extend room fingerprint scoring to use:
  - median RSSI
  - MAD-derived spread
  - scanner reliability / visibility weighting
- bounded missing-feature penalties
- Allow weak scanners to contribute to fingerprinting even if they are unhelpful for trilat.

Goal:

- strengthen room identity without increasing state size dramatically.

### Phase 4: Dynamic geometry/fingerprint blending

- Replace the fixed fingerprint weight with an adaptive weight driven first by:
  - geometry quality
  - fingerprint coverage / confidence
- Optionally incorporate the lightweight anisotropy scalar from Phase 1 after it has been
  validated against captures.

Validation criterion for incorporating the anisotropy scalar:

- only incorporate it if at least `70%` of the false room-challenge events in the reference
  captures occurred with `anisotropy_ratio >= 1.5`
- do not treat this criterion as satisfied unless at least `5` false-challenge events were
  observed in the validation set

For this plan, a false room-challenge event means:

- a room challenger formed while the device was believed stationary within the same floor context,
- the challenger later resolved back to the original stable room or to another known-correct room,
- and manual review of the capture indicates the challenger room was not the real room

Goal:

- stop over-trusting geometry when the solve is directionally weak.

### Phase 5: Covariance-aware geometry scoring if simpler fixes are insufficient

- Replace the isotropic room geometry kernel with a covariance-aware distance metric.
- Derive `Sigma_solve` explicitly from the active weighted anchor geometry before enabling this
  phase.

Deferral criterion:

- defer Phase 5 if, after Phases 2-4 are deployed and validated on the reference captures, the
  targeted room-wander scenarios no longer produce false stable room switches
- only advance to Phase 5 if those simpler phases still leave repeatable false stable switches in
  the validation scenarios

Goal:

- make room geometry evidence reflect actual solve uncertainty rather than assuming circular error.

## Suggested Initial Heuristics

These are starting points, not final values:

- if geometry quality is below a threshold and fingerprint coverage is good, raise fingerprint
  weight substantially
- if geometry quality is below a threshold and the challenging room's fingerprint coverage is
  poor, hold the stable room
- if a room has too few calibration samples, require extra dwell or score margin before it can
  win
- if candidate room displacement is mostly along the weak axis, increase room-switch dwell
- if `anisotropy_ratio >= 1.5`, reduce geometry contribution along the weak axis
- if covariance-aware scoring is not yet implemented, use the anisotropy scalar only as a
  guardrail / blend input, not as a fake covariance substitute

These should be tuned on real captures rather than frozen up front.

## Non-Goals

This plan is not primarily about:

- fixing wrong floor selection
- replacing the topology-gated floor work
- reintroducing per-second calibration buckets

It is specifically about same-floor room accuracy under anisotropic geometry.

## Expected Outcome

If this plan works:

- room classification becomes less biased by weak-axis trilat wander
- fingerprinting becomes more useful without increasing sample storage much
- `Guest Room`, `Ana's Office`, and `Sophia's room` should stop flipping purely because the solve
  wandered along the weak axis
- the earlier `room-wander-analysis.md` failure class should be materially reduced

## Recommendation

This is a strong next software step after the trapped-floor recovery work.

It addresses a different but equally important failure mode:

- the floor is correct,
- the room is wrong,
- and the current classifier is too willing to trust biased geometry.
