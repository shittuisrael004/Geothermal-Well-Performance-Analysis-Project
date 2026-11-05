"""Performance calculations: injectivity, steam fraction, mass flows and efficiency."""
import numpy as np
import pandas as pd
from iapws import IAPWS97
from scipy import stats

GAL_TO_M3 = 3.785411784e-3
SEPARATOR_ELEVATION_FT = 5415.0     # from the report (Utah FORGE site)


def f_to_c(f):
    return (np.asarray(f, dtype=float) - 32.0) / 1.8


def separator_conditions(elevation_ft: float = SEPARATOR_ELEVATION_FT) -> dict:
    """Atmospheric separator: pressure from altitude, then boiling point and liquid density."""
    h_m = elevation_ft * 0.3048
    p_MPa = 101.325 * (1 - 2.25577e-5 * h_m) ** 5.25588 / 1000.0
    liq, vap = IAPWS97(P=p_MPa, x=0), IAPWS97(P=p_MPa, x=1)
    return {"p_MPa": p_MPa, "T_boil_F": (liq.T - 273.15) * 1.8 + 32.0,
            "rho_liquid": liq.rho, "h_liquid": liq.h, "h_fg": vap.h - liq.h}


# Saturated-liquid enthalpy on a 1 degF grid, so we can look it up fast for 80,000 rows.
_GRID_F = np.arange(40.0, 401.0, 1.0)
_GRID_H = np.array([IAPWS97(T=f_to_c(t) + 273.15, x=0).h for t in _GRID_F])


def steam_fraction(T_F, sep: dict) -> np.ndarray:
    """Mass fraction that flashes to steam when hot liquid at T_F drops to the separator.

    Energy balance:  x = (h_liquid(T) - h_liquid(T_boil)) / h_fg(T_boil)   (kJ/kg)
    """
    h_in = np.interp(np.asarray(T_F, dtype=float), _GRID_F, _GRID_H)
    return np.clip((h_in - sep["h_liquid"]) / sep["h_fg"], 0.0, 1.0)


def water_density(T_C: float, p_MPa: float = 0.1) -> float:
    """Density of liquid water, kg/m3."""
    return IAPWS97(T=T_C + 273.15, P=p_MPa).rho


def gpm_to_kg_s(gpm, rho):
    """US gallons per minute -> kg/s, for a fluid of density rho (kg/m3)."""
    return np.asarray(gpm, dtype=float) * GAL_TO_M3 / 60.0 * rho


def mass_flows(df: pd.DataFrame, T_inj_C: float = 20.0, liquid_col: str = "sep_total_corr_gpm",
               T_col: str = "T16B_corr_F", steam_x=None, sep: dict = None) -> pd.DataFrame:
    """Injected and produced MASS flow (kg/s) and efficiency = out / in."""
    sep = sep or separator_conditions()
    out = pd.DataFrame(index=df.index)
    out["inj_kg_s"] = gpm_to_kg_s(df["inj_gpm"], water_density(T_inj_C))
    out["sep_liquid_kg_s"] = gpm_to_kg_s(df[liquid_col], sep["rho_liquid"])
    out["steam_frac"] = steam_fraction(df[T_col], sep) if steam_x is None else steam_x
    out["produced_kg_s"] = out["sep_liquid_kg_s"] / (1.0 - out["steam_frac"])
    out["efficiency"] = out["produced_kg_s"] / out["inj_kg_s"]
    return out


def injectivity_index(df: pd.DataFrame) -> pd.Series:
    """Wellhead injectivity: gpm of water per 100 psi of wellhead injection pressure."""
    return df["inj_gpm"] / df["p_inj_psi"] * 100.0


def linear_trend(s: pd.Series) -> dict:
    """Straight-line trend of a time series: slope per day, its uncertainty, and total change."""
    s = s.dropna()
    days = (s.index - s.index[0]).total_seconds() / 86400.0
    fit = stats.linregress(days, s.values)
    return {"slope_per_day": fit.slope, "stderr": fit.stderr, "r2": fit.rvalue ** 2,
            "days": days.max(), "change": fit.slope * days.max()}


# ---------------------------------------------------------------- thermal power
def enthalpy_liquid(T_F):
    """Energy content of liquid water (kJ/kg) at T_F. Pressure effects are small and ignored."""
    return np.interp(np.asarray(T_F, dtype=float), _GRID_F, _GRID_H)


def thermal_power(df: pd.DataFrame, T_inj_C: float = 20.0, T_col: str = "T16B_corr_F",
                  mf: pd.DataFrame = None, **mass_kw) -> pd.DataFrame:
    """Thermal power carried out by the produced fluid, relative to the injected water.

        P = produced mass flow x (h_produced - h_injected)

    Returns kg/s, kJ/kg values and power in megawatts-thermal (MWt).
    """
    mf = mass_flows(df, T_inj_C=T_inj_C, T_col=T_col, **mass_kw) if mf is None else mf
    out = pd.DataFrame(index=df.index)
    out["produced_kg_s"] = mf["produced_kg_s"]
    out["h_prod_kJ_kg"] = enthalpy_liquid(df[T_col])
    out["h_inj_kJ_kg"] = IAPWS97(T=T_inj_C + 273.15, P=0.1).h
    out["dh_kJ_kg"] = out["h_prod_kJ_kg"] - out["h_inj_kJ_kg"]
    out["power_MW"] = out["produced_kg_s"] * out["dh_kJ_kg"] / 1000.0   # kJ/s = kW -> MW
    return out


def thermal_power_at_separator(df: pd.DataFrame, T_inj_C: float = 20.0, sep: dict = None,
                               mf: pd.DataFrame = None) -> pd.Series:
    """Cross-check: add up the heat leaving the separator as liquid and as steam (MWt)."""
    sep = sep or separator_conditions()
    mf = mass_flows(df, T_inj_C=T_inj_C, sep=sep) if mf is None else mf
    h_inj = IAPWS97(T=T_inj_C + 273.15, P=0.1).h
    h_vap = sep["h_liquid"] + sep["h_fg"]
    steam_kg_s = mf["produced_kg_s"] - mf["sep_liquid_kg_s"]
    heat_kW = mf["sep_liquid_kg_s"] * sep["h_liquid"] + steam_kg_s * h_vap - mf["produced_kg_s"] * h_inj
    return heat_kW / 1000.0


# ---------------------------------------------------------------- helpers shared by notebooks
def find_plateau_start(daily_eff: pd.Series, tol: float = 0.02, n_final: int = 3):
    """Start of the plateau: working back from the end, days within `tol` of the final level.

    Returns (start_day, final_level).  Same rule as used in notebook 03.
    """
    final = daily_eff.iloc[-n_final:].median()
    close = ((daily_eff - final).abs() / final) <= tol
    start = None
    for day in reversed(daily_eff.index):
        if close[day]:
            start = day
        else:
            break
    return start, final


def recalibrate_through_origin(frame: pd.DataFrame, const: pd.DataFrame, cal: pd.DataFrame) -> pd.DataFrame:
    """Alternative flow calibration: best straight line forced through (0, 0).

    We first undo the with-intercept correction to recover the raw meter reading,
    then apply the through-origin slope instead.
    """
    out = frame.copy()
    for m, cal_col in [("sep1", "sep1_raw_gpm"), ("sep2", "sep2_raw_gpm")]:
        a, b = const.loc[f"{m}_gpm", "slope"], const.loc[f"{m}_gpm", "intercept"]
        raw = (frame[f"{m}_corr_gpm"] - b) / a
        x, y = cal[cal_col].values, cal["liberty_gpm"].values
        out[f"{m}_corr_gpm"] = raw * (x * y).sum() / (x * x).sum()
    out["sep_total_corr_gpm"] = out["sep1_corr_gpm"] + out["sep2_corr_gpm"]
    return out
