#!/usr/bin/env python3
"""
visualize_spread_multi_full.py — отчёт по экспериментам: 4 графика + таблица

Пример:
    python visualize_spread_multi_full.py archive --save report.png --min-cov 0.1
"""
import argparse, json, os, pathlib, sys, math
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns


def load_data(root: pathlib.Path):
    rows = []
    for p in sorted(root.rglob("experiment_*.json")):
        d = json.loads(p.read_text())
        if not d: continue
        t0 = min(r["start_time"] for r in d)
        t1 = max(r["receive_time"] for r in d)
        rows.append({
            "algorithm": d[0].get("algorithm", "unknown"),
            "spread_s": t1 - t0,
            "reports": len(d),
        })
    if not rows:
        print("⚠  Нет experiment_*.json в", root)
        sys.exit(1)
    df = pd.DataFrame(rows)
    df["coverage"] = df.reports / int(os.getenv("NODE_COUNT", "111"))
    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("archive", type=pathlib.Path, help="путь до папки archive")
    ap.add_argument("--min-cov", type=float, default=0.0,
                    help="отфильтровать прогоны с coverage < порога (0..1)")
    ap.add_argument("--save", metavar="FILE.png",
                    help="префикс сохранения (расширение .png отсекается)")
    ap.add_argument("--linear", action="store_true",
                    help="линейная Y-ось вместо логарифмической")
    args = ap.parse_args()

    NODE = int(os.getenv("NODE_COUNT", "111"))
    df = load_data(args.archive)
    if args.min_cov > 0:
        before = len(df)
        df = df[df.coverage >= args.min_cov]
        print(f"Фильтр: убрано {before - len(df)} прогонов (coverage < {args.min_cov})")

    # агрегируем summary
    summary = df.groupby("algorithm").agg(
        mean_time=("spread_s", "mean"),
        std_time=("spread_s", "std"),
        mean_cov=("coverage", "mean")
    ).reset_index().sort_values("mean_time")

    # дополнительная метрика score (α=0.5)
    max_t = summary.mean_time.max()
    summary["score"] = 0.5 * (summary.mean_time / max_t) - 0.5 * summary.mean_cov
    summary = summary.sort_values("score")  # чем ниже score, тем лучше

    algs = summary.algorithm.tolist()

    # префикс для сохранения
    base = None
    if args.save:
        base = os.path.splitext(args.save)[0]

    # ——— 1) Dual-axis + Box-plot (две панели) ———
    fig1 = plt.figure(figsize=(10, 8))
    gs1 = fig1.add_gridspec(2, 1, height_ratios=[2, 3], hspace=0.4)
    # (1A) Dual-axis
    ax1 = fig1.add_subplot(gs1[0])
    x = np.arange(len(algs))
    times = summary.mean_time.values
    errs = summary.std_time.fillna(0).values
    covs = summary.mean_cov.values

    bars = ax1.bar(x, times, yerr=errs, capsize=5, width=0.6,
                   color="#4c72b0", alpha=0.8, label="Mean spread time")
    if not args.linear:
        ax1.set_yscale("log")
    ax1.set_xticks(x);
    ax1.set_xticklabels(algs, rotation=15)
    ax1.set_ylabel("Mean spread time, s")
    ax1.grid(True, axis="y", which="both", linestyle="--", alpha=0.4)
    # подписи
    for xi, t in zip(x, times):
        ax1.text(xi, t * 1.05, f"{t:.1f}", ha="center", va="bottom", fontsize=9)

    ax2 = ax1.twinx()
    ax2.plot(x, covs, color="#dd8452", marker="o", lw=2, label="Mean coverage")
    ax2.set_ylim(0, 1)
    for xi, c in zip(x, covs):
        ax2.text(xi, c + 0.02, f"{c:.2f}", ha="center", va="bottom", fontsize=9)

    h1, l1 = ax1.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax1.legend(h1 + h2, l1 + l2, loc="upper left", framealpha=0.9)
    ax1.set_title(f"Spread time & coverage (N={NODE})")

    # (1B) Box-plot + stripplot
    ax3 = fig1.add_subplot(gs1[1])
    sns.boxplot(data=df, x="algorithm", y="spread_s", ax=ax3,
                showfliers=True, palette="pastel")
    sns.stripplot(data=df, x="algorithm", y="spread_s", ax=ax3,
                  hue="coverage", palette="coolwarm",
                  size=6, jitter=0.3, linewidth=0)
    if not args.linear:
        ax3.set_yscale("log")
    ax3.set_ylabel("Spread time, s")
    ax3.set_xlabel("")
    ax3.legend(title="coverage", bbox_to_anchor=(1.02, 1), loc="upper left")
    ax3.set_title("Distribution of spread times by algorithm")

    if base:
        fname = f"{base}_dualbox.png"
        fig1.savefig(fname, dpi=150)
        print("Saved", fname)
    else:
        plt.show()

    # ——— 2) Scatter coverage vs spread_time ———
    fig2, ax4 = plt.subplots(figsize=(6, 4))
    sns.scatterplot(data=df, x="coverage", y="spread_s",
                    hue="algorithm", style="algorithm",
                    s=80, ax=ax4)
    if not args.linear:
        ax4.set_yscale("log")
    ax4.set_xlabel("Coverage (fraction)")
    ax4.set_ylabel("Spread time, s")
    ax4.grid(True, which="both", axis="y", linestyle="--", alpha=0.4)
    ax4.set_title("Scatter: coverage vs spread time")
    if base:
        fname = f"{base}_scatter.png"
        fig2.savefig(fname, dpi=150)
        print("Saved", fname)
    else:
        plt.show()

    # ——— 3) Гистограммы spread_time по алгоритмам ———
    ncol = 2
    nrow = math.ceil(len(algs) / ncol)
    fig3, axes = plt.subplots(nrow, ncol, figsize=(8, 4 * nrow))
    axes = axes.flatten()
    for i, alg in enumerate(algs):
        ax = axes[i]
        sns.histplot(df.loc[df.algorithm == alg, "spread_s"],
                     bins=20, ax=ax, kde=False,
                     log_scale=(not args.linear))
        ax.set_title(alg)
        ax.set_xlabel("spread time, s")
        ax.set_ylabel("count")
    # пустые
    for j in range(len(algs), len(axes)):
        axes[j].axis("off")
    fig3.tight_layout()
    if base:
        fname = f"{base}_hist.png"
        fig3.savefig(fname, dpi=150)
        print("Saved", fname)
    else:
        plt.show()

    # ——— 4) Таблица summary + score ———
    fig4, ax5 = plt.subplots(figsize=(6, 1 + 0.4 * len(algs)))
    ax5.axis("off")
    tbl = summary[["algorithm", "mean_time", "std_time", "mean_cov", "score"]].copy()
    tbl = tbl.round({"mean_time": 1, "std_time": 1, "mean_cov": 2, "score": 3})
    cell = tbl.values.tolist()
    cols = tbl.columns.tolist()
    table = ax5.table(cellText=cell, colLabels=cols,
                      loc="center", cellLoc="center")
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    fig4.tight_layout()
    if base:
        fname = f"{base}_table.png"
        fig4.savefig(fname, dpi=150)
        print("Saved", fname)
    else:
        plt.show()


if __name__ == "__main__":
    main()
