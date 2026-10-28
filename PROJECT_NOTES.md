# Project Notes: Geothermal Well Performance Analysis

Living document. Update as decisions are made.

## 1. Data source and licence
- **Dataset:** Utah FORGE Wells 16A(78)-32 and 16B(78)-32 Extended Circulation Test Data, Aug and Sep 2024
- **Repository:** Geothermal Data Repository, submission 1683, https://gdr.openei.org/submissions/1683
- **DOI:** 10.15121/2475065
- **Licence:** CC BY 4.0 (verified on the submission page). Attribution required.
- **Authors:** McLennan, England, Swearingen (EGI, University of Utah)
- **Download:** one zip, 15.86 MB, in `data/raw/` untouched.

## 2. The experiment in plain language
Cold water is pumped DOWN well 16A (the injector) at high pressure. It travels through a
fracture network in hot granite (an Enhanced Geothermal System, EGS) and comes back UP well 16B
(the producer), hot. At the surface it passes an atmospheric separator, where some flashes to steam,
and the rest flows to a sump. The test ran 8 Aug to 5 Sep 2024, steady at 10 bpm from 11 Aug.

Units: bpm = barrels per minute (1 bbl = 42 US gal, so 10 bpm = 420 gpm), gpm = gallons per minute,
psi = pounds per square inch, degF = degrees Fahrenheit.

## 3. Files in the zip
| File | Content |
|---|---|
| `...Data 08082024 to 09052024 (30 sec increment).xlsx` | RAW, UNCORRECTED, 81,239 rows x 11 columns, every 30 s, Mountain Time |
| `Field Calibration of Flow Meters.xlsx` | 8 points: Liberty pump truck rate vs 3 Pason flow meters |
| `Manual Temperature and Pressure Data.xlsx` | 75 manual gauge/temperature-gun readings vs Pason |
| `Extended Circulation Test Report-Final.docx` | Test narrative, correction method, reference result (~90% efficiency) |
| `Read Me.docx` | Column dictionary |

### Column dictionary (main file)
| # | Raw header | Our name | Meaning |
|---|---|---|---|
| A | Date & Time of Day | `time` | Mountain Time |
| B | 16B Wellhead Pressure | `p16B_psi` | Producer wellhead pressure (unreliable, see below) |
| C | 16B-DIS FLOW 1 | `q16B_1_gpm` | Producer flow, upstream of separator (SUSPECT meter) |
| D | 16B-DIS FLOW 2 | `q16B_2_gpm` | Redundant producer flow meter |
| E | 16B-DIS TEMP | `T16B_F` | Producer temperature (reads LOW, see below) |
| F | SEP DIS FLOW 1 | `sep1_gpm` | Separator outlet line 1 |
| G | SEP DIS FLOW 2 | `sep2_gpm` | Separator outlet line 2 |
| H | SEP FLOW TOTAL | `sep_total_gpm` | F + G (raw) |
| I | 16A Wellhead Pressure | `p16A_psi` | Injection pressure (transducer) |
| J | Liberty Pump Rate | `liberty_bpm` | Injection rate (the reference "truth") |
| K | Liberty Wellhead Pressure | `liberty_p_psi` | Injection pressure (Liberty) |

## 4. Findings from the first inspection
- Timestamps are clean: 30 s steps, no duplicates, one 70 s step.
- Sensors have many NaNs (flow 1 on 16B is present for only 56% of rows). Spikes exist
  (e.g. 16B pressure max 1,593 psi vs median 252). Shut-ins and start-up produce zeros.
- Raw separator flow reads HIGH. Fit against Liberty: `true = 0.907*raw - 9.3` (sep1), `0.898*raw - 5.9` (sep2).
- Raw producer temperature reads LOW. Manual minus Pason averages +11.3 degF.
- Manual pressure gauge reads ~55 psi lower than Pason producer pressure.
- Quick check on the steady window 15 Aug to 3 Sep: injection 421 gpm, corrected separator liquid
  299 gpm (71%), about 88% once the report's 19.6% steam fraction is added. Report says ~90%.
- Injection pressure drifted from ~2,906 to ~2,793 psi. Report says "starting to decline slightly".

## 5. Pipeline plan
| Notebook | Module | Goal | Output |
|---|---|---|---|
| 01_explore | `load.py` | Load all files, units, ranges, NaN map, plots of raw signals | none (figures) |
| 02_clean | `clean.py` | Parse and rename; flag test phases; remove spikes; fit and apply flow calibration; correct temperature; interpolate short gaps only | `data/processed/*.csv` |
| 03_performance | `analysis.py` | Injection rate and pressure, injectivity, liquid recovery, mass-flow efficiency | figures, summary table |
| 04_power_decline | `analysis.py` | Thermal power = mass flow x heat capacity x (T_prod - T_inj); trend over time; pressure decline rate | figures, key results |

## 6. Assumptions (must be stated in the README)
1. Liberty rate is the reference for flow (calibrated frac pumps).
2. Calibration by linear regression through the 8 points (matches the report's regressed equations).
3. Producer temperature corrected using the manual-vs-Pason offset (report: gun reads 8 to 10 degF higher).
4. Steam fraction taken from the report (19.6%, boiling point 202.2 degF at 5,415 ft). Not independently derived.
5. Injection water temperature is NOT in the dataset. Needs an assumed value (ambient pit water, ~60 to 80 degF), with sensitivity shown.
6. Water density and heat capacity from standard tables, stated at the temperatures used.

## 7. Open questions
- Which exact days count as "steady state" (candidate: 15 Aug to 3 Sep).
- Whether to fit the temperature offset as a constant or as a function of temperature.
- Whether to commit raw data to GitHub (15.9 MB, allowed under CC BY 4.0) or ship a download script.

## 8. Validation target
Reproduce the report's Fig. 28: efficiency ~90%, injection ~26.5 kg/s, production ~20 to 23 kg/s, produced temperature ~355 to 370 degF.

## 9. Progress log
### 01_explore: done
Loaded all files, mapped missing data, plotted raw signals, confirmed meter and thermometer biases.

### 02_clean: done
Decisions made (these go in the README method section):
- **Phases** labelled from the report's schedule; steady 10 bpm phase = 11 Aug 06:00 to 4 Sep 06:00.
- **Spikes:** Hampel filter (7-sample window) plus loose physical limits. About 90 points removed in total.
  Lesson: a first 600 psi limit on 16B pressure wrongly removed 3,492 REAL shut-in readings (1,400 to 1,600 psi, wind-down phase). Limit widened to 2,000 psi.
- **Flow calibration:** linear regression (scipy) of Liberty rate on each separator meter, WITH intercept.
  sep1: 0.907*x - 9.31 (R2 0.9987); sep2: 0.898*x - 5.90 (R2 0.9992). Applied to separator meters only.
  The producer-discharge meters (`q16B_*`) are NOT used: the report calls one impaired, and the calibration file does not say which column it belongs to.
- **Temperature:** +11.3 degF (std 4.6, n=72), applied only while fluid is hot (>200 degF).
- **Pressure:** `p16B_psi` left uncorrected (gauge reads ~55 psi lower, but transducer is erratic and gauge readings are few). Indicative only.
  16A transducer reads ~38 psi lower than Liberty's sensor; 16A used, Liberty as fallback.
- **Gaps:** linear interpolation up to 10 samples (5 min) only.
- **`valid_steady` flag:** steady phase AND 5-min median rate >= 9.5 bpm for the previous 2 h (missing rate accepted if injection pressure > 2,500 psi). 65,856 rows (22.9 days, 81% of test).
  Bug caught: a first version excluded 2 h after any single reading <9.5 bpm; single noisy readings (~9.1 bpm) made thin stripes in the overview plot.
- **Validation:** corrected liquid recovery 70% (294.6 / 421.1 gpm; raw would be 81%); ~87% with the report's 19.6% steam. Report: ~90%.
- **Trend to explain in 03:** corrected return flow rises from ~275 gpm (mid-Aug) to ~325 gpm (Sep) at constant injection.
- Outputs: `data/processed/forge_clean_30s.csv`, `forge_clean_1h.csv`, `correction_constants.csv`.

### Still open for 03_performance
- Convert to MASS flow to compare with the report properly (needs water density at the measured temperatures).
- Test sensitivity of recovery to the calibration choice (with vs without intercept).
