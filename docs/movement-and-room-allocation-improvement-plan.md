Device Movement and Room Allocation Improvement Plan

This document describes a proposed set of enhancements for improving BLE-based indoor positioning accuracy in Bermuda (and similar ESPresense-like systems). The focus is on three layers: RSSI filtering, distance stabilization, and improved room attribution using explicit motion detection and hysteresis.

## Implementation Status

✅ **Phase 1 Complete**: RSSI Median + EMA filtering implemented (Section 2.1)
- Implemented in `bermuda_advert.py` with configurable parameters
- Default: 5-sample median window with 0.3 EMA alpha
- Filtering applied before distance calculation
- Configuration parameters: `rssi_median_window` and `rssi_ema_alpha`

🔲 **Pending**: Outlier handling (Section 2.2)
🔲 **Pending**: Distance estimation improvements (Section 3)
🔲 **Pending**: Movement detection (Section 4)
🔲 **Pending**: Room attribution improvements (Section 5)

⸻

1. Overview

BLE RSSI is noisy, highly variable, and environment-dependent. Improving location accuracy requires addressing this at multiple points in the processing pipeline:
	1.	Clean raw RSSI samples per device and per scanner.
	2.	Produce a stable distance estimate that respects physical constraints.
	3.	Determine movement state, allowing room changes only when a device is actually moving.
	4.	Allocate rooms using hysteresis, dwell times, and confidence scoring.

This layered approach yields significantly more stable room attribution without sacrificing responsiveness.

⸻

2. RSSI Filtering Enhancements

2.1 Sliding Median + EMA ✅ IMPLEMENTED

Maintain a small time-based buffer of recent RSSI samples per device and scanner. Compute:
	•	Median of the buffer to remove spikes.
	•	Exponential moving average (EMA) over the median to smooth remaining variation.

This reduces jitter before converting RSSI to distance.

**Implementation Details:**
- Located in `BermudaAdvert.update_advertisement()` method (bermuda_advert.py:248-263)
- Uses `statistics.median()` on the last N samples from `hist_rssi`
- EMA formula: `filtered = alpha × median + (1-alpha) × previous_filtered`
- New attribute: `BermudaAdvert.filtered_rssi` stores the filtered value
- Distance calculation in `_update_raw_distance()` now uses filtered RSSI
- Configuration:
  - `rssi_median_window`: Number of samples (default: 5)
  - `rssi_ema_alpha`: Smoothing factor 0.0-1.0 (default: 0.3)
- Graceful fallback to raw RSSI when insufficient samples available

2.2 Outlier Handling

Track mean and standard deviation of RSSI over a short history window. If an incoming RSSI deviates excessively from the historical range, drop or clamp it. This prevents erratic readings from distorting distance estimates.

⸻

3. Stable Distance Estimation

3.1 Log-Space Filtering

Apply smoothing in log-distance space (the natural domain of the RSSI model). Convert filtered values back to meters afterward.

3.2 Maximum Speed Constraint

Enforce a physical limit on how quickly distance can change. For each new estimate, clamp the change based on human walking speed and time delta between readings.

3.3 Adaptive Smoothing

Adjust filtering strength based on signal stability:
	•	High variance → stronger smoothing.
	•	Low variance → more responsive updates.

⸻

4. Movement Detection

Movement is inferred from trends in distance signals rather than device sensors. Compute approximate velocity over a sliding window:
	•	Use derivatives of per-scanner distances.
	•	Optionally choose the maximum per-scanner velocity as the global movement signal.

Classify the device as:
	•	STATIONARY if velocity remains below a threshold for a dwell period.
	•	MOVING if velocity exceeds a threshold for a dwell period.

Hysteresis ensures stability in the motion state.

⸻

5. Room Attribution Improvements

5.1 Hysteresis on Distance Differences

Do not switch rooms based solely on the smallest current distance. Require:
	•	Candidate room to be closer than the current room by a margin.
	•	Dominance maintained for a dwell time.

5.2 State Machine for Room Tracking

Maintain a per-device state machine:
	•	STABLE(room)
	•	CANDIDATE(room_new)
	•	UNKNOWN

Transitions depend on filtered distance and movement state.

5.3 Scoring Instead of Raw Minimum

Compute a soft score for each scanner using exponential decay based on distance. Smooth these scores over time and choose the highest persistent score.

This reduces oscillations near doorways or room boundaries.

5.4 Handling Signal Loss

If the device loses signal for a period, fall back to UNKNOWN. When a scanner regains a strong signal, reassign the device to its area.

⸻

6. Integration Strategy
	1.	Implement movement detection and state machine at the aggregation layer.
	2.	Keep per-scanner RSSI and distance filtering independent of room attribution.
	3.	Export motion state and final room attribution as part of the device entity.

This approach avoids modifying firmware on BLE scanners and centralizes logic in the Bermuda backend.

⸻

7. Summary

This plan introduces structured filtering, explicit movement detection, and more robust room attribution logic. These combined improvements can significantly reduce incorrect room switches, minimize jitter, and deliver smoother, more realistic indoor presence detection behavior.
