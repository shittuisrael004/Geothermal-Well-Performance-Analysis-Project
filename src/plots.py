"""Small plotting helpers shared by the notebooks."""
import matplotlib.pyplot as plt

FIG_DIR = "../figures/"


def apply_style():
    """One consistent look for every figure."""
    plt.rcParams.update({"figure.dpi": 110, "axes.grid": True, "grid.alpha": 0.3,
                         "axes.spines.top": False, "axes.spines.right": False})


def savefig(fig, name: str, fig_dir: str = FIG_DIR, dpi: int = 150):
    """Save a figure into the figures folder (tight layout, fixed resolution)."""
    fig.tight_layout()
    fig.savefig(f"{fig_dir}{name}", dpi=dpi)


def shade_window(ax, start, end, color="gold", alpha=0.2, label=None):
    """Shade a time window (for example the plateau) on an axis."""
    ax.axvspan(start, end, color=color, alpha=alpha, label=label, lw=0)
