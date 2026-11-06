"""Tests for src/clean.py, using small synthetic data."""
import numpy as np
import pandas as pd
import pytest

from clean import (HARD_LIMITS, apply_flow_calibration, correct_temperature, fill_short_gaps,
                   fit_flow_calibration, flag_valid_steady, hampel_flag, label_phases,
                   remove_bad_values)


def test_hampel_flags_isolated_spike_and_keeps_step():
    s = pd.Series([10, 10, 10, 95, 10, 10, 10, 10, 25, 25, 25, 25, 25, 25], dtype=float)
    flags = hampel_flag(s, floor=20)
    assert flags.iloc[3]                      # the isolated spike
    assert flags.sum() == 1                   # nothing else, in particular not the step


def test_remove_bad_values_limits_and_spikes():
    idx = pd.date_range("2024-08-20", periods=60, freq="30s")
    df = pd.DataFrame({c: 100.0 for c in HARD_LIMITS}, index=idx)
    df["p16B_psi"] = 300.0
    df.iloc[20, df.columns.get_loc("p16B_psi")] = 5000.0       # outside the 2,000 psi limit
    df.iloc[40, df.columns.get_loc("sep1_gpm")] = 590.0        # inside the limit, but an isolated spike
    clean, counts = remove_bad_values(df)
    assert np.isnan(clean["p16B_psi"].iloc[20])
    assert np.isnan(clean["sep1_gpm"].iloc[40])
    assert counts.loc["p16B_psi", "out_of_range"] == 1
    assert counts.loc["sep1_gpm", "spikes"] == 1
    assert len(clean) == len(df)                               # rows are never dropped


def test_real_high_shut_in_pressure_is_kept():
    idx = pd.date_range("2024-09-05", periods=200, freq="30s")
    df = pd.DataFrame({c: 100.0 for c in HARD_LIMITS}, index=idx)
    df["p16B_psi"] = 1500.0                                    # sustained shut-in pressure
    clean, _ = remove_bad_values(df)
    assert clean["p16B_psi"].notna().all()


def test_fit_flow_calibration_recovers_known_line():
    x = np.array([40, 80, 120, 200, 280, 360, 420, 460], dtype=float)
    cal = pd.DataFrame({"sep1_raw_gpm": x, "sep2_raw_gpm": x, "liberty_gpm": 0.9 * x - 5.0})
    fits = fit_flow_calibration(cal)
    assert fits.loc["sep1_gpm", "slope"] == pytest.approx(0.9)
    assert fits.loc["sep1_gpm", "intercept"] == pytest.approx(-5.0)
    assert fits.loc["sep1_gpm", "r_squared"] == pytest.approx(1.0)


def test_apply_flow_calibration_clips_negative_and_sums():
    fits = pd.DataFrame({"slope": [0.9, 0.9], "intercept": [-5.0, -5.0]}, index=["sep1_gpm", "sep2_gpm"])
    df = pd.DataFrame({"sep1_gpm": [2.0, 100.0], "sep2_gpm": [2.0, 200.0]})
    out = apply_flow_calibration(df, fits)
    assert out["sep1_corr_gpm"].iloc[0] == 0.0                 # 0.9*2 - 5 < 0 -> clipped
    assert out["sep_total_corr_gpm"].iloc[1] == pytest.approx(85.0 + 175.0)


def test_correct_temperature_only_adds_offset_when_hot():
    df = pd.DataFrame({"T16B_F": [70.0, 150.0, 300.0, 360.0]})
    out = correct_temperature(df, offset_F=11.0)
    assert out["T16B_corr_F"].tolist() == [70.0, 150.0, 311.0, 371.0]


def test_fill_short_gaps_respects_limit():
    s = pd.Series([1.0] + [np.nan] * 3 + [5.0] + [np.nan] * 12 + [9.0])
    out = fill_short_gaps(pd.DataFrame({"x": s}), ["x"], max_samples=10)["x"]
    assert out.iloc[1:4].notna().all()                         # 3-sample gap filled
    assert out.iloc[5:15].notna().all()                        # first 10 samples of the long gap are filled
    assert out.iloc[15:17].isna().all()                        # the rest stays empty


def test_label_phases_order():
    idx = pd.date_range("2024-08-08 07:00", "2024-09-05 12:00", freq="5min")
    rate = pd.Series(0.0, index=idx)
    rate[idx >= "2024-08-08 09:30"] = 2.5
    rate[idx >= "2024-08-11 06:00"] = 10.0
    rate[idx >= "2024-09-04 06:00"] = 0.0
    phase = label_phases(pd.DataFrame({"liberty_bpm": rate}))
    assert phase["2024-08-08 08:00"] == "0_pre_injection"
    assert phase["2024-08-10 00:00"] == "2_flow_2.5bpm"
    assert phase["2024-08-20 00:00"] == "5_steady_10bpm"
    assert phase["2024-09-05 00:00"] == "6_wind_down"


def test_valid_steady_excludes_pump_stop_and_settling_but_not_single_dip():
    idx = pd.date_range("2024-08-20", periods=2 * 60 * 24, freq="30s")      # one day
    df = pd.DataFrame({"inj_gpm": 420.0, "p_inj_psi": 2800.0, "phase": "5_steady_10bpm"}, index=idx)
    stop = (idx >= "2024-08-20 06:00") & (idx < "2024-08-20 07:00")
    df.loc[stop, ["inj_gpm", "p_inj_psi"]] = [0.0, 1000.0]                  # one-hour pump stop
    df.loc["2024-08-20 15:00:00", "inj_gpm"] = 9.1 * 42                     # a single noisy reading
    ok = flag_valid_steady(df)
    assert not ok[pd.Timestamp("2024-08-20 06:30:00")]                                       # during the stop
    assert not ok[pd.Timestamp("2024-08-20 08:30:00")]                                       # still settling (< 2 h after restart)
    assert ok[pd.Timestamp("2024-08-20 10:00:00")]                                           # settled
    assert ok[pd.Timestamp("2024-08-20 15:30:00")]                                           # a single noisy reading does not exclude
