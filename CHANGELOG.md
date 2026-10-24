# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Calendar Versioning](https://calver.org/) (`YYYY.MM.PATCH`).

---

## [2026.10.0] - 2026-10-24

### Overview
This release establishes the modern communicating heat pump, dual-fuel, and diagnostic platform for the Daikin One+ integration in Home Assistant.

* **Upstream Baseline:** Forked from [`zlangbert/ha-daikinone:v0.10.1`](https://github.com/zlangbert/ha-daikinone/releases/tag/v0.10.1) (commit `f4ea9a6`).
* **Test Suite:** Expanded from upstream's 29 tests to **271 automated tests** covering all client protocols, model serialization, device mappers, and entity platforms.
* **Community & Architectural Attribution:** Incorporates API register research and feature inspiration from `@apetrycki`'s pioneering work in [`daikinskyport`](https://github.com/apetrycki/daikinskyport) (which originally identified registers for OneClean, Night Mode, and Aux Heat), reimplemented here using modern strongly-typed Home Assistant entity platforms. Special recognition also goes to `@chrisjohnson00` (auth resilience), `@onnastick` (away mode wire mapping), and `@ManuelMcLure` (unsupported device handling). Co-developed and hardware-tested with Google DeepMind Antigravity.

---

### Features & Enhancements

#### 1. Dual-Fuel Balance Point & Heating Priority
* **Balance Point Setpoint (`number.<thermostat>_dual_fuel_balance_point`):** Added a native number entity controlling `auxHeatLockoutTemp` with box input mode (`NumberMode.BOX`), trailing debounced writes (0.8s), dynamic bounds expansion, 0.5°C steps, and optimistic UI updates.
  - *Upstream PR:* [zlangbert/ha-daikinone#140](https://github.com/zlangbert/ha-daikinone/pull/140) (Submitted & Open)
* **Dual-Fuel Priority Preference (`select.<thermostat>_dual_fuel_priority`):** Added select entity allowing switching between `Comfort` and `Efficiency` heating priorities (`dualFuelPreference`).
  - *Upstream PR:* [zlangbert/ha-daikinone#138](https://github.com/zlangbert/ha-daikinone/pull/138) (Submitted & Open)

#### 2. Operating State & Live Fuel Source Detection
* **Operating State Sensor (`sensor.<thermostat>_operating_state`):** Exposes a 12-state operating sensor reporting the physical HVAC operating state (`idle`, `heating`, `cooling`, `aux_heating`, `circulating`, etc.).
* **Active Fuel Detection:** Attributes provide live telemetry on the active energy source (`Gas`, `Electric`, or `None`) by analyzing equipment staging and outdoor temperature relative to the balance point.
  - *Branch:* [`feature/operating-state-sensor`](https://github.com/wirecuttr/ha-daikinone/tree/feature/operating-state-sensor)

#### 3. Fan Circulation Scheduling & Night Mode
* **Fan Circulation Schedule:** Added native time entities (`time.<thermostat>_fan_circulation_start_time`, `time.<thermostat>_fan_circulation_end_time`) and select entity (`select.<thermostat>_fan_circulation_duty_cycle`) to configure quiet fan circulation schedules and duty cycles without cloud app dependence.
* **Thermostat Night Mode:** Added `switch.<thermostat>_night_mode` and schedule interval controls (`time.<thermostat>_night_mode_start_time`, `time.<thermostat>_night_mode_end_time`) to dim display backlights and enforce silent night operation.
  - *Upstream PR:* [zlangbert/ha-daikinone#141](https://github.com/zlangbert/ha-daikinone/pull/141) (Submitted & Open)

#### 4. Diagnostic Faults & Error History Tracking
* **Equipment & System Error Sensors:** Exposes `sensor.<thermostat>_last_equipment_error` (`fault1`–`fault25`) and `sensor.<thermostat>_last_system_error` (`sysFault1`–`sysFault20`) using `SensorDeviceClass.TIMESTAMP`.
* **Empirical Diagnostic Mapping:** Validates 2-character uppercase hex codes (`latest_code`), criticality severity levels, equipment IDs, and filters out pre-NTP boot records (`Date == 22`). Exposes the top 3 newest errors in `recent_errors` attributes alongside physical thermostat navigation action prompts.
  - *Upstream PR:* [zlangbert/ha-daikinone#143](https://github.com/zlangbert/ha-daikinone/pull/143) (Submitted & Open)

#### 5. HVAC Consumables & Maintenance Alerts
* **Consumable Life Sensors:** Added remaining life percentage sensors (`sensor.<thermostat>_media_air_filter_life`, `sensor.<thermostat>_service_inspection_life`) with detailed usage attributes (`days_remaining`, `runtime_hours_used`).
* **Diagnostic Problem Sensors:** Added `binary_sensor.<thermostat>_media_air_filter_replacement` and `binary_sensor.<thermostat>_service_inspection_due` (`device_class: problem`).
* **Two-Tier Hardware Guards:** Hardware inventory checks (`NumMediafilters`, `NumUVBulbs`, etc.) and configured threshold checks (`alert*Limit > 0`) guarantee 0 ghost entities on unsupported units.
  - *Upstream PR:* [zlangbert/ha-daikinone#142](https://github.com/zlangbert/ha-daikinone/pull/142) (Submitted & Open)

#### 6. Emergency Heat Switch & Native Away Mode Preset
* **Emergency Heat Decoupling:** Implemented dedicated `switch.<thermostat>_emergency_heat` (`DaikinThermostatMode.AUX_HEAT`), aligning with modern Home Assistant core architecture (RFC #932) and eliminating preset conflicts in sub-zero winter climates.
* **Native Away Preset:** Configured `preset_mode: away` on `climate.<thermostat>` using `geofencingAway`.
* **AC-Only Guard:** Gated with `modeEmHeatAvailable` to prevent phantom entities on cooling-only hardware (resolves upstream Issue #25).
  - *Related Discussions:* [Issue #123 Comment](https://github.com/zlangbert/ha-daikinone/issues/123#issuecomment-6324305522), [PR #131 Review](https://github.com/zlangbert/ha-daikinone/pull/131#issuecomment-6324426484)
  - *Branch:* [`feature/emergency-heat-switch-and-away-preset`](https://github.com/wirecuttr/ha-daikinone/tree/feature/emergency-heat-switch-and-away-preset)

#### 7. OneClean Air Scrub Switch
* Added `switch.<thermostat>_one_clean_fan` allowing 3-hour high-speed air purification cycles.
  - *Upstream Reference:* Adopted and refined from [zlangbert/ha-daikinone#124](https://github.com/zlangbert/ha-daikinone/pull/124).

#### 8. Schedule Control
* Added `button.<thermostat>_resume_schedule` to dismiss temporary hold overrides and `switch.<thermostat>_schedule` to toggle schedule execution.
  - *Upstream PR:* [zlangbert/ha-daikinone#137](https://github.com/zlangbert/ha-daikinone/pull/137) (Submitted & Open)

---

### Bug Fixes & Architectural Improvements

* **Multi-Equipment Device Collision Fix:** Fixed bug where multi-split or dual-furnace systems collided on device identifiers in Home Assistant's device registry. Indoor air handlers and outdoor compressors now properly appear as separate linked sub-devices.
  - *Upstream PR:* [zlangbert/ha-daikinone#136](https://github.com/zlangbert/ha-daikinone/pull/136) (Submitted & Open)
* **Auth Self-Healing & Transport Resiliency:** Implemented defensive `asyncio.Lock` ladder, automatic token re-negotiation on HTTP 401/403 expiry, and Home Assistant config entry reauthentication flow.
  - *Upstream Reference:* Refined and hardened from [zlangbert/ha-daikinone#129](https://github.com/zlangbert/ha-daikinone/pull/129)
* **Defensive Ingestion for Unsupported Devices:** Traps schema variations (`KeyError`, `ValueError`, `TypeError`) and logs deduplicated diagnostics without crashing setup.
  - *Upstream Reference:* [zlangbert/ha-daikinone#133](https://github.com/zlangbert/ha-daikinone/pull/133), companion PR [ManuelMcLure/ha-daikinone#1](https://github.com/ManuelMcLure/ha-daikinone/pull/1)
* **EPA 6-Tier AQI Standard:** Reconciled indoor air quality mapping with the EPA AirNow 6-tier standard (0–5), defensive `_missing_ = UNKNOWN` fallback, and official string translations.
  - *Upstream Reference:* Reconciles [zlangbert/ha-daikinone#126](https://github.com/zlangbert/ha-daikinone/pull/126) and [#127](https://github.com/zlangbert/ha-daikinone/pull/127)
* **Strict Sentence Case Standards:** All entity names, descriptions, translations, and UI labels adhere to Home Assistant sentence-case conventions.

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
