Review of Proposed Considerations and Device Filtering Strategy

This document evaluates the earlier comment block regarding computational complexity, tuning requirements, and use of existing max-velocity logic. It also clarifies why many Bluetooth devices appear in the selection UI and proposes a cleaner filtering approach.

⸻

1. Evaluation of the Considerations

1.1 Computational Complexity

The concern about computational load is reasonable in a large installation, but the impact is minor for typical setups with a small number of real devices. Key points:
	•	The logic remains proportional to devices × scanners, similar to existing Bermuda behavior.
	•	Added work consists of small buffers and lightweight arithmetic operations.
	•	No heavy external dependencies should be introduced.

Recommended practices:
	•	Keep buffer sizes small (5–10 samples).
	•	Compute movement state intermittently rather than every update.
	•	Avoid heavy libraries; basic Python math is sufficient.

1.2 Parameter Tuning

Additional filtering and motion logic introduces new parameters:
	•	EMA smoothing factor
	•	Velocity thresholds
	•	Dwell times
	•	Distance margin for room switching
	•	Outlier thresholds

Advice:
	•	Provide sensible defaults.
	•	Expose them in the UI under an “Advanced” section.
	•	Keep optional tuning hidden for most users to preserve simplicity.

1.3 Max Velocity Logic Already Present

The Bermuda codebase already includes a max_velocity constraint. This can serve as a foundation for:
	•	Deriving a movement state (MOVING vs STATIONARY).
	•	Enforcing physical limits on distance changes.

Integrating the new movement detection with existing velocity checks improves consistency and minimizes redundant logic.

⸻

2. Why So Many Bluetooth Devices Appear

Home Assistant’s Bluetooth system receives advertisements from every BLE device in range. Bermuda cannot change this behavior. As a result:
	•	The device selection UI displays all detected BLE MACs.
	•	Only devices explicitly configured in Bermuda receive full processing and entity creation.

This can be confusing when only a small number of devices are relevant.

⸻

3. Improving Device Filtering

A focused strategy can make the UI and processing pipeline more manageable.

3.1 UI-Level Filtering

Add optional filters to the device selection interface:
	•	Hide untracked devices
	•	Hide unknown vendors
	•	Show only existing Bermuda entities
	•	Show only devices with private/randomized MACs

This keeps the selection process concise and avoids noise.

3.2 Internal Whitelisting

Internally maintain a whitelist of tracked devices:
	•	Only devices on the whitelist receive buffering, filtering, and movement analysis.
	•	Unknown devices can be ignored or handled with minimal processing.

Benefits:
	•	Reduced processing load
	•	Cleaner logs
	•	More predictable behavior

⸻

4. Summary

The earlier comments are directionally correct but can be improved with clearer framing, reduced emphasis on heavy computation, and removal of unnecessary library suggestions. Device filtering remains an important UX and performance improvement and can be addressed cleanly through UI filtering and internal whitelisting.
