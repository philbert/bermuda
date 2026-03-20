# Trapped Floor Recovery Plan

Date drafted: 2026-03-20

Related documents:
- `docs/topology-gated-floor-inference-design.md`
- `docs/topology-gated-floor-inference-gap-analysis.md`
- `docs/room-wander-analysis.md`

## Purpose

This document proposes a recovery path for a specific failure mode that still exists after
topology-gated floor inference was added:

- a device is physically outside or near `garage_front`,
- Bermuda collapses it onto `ground_floor`,
- room inference starts returning `Guest Room` / `Ana's Office`,
- the reachability gate then prevents the device from escaping back to the correct floor.

The current gate is doing its original job, but it has no model for how to recover once a wrong
floor has already been accepted.

This plan is intentionally targeted at recovery. It does not replace the topology-gated design.

## Problem Summary

The current implementation treats the current floor estimate as authoritative enough to block
challenger floors whenever:

- `floor_confidence` is above the gate threshold,
- a recent `last_good_position` exists,
- transition-zone coverage exists for the floor pair.

That is correct for a real indoor device, but it breaks when the current floor was itself reached
through weak or contradictory evidence.

The resulting loop is:

1. Device is mis-solved onto the wrong floor.
2. `last_good_position` is updated from that wrong solve.
3. The reachability gate uses that wrong indoor reference position.
4. The correct floor challenger is blocked for lacking fresh transition evidence.
5. Room inference keeps selecting plausible rooms on the wrong floor.

This makes the wrong floor estimate self-sealing.

## Constraints

Any fix must preserve the useful behavior that already exists:

- a real phone sleeping in `Guest Room` must not teleport to `Garage front`,
- floor changes should still require topology support when the current floor is trustworthy,
- Bermuda should continue to publish a concrete best guess rather than falling back to `unknown`.

The user preference here is explicit:

- always make a guess,
- do not hide bad states behind `unknown`,
- expose enough signal to understand what needs fixing.

## Core Design Rule

Separate these two ideas conceptually:

1. **Current floor guess**
2. **Current floor gating authority**

Bermuda should always publish a current floor guess.

But only a sufficiently supported current floor should be allowed to hard-block challengers via
topology.

Implementation note:

- do not introduce a second independent gate-authority field,
- reuse the existing `floor_confidence` concept from
  `docs/topology-gated-floor-inference-gap-analysis.md`,
- extend it so confidence can decay under sustained contradiction,
- and attach provenance / reason diagnostics to explain why the gate is active or softened.

That keeps the design aligned with the topology-gated work instead of creating a competing trust
state machine.

## Proposed State Additions

Extend `TrilatDecisionState` with recovery-oriented state that builds on the existing
`floor_confidence` work:

- `last_trusted_floor_id`
- `last_trusted_position`
- `last_trusted_position_at`
- `floor_confidence`
- `floor_confidence_source`
- `floor_confidence_reason_flags`
- `confidence_decay_since`
- `same_floor_valid_anchor_count`
- `other_floor_valid_anchor_count`

Provisional diagnostic enums for Phase 1:

- `floor_confidence_source`:
  - `transition_traversal`
  - `fingerprint_convergence`
  - `anchor_count_and_geometry`
  - `inherited_from_prior`
  - `recovery_shortcut`
- `floor_confidence_reason_flags`:
  - `too_few_same_floor_anchors`
  - `geometry_below_threshold`
  - `fingerprint_not_favoring_floor`
  - `other_floor_anchors_dominating`
  - `never_confirmed`
  - `boot_or_warm_start_open_mode`

The existing `last_good_position` remains useful for continuity and diagnostics, but it should no
longer be the only reference used to decide whether the current floor may imprison the device.

`last_trusted_position_at` should have an explicit role:

- it is the timestamp when the current `last_trusted_*` reference was last earned through the
  normal confidence path
- if that timestamp is older than a configurable staleness window, treat the trusted reference as
  stale for warm-start / recovery purposes and stay in open mode until confidence is re-earned
- provisional starting value for that staleness window: `12 hours`

Room churn can still be logged as a diagnostic, but it should not be a primary floor-confidence
demotion signal until same-floor room-wander fixes are in place. Otherwise a correctly placed
phone on the right floor could be penalized for a separate room-classification bug.

If room churn is later promoted into floor-confidence logic, that should only happen after
`docs/anisotropic-room-classification-plan.md` Phase 2 guardrails are deployed and validated.

## Confidence Model

### When floor confidence becomes high enough to gate

A floor should earn gate authority through one of two paths:

1. a recent transition traversal matching the floor pair, or
2. sustained non-topological floor evidence where all of the following remain true:
   - at least 2 stable same-floor valid anchors,
   - `geometry_quality >= 0.30`,
   - and the Stage 4 floor fingerprint evidence continues to favor the selected floor by at least
     the configured margin.

The second path is intentionally conjunctive. It should require more than a single decent solve on
the selected floor.

Traversal-based authority should be time-bounded:

- provisional traversal validity window for confidence earning: `2 minutes` after zone exit
- after that window expires, gate authority must be maintained or re-earned through path 2
- traversal alone should not keep the gate active indefinitely for a stationary device with weak
  subsequent evidence

For this plan, define:

- `floor_fingerprint_margin` =
  selected floor Stage 4 fingerprint-global floor evidence minus the second-best reachable floor
  score
- provisional support threshold:
  `floor_fingerprint_margin >= 0.10`
- if only one reachable floor has non-zero fingerprint evidence, treat fingerprint support as
  present but still require the anchor-count and geometry checks above

### When floor confidence decays

A selected floor should lose gate authority when contradiction persists, for
example:

- `geometry_quality < 0.30`,
- same-floor valid anchors stay below 2 for a sustained period,
- stable anchors are mostly `valid_other_floor`,
- `floor_fingerprint_margin < 0.10`,
- the selected floor was never reached via trusted evidence in the first place.

If only one reachable floor has non-zero fingerprint evidence, treat the
`floor_fingerprint_margin < 0.10` decay condition as not met.

This should be implemented as decay of the single `floor_confidence` field, not as a second
independent `floor_trust_level`.

This is intentionally not a strict mirror of the earn logic.

- a device with low same-floor anchors and poor geometry, but with no contradicting other-floor
  anchors, will remain in whatever confidence state it last held
- absence of contradicting evidence is not treated as positive evidence that the floor is wrong
- this keeps weak-but-uncontradicted devices from being forced out of gate authority solely by
  temporary local signal collapse
- a legitimate traversal can therefore expire into low-confidence open mode if path 2 has not yet
  been satisfied; that is acceptable in the first version because it is still safer than letting
  stale traversal evidence keep the gate active indefinitely

### Confidence transition mechanism

The first implementation should use timer-driven threshold transitions, not continuous decay.

Recommended behavior:

- if all contradiction criteria remain true continuously for at least `T_decay`, drop
  `floor_confidence` below the gate threshold in one step
- if the gate-earn criteria remain true continuously for at least `T_recover`, raise
  `floor_confidence` back above the gate threshold in one step
- do not implement a partially softened gate in the first version

This keeps the state machine inspectable:

- the gate is either active or not active for the current cycle
- the transition reason is tied to explicit timers rather than hidden numeric drift

`confidence_decay_since` should mean:

- the timestamp when all decay criteria first became continuously true
- reset to `None` as soon as any decay criterion clears
- reset to `None` when confidence recovers above the gate threshold

`T_recover` should be interpreted as sustained evidence:

- the anchor-count, geometry, and floor-fingerprint conditions must remain true continuously for
  the full recovery window
- do not allow a one-cycle floor fingerprint spike to re-enable the gate

### Boot and warm-start behavior

At startup, after long absence, or after a tracking collapse:

- if `floor_id` is `None`, or
- if `floor_confidence` is below the gate-activation threshold, or
- if there is no `last_trusted_floor_id`,
- or if `last_trusted_position_at` is older than the trusted-reference staleness window,

the reachability gate should operate in open mode for that cycle. The estimator may still publish
its best floor guess, but it must not treat that guess as authoritative enough to block
challengers.

This is also the intended behavior for never-trusted devices:

- if `last_trusted_floor_id` is `None`, the recovery shortcut is unavailable
- but open-mode evidence competition still runs
- normal evidence competition is therefore the recovery path for such devices, not the shortcut

This is the key difference between:

- a real phone in `Guest Room`,
- a brown bin that has been numerically trapped in `Guest Room`.

## Recovery Rule

When the current floor has **high enough floor confidence**:

- keep the current reachability gate behavior,
- require transition evidence or motion-budget plausibility,
- continue blocking impossible teleports.

When the current floor has **low floor confidence**:

- allow the challenger floor to form even if the reachability gate would normally block it,
- allow challenger dwell and challenger motion budget to accumulate,
- use the gate as a diagnostic signal, not as a hard veto.

This is not a blind bypass. It is a recovery mode that activates only when the current floor is
already contradicted by the rest of the estimator.

## Recovery Shortcut To The Last Trusted Floor

Add an explicit escape hatch:

If all of the following are true:

- the current floor has low floor confidence,
- the challenger floor matches `last_trusted_floor_id`,
- challenger evidence persists for a dedicated recovery dwell,
- current-floor contradiction remains active,
- reverse-pair topology coverage exists, or if that reverse pair is not explicitly configured,
  a bounded recovery motion-budget check passes,

then allow the switch back to `last_trusted_floor_id` without requiring a fresh transition
traversal.

This is the main mechanism that should free a trapped bin from `Guest Room` / `Ana's Office`
and let it return to `garage_front` or `street_level`.

This is intentionally narrower than a full blind bypass:

- it only applies to the last structurally trusted floor,
- it still requires sustained challenger evidence,
- and it still requires a plausibility check tied to the known floor pair.

This means the shortcut does not require users to configure both directional pairs just to make
recovery work. If reverse-pair coverage is absent, the motion-budget fallback is the intended
recovery check.

Post-shortcut behavior:

- after a recovery shortcut fires, set `floor_confidence` below the gate threshold on the
  recovered floor
- do not inherit the old high-confidence state automatically
- require the recovered floor to re-earn gate authority through the normal `T_recover` path

## Why This Should Differentiate Phone vs Bin

### Guest Room phone overnight

A real phone in `Guest Room` typically shows:

- stable `ground_floor`,
- stable `Guest Room`,
- multiple same-floor valid anchors,
- acceptable geometry from those anchors,
- strong residual consistency,
- adequate position confidence,
- and `floor_fingerprint_margin >= 0.10` favoring `ground_floor`.

That should keep `floor_confidence` above the gate threshold, so the topology gate remains strict.

### Trapped brown bin overnight

The trapped bin shows a very different pattern:

- poor geometry quality,
- only one stable same-floor valid anchor,
- one stable `valid_other_floor` anchor,
- mediocre raw position confidence,
- strong filtered continuity despite weak observability.

That is exactly the profile that should prevent the indoor floor from earning or keeping enough
gate authority to imprison the device.

### Confidence recovery after a successful escape

Once the bin has recovered back to `street_level` or `garage_front`, it should rebuild gate
authority using the same timer-driven earn path:

- sustained same-floor anchor support
- `geometry_quality >= 0.30`
- `floor_fingerprint_margin >= 0.10` favoring the recovered floor
- or transition traversal on the next legitimate move

This prevents the device from remaining permanently in open mode after a successful recovery.

When confidence is re-earned after recovery:

- refresh `last_trusted_floor_id`
- refresh `last_trusted_position`
- refresh `last_trusted_position_at`
- and record the source as normal evidence re-convergence rather than `recovery_shortcut`

## Important Non-Goal

This plan does **not** primarily aim to improve `Guest Room` vs `Ana's Office` classification.

That room distinction is downstream.

The main goal is:

- prevent a wrong indoor floor from becoming authoritative enough to trap the device.

Once the floor recovers, room classification should naturally stop selecting indoor rooms for the
bin.

## Proposed Implementation Phases

### Phase 1: Extend `floor_confidence` diagnostics only

- Add the recovery-oriented state fields to `TrilatDecisionState`.
- Expose diagnostics for:
  - current floor confidence,
  - current floor confidence source,
  - last trusted floor,
  - same-floor vs other-floor valid anchor counts,
  - confidence-decay reason flags,
  - `confidence_decay_since`,
  - optional room-churn diagnostic for later comparison only.
- Do not change switching behavior yet.

Goal:

- verify from logs that phone and bin produce clearly different confidence signatures.
- verify that the proposed Phase 1 enums are actually interpretable in live traces.

### Phase 2: Split trusted references and make the gate use them

- Split `last_good_position` from `last_trusted_position`.
- Update `last_trusted_position` only when floor-confidence criteria are satisfied.
- Keep `last_good_position` for general continuity and diagnostics.
- Make the reachability gate consult `floor_confidence` and `last_trusted_position` together.
- If current floor confidence is high, keep hard gate behavior.
- If current floor confidence is low, let challenger formation proceed.
- Preserve gate diagnostics so blocked-vs-recovery decisions remain visible in logs.

Goal:

- prevent weak indoor collapses from immediately becoming authoritative challenger references
  while enabling recovery without weakening the normal anti-teleport protection.

### Phase 3: Add recovery shortcut to the last trusted floor

- If challenger matches `last_trusted_floor_id` and contradiction persists, permit a switch back
  after dwell even without a new traversal event.
- Require reverse-pair coverage or a bounded recovery motion-budget check before the shortcut is
  allowed.
- Use a dedicated `recovery_dwell` timer rather than reusing the normal floor-switch dwell.
- Reset challenger and confidence state cleanly after the recovery switch.

Goal:

- let trapped devices return to the last structurally credible floor.

### Phase 4: Tune thresholds with real captures

Use at least these comparison captures:

- brown bin `garage_front -> street_side -> garage_front`,
- trapped brown bin overnight,
- wife's phone overnight in `Guest Room`.

Tune using data, not intuition, for:

- minimum same-floor valid anchor count,
- geometry threshold for gate activation,
- floor-confidence decay threshold,
- `T_decay`,
- `T_recover`,
- recovery dwell duration.

## Suggested Initial Heuristics

These are starting points, not final values:

- gate-active floor requires either:
  - recent transition traversal, or
  - `same_floor_valid_anchor_count >= 2`,
  - `geometry_quality >= 0.30`,
  - and `floor_fingerprint_margin >= 0.10`
- floor confidence drops below the gate threshold if, for at least `T_decay`:
  - `same_floor_valid_anchor_count < 2`, and
  - `other_floor_valid_anchor_count >= 1`, and
  - geometry quality remains poor, and
  - `floor_fingerprint_margin < 0.10`
- floor confidence rises back above the gate threshold if the earn criteria remain true for at
  least `T_recover`
- recovery switch allowed when:
  - challenger equals `last_trusted_floor_id`,
  - contradiction persists,
  - dedicated `recovery_dwell` expires,
  - recovery motion budget is not exceeded
- provisional timer starting values:
  - `T_decay = 10 minutes`
  - `T_recover = 5 minutes`
  - traversal validity window for path 1 = `2 minutes`

At boot or warm-start, if `floor_confidence` is below threshold, the gate stays open until the
current floor earns authority again.

These thresholds should be logged and iterated against captures before being treated as stable.

## Risks

### Over-recovery

If trust is demoted too aggressively, real indoor devices may become eligible for floor escape when
they should remain blocked.

Mitigation:

- require multiple contradiction signals,
- require sustained duration,
- prefer recovery only toward `last_trusted_floor_id`.

### Never-trusted devices

Some low-signal devices may never build a trusted floor if the trust bar is too high.

Mitigation:

- keep publishing a best guess,
- use confidence only for gate hardness, not for whether a floor may be shown.

This is a known limitation, not a fully solved case:

- such devices may remain permanently in low-confidence open mode
- they can still recover through normal evidence competition
- but they will not benefit from the `last_trusted_floor_id` shortcut until they have earned a
  trusted reference at least once

### Hidden complexity

Adding recovery state can still create an implicit state machine if not kept narrow.

Mitigation:

- reuse one `floor_confidence` field instead of adding a second gate-authority field,
- log confidence-threshold transitions explicitly,
- keep state model simple,
- make confidence reasons inspectable in diagnostics.

## Expected Outcome

If this plan works, Bermuda should behave like this:

- a phone genuinely in `Guest Room` stays on `ground_floor` and remains topology-protected,
- a bin wrongly trapped on `ground_floor` can recover back to `garage_front` / `street_level`,
- the software continues to emit a concrete best guess at all times,
- the diagnostics become more honest about whether the current floor is authoritative enough to gate
  future transitions.

## Recommendation

Implement this before physical anchor optimization.

The current captures suggest there is still meaningful software value available from:

- better separation of floor guess vs floor gating authority,
- better handling of contradictory anchor sets,
- and an explicit recovery path out of self-sealed bad states.

Anchor placement will still matter, but it should not be used to compensate for a state machine
that cannot recover once it is wrong.
