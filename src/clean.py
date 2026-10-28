"""Cleaning steps for the raw Utah FORGE circulation test data.

Each function does ONE job so that the notebook can show and explain every step.
Order used in 02_clean.ipynb:
    label_phases -> remove_bad_values -> fit/apply flow calibration
    -> correct temperature -> build injection signals -> fill short gaps
"""
import numpy as np
import pandas as pd
from scipy import stats

GPM_PER_BPM = 42.0  # 1 US oil barrel = 42 US gallons

# Values outside these ranges are physically impossible for this test.
HARD_LIMITS = {
    "p16B_psi": (0, 2000),   # shut-in pressure after the test is a REAL 1,400-1,600 psi
    "sep1_gpm": (0, 600),
    "sep2_gpm": (0, 600),
    "p16A_psi": (0, 3500),
    "liberty_p_psi": (0, 3500),
    "liberty_bpm": (0, 15),
    "T16B_F": (40, 400),
}

# A point must differ from its neighbours by at least this much to count as a spike.
SPIKE_FLOOR = {
    "p16B_psi": 50.0,
    "sep1_gpm": 40.0,
    "sep2_gpm": 40.0,
    "p16A_psi": 100.0,
    "liberty_p_psi": 100.0,
    "liberty_bpm": 1.0,
    "T16B_F": 10.0,
}

# Raw meter columns that the field calibration covers (separator outlets only).
CAL_METERS = {"sep1_gpm": "sep1_raw_gpm", "sep2_gpm": "sep2_raw_gpm"}

# Phase boundaries from Tables 2 and 3 of the test report (Mountain Time).
PHASE_STARTS = [
    ("2_flow_2.5bpm", "2024-08-09 17:00"),   # producer opened to separator
    ("3_step_5bpm", "2024-08-10 01:00"),
    ("4_step_7.5bpm", "2024-08-10 13:00"),
    ("5_steady_10bpm", "2024-08-11 06:00"),
]


def hampel_flag(s: pd.Series, window: int = 7, k: float = 5.0, floor: float = 0.0) -> pd.Series:
    """True where a point is an isolated spike.

    A point is a spike if it is further from the rolling median of its neighbours
    than both  k * (robust spread)  and  `floor`.  A window of 7 samples (3.5 min)
    removes spikes up to 3 samples long but keeps genuine step changes intact.
    """
    med = s.rolling(window, center=True, min_periods=3).median()
    dev = (s - med).abs()
    mad = dev.rolling(window, center=True, min_periods=3).median()
    return dev > np.maximum(k * 1.4826 * mad, floor)


def label_phases(df: pd.DataFrame, end_rate_bpm: float = 9.0) -> pd.Series:
    """Label each row with the test phase."""
    phase = pd.Series("0_pre_injection", index=df.index, dtype="object")
    first_inj = df.index[df["liberty_bpm"] > 0.5][0]
    phase[df.index >= first_inj] = "1_shut_in_2.5bpm"
    for name, start in PHASE_STARTS:
        phase[df.index >= pd.Timestamp(start)] = name
    # The steady phase ends when the 1-hour median rate drops for good.
    hourly = df["liberty_bpm"].rolling(120, center=True, min_periods=30).median()
    steady_end = hourly[(hourly >= end_rate_bpm)].index.max()
    phase[(df.index > steady_end)] = "6_wind_down"
    return phase


def remove_bad_values(df: pd.DataFrame):
    """Set impossible values and isolated spikes to NaN. Returns (clean_df, counts)."""
    out = df.copy()
    rows = []
    for col, (lo, hi) in HARD_LIMITS.items():
        before = out[col].notna().sum()
        out_of_range = (out[col] < lo) | (out[col] > hi)
        out.loc[out_of_range, col] = np.nan
        spikes = hampel_flag(out[col], floor=SPIKE_FLOOR[col])
        out.loc[spikes, col] = np.nan
        rows.append({"column": col, "valid_before": before,
                     "out_of_range": int(out_of_range.sum()),
                     "spikes": int(spikes.sum()),
                     "valid_after": int(out[col].notna().sum())})
    return out, pd.DataFrame(rows).set_index("column")


def fit_flow_calibration(cal: pd.DataFrame) -> pd.DataFrame:
    """Straight-line fit  true_gpm = slope * raw_gpm + intercept  for each meter."""
    rows = []
    for col, cal_col in CAL_METERS.items():
        fit = stats.linregress(cal[cal_col], cal["liberty_gpm"])
        rows.append({"meter": col, "slope": fit.slope, "intercept": fit.intercept,
                     "r_squared": fit.rvalue ** 2, "n_points": len(cal)})
    return pd.DataFrame(rows).set_index("meter")


def apply_flow_calibration(df: pd.DataFrame, fits: pd.DataFrame) -> pd.DataFrame:
    """Add corrected separator flows. Negative results are clipped to zero."""
    out = df.copy()
    for col in CAL_METERS:
        corrected = fits.loc[col, "slope"] * out[col] + fits.loc[col, "intercept"]
        out[col.replace("_gpm", "_corr_gpm")] = corrected.clip(lower=0)
    out["sep_total_corr_gpm"] = out["sep1_corr_gpm"] + out["sep2_corr_gpm"]
    return out


def temperature_offset(manual: pd.DataFrame):
    """Mean and spread of (manual temperature gun - Pason thermocouple), in degF."""
    d = (manual["T_manual_F"] - manual["T_pason_F"]).dropna()
    return d.mean(), d.std(), len(d)


def correct_temperature(df: pd.DataFrame, offset_F: float, min_hot_F: float = 200.0) -> pd.DataFrame:
    """Add the offset only while hot fluid is flowing (the thermocouple error is a
    flowing-fluid problem; cold, shut-in readings are left alone)."""
    out = df.copy()
    out["T16B_corr_F"] = out["T16B_F"].where(out["T16B_F"] < min_hot_F, out["T16B_F"] + offset_F)
    return out


def build_injection_signals(df: pd.DataFrame) -> pd.DataFrame:
    """Injection rate in gpm and one combined injection pressure."""
    out = df.copy()
    out["inj_gpm"] = out["liberty_bpm"] * GPM_PER_BPM
    out["p_inj_psi"] = out["p16A_psi"].fillna(out["liberty_p_psi"])
    return out


def fill_short_gaps(df: pd.DataFrame, cols, max_samples: int = 10) -> pd.DataFrame:
    """Linear interpolation across gaps of at most `max_samples` (5 min). Longer gaps stay NaN."""
    out = df.copy()
    for col in cols:
        out[col] = out[col].interpolate(limit=max_samples, limit_area="inside")
    return out


def flag_valid_steady(df: pd.DataFrame, rate_min_bpm: float = 9.5, settle_hours: float = 2.0,
                      p_running_psi: float = 2500.0) -> pd.Series:
    """True when we are in the steady phase AND the pump has been running at ~10 bpm
    for the last `settle_hours` hours (so pump stops and restarts are excluded).

    Robustness choices:
    * the rate is judged by its 5-minute median, so one noisy reading cannot trigger an exclusion;
    * where the rate record is missing, an injection pressure above `p_running_psi`
      counts as evidence that the pump is running.
    """
    rate = df["inj_gpm"] / GPM_PER_BPM
    rate_smooth = rate.rolling(10, center=True, min_periods=3).median()
    running = (rate_smooth >= rate_min_bpm) | (rate_smooth.isna() & (df["p_inj_psi"] > p_running_psi))
    n = int(settle_hours * 120)
    held = running.astype(float).rolling(n, min_periods=n).min() == 1.0
    return (df["phase"] == "5_steady_10bpm") & held
