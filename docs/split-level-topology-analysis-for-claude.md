# Split-Level Topology Analysis For Claude Review

## Purpose

This note is a deliberate step back from the recent implementation work.

The current effort may be optimizing a local maximum: tuning floor challenger logic inside a floor-first architecture, instead of solving the underlying physical reasoning problem.

The goal of this review is to critique the problem framing itself and propose a better target architecture for split-level homes.

## Core Claim

The repeated `ground_floor -> street_level -> garage_front` failures do not look like isolated threshold bugs.

They look like a topology failure:

- Bermuda allows a floor change without strong evidence that the device plausibly passed through a real floor-transition region.
- Once the floor flips, room inference becomes trapped on the new floor and drifts toward plausible rooms there.
- This means downstream room errors are often consequences of an earlier impossible floor transition, not independent classification errors.

## Physical Reality

In this house, floor changes are not arbitrary.

- The house has `basement`, `street_level`, `ground_floor`, and `top_floor`.
- `street_level` is an intermediate split level, not a full separate floor plate.
- A device cannot move from `Guest Room` or `Ana's Office` directly to `Garage front`.
- The only physically valid way to change floors is to pass through one of a small set of real transition points or transition zones.

That physical constraint is stronger than any current RSSI-only floor challenger.

## Recent Evidence

### Failure 1: Guest Room -> Garage front

From March 13, 2026:

- `22:31:15Z`: area becomes `Guest Room`
- `23:31:20` local in the HA log:
  - `selected=ground_floor`
  - `challenger=street_level`
  - `fp_floor=ground_floor`
  - `fp_conf=0.619`
  - `transition_support=0.000`
- `22:31:33Z`: floor becomes `Street level`
- `22:31:40Z`: area becomes `Garage front`

Interpretation:

- Bermuda was still on the ground floor and still had ground-floor fingerprint evidence.
- No transition sample support was active.
- The floor still flipped.
- Once the floor flipped, the room followed.

### Failure 2: Ana's Office -> Garage front

From March 13, 2026:

- `22:49:24Z`: area becomes `Ana's Office`
- `23:49:28` local in the HA log:
  - `selected=ground_floor`
  - `fp_floor=ground_floor`
  - `fp_conf=0.603`
  - `transition_support=0.000`
- `23:50:12` local:
  - `selected=ground_floor`
  - `challenger=street_level`
  - `fp_floor=street_level`
  - `fp_conf=0.572`
  - room still resolves to `Ana's Office`
  - `transition_support=0.000`
- `22:50:16Z`: floor becomes `Street level`
- `22:50:24Z`: area becomes `Garage front`

Interpretation:

- The same impossible transition happened from a different ground-floor room.
- This strongly suggests the bug is not specific to `Guest Room`.
- It is also not fixed by the current transition-sample hook, because transition diagnostics remained zero throughout the challenger.

## Why The Current Direction Looks Like A Local Maximum

Recent work has improved observability and removed some obvious bugs:

- floor-switch cold resets were removed,
- diagnostics are much better,
- cross-floor anchor inclusion experiments were run,
- cross-floor fingerprint guidance was added,
- transition samples were added,
- transition dwell reduction and later no-route veto logic were added.

But the core failure still persists.

That suggests the current optimization target may be wrong:

- The architecture still begins from a floor-first worldview.
- Transition evidence is being used as a modifier on challenger timing.
- Physical route plausibility is still not the primary state constraint.

In other words, the system still asks:

- "Which floor currently has the strongest evidence?"

before it asks:

- "Is this floor change physically plausible from where the device was recently estimated to be?"

For a split-level house, that order may be backwards.

## Stronger Problem Framing

This looks more like a constrained state-estimation problem than a pure instantaneous classification problem.

At each time step, Bermuda should not only infer:

- current `x/y/z`,
- current floor,
- current room,

it should also enforce transition plausibility over time:

- what floor changes are reachable from the recent path,
- whether the estimated motion could have reached a floor-transition point,
- whether the elapsed time is enough to traverse a valid path at realistic speed.

This does not necessarily require a mathematically heavy solution, but it does require the topology model to be first-class.

## Signals Bermuda Already Has

The system already appears to have enough information to reason much better:

- scanner anchor `x/y/z`,
- per-floor scanner metadata,
- solved or partially solved `x/y/z`,
- room calibration samples,
- transition sample `x/y/z` points or zones,
- timestamps,
- velocity estimates,
- maximum speed constraints,
- fingerprint evidence,
- RSSI floor evidence,
- continuity from prior stable room/floor.

The problem may not be missing data. It may be insufficient use of the spatial and temporal structure already available.

## Key Design Question

What should a transition sample actually be?

There are at least three plausible models:

### Option A: Transition sample as a calibration-like learned zone

Treat transition samples similarly to room calibration samples:

- they are real observation windows at known `x/y/z`,
- they collect fingerprints and quality metrics over time,
- runtime checks ask whether the current live fingerprint and geometry resemble a known transition region.

Strength:

- naturally uses live evidence, not just declared geometry.

Weakness:

- may still be too "sample matching" oriented if what is really needed is a stronger path constraint.

### Option B: Transition sample as an explicit topology node or zone

Treat transition samples primarily as topology primitives:

- each one defines a place where floor changes are physically allowed,
- each one has geometry and supported destination floors,
- floor changes are only plausible when the recent estimated path intersects such a zone within time and speed limits.

Strength:

- directly matches physical reality.

Weakness:

- may need a more explicit motion/path model than Bermuda currently has.

### Option C: Hybrid

Use transition samples as both:

- learned evidence regions,
- topology constraints.

This may be the most realistic approach:

- the geometry defines what transitions are physically possible,
- the learned fingerprints define whether the device was actually near the transition point.

## Topology Heuristic That Seems Necessary

A strong heuristic that appears justified:

- a floor change should be strongly disfavored, or outright vetoed, if there is high confidence that the device has not recently passed through, moved toward, or been near a valid transition point for that floor change.

This should still be flexible enough to tolerate latency and imperfect room assignment.

That implies some form of recent route memory:

- if a device was near a valid transition point recently, a floor change may remain plausible for a short window,
- if it was not, a cross-floor challenger from a remote room should be heavily constrained.

## Kinematic Reasoning

Velocity and max-speed constraints likely matter here.

If Bermuda has:

- current and prior `x/y/z`,
- estimated velocity,
- a max speed limit,
- known transition point coordinates,

then it should be possible to reason about whether a claimed floor change is reachable.

Example:

- If the device was recently stable in `Guest Room`,
- and the nearest valid path to `street_level` requires moving through `Entrance Hall` / stairwell / door transition points,
- and the elapsed time is too short for that route,
- then a `street_level` challenger should be very hard to accept.

This does not require perfect route planning. Even a coarse reachable-within-time heuristic may be much better than the current challenger logic.

## Concern About The Current Transition Hook

The recent implementation treated transition support mostly as:

- dwell reduction when transition evidence is positive,
- later, some veto logic when evidence is absent.

That may still be too downstream and too weak.

The deeper issue may be:

- transition plausibility should not merely adjust challenger timing,
- it should shape the state space of plausible floor changes before room assignment becomes trapped on the wrong floor.

## Questions For Claude To Critique

Please critique the following directly:

1. Is the problem primarily a topology / route-plausibility problem rather than a floor-threshold problem?
2. Is it a mistake to keep trying to tune the current floor-first challenger architecture?
3. Should transition samples be modeled more like:
   - calibration-like learned evidence regions,
   - explicit topology nodes/zones,
   - or a hybrid of both?
4. Should a floor change be impossible, or only extremely unlikely, unless a valid transition point was observed recently enough?
5. What is the simplest useful way to incorporate time, velocity, and maximum speed into floor-change plausibility?
6. Is there a better formulation here:
   - HMM/state machine,
   - constrained graph traversal,
   - route plausibility scoring,
   - factor graph / smoother,
   - or something simpler?
7. Given the repeated `Guest Room -> Garage front` and `Ana's Office -> Garage front` failures, what architecture change is most likely to solve the actual problem instead of refining a local maximum?

## What A Good Answer Would Provide

A useful critique should:

- challenge the framing if it is wrong,
- say whether the recent implementation path is fundamentally mis-prioritized,
- propose the right level of topology modeling for Bermuda,
- define how strong floor-transition constraints should be,
- say whether transition samples should primarily be evidence, topology, or both,
- recommend the next architectural slice with the highest information gain.

## Bottom Line

The repeated failures now suggest:

- the issue is not one bad room,
- the issue is not one missing reset fix,
- the issue is not just missing transition samples,
- the issue is that Bermuda still allows floor changes that are not physically plausible from the recent path.

That is the part that needs to be reviewed and likely redesigned.

---

## Technical Advisory — 2026-03-14

*Reviewed against: split-level-topology-analysis-for-claude.md, coordinator.py, room_classifier.py, ESTIMATION_PIPELINE_PROPOSAL.md, global-trilateration-refactor-plan.md.*

---

### 1. Executive Judgment

**No. You are still solving the wrong problem, and the sophistication of the current approach makes that harder to see.**

The core loop is: RSSI builds a challenger, a timer runs, vetoes try to block the switch, eventually the switch goes through. Every improvement in this direction makes the veto machinery more elaborate and the timing conditions more precise. But the problem is not that the veto machinery is insufficiently elaborate. The problem is that **you are using vetoes to correct a decision that should never have been a candidate in the first place.**

The local maximum is this: you are asking RSSI evidence what floor the device is on, and then asking fingerprints and topology whether they object to the answer. This is backward. RSSI is the noisiest, most structurally ambiguous signal you have for floor discrimination in a split-level house. You have put it first and made everything else defensive.

A veto pattern that expires is not a correctness mechanism. It is a delay mechanism. Given enough time, a challenger that has been accumulating RSSI evidence will outlast every veto you install. The person in Guest Room, stationary, generating a persistent street_level RSSI challenge, will always eventually exhaust the fingerprint hold ceiling (currently 2× dwell), and at that point the switch will happen unless fingerprint conditions are exactly right at that exact update cycle.

That is not a threshold problem. That is an architecture problem.

---

### 2. Deep Problem Framing

The right framing is **topology-constrained state estimation**, and the problem documents already say this. But the implementations have not made this the load-bearing concept. They have added topology as a modifier on top of a classification engine, which is not the same thing.

The distinction that matters:

- **Classification** asks: given this RSSI snapshot, which floor is most likely? It is stateless.
- **Constrained state estimation** asks: given where I recently was and what paths are physically traversable, which floor changes are reachable? It is temporal and spatial.

Floor classification and floor state estimation produce the same answer when transitions are fast and clean. They produce systematically different answers when the device is stationary in a split-level ambiguity zone. In your failure cases, the device is exactly stationary in such a zone. The classification answer keeps flipping with RSSI noise. The state estimation answer should remain stable because no traversal happened.

The failure mode is not a floor classification error. It is a state transition that should never have been permitted. You cannot fix a state transition problem by improving a classifier.

Of the framings in the document:

- floor classification: wrong framing, this is what the current code implements
- route plausibility: partially right, but route is the wrong word; there is no route to plan; the question is simply whether any valid inter-floor path was recently traversed
- constrained state estimation: right framing
- topology plus motion inference: correct but sounds heavier than it needs to be; the minimum viable version is simple

The simplest useful version of constrained state estimation here is: **a floor change is only plausible if the device has recently been within effective range of a valid transition zone for the target floor, or if no transition zones are configured for the current layout.** That is it. No path planning. No graph traversal. Just: was the device near the gate?

---

### 3. Transition Samples: What Should They Be?

They should be **Option B, topology nodes**, with enough fingerprint characterization to determine proximity reliably.

The document describes three options. Option A (calibration-like evidence) is what they currently are. The problem with Option A is precisely what the document suspects: it frames the question as "does the current signal resemble the transition zone?" rather than "did the device pass through the transition zone recently?"

Positive evidence of proximity is useful. But the essential function of a transition sample is **defining where floor changes are physically possible**. That is a topological claim, not a fingerprint similarity claim.

In the current implementation, transition support reduces dwell by up to 40%. This treats transition proximity as a convenience signal that helps legitimate transitions go faster. It says nothing about the case where there is no transition support. Absence of transition evidence is currently neutral: the base dwell applies unchanged.

This is the design error. If transition zones are configured and the challenger floor is one of the floors connected by those zones, then absence of recent proximity to any valid transition zone is strong negative evidence. Not neutral. The device cannot have changed floors without passing through a physical doorway or stairwell. Absence of transition proximity should increase the challenge to a floor switch, not merely fail to decrease it.

The current transition_switch_veto attempts to capture this, but with a critical coupling flaw: it requires `fingerprint_has_floor_signal` AND `current_floor_fp_score >= challenger_floor_fp_score` as additional prerequisites. This means the topology constraint only activates when the fingerprint is also already doing its job. The moment fingerprint evidence is uncertain — which is exactly the situation where you most need the topology constraint — the topology veto silently disarms. These two conditions should be independent. Topology does not need fingerprint to agree in order to know that the device did not pass through a stairwell.

---

### 4. Physical Constraints and Time

You have the right data. The question is whether you are using the temporal structure, not just the spatial structure.

The key concept is a **reachability budget**:

```
reachability_budget_m = elapsed_time_s × max_speed_m_per_s
```

For each pending floor challenger, compute the Euclidean distance from the current position estimate to the nearest valid transition zone for the target floor. Call this `d_to_transition_m`. If `d_to_transition_m > reachability_budget_m`, the floor change is physically impossible.

This does not require path planning. It uses Euclidean distance as a lower bound on travel distance. A real path must be at least as long as the straight-line distance, so if even the straight-line distance is unreachable, the real path definitely is.

For your specific failure: Guest Room to Garage front. The nearest stairwell between ground_floor and street_level is not adjacent to Guest Room. Even if the device could teleport at max speed, it would take several seconds to reach the stairwell. The RSSI-driven floor switch at 22:31:33Z happened roughly 18 seconds after 22:31:15Z when the device was stable in Guest Room. At 1.5 m/s, that is about 27 meters of reachable distance. If the nearest valid transition zone is within 27 meters, the reachability budget does not help. But if the person was observed stationary (velocity near zero, position stable), the effective reachability budget at the switch moment is much smaller — effectively, they have not moved.

This is where velocity matters more than max speed. If position history shows near-zero velocity for the past 15 seconds, the effective reachability budget is `velocity × time` not `max_speed × time`. A stationary device has a near-zero budget. The floor change is implausible.

The lightest-weight implementation:

1. Maintain a short rolling estimate of device velocity (already present in state).
2. For each active floor challenger, compute distance to nearest configured transition zone for the challenger floor.
3. Compute `effective_reachability_m = integral(velocity_history) over the challenger window`, or as a simpler approximation: `mean_velocity_m_per_s × challenger_dwell_s`, capped at `max_speed × challenger_dwell_s`.
4. If `d_to_transition_m > effective_reachability_m + position_uncertainty_m`, the challenger is physically implausible.

This does not need to be exact. A conservative margin works. The point is to make the implausibility of a stationary-to-remote-floor transition explicit in the state machine, not merely a higher hurdle.

Explicit path reasoning is not needed. The Euclidean lower bound is sufficient for the common failure cases, which involve a stationary device far from any stairwell.

---

### 5. What Is The Right Architecture?

For a split-level house, the pipeline should run in this order:

**Stage 1: Geometry solve**
Multilateration with soft cross-floor inclusion. This produces a position estimate with uncertainty. This is already being worked on correctly.

**Stage 2: Global fingerprint floor inference**
What floor does the current RSSI signature best match, scored globally across all floors? This is already implemented and appears to work. This should produce a probability distribution over floors, not a single floor with a confidence number.

**Stage 3: Topology reachability filter**
Given the current position estimate, the velocity history, and the configured transition zone graph, which floor changes are geometrically reachable in the elapsed time? This is the missing piece. It does not replace the floor evidence. It pre-filters what floor changes are physically possible before the evidence competition even starts.

**Stage 4: Floor posterior**
Combine Stage 2 (fingerprint floor distribution) with Stage 3 (reachability filter) and the existing RSSI floor evidence. The reachability filter acts as a hard or near-hard gate: floors that are geometrically unreachable do not compete, regardless of RSSI. Fingerprint floor evidence is the primary discriminator among reachable floors. RSSI floor evidence is a secondary input.

**Stage 5: Room classification**
Room classification on the selected floor. Fingerprint-primary, geometry-secondary. Already partially implemented.

**Stage 6: Hysteresis and continuity**
Hold states against weak evidence. This is a stability layer. It should not be the primary mechanism preventing impossible transitions, because it can be exhausted. With the topology filter in Stage 3, hysteresis only needs to handle legitimate ambiguity at boundaries, not physically impossible teleportation.

The key ordering principle: **topology before hysteresis, not after.** Hysteresis is a probabilistic preference for stability. Topology is a physical constraint. Physical constraints should not be downstream of probabilistic preferences.

Signal hierarchy:
- **Primary gate**: physical reachability (topology)
- **Primary selector**: fingerprint floor evidence
- **Secondary selector**: RSSI floor evidence
- **Refinement**: geometry/position
- **Stabilizer**: continuity and hysteresis

This is roughly the inverse of the current ordering.

---

### 6. What Should We Stop Doing?

**Stop tuning the veto thresholds.** The thresholds `_TRILAT_FINGERPRINT_FLOOR_CONFIDENCE_HIGH = 0.70`, `_TRILAT_FINGERPRINT_FLOOR_CONFIDENCE_MODERATE = 0.55`, and `_TRILAT_FINGERPRINT_FLOOR_SCORE_RATIO_HOLD = 1.25` are not wrong in themselves, but tuning them is not moving you toward the solution. A veto that fires at 0.72 instead of 0.70 is not architecturally different. It fails under the same conditions, just slightly shifted.

**Stop extending the fingerprint hold ceiling.** The hold ceiling at 2× dwell is already generous. Making it 3× or 4× just delays the failure without preventing it. The problem is that the hold can expire; making it harder to expire is not the same as making the switch not happen.

**Stop requiring fingerprint agreement as a prerequisite for the transition veto.** The `transition_switch_veto_active` path at coordinator.py:2908-2915 requires `fingerprint_has_floor_signal` and `current_floor_fp_score >= challenger_floor_fp_score`. This coupling is wrong. The topology constraint should stand on its own: if the device could not have reached a valid transition zone, the floor change is blocked regardless of what the fingerprint says. The coupling with fingerprint makes the topology veto weaker exactly when it needs to be strongest.

**Stop treating absence of transition support as neutral.** When transition zones are configured for the current layout and none support the challenger floor, the current architecture treats this as simply the base dwell case: no reduction. That is the wrong semantic. The right semantic is: no valid transition zone reachable → significantly harder to switch floors.

**Stop building toward more complex veto rules.** The current veto logic is already at the limit of debuggability: fingerprint hold, hold ceiling, expired hold, fingerprint confidence, floor score ratio, transition support, transition veto, coupled conditions. Adding more rules to this structure will not fix the architecture and will add more edge cases.

---

### 7. Safest Path Forward

Before any more code changes, you need to understand exactly why the veto failed in the specific failure traces. The log at 23:31:20 shows `fp_conf=0.619` for ground_floor, but the floor switched 13 seconds later. Right now, you do not know what the decision state looked like at the exact switch moment, which was a different update cycle.

Here is the specific experiment to run immediately, with zero behavior change:

**Add one log line at the exact moment of every floor switch**, emitting:
- `fingerprint_supports_current_floor` (True/False)
- `fingerprint_hold_active` (True/False)
- `challenger_fingerprint_hold_expired` (True/False)
- `challenger_effective_dwell_s`
- `effective_required_dwell_s`
- `fp_conf` at this cycle
- `current_floor_fp_ratio` (the raw value, not the threshold check)
- `transition_switch_veto_active` precondition values individually

This will tell you definitively which path executed and why. My hypothesis: the fingerprint hold exhausted its ceiling (`challenger_fingerprint_hold_expired = True`), at which point the timer resumed, and at the exact switch cycle either `fp_conf` had dipped slightly or the ratio condition was marginally unfavorable, so `fingerprint_supports_current_floor` was False, and neither veto fired.

If that hypothesis is correct, the root cause is not that the threshold is wrong. It is that the veto is evaluated at one point in time, the system is sensitive to the exact RF conditions at that single cycle, and the hold ceiling creates a timing window where the most critical check runs only once under potentially unfavorable conditions.

**The safest next architectural step** after confirming the hypothesis:

Make the transition topology constraint independent of the fingerprint. Specifically: if transition zones are configured for the current layout, and the computed reachability budget (position uncertainty + velocity × elapsed time) is insufficient to have reached any valid transition zone for the challenger floor, block the floor change. Do not require fingerprint agreement as a prerequisite. Log this as `transition_reachability_veto_active`. Measure whether this alone stops the specific failure pattern.

If you think a full experiment or replay framework is needed before more changes: yes, the switch-time decision logging above is a minimal replay framework. Do that first. Do not write more veto logic until you have a log that shows you the exact decision state at the moment of every incorrect switch.

---

### 8. Concrete Recommendation

**Design direction**: Move from a veto-on-RSSI-decision architecture to a topology-gate-before-RSSI-decision architecture. Physical reachability through configured transition zones is a first-class constraint, not an evidence modifier. Fingerprint evidence is the primary floor selector, not a veto on RSSI evidence.

This does not require a rewrite. The existing floor challenger state machine is still the right structure. The change is in where topology enters it: before the timer runs out, not after.

**Next 3 implementation steps, in order:**

**Step 1: Add switch-time decision logging.**
At every floor switch (line 2917, `state.floor_id = best_floor_id`), emit a single structured log line capturing: `fingerprint_supports_current_floor`, `fingerprint_hold_active`, `challenger_fingerprint_hold_expired`, `challenger_effective_dwell_s`, `effective_required_dwell_s`, `fp_conf`, `transition_support_01`, and the full precondition values of the transition_switch_veto check individually. This is diagnostic-only, zero behavior change. Run it until you capture the next `Guest Room -> Garage front` failure. Analyze the log to confirm or refute the hold-expiry hypothesis.

**Step 2: Decouple the transition topology constraint from the fingerprint condition.**
Specifically, remove the `fingerprint_has_floor_signal` and `current_floor_fp_score >= challenger_floor_fp_score` requirements from the `transition_switch_veto_active` path. The condition should be: transition zones are configured for the current layout, transition_support_01 is below threshold, and the challenger floor is one that transition zones should connect. That is a topological claim and does not need fingerprint agreement. Gate this behind a feature flag. Run it and observe whether the failure pattern stops without introducing new stuck-floor failures.

**Step 3: Add reachability budget check as a pre-gate on challenger formation.**
Using the current position estimate, the velocity history, and the transition zone x/y/z coordinates, compute the minimum Euclidean distance from the current estimate to the nearest valid transition zone for any potential challenger floor. Compare this to `velocity_estimate × floor_dwell_seconds + position_uncertainty_m`. If the transition zone is unreachable given the device's recent motion, set the challenger's initial effective dwell requirement significantly higher (or block it from accumulating at all during the reachability-impossible window). This implements the core of topology-constrained state estimation without requiring path planning. For a stationary device far from any stairwell, this makes a cross-floor challenge geometrically implausible from the first update cycle.

These three steps can be implemented sequentially, each validated against the failure traces before the next step begins. No step requires touching the geometry solver, the fingerprint model, or the room classifier. The scope is contained to the floor challenger state machine.

**One thing to be direct about**: the current document corpus is excellent and the problem is well understood. The issue is not analytical clarity. The issue is that the implementation has consistently chosen to add complexity to the reactive side (better vetoes) rather than to the proactive side (topology gates before the decision). The next implementation cycle should prioritize the proactive side. If the topology gate in Step 2 and Step 3 solves the failure cases, you may find that much of the veto machinery becomes unnecessary and can be simplified.
