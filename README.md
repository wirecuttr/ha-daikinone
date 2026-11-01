# Daikin One for Home Assistant

![GitHub release (latest by date)](https://img.shields.io/github/v/release/wirecuttr/ha-daikinone?style=flat-square) [![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

An enhanced custom integration for Home Assistant providing complete control, 7-day cloud scheduling, dual-fuel management, and deep diagnostic telemetry for Daikin One+, One Touch, and One Lite smart HVAC systems.

Communicating directly with the Daikin Skyport cloud API, this integration models the full HVAC equipment hierarchy—including communicating inverter heat pumps, variable-speed gas furnaces, ductless multi-split systems, and indoor air quality sensors—exposing granular hardware telemetry, native Home Assistant HVAC actions, and maintenance alerts.

- [Daikin One for Home Assistant](#daikin-one-for-home-assistant)
  - [Supported Equipment](#supported-equipment)
    - [Thermostats](#thermostats)
    - [Air Handlers & Indoor Units](#air-handlers--indoor-units)
    - [Heat Pumps & Outdoor Units](#heat-pumps--outdoor-units)
    - [Air Conditioners](#air-conditioners)
    - [Furnaces](#furnaces)
    - [Coils & System Accessories](#coils--system-accessories)
  - [Entity Platforms](#entity-platforms)
    - [Climate](#climate)
    - [Telemetry & Diagnostic Sensors](#telemetry--diagnostic-sensors)
    - [Configuration Controls](#configuration-controls)
    - [Maintenance & Diagnostic Alerts](#maintenance--diagnostic-alerts)
  - [7-Day Cloud Scheduling](#7-day-cloud-scheduling)
    - [Companion Lovelace Card](#companion-lovelace-card)
    - [Custom Services](#custom-services)
  - [Installation](#installation)
    - [Install via HACS (Recommended)](#install-via-hacs-recommended)
    - [Manual Install](#manual-install)

---

## Supported Equipment

The integration supports unitary communicating systems, ductless multi-splits (P1/P2 bus), and conventional 24V equipment across Daikin, Amana, and Goodman lines.

If you have a Daikin One system (or compatible communicating Amana/Goodman system) and your equipment is not listed below, please open an issue with your diagnostic data (retrieved by clicking **Download Diagnostics** on the thermostat device page in Home Assistant).

### Thermostats
* [Daikin One+ Smart Thermostat](https://daikincomfort.com/products/thermostats-controls/daikin-one-plus) (`DTST-CW-A-A` / `ONEPLUS`)
* [Daikin One Touch Smart Thermostat](https://daikincomfort.com/products/thermostats-controls/daikin-one-touch) (`DTST-TOU-A-A`)
* [Daikin One Lite Smart Thermostat](https://daikincomfort.com/products/thermostats-controls/daikin-one-lite) (`ONELITE_24V` / `D2271`)
* Amana Smart Thermostat (`ATST-CWE-BL-A`)

### Air Handlers & Indoor Units
* [MBVC Modular Blower](https://daikincomfort.com/products/heating-cooling/whole-house/air-handlers-coils/mbvc-modular)
* [DFVE Variable-Speed Air Handler](https://daikincomfort.com/products/heating-cooling/whole-house/air-handlers-coils/dfve) (e.g. `DFVE60DP1300A`)
* [FDMQ Concealed Slim-Duct Units](https://daikincomfort.com/products/heating-cooling/single-zone-ductless/multi-zone/fdmq-indoor-unit) (e.g. `FDMQ12WVJU9`, `FDMQ18RVJU`, `FDMQ24WVJU9`)
* FTWR Series Ductless Mini-Split Indoor Units
* FTQ Series SkyAir Multi-Position Air Handlers (e.g. `FTQ24TAVJUA`, `FTQ42TAVJUA`)

### Heat Pumps & Outdoor Units
* [DZ9VC](https://daikincomfort.com/products/heating-cooling/whole-house/heat-pump/dz9vc)
* [DZ6VS](https://daikincomfort.com/products/heating-cooling/whole-house/heat-pump/daikin-fit-heat-pump-dz6vs)
* [DZ17VSA](https://daikincomfort.com/products/heating-cooling/whole-house/heat-pump/daikin-fit-heat-pump)
* [DH7VS / DH7VSA](https://daikincomfort.com/products/heating-cooling/whole-house/heat-pump/daikin-fit-heat-pump) (e.g. `DH7VSA4810`, `DH7VSA6010A`)
* 4MXL Multi-Zone Outdoor Inverter Heat Pump (e.g. `4MXL36TVJU`)
* RZQ SkyAir Outdoor Inverter Heat Pumps (e.g. `RZQ24TAVJUA`, `RZQ42TAVJUA`)
* Amana ASZS6 Series Variable-Speed Inverter Heat Pump (e.g. `ASZS603610`)
* Goodman GSXC16 Series Communicating Inverter Heat Pump / AC (e.g. `GSXC160481CC`)

### Air Conditioners
* [DX6VS](https://daikincomfort.com/products/heating-cooling/whole-house/air-conditioner/daikin-fit-dx6vs)
* [DX17VS / DX17VSS](https://daikincomfort.com/products/heating-cooling/whole-house/air-conditioner/daikin-fit-dx17vs) (e.g. `DX17VSS241BA`, `DX17VSS601AA`)

### Furnaces
* [DM97MC Modulating Gas Furnace](https://daikincomfort.com/products/heating-cooling/whole-house/gas-furnaces/dm97mc)
* [DM80VC Variable-Speed Gas Furnace](https://daikincomfort.com/products/heating-cooling/whole-house/gas-furnaces/dm80vc)
* [DR96TC Two-Stage Variable-Speed Gas Furnace](https://daikincomfort.com/products/heating-cooling/whole-house/gas-furnaces/dr96tc) (e.g. `DR96TC0804CNAB`, `DR96TC1005CNAA`)
* Amana AMVM97 Modulating Gas Furnace (e.g. `AMVM970803BNBD`)
* Goodman GMVM97 Modulating Gas Furnace

### Coils & System Accessories
* Communicating Electronic Expansion Valve (EEV) Coils (e.g. `CAPEA`, `CHPE`, `2301AC01-05`)
* Daikin One Home Air Monitor (Haven Indoor Air Quality Monitor)
* EWC Controls UT-3000 Communicating Zone Control Board

---

## Entity Platforms

When configured, the integration creates device entries for each thermostat along with modeled child devices for connected indoor units and outdoor condensers.

### Climate
* **HVAC Modes:** `heat`, `cool`, `heat_cool` (Auto), `emergency_heat`, and `off`.
* **Native HVAC Actions:** Reports true operating states directly to Home Assistant: `heating`, `cooling`, `idle`, `fan`, `defrosting`, and `preheating`.
* **Humidity Control:** Direct target humidity slider (25% to 65%) exposed via `climate.set_humidity` whenever humidification or dehumidification hardware is detected.
* **Preset Modes:** Supports `none`, `away`, and `eco`.
* **Optimistic Transport Updates:** Writes apply immediately in the UI without rubber-banding while awaiting the cloud polling cycle.

### Telemetry & Diagnostic Sensors
* **Heat Source Telemetry (`sensor.*_heat_source`):** Enum sensor indicating whether delivered heat is provided by the heat pump (`heat_pump`), gas auxiliary heat (`aux_heat`), emergency strip heat (`emergency_heat`), or idle (`none`).
* **Schedule Hold Status (`sensor.*_schedule_status`):** Tracks current schedule state: `using_schedule`, `temporary_hold`, `permanent_hold`, or `away`.
* **Unitary System Telemetry:** Indoor blower airflow (CFM), demand percentages, compressor inverter frequency, fan RPM, and supply/return air temperatures.
* **Ductless Multi-Split Telemetry (P1/P2):** Suction and discharge temperatures, liquid and gas pipe temperatures, heat exchanger temperatures, and EEV pulse counts.
* **Consumables:** Remaining life percentage sensors for media air filters, UV bulbs, and HEPA filtration units.
* **Indoor Air Quality:** AQI, PM2.5, and VOC measurements when paired with Daikin or Haven IAQ sensors.

### Configuration Controls
* **Dual-Fuel Balance Point (`number.*_dual_fuel_balance_point`):** Adjusts the outdoor temperature lockout threshold below which the heat pump ceases operation and the gas furnace provides heating.
* **Hardware Calibration Offsets (`number.*_temperature_offset`, `number.*_humidity_offset`):** Calibrates indoor display temperature ($\pm 10^\circ\text{F}$ / $\pm 5.5^\circ\text{C}$) and humidity ($\pm 15\%$) directly in the hardware registers.
* **Outdoor Unit Quiet Mode (`switch.*_quiet_mode`):** Sets the outdoor inverter sound level restriction mode.
* **Thermostat Night Mode:** Dedicated configuration toggle (`switch.*_night_mode`) and schedule start/stop time selectors (`time.*_night_mode_start_time`, `time.*_night_mode_stop_time`).

### Maintenance & Diagnostic Alerts
* **Consumable Alerts (`binary_sensor.*`):** Replace filter, replace UV bulb, and replace HEPA filter binary warnings based on hardware maintenance thresholds.
* **Fault Codes:** Diagnostic error code tracking for equipment troubleshooting.
* **Cloud Connectivity:** Real-time online/offline connection state tracking for Daikin cloud communication.

---

<!-- markdownlint-disable-next-line no-inline-html -->
<img src="docs/dashboard.png" width="350" alt="dashboard example">

Dashboard source can be found [here](docs/dashboard.yaml) if you'd like you use it as a starting point for your own dashboard.

---

## 7-Day Cloud Scheduling

The integration provides complete bidirectional management of the 7-day schedule stored in the Daikin cloud (up to 6 individual periods per day, Monday through Sunday).

### Companion Lovelace Card

For interactive schedule editing from your Lovelace dashboards, install the companion card via HACS:

👉 **[`wirecuttr/daikin-schedule-card`](https://github.com/wirecuttr/daikin-schedule-card)**

* Interactive 7-day timeline editor for all 6 daily periods.
* Single-click day copying across weekdays and weekends with bulk apply.
* Directly synchronized with the Daikin cloud via `daikinone.set_schedule`.

### Custom Services

#### `daikinone.get_schedule`
Retrieves the complete 7-day schedule matrix and active schedule status for use in automations or dashboard scripts via service response data.

```yaml
service: daikinone.get_schedule
target:
  entity_id: climate.mainfloor_thermostat
response_variable: schedule
```

#### `daikinone.set_schedule`
Updates one or more days of the schedule matrix in a single atomic transaction.

```yaml
service: daikinone.set_schedule
target:
  entity_id: climate.mainfloor_thermostat
data:
  schedule_enabled: true
  temperature_unit: "°C"
  days:
    mon:
      - part: 1
        enabled: true
        start_time: "06:30"
        heat_target: 20.0
        cool_target: 24.0
        label: "wake"
      - part: 2
        enabled: true
        start_time: "22:00"
        heat_target: 18.0
        cool_target: 23.0
        label: "sleep"
```

To copy complete 7-day schedules across thermostats, see the [Thermostat Schedule Copy Script](docs/copy_schedule_script.md).

---

## Installation

### Install via HACS (Recommended)

_HACS must be [installed](https://hacs.xyz/docs/installation/prerequisites) before following these steps._

1. Log into Home Assistant and open **HACS** from the sidebar.
2. In the HACS console, select **Integrations**.
3. Select the three dots icon in the top-right corner, and select **Custom repositories**.
4. Paste `https://github.com/wirecuttr/ha-daikinone` into the **Repository** box and select **Integration** in the **Category** menu.
5. Select **Add**.
6. Restart Home Assistant.
7. Click the button below to add the integration and begin setup:

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=daikinone)

### Manual Install

_A manual installation is higher maintenance than installation via HACS._

1. Download or clone this repository.
2. Copy the `custom_components/daikinone` folder to your Home Assistant `/config/custom_components/` directory.
3. Restart Home Assistant.
4. Click the button above or navigate to **Settings** $\rightarrow$ **Devices & Services** $\rightarrow$ **Add Integration** and search for **Daikin One**.
