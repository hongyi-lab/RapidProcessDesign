"""Editable 1600 x 900 engineering diagrams. Requires matplotlib.

Run from any directory. This draws the specification, not measured aircraft results.
SVG text remains editable; node coordinates below are screen pixels.
"""
from pathlib import Path
import argparse

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Circle

ROOT = Path(__file__).resolve().parents[1]
INK, BLUE, ORANGE, MUTED = "#172b3a", "#206b94", "#b75b1c", "#536775"
plt.rcParams.update({"font.family": "serif", "font.serif": ["Times New Roman", "DejaVu Serif"],
                     "font.weight": "bold", "svg.fonttype": "none", "font.size": 16})


def canvas():
    fig = plt.figure(figsize=(16, 9), dpi=100, facecolor="white")
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set(xlim=(0, 1600), ylim=(900, 0))
    ax.axis("off")
    return fig, ax


def label(ax, x, y, text, size=16, color=MUTED, **kw):
    return ax.text(x, y, text, fontsize=size, color=color, ha="center", va="center", **kw)


def box(ax, x, y, w, h, module, title, subtitle="", fill="#f2f6f9", edge=INK):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=10",
                              facecolor=fill, edgecolor=edge, linewidth=1.5, zorder=3))
    ax.text(x+18, y+22, module, fontsize=14, color=edge, ha="left", va="center", zorder=4)
    label(ax, x+w/2, y+h/2+4 if subtitle else y+h/2+10, title, 19, INK, zorder=4)
    if subtitle:
        label(ax, x+w/2, y+h-21, subtitle, 15, MUTED, zorder=4)


def line(ax, points, color=INK, dashed=False, end=True, width=2.1):
    xs, ys = zip(*points)
    ax.plot(xs, ys, color=color, lw=width, linestyle=(0, (5, 4)) if dashed else "-",
            solid_capstyle="round", zorder=2)
    if end:
        ax.add_patch(FancyArrowPatch(points[-2], points[-1], arrowstyle="-|>",
                                    mutation_scale=16, color=color, lw=width,
                                    linestyle="-", zorder=2))


def dot(ax, x, y, color=INK):
    ax.add_patch(Circle((x, y), 3.8, color=color, zorder=3))


def save(fig, name, out):
    out.mkdir(parents=True, exist_ok=True)
    for ext in ("svg", "png"):
        fig.savefig(out / f"{name}.{ext}", dpi=100, facecolor="white")
    plt.close(fig)


def main_diagram(out):
    fig, ax = canvas()
    top = [(60, "M01", "Mission requirements", "profile / payload"),
           (460, "M02", "Design problem", "variables / constraints"),
           (860, "M03", "Preliminary sizing", "initial design / state"),
           (1260, "M04", "Geometry & layout", "shape / usable space")]
    for x, mid, title, sub in top:
        box(ax, x, 60, 280, 110, mid, title, sub)
    for x in (340, 740, 1140):
        line(ax, [(x, 115), (x+120, 115)])
    ax.add_patch(FancyBboxPatch((65, 285), 1470, 355, boxstyle="round,pad=0,rounding_size=16",
                              fc="#fafcfd", ec="#a0bacb", lw=1.5, zorder=0))
    label(ax, 790, 309, "INNER ANALYSIS  |  fixed design x", 18, BLUE)
    for x, mid, title, sub in [(105, "M05–M06", "Flight state & trim", "conditions / forces / moments"),
                              (635, "M07–M08", "Loads & structure", "distributed loads / response"),
                              (1165, "M09–M10", "Mass, CG & mission", "fuel / propulsion / performance")]:
        box(ax, x, 350, 330, 110, mid, title, sub)
    line(ax, [(1400, 170), (1400, 250), (270, 250), (270, 350)])
    label(ax, 820, 232, "fixed geometry, layout and model inputs", 16)
    line(ax, [(435, 405), (635, 405)])
    line(ax, [(965, 405), (1165, 405)])
    box(ax, 635, 515, 330, 88, "C01", "Residuals acceptable?", fill="#e5f1f8", edge=BLUE)
    line(ax, [(1330, 460), (1330, 558), (965, 558)])
    line(ax, [(635, 558), (270, 558), (270, 460)], BLUE, True)
    label(ax, 420, 536, "no: update state y", 17, BLUE)
    box(ax, 105, 710, 330, 100, "O01", "Update design x", "teacher decisions pending", fill="#fff1e5", edge=ORANGE)
    box(ax, 635, 710, 330, 100, "M11", "Objectives & constraints", "valid, converged analysis")
    box(ax, 1165, 710, 330, 100, "M12", "Independent review", "selected candidate / evidence")
    line(ax, [(800, 603), (800, 710)], BLUE)
    label(ax, 930, 672, "yes + valid", 16, BLUE)
    line(ax, [(635, 760), (435, 760)], ORANGE, True)
    line(ax, [(965, 760), (1165, 760)])
    line(ax, [(105, 760), (30, 760), (30, 25), (1400, 25), (1400, 60)], ORANGE, True)
    label(ax, 550, 43, "OUTER DESIGN LOOP", 15, ORANGE)
    label(ax, 800, 858, "Proposed architecture  •  Missing / out-of-range / failed analyses return status only", 16, MUTED)
    save(fig, "bwb-engineering-pipeline", out)


def detail_diagram(out):
    fig, ax = canvas()
    box(ax, 55, 350, 275, 115, "M04", "Geometry & layout", "fixed x / regions / positions")
    for x, mid, title, sub in [(460, "M05", "Flight state", "atmosphere / q / Re / Mach"),
                              (855, "M06", "Aero & trim", "forces / moments / controls"),
                              (1250, "M07", "Load transfer", "aero + inertia / boundaries")]:
        box(ax, x, 235, 285, 110, mid, title, sub)
    for x, mid, title, sub in [(460, "M10", "Propulsion & mission", "fuel flow / mission integral"),
                              (855, "M09", "Mass & CG", "component / tank ledger"),
                              (1250, "M08", "Structure", "response / structural mass")]:
        box(ax, x, 555, 285, 110, mid, title, sub)
    # Geometry bus: separate from analysis-state feedback.
    line(ax, [(192, 350), (192, 120), (1565, 120), (1565, 610), (1535, 610)])
    line(ax, [(998, 120), (998, 235)])
    dot(ax, 998, 120)
    for port in (603, 1393):
        line(ax, [(port, 120), (port, 235)])
        dot(ax, port, 120)
    label(ax, 860, 94, "shape / internal layout / reference geometry", 17)
    line(ax, [(192, 465), (192, 735), (998, 735), (998, 665)])
    line(ax, [(603, 735), (603, 665)])
    dot(ax, 603, 735)
    label(ax, 465, 765, "usable volumes / component positions", 17)
    line(ax, [(745, 290), (855, 290)])
    line(ax, [(1140, 290), (1250, 290)])
    line(ax, [(1393, 345), (1393, 555)])
    label(ax, 1453, 450, "loads", 16)
    line(ax, [(1250, 610), (1140, 610)])
    label(ax, 1195, 644, "mass", 16)
    line(ax, [(855, 595), (745, 595)])
    label(ax, 799, 575, "m, CG", 15)
    line(ax, [(745, 638), (855, 638)], BLUE, True)
    label(ax, 800, 672, "tank fuel", 15, BLUE)
    # Coupling state feedback, with separate ports for each physical dependency.
    line(ax, [(965, 555), (965, 345)], BLUE, True)
    label(ax, 904, 445, "m, CG", 16, BLUE)
    line(ax, [(1045, 555), (1045, 468), (1194, 468), (1194, 323), (1250, 323)], BLUE, True)
    label(ax, 1123, 445, "inertia", 16, BLUE)
    line(ax, [(855, 323), (800, 323), (800, 416), (603, 416), (603, 555)])
    label(ax, 691, 392, "trim / drag", 17)
    line(ax, [(460, 610), (398, 610), (398, 290), (460, 290)], BLUE, True)
    label(ax, 373, 490, "next state", 16, BLUE, rotation=90)
    label(ax, 800, 830, "Repeat at each mission / load case  •  C01 checks all residuals (Figure 1)", 17, BLUE)
    label(ax, 800, 870, "Proposed rigid-aero / static-structure baseline  •  Model coverage is documented separately", 15, MUTED)
    save(fig, "bwb-analysis-coupling", out)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, default=ROOT / "docs/figures")
    args = p.parse_args()
    main_diagram(args.output)
    detail_diagram(args.output)
    print(f"Wrote two SVG/PNG pairs to {args.output.resolve()}")
