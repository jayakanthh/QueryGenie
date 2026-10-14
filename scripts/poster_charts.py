"""Charts for the project poster (print, 300 dpi). Every value is a measured result from results/."""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "Review-III", "poster_assets")
PAPER, OURS, INK, MUTED, GRID = "#C55A11", "#0070C0", "#1F2937", "#6B7280", "#E5E7EB"   # validated pair (dataviz)
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 15, "axes.edgecolor": MUTED, "axes.labelcolor": INK,
                     "xtick.color": INK, "ytick.color": MUTED, "axes.spines.top": False, "axes.spines.right": False})


def finish(ax, title, ylabel, ymax):
    ax.set_title(title, loc="left", fontsize=18, fontweight="bold", color=INK, pad=12)
    ax.set_ylabel(ylabel, color=MUTED)
    ax.set_ylim(0, ymax)
    ax.yaxis.grid(True, color=GRID, linewidth=1)
    ax.set_axisbelow(True)


def label(ax, bars, fmt):
    for b in bars:
        ax.text(b.get_x() + b.get_width() / 2, b.get_height() + ax.get_ylim()[1] * 0.015, fmt(b.get_height()),
                ha="center", va="bottom", fontsize=15, fontweight="bold", color=INK)


def save(fig, name):
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, name), dpi=300, facecolor="white")
    plt.close(fig)


# 1. Reproduction against the paper (two benchmarks, two series)
fig, ax = plt.subplots(figsize=(7.6, 4.8))
x, w = [0, 1], 0.34
p = ax.bar([i - w / 2 - 0.01 for i in x], [77.9, 70.9], w, color=PAPER, label="CodeS paper")
o = ax.bar([i + w / 2 + 0.01 for i in x], [77.8, 69.5], w, color=OURS, label="Our reproduction")
label(ax, p, lambda v: f"{v:.1f}%"); label(ax, o, lambda v: f"{v:.1f}%")
ax.set_xticks(x, ["Spider dev\n(1,034 questions)", "Spider-Realistic\n(508 questions)"])
finish(ax, "Reproduction: execution accuracy", "Execution accuracy (%)", 100)
ax.legend(frameon=False, loc="upper right", fontsize=13)
save(fig, "chart_reproduction.png")

# 2. Accuracy on the answers it gives
fig, ax = plt.subplots(figsize=(7.6, 4.8))
b = ax.bar([0, 1], [77.8, 83.3], 0.5, color=[PAPER, OURS])
label(ax, b, lambda v: f"{v:.1f}%")
ax.set_xticks([0, 1], ["Original CodeS-1B\n(answers 100%)", "With abstention\n(answers 90.4%)"])
finish(ax, "Correct when it answers", "Accuracy on answered (%)", 100)
save(fig, "chart_enhancement.png")

# 3. Wrong answers given (separate chart: different scale, no dual axis)
fig, ax = plt.subplots(figsize=(7.6, 4.8))
b = ax.bar([0, 1], [230, 156], 0.5, color=[PAPER, OURS])
label(ax, b, lambda v: f"{int(v)}")
ax.set_xticks([0, 1], ["Original CodeS-1B", "With abstention"])
finish(ax, "Wrong answers given (of 1,034)", "Wrong answers", 260)
ax.text(1, 156 + 34, "−32%", ha="center", fontsize=15, color=OURS, fontweight="bold")
save(fig, "chart_wrong.png")

# 4. Calibration: accuracy by the share of candidate queries that agree (one series)
fig, ax = plt.subplots(figsize=(7.6, 4.8))
b = ax.bar(range(4), [56.8, 75.6, 82.3, 88.3], 0.55, color=OURS)
label(ax, b, lambda v: f"{v:.1f}%")
ax.set_xticks(range(4), ["25%", "50%", "75%", "100%"])
ax.set_xlabel("Share of candidate queries that agree with the answer", color=MUTED)
finish(ax, "More agreement → more often right", "Accuracy (%)", 100)
save(fig, "chart_calibration.png")
print("charts saved to", OUT)
