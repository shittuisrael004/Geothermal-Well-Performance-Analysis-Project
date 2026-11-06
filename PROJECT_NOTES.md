# Project notes

Plan, decisions and results log for the Utah FORGE extended circulation test analysis. The README summarises the results; this file records how and why.

## 1. Data

- Dataset: Utah FORGE Wells 16A(78)-32 and 16B(78)-32 Extended Circulation Test Data, August and September 2024. Geothermal Data Repository submission 1683, DOI 10.15121/2475065.
- Licence: CC BY 4.0 (checked on the submission page). Attribution required.
- Authors: McLennan, England, Swearingen (Energy & Geoscience Institute, University of Utah).
- One zip, 15.9 MB, unpacked into `data/raw/Extended Circulation Test/` and never edited.

| File | Content |
|---|---|
| `Extended Circulation Test Data 08082024 to 09052024 (30 sec increment).xlsx` | Raw, uncorrected series: 81,239 rows, 11 columns, 30 s sampling, Mountain Time |
| `Field Calibration of Flow Meters.xlsx` | 8 points: pump-truck (Liberty) rate against three flow meters |
| `Manual Temperature and Pressure Data.xlsx` | 75 manual temperature-gun and pressure-gauge readings next to the recorded values |
| `Extended Circulation Test Report-Final.docx` | Schedule, correction methods, reference results |
| `Read Me.docx` | Column dictionary |

Columns of the main file:

| Raw header | Name used | Meaning |
|---|---|---|
| Date & Time of Day | `time` | Mountain Time |
| 16B Wellhead Pressure | `p16B_psi` | Producer wellhead pressure |
| 16B-DIS FLOW 1, 2 | `q16B_1_gpm`, `q16B_2_gpm` | Producer flow before the separator (suspect meter, per the report) |
| 16B-DIS TEMP | `T16B_F` | Producer temperature (reads low) |
| SEP DIS FLOW 1, 2 | `sep1_gpm`, `sep2_gpm` | Separator outlet flow, two lines |
| SEP FLOW TOTAL | `sep_total_gpm` | Sum of the two lines |
| 16A Wellhead Pressure | `p16A_psi` | Injection pressure (transducer) |
| Liberty Pump Rate | `liberty_bpm` | Injection rate, the reference |
| Liberty Wellhead Pressure | `liberty_p_psi` | Injection pressure (Liberty) |

Units: bpm = barrels per minute (1 bbl = 42 US gal, so 10 bpm = 420 gpm); gpm = US gallons per minute; psi; °F.

## 2. Pipeline

| Notebook | Module | Output |
|---|---|---|
| 01_explore | `load.py` | Figures only |
| 02_clean | `clean.py` | `forge_clean_30s.csv` (not committed), `forge_clean_1h.csv`, `correction_constants.csv` |
| 03_performance | `analysis.py`, `plots.py` | `key_results.csv`, `performance_daily.csv` |
| 04_power_decline | `analysis.py`, `plots.py` | `power_key_results.csv`, `power_daily.csv`, `power_1h.csv` |

Notebooks must be run in this order. Unit tests for `src/` are in `tests/`.

## 3. Decisions and assumptions

### Cleaning (notebook 02)
1. **Phases** from the report's schedule: 2.5 bpm flow from 9 Aug 17:00, 5 bpm from 10 Aug 01:00, 7.5 bpm from 10 Aug 13:00, steady 10 bpm from 11 Aug 06:00 to 4 Sep 06:00 (end detected from the data), then wind-down.
2. **Spikes:** Hampel filter, 7-reading window, with a per-signal minimum deviation, plus loose physical limits. About 90 points removed in total. The limit on 16B pressure is 2,000 psi: an initial 600 psi limit would have removed 3,492 real shut-in readings (1,400 to 1,600 psi, wind-down phase).
3. **Flow calibration:** linear regression of the Liberty rate on each separator meter, with intercept. Meter 1: 0.9074 x - 9.31 (R² 0.9987). Meter 2: 0.8979 x - 5.90 (R² 0.9992). Negative results clipped to zero. Applied to the separator meters only. The producer-discharge meters are not used: the report calls the meter upstream of the separator suspect, and the calibration file does not say which column it belongs to.
4. **Temperature:** +11.26 °F (standard deviation 4.6, n = 72), applied only above 200 °F. The report quotes 8 to 10 °F on average.
5. **Pressure:** `p16B_psi` left as recorded (the manual gauge reads about 55 psi lower, but the transducer is described as erratic and gauge readings are few). The 16A transducer reads about 38 psi lower than Liberty's sensor; 16A is used, with Liberty as fallback.
6. **Gaps:** linear interpolation up to 10 readings (5 min).
7. **`valid_steady` flag:** steady phase and 5-minute median rate of at least 9.5 bpm for the previous 2 hours; a missing rate is accepted if the injection pressure exceeds 2,500 psi. 65,856 rows (22.9 days, 81% of the test). Judging the rate by a 5-minute median avoids excluding 2 hours after each single noisy reading near 9.1 bpm.

### Performance (notebook 03)
8. **Plateau:** working back from the end, days within 2% of the final efficiency. Result: 29 Aug to 4 Sep.
9. **Steam fraction:** energy balance with IAPWS-97 steam tables. Separator pressure from the site elevation (5,415 ft), giving a boiling point of 202.1 °F (report: 202.2 °F). Saturated-liquid enthalpy is used for the well fluid.
10. **Efficiency:** mass out divided by mass in, as defined in the report. Produced mass = separator liquid / (1 - steam fraction). Injected mass uses the density of water at the assumed 20 °C.
11. **Injectivity:** injection rate over wellhead pressure, in gpm per 100 psi. Trend only.

### Power (notebook 04)
12. **Thermal power** = produced mass flow x (h produced - h injected). Enthalpy of liquid water at the corrected producer temperature; injected water at 20 °C. Pressure effects on enthalpy ignored.
13. **Decline test:** straight line through the seven daily plateau values, with a 95% range from the t distribution.

## 4. Results

Plateau, 29 Aug to 4 Sep.

| Metric | Value | Range tested |
|---|---|---|
| Efficiency | 90.3% | 88.3 to 92.2% |
| Injected / produced mass flow | 26.5 / 23.9 kg/s | |
| Steam fraction | 18.3% | report: 19.6% |
| Volume recovery (liquid) | 76.6% | |
| Injection pressure | 2,825 psi | falls 11.1 psi/day after 21 Aug (-158 psi, -5.4%) |
| Injectivity | 14.9 gpm per 100 psi | |
| Producer temperature (corrected) | 375 °F | |
| Thermal power | 17.3 MWt | 16.3 to 18.4 MWt |
| Energy gained per kg | 727 kJ/kg | |
| Heat produced, steady rows | 8,187 MWh thermal | lower bound |

- Efficiency climbs from about 45% (11 Aug) to 90% (29 Aug). It reached about 89% on 23 Aug, fell to about 82% after the 24 Aug rate increase and the 26 Aug half-rate period, and recovered.
- Power grew from about 7 MWt (11 Aug) to 13.9 MWt (first day above 360 °F, 14 Aug) to 17.4 MWt on the plateau. 79% of the growth since 14 Aug is more water returning, 21% is hotter water.
- Plateau trends (daily values): power +0.035 MW/day, 95% range -0.028 to +0.099 (p = 0.21), i.e. between -1.1% and +4.0% per week; temperature -0.18 °F/day, range -0.55 to +0.20 (p = 0.28). No decline detected; a decline faster than about 1.1% per week is ruled out.
- The 24 to 27 Aug power dip (-6 to -8%) coincides with a 6 to 10% fall in mass flow while the temperature rose by up to 5 °F.
- Sensitivity of efficiency: calibration through the origin +1.9 points; steam fixed at 19.6% of total +1.5; steam of 19.6% added to the liquid -2.0; raw temperature -1.3; injection water 10 to 30 °C within 0.2. No steam at all would give 74%.
- Sensitivity of power: injection water 10 to 30 °C +5.8 / -5.8%; raw temperature -5.3%; calibration through the origin +2.1%; temperature offset ±4.6 °F -2.1 / +2.2%; steam definitions +1.7 / -2.2%.
- Checks: injected mass flow matches the report (26.5 kg/s) and efficiency matches its headline (about 90%) without tuning. Thermal power agrees with m x cp x dT within 1.2%. The separator-based and wellhead-based power methods agree exactly by construction, so that check covers the code, not the physics.

## 5. Limitations

See the README for the full list. The two with the largest effect: the injection water temperature is assumed (20 °C; about 6% of power per 10 °C), and the seven-day plateau cannot show long-term decline.

## 6. Open items

- A measured injection temperature (the report says one was recorded) would replace the 20 °C assumption. Re-run notebooks 03 and 04 with it.
- The calibration equations in the report's Figure 26 could replace the fitted lines if they can be read exactly.
