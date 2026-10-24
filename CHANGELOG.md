# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Calendar Versioning](https://calver.org/) (`YYYY.MM.PATCH`).

---

## [2026.10.0] - 2026-10-24

### Overview
This release establishes the modern communicating heat pump, dual-fuel, and diagnostic platform for the Daikin One+ integration in Home Assistant.

* **Upstream Baseline:** Forked from [`zlangbert/ha-daikinone:v0.10.1`](https://github.com/zlangbert/ha-daikinone/releases/tag/v0.10.1) (commit `f4ea9a6`).
* **Test Suite:** Expanded from upstream's 29 tests to **297 automated tests** covering all client protocols, model serialization, device mappers, and entity platforms.
* **Community & Architectural Attribution:** Incorporates API register research and feature inspiration from `@apetrycki`'s pioneering work in [`daikinskyport`](https://github.com/apetrycki/daikinskyport) (which originally identified registers for OneClean, Night Mode, and Aux Heat), reimplemented here using modern strongly-typed Home Assistant entity platforms. Special recognition also goes to `@chrisjohnson00` (auth resilience), `@onnastick` (away mode wire mapping), and `@ManuelMcLure` (unsupported device handling). Co-developed and hardware-tested with Google DeepMind Antigravity.

---

### Breaking Changes

* **Emergency Heat Preset Mode Removed in Favor of Dedicated Switch:**  
  The legacy "Emergency heat" preset mode was removed from `climate.<thermostat>` `preset_modes` in favor of the dedicated `switch.<thermostat>_emergency_heat` entity. This aligns with Home Assistant Core architecture standards (RFC #932) and resolves sub-zero concurrency and race conditions when toggling aux heat.
  - **Action Required:** Users with existing automations calling `climate.set_preset_mode` with preset `"Emergency heat"` or `"emergency_heat"` must update them to call `switch.turn_on` on `switch.<thermostat>_emergency_heat` (and `switch.turn_off` to disengage).

---

### Features & Enhancements

#### 1. Dual-Fuel Balance Point & Heating Priority
* **Balance Point Setpoint (`number.<thermostat>_dual_fuel_balance_point`):** Added a native number entity controlling `auxHeatLockoutTemp` with box input mode (`NumberMode.BOX`), trailing debounced writes (0.8s), dynamic bounds expansion, 0.5°C steps, and optimistic UI updates.
  - *Upstream PR:* [zlangbert/ha-daikinone#140](https://github.com/zlangbert/ha-daikinone/pull/140) (Submitted & Open)
* **Dual-Fuel Priority Preference (`select.<thermostat>_dual_fuel_priority`):** Added select entity allowing switching between `Comfort` and `Efficiency` heating priorities (`dualFuelPreference`).
  - *Upstream PR:* [zlangbert/ha-daikinone#138](https://github.com/zlangbert/ha-daikinone/pull/138) (Submitted & Open)

#### 2. Fan Circulation Scheduling & Night Mode
* **Fan Circulation Schedule:** Added native time entities (`time.<thermostat>_fan_circulation_start_time`, `time.<thermostat>_fan_circulation_end_time`) and select entity (`select.<thermostat>_fan_circulation_duty_cycle`) to configure quiet fan circulation schedules and duty cycles without cloud app dependence.
* **Thermostat Night Mode:** Added `switch.<thermostat>_night_mode` and schedule interval controls (`time.<thermostat>_night_mode_start_time`, `time.<thermostat>_night_mode_end_time`) to dim display backlights and enforce silent night operation.
  - *Upstream PR:* [zlangbert/ha-daikinone#141](https://github.com/zlangbert/ha-daikinone/pull/141) (Submitted & Open)

#### 3. Diagnostic Faults & Error History Tracking
* **Equipment & System Error Sensors:** Exposes `sensor.<thermostat>_last_equipment_error` (`fault1`–`fault25`) and `sensor.<thermostat>_last_system_error` (`sysFault1`–`sysFault20`) using `SensorDeviceClass.TIMESTAMP`.
* **Empirical Diagnostic Mapping:** Validates 2-character uppercase hex codes (`latest_code`), criticality severity levels, equipment IDs, and filters out pre-NTP boot records (`Date == 22`). Exposes the top 3 newest errors in `recent_errors` attributes alongside physical thermostat navigation action prompts.
  - *Upstream PR:* [zlangbert/ha-daikinone#143](https://github.com/zlangbert/ha-daikinone/pull/143) (Submitted & Open)

#### 4. HVAC Consumables & Maintenance Alerts
* **Consumable Life Sensors:** Added remaining life percentage sensors (`sensor.<thermostat>_media_air_filter_life`, `sensor.<thermostat>_service_inspection_life`) with detailed usage attributes (`days_remaining`, `runtime_hours_used`).
* **Diagnostic Problem Sensors:** Added `binary_sensor.<thermostat>_media_air_filter_replacement` and `binary_sensor.<thermostat>_service_inspection_due` (`device_class: problem`).
* **Two-Tier Hardware Guards:** Hardware inventory checks (`NumMediafilters`, `NumUVBulbs`, etc.) and configured threshold checks (`alert*Limit > 0`) guarantee 0 ghost entities on unsupported units.
  - *Upstream PR:* [zlangbert/ha-daikinone#142](https://github.com/zlangbert/ha-daikinone/pull/142) (Submitted & Open)

#### 5. Emergency Heat Switch & Native Away Mode Preset
* **Emergency Heat Decoupling:** Implemented dedicated `switch.<thermostat>_emergency_heat` (`DaikinThermostatMode.AUX_HEAT`), aligning with modern Home Assistant core architecture (RFC #932) and eliminating preset conflicts in sub-zero winter climates.
* **Native Away Preset:** Configured `preset_mode: away` on `climate.<thermostat>` using `geofencingAway`.
* **AC-Only Guard:** Gated with `modeEmHeatAvailable` to prevent phantom entities on cooling-only hardware (resolves upstream Issue #25).
  - *Related Discussions:* [Issue #123 Comment](https://github.com/zlangbert/ha-daikinone/issues/123#issuecomment-6324305522), [PR #131 Review](https://github.com/zlangbert/ha-daikinone/pull/131#issuecomment-6324426484)
  - *Branch:* [`feature/emergency-heat-switch-and-away-preset`](https://github.com/wirecuttr/ha-daikinone/tree/feature/emergency-heat-switch-and-away-preset)

#### 6. OneClean Air Scrub Switch
* Added `switch.<thermostat>_one_clean_fan` allowing 3-hour high-speed air purification cycles.
  - *Upstream Reference:* Adopted and refined from [zlangbert/ha-daikinone#124](https://github.com/zlangbert/ha-daikinone/pull/124).

#### 7. Schedule Control
* Added `button.<thermostat>_resume_schedule` to dismiss temporary hold overrides and `switch.<thermostat>_schedule` to toggle schedule execution.
  - *Upstream PR:* [zlangbert/ha-daikinone#137](https://github.com/zlangbert/ha-daikinone/pull/137) (Submitted & Open)

#### 8. Native Thermostat & Equipment Availability Cascade
* **Availability Architecture (`_is_device_available` / `is_device_online`):** Entities across all platforms (`climate`, `sensor`, `binary_sensor`, `switch`, `select`, `number`, `time`, `button`) now dynamically track hardware reachability instead of remaining hardcoded to available. Subordinate equipment entities (furnaces, heat pumps, coils) automatically inherit parent thermostat online status.
* **Empty Offline Payload Trap Fixed:** Fixed coordinator bug where thermostats reporting offline with empty telemetry payloads (`online: false, data: {}`) during power outages or network interruptions were skipped, retaining stale cached data. Thermostats are now properly marked offline.
* **Diagnostic Connectivity Tracking:** Added and refined dynamic device reachability tracking and diagnostic connectivity (`binary_sensor.<thermostat>_connectivity` / `sensor.<thermostat>_online_status`), which remains available during outages to cleanly display `Offline` instead of transitioning to an ambiguous `Unavailable` state. Enabled state polling on `button.<thermostat>_resume_schedule` to track availability.
  - *Branch:* [`feature/thermostat-connectivity`](https://github.com/wirecuttr/ha-daikinone/tree/feature/thermostat-connectivity)

#### 9. Skyport Location Support & 3-Tier Device Hierarchy
* **Manifest Modernization (`integration_type: hub`):** Declared integration type as `hub` in `manifest.json`, standardizing Home Assistant settings under the `Hubs` header.
* **Property Location Hub Devices:** Supports Daikin Skyport property locations (`/locations`). Registers each property as a parent Location Hub device (`entry_type: DeviceEntryType.SERVICE`, `model: "Skyport Location"`). Thermostats declare `via_device` pointing to their parent Location Hub, and child equipment points to the thermostat, establishing a clean 3-tier device hierarchy (`Location Hub -> Thermostat -> HVAC Equipment`).
* **Dynamic Config Entry Title:** Automatically names config entries using the primary location name (e.g. `Home`), with in-place migration for existing installations.
* **Empty Location Filtering & Defensive Address Parsing:** Safely decodes inner-JSON address payloads with plain-text fallback, while filtering out unpopulated properties without active thermostats to prevent ghost hub devices.
  - *Upstream PR:* [zlangbert/ha-daikinone#144](https://github.com/zlangbert/ha-daikinone/pull/144) (Submitted & Open)
  - *Branch:* [`feature/location-device-hierarchy`](https://github.com/wirecuttr/ha-daikinone/tree/feature/location-device-hierarchy)

#### 11. EPA 6-Tier AQI Standard & Resilient Fallback
* **Standardized 6-Tier Scale:** Reconciled indoor air quality mapping with the official EPA AirNow 6-tier standard (0–5: Good, Moderate, Unhealthy for Sensitive Groups, Unhealthy, Very Unhealthy, Hazardous), eliminating truncated index errors.
* **Defensive Fallback & Localization:** Added `_missing_ = UNKNOWN` fallback for undefined air quality levels and complete string translations for all tiers.
  - *Upstream Reference:* Reconciles unmerged upstream PRs [zlangbert/ha-daikinone#126](https://github.com/zlangbert/ha-daikinone/pull/126) and [#127](https://github.com/zlangbert/ha-daikinone/pull/127).

#### 12. Multi-Equipment Sub-Device Registry Scoping
* **Furnace & Multi-Split Device Collision Fix:** Fixed long-standing upstream bug where multi-furnace or multi-split systems collided on device identifiers in Home Assistant's device registry. Scopes device identifiers with parent `thermostat_id`, allowing each indoor air handler, furnace, coil, and outdoor compressor to register as a separate linked device.
  - *Upstream PR:* [zlangbert/ha-daikinone#136](https://github.com/zlangbert/ha-daikinone/pull/136) (Submitted & Open; addresses upstream Issue #135).

#### 13. Auth Self-Healing & Transport Resiliency
* **Lock Ladder & Auto Token Re-Negotiation:** Implemented an `asyncio.Lock` ladder in `client/transport.py` to serialize authentication across concurrent entity polls and automatically re-negotiate expired tokens on HTTP 401/403 responses.
* **Transient Setup Retry:** Maps network timeouts and 5xx gateway errors to `ConfigEntryNotReady` for Home Assistant automatic backoff retries instead of failing permanently.
* **Config Flow Reauthentication:** Implemented native reauth flow (`async_step_reauth` / `async_step_reauth_confirm`) allowing users to update changed credentials in-place.
  - *Upstream Reference:* Adopted and hardened from unmerged upstream PR [zlangbert/ha-daikinone#129](https://github.com/zlangbert/ha-daikinone/pull/129) (addresses upstream Issue #128).

#### 14. Defensive Ingestion for Unsupported Devices
* **Schema Variation Hardening:** Traps schema variations (`KeyError`, `ValueError`, `TypeError`) when ingesting unusual or legacy Daikin hardware models without crashing integration setup.
* **Deduplicated Error Logging:** Tracks unsupported device IDs in `_unsupported_device_ids` to eliminate repetitive log flooding on every polling interval.
  - *Upstream Reference:* Hardened from unmerged upstream PR [zlangbert/ha-daikinone#133](https://github.com/zlangbert/ha-daikinone/pull/133), companion PR [ManuelMcLure/ha-daikinone#1](https://github.com/ManuelMcLure/ha-daikinone/pull/1).

---

### Architectural & Quality Improvements

* **Strict Sentence Case Standards:** All entity names, descriptions, translations, and UI labels adhere to Home Assistant sentence-case conventions.
* **Schema v0 & v1 Unique ID Migration:** Full non-breaking backward compatibility with upstream legacy unique IDs while standardizing on Schema v1 keys.
* **Comprehensive Automated Test Suite:** Expanded test suite from upstream's 29 tests to 297 automated unit and integration tests (100% passing) with strict static type checking (`ty check`) and linting (`ruff`).

---

### Installation via HACS

If you are switching from the upstream `zlangbert/ha-daikinone` repository:

1. In Home Assistant, open **HACS** $\rightarrow$ **Integrations**.
2. Click on the existing **Daikin One** repository card.
3. Click the three dots in the top right corner and select **Remove**.
4. **Ignore the warning** prompting you to delete the configured integration from Settings $\rightarrow$ Devices & Services first. (Your configured thermostats, entity IDs, automations, and historical statistics will remain completely safe in Home Assistant Core).
5. Confirm the removal on the next dialog.
6. In HACS, click the three dots in the top right corner $\rightarrow$ select **Custom repositories**.
7. Add your repository:
   - **Repository:** `https://github.com/wirecuttr/ha-daikinone`
   - **Category:** `Integration`
8. Click **Add**, search for **Daikin One**, and click **Download** (version `2026.10.0`).
9. Restart Home Assistant Core. All existing entities will automatically link to the new release alongside all new entities.

---

*Co-developed and hardware-tested with Google DeepMind Antigravity.*
