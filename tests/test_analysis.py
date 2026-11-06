"""Tests for src/analysis.py."""
import numpy as np
import pandas as pd
import pytest

from analysis import (GAL_TO_M3, find_plateau_start, gpm_to_kg_s, injectivity_index, linear_trend,
                      mass_flows, separator_conditions, steam_fraction, thermal_power,
                      thermal_power_at_separator, water_density)


@pytest.fixture(scope="module")
def sep():
    return separator_conditions()


def test_boiling_point_at_site_elevation(sep):
    assert sep["T_boil_F"] == pytest.approx(202.2, abs=0.5)       # the report gives 202.2 F
    assert sep["rho_liquid"] == pytest.approx(962, abs=3)


def test_steam_fraction_properties(sep):
    assert steam_fraction(sep["T_boil_F"], sep) == pytest.approx(0.0, abs=1e-3)   # no flashing at the boiling point
    temps = np.array([250.0, 300.0, 350.0, 380.0])
    x = steam_fraction(temps, sep)
    assert np.all(np.diff(x) > 0)                                  # hotter water flashes more
    assert steam_fraction(375.0, sep) == pytest.approx(0.18, abs=0.01)


def test_unit_conversions():
    assert water_density(20.0) == pytest.approx(998.2, abs=0.2)
    assert gpm_to_kg_s(420.0, 998.2) == pytest.approx(420 * GAL_TO_M3 / 60 * 998.2)
    assert gpm_to_kg_s(420.0, 998.2) == pytest.approx(26.4, abs=0.1)


def _frame(n=5, inj_gpm=420.0, T=375.0):
    idx = pd.date_range("2024-09-01", periods=n, freq="30s")
    return pd.DataFrame({"inj_gpm": inj_gpm, "T16B_corr_F": T, "sep_total_corr_gpm": 300.0}, index=idx)


def test_efficiency_equals_one_when_mass_balances(sep):
    df = _frame()
    x = 0.2
    inj_kg_s = gpm_to_kg_s(df["inj_gpm"], water_density(20.0))
    liquid_gpm = inj_kg_s * (1 - x) / sep["rho_liquid"] * 60 / GAL_TO_M3
    df["sep_total_corr_gpm"] = liquid_gpm
    mf = mass_flows(df, steam_x=x, sep=sep)
    assert mf["efficiency"].to_numpy() == pytest.approx(np.ones(len(df)), abs=1e-9)


def test_thermal_power_matches_textbook_within_a_few_percent(sep):
    df = _frame()
    mf = mass_flows(df, sep=sep)
    tp = thermal_power(df, mf=mf)
    T_out_C, T_in_C = (375.0 - 32) / 1.8, 20.0
    textbook = mf["produced_kg_s"] * 4.3 * (T_out_C - T_in_C) / 1000.0
    assert (tp["power_MW"] / textbook).iloc[0] == pytest.approx(1.0, abs=0.03)


def test_separator_and_wellhead_power_methods_agree(sep):
    df = _frame()
    mf = mass_flows(df, sep=sep)
    a = thermal_power(df, mf=mf)["power_MW"]
    b = thermal_power_at_separator(df, sep=sep, mf=mf)
    assert (a - b).abs().max() < 1e-9


def test_injectivity_index():
    df = pd.DataFrame({"inj_gpm": [420.0], "p_inj_psi": [2800.0]})
    assert injectivity_index(df).iloc[0] == pytest.approx(15.0)


def test_linear_trend_recovers_slope():
    idx = pd.date_range("2024-09-01", periods=48, freq="1h")
    s = pd.Series(100.0 - 2.0 * np.arange(48) / 24.0, index=idx)   # -2 per day
    t = linear_trend(s)
    assert t["slope_per_day"] == pytest.approx(-2.0)
    assert t["r2"] == pytest.approx(1.0)


def test_find_plateau_start():
    days = pd.date_range("2024-08-11", periods=12).date
    eff = pd.Series([0.45, 0.60, 0.70, 0.75, 0.80, 0.85, 0.88, 0.90, 0.905, 0.91, 0.905, 0.91], index=days)
    start, final = find_plateau_start(eff)
    assert start == days[7]                                         # 0.90 is within 2% of 0.91; 0.88 is not
    assert final == pytest.approx(0.91, abs=0.005)
