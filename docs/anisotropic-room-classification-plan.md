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

### Proposed room geometry scoring

Replace the isotropic room kernel with an uncertainty-aware one.

Instead of:

`d^2 = dx^2 + dy^2 + weighted_dz^2`

use a covariance-aware distance:

`d^2 = (p - sample)^T * inv(Sigma_solve + Sigma_room) * (p - sample)`

Where:

- `Sigma_solve` is the live XY uncertainty from trilat geometry
- `Sigma_room` is the room sample's support radius expressed as covariance

This means:

- separation along a weak axis counts less as geometry evidence
- separation along a strong axis still counts strongly

That is exactly what is needed when `Guest Room`, `Ana's Office`, and `Sophia's room` are being
distinguished partly by coordinates along a weak axis.

### Lightweight fallback

If full covariance propagation is too large a first step, use a simpler live anisotropy scalar:

- derive `anisotropy_ratio = weak_axis_variance / strong_axis_variance`
- when anisotropy is large, reduce geometry influence and increase fingerprint influence

This is weaker than full Mahalanobis scoring, but still useful.

## Part 2: Stronger Fingerprinting Without Reintroducing Buckets

The recommended direction is **not** to bring back `buckets_1s`.

Instead, strengthen the existing compact sample representation.

### Proposed fingerprint features

Continue using per-sample RSSI medians as the primary center values, but also use:

- `rssi_mad` as a per-scanner reliability / expected spread term
- `packet_count` or a better visibility-derived count as a confidence weight
- optional use of `rssi_min` / `rssi_max` or span as a coarse stability signal

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

## Part 3: Adaptive Geometry vs Fingerprint Blending

The fixed fingerprint weight should be replaced by a dynamic blend.

Suggested inputs to the blend:

- live geometry quality
- live anisotropy ratio
- live residual consistency
- live same-floor valid anchor count
- fingerprint coverage and confidence

Example behavior:

- good geometry, low anisotropy: geometry retains meaningful influence
- poor geometry, high anisotropy: fingerprint weight rises substantially
- weak fingerprint coverage as well: keep the stable room and require stronger challenger evidence

This is better than globally increasing fingerprint weight, because it adapts to the live solve.

## Part 4: Room-Switch Gating

The room-switch logic should also use anisotropy and geometry quality.

Recommended changes:

- require stronger evidence when the candidate room differs mostly along the weak axis
- do not advance a room challenger when geometry quality is poor and the challenger's geometry
  support is weak
- if fingerprint is driving the challenger while geometry is low-quality, require extra dwell or
  a larger score margin

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

## Why This Should Help `room-wander-analysis.md`

The `Living Room -> Sophia's room -> Living Room` failure described in
`docs/room-wander-analysis.md` is a strong match for this proposal.

That analysis already identified:

- stable floor
- poor same-floor geometry
- relatively high position confidence despite poor geometry quality
- a room switch that the pipeline accepted while geometry was weak

This proposal would help in two ways:

1. The geometry score for `Sophia's room` would be reduced if the room separation was mostly
   along the weak local axis.
2. The classifier would be more willing to favor fingerprint evidence or simply hold the stable
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

Goal:

- validate that the observed room-jump cases line up with high anisotropy.

### Phase 2: Fingerprint enrichment

- Extend room fingerprint scoring to use:
  - median RSSI
  - MAD-derived spread
  - scanner reliability / visibility weighting
- Allow weak scanners to contribute to fingerprinting even if they are unhelpful for trilat.

Goal:

- strengthen room identity without increasing state size dramatically.

### Phase 3: Dynamic geometry/fingerprint blending

- Replace the fixed fingerprint weight with an adaptive weight driven by:
  - geometry quality
  - anisotropy
  - residual consistency
  - live fingerprint coverage

Goal:

- stop over-trusting geometry when the solve is directionally weak.

### Phase 4: Covariance-aware geometry scoring

- Replace the isotropic room geometry kernel with a covariance-aware distance metric.

Goal:

- make room geometry evidence reflect actual solve uncertainty rather than assuming circular error.

### Phase 5: Room-switch guardrails

- Increase dwell or margin requirements when the candidate switch is aligned with the weak axis.
- Prevent same-floor room switches when:
  - geometry quality is poor,
  - challenger geometry score is weak,
  - and fingerprint support is not clearly decisive.

Goal:

- stop room wander from becoming a stable room assignment.

## Suggested Initial Heuristics

These are starting points, not final values:

- if geometry quality is below a threshold, raise fingerprint weight substantially
- if anisotropy ratio exceeds a threshold, reduce geometry contribution along the weak axis
- if candidate room displacement is mostly along the weak axis, increase room-switch dwell
- if fingerprint support is weak and geometry is anisotropic, hold the stable room

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
