"""Load the raw Utah FORGE extended circulation test files.

Nothing is corrected here. We only read, name columns and set types.
"""
from pathlib import Path
import pandas as pd

RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "raw" / "Extended Circulation Test"

MAIN_FILE = "Extended Circulation Test Data 08082024 to 09052024 (30 sec increment).xlsx"
FLOW_CAL_FILE = "Field Calibration of Flow Meters.xlsx"
MANUAL_TP_FILE = "Manual Temperature and Pressure Data.xlsx"

# Order follows the Read Me column dictionary (A..K).
MAIN_COLUMNS = [
    "time",           # A  Mountain Time
    "p16B_psi",       # B  producer wellhead pressure
    "q16B_1_gpm",     # C  producer flow 1, upstream of separator (suspect)
    "q16B_2_gpm",     # D  producer flow 2, redundant
    "T16B_F",         # E  producer temperature, uncorrected
    "sep1_gpm",       # F  separator outlet line 1
    "sep2_gpm",       # G  separator outlet line 2
    "sep_total_gpm",  # H  F + G
    "p16A_psi",       # I  injector wellhead pressure (transducer)
    "liberty_bpm",    # J  injection rate (Liberty), barrels per minute
    "liberty_p_psi",  # K  injector wellhead pressure (Liberty)
]


def load_main(raw_dir: Path = RAW_DIR) -> pd.DataFrame:
    """Raw 30-second time series, indexed by time. The first 4 rows are headers/units."""
    df = pd.read_excel(raw_dir / MAIN_FILE, header=None, skiprows=4)
    df.columns = MAIN_COLUMNS
    df["time"] = pd.to_datetime(df["time"])
    return df.set_index("time").sort_index()


def load_flow_calibration(raw_dir: Path = RAW_DIR) -> pd.DataFrame:
    """Calibration points: Liberty pump rate vs the three Pason flow meters (all gpm)."""
    cal = pd.read_excel(raw_dir / FLOW_CAL_FILE, header=None, skiprows=3).iloc[:, 1:7]
    cal.columns = ["liberty_bpm", "liberty_gpm", "liberty_gpm_dup",
                   "sep1_raw_gpm", "sep2_raw_gpm", "dis16B_raw_gpm"]
    return cal.astype(float).reset_index(drop=True)


def load_manual_tp(raw_dir: Path = RAW_DIR) -> pd.DataFrame:
    """Manual temperature-gun and pressure-gauge readings next to the Pason values."""
    df = pd.read_excel(raw_dir / MANUAL_TP_FILE, header=None, skiprows=4).iloc[:, 1:9]
    df.columns = ["date", "clock", "time", "T_manual_F", "p_manual_psi",
                  "T_pason_F", "p_pason_psi", "dT_F"]
    df = df[pd.to_datetime(df["time"], errors="coerce").notna()].copy()  # drops the 'Average' row
    df["time"] = pd.to_datetime(df["time"])
    for c in ["T_manual_F", "p_manual_psi", "T_pason_F", "p_pason_psi", "dT_F"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.drop(columns=["date", "clock"]).set_index("time")


if __name__ == "__main__":
    main = load_main()
    print(main.shape, main.index.min(), "->", main.index.max())
    print(load_flow_calibration().shape, load_manual_tp().shape)
