"""Reproducible exploratory analysis of the processed ECO Household 1 data."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / ".cache/matplotlib"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

EXPECTED_ROWS = 7_584
EXPECTED_DAYS = 79
INTERVAL_SECONDS = 900
DEFAULT_INPUT = ROOT / "data/processed/eco_household_1_15min.parquet"
REQUIRED_COLUMNS = {
    "date", "interval_start_second", "time_of_day", "hour", "day_of_week",
    "day_name", "is_weekend", "powerallphases_mean_w", "powerallphases_max_w",
    "powerallphases_min_w", "powerallphases_std_w", "energy_wh",
    "occupancy_fraction", "occupancy_state", "interval_seconds",
    "powerl1_mean_w", "powerl2_mean_w", "powerl3_mean_w",
}
POWER = "powerallphases_mean_w"


def load_and_validate(path: Path) -> pd.DataFrame:
    """Load the real Parquet file and verify the Phase 2B data contract."""
    frame = pd.read_parquet(path)
    missing = REQUIRED_COLUMNS - set(frame.columns)
    if missing:
        raise ValueError(f"Missing columns: {sorted(missing)}")
    if len(frame) != EXPECTED_ROWS or frame.isna().any().any():
        raise ValueError(f"Expected {EXPECTED_ROWS} rows and no nulls; got {len(frame)} rows.")
    frame["date"] = pd.to_datetime(frame["date"])
    if frame["date"].nunique() != EXPECTED_DAYS:
        raise ValueError(f"Expected {EXPECTED_DAYS} dates.")
    if not (frame.groupby("date").size() == 96).all():
        raise ValueError("Every date must contain 96 intervals.")
    if frame.duplicated(["date", "interval_start_second"]).any():
        raise ValueError("Duplicate date/interval positions.")
    if set(frame["occupancy_state"].unique()) - {"occupied", "unoccupied", "mixed"}:
        raise ValueError("Unexpected occupancy state.")
    if not frame["occupancy_fraction"].between(0, 1).all():
        raise ValueError("Occupancy fractions must be within [0, 1].")
    if not (frame["interval_seconds"] == INTERVAL_SECONDS).all():
        raise ValueError("Unexpected interval length.")
    if not np.isfinite(frame.select_dtypes("number").to_numpy()).all():
        raise ValueError("Non-finite numeric values.")
    return frame.sort_values(["date", "interval_start_second"]).reset_index(drop=True)


def _save(fig: plt.Figure, path: Path) -> Path:
    fig.savefig(path, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return path


def make_figures(frame: pd.DataFrame, out: Path) -> list[Path]:
    """Create static plots from the loaded ECO-derived Parquet records."""
    out.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    d = frame.copy()
    d["datetime"] = d["date"] + pd.to_timedelta(d["interval_start_second"], unit="s")

    fig, ax = plt.subplots(figsize=(13, 4.8))
    ax.plot(d["datetime"], d[POWER], lw=.7, color="#176B87", label="15-minute mean")
    ax.plot(d["datetime"], d["powerallphases_max_w"], lw=.45, alpha=.5, color="#E07A3F", label="15-minute maximum")
    ax.set(title="Household 1 electricity across available dates", ylabel="Power (W)", xlabel="Date (timezone not assigned)")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax.grid(alpha=.2); ax.legend(frameon=False)
    paths.append(_save(fig, out / "power-over-time.png"))

    profile = d.groupby("interval_start_second")[POWER].agg(
        mean="mean", median="median", q25=lambda s: s.quantile(.25), q75=lambda s: s.quantile(.75)
    )
    x = profile.index.to_numpy() / 60
    fig, ax = plt.subplots(figsize=(11, 4.8))
    ax.fill_between(x, profile.q25, profile.q75, color="#77AADD", alpha=.28, label="25th–75th percentile")
    ax.plot(x, profile["median"], color="#176B87", lw=1.8, label="Median")
    ax.plot(x, profile["mean"], color="#D35F5F", lw=1.3, label="Mean")
    ax.set(title="Daily 15-minute consumption profile", xlabel="Time of day", ylabel="Mean total power (W)")
    ax.set_xticks(np.arange(0, 1441, 120), [f"{h:02d}:00" for h in range(0, 25, 2)])
    ax.grid(alpha=.2); ax.legend(frameon=False)
    paths.append(_save(fig, out / "daily-consumption-profile.png"))

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.7))
    for ax, col, title in [
        (axes[0], POWER, "15-minute mean power"),
        (axes[1], "powerallphases_max_w", "15-minute maximum power"),
    ]:
        values = d[col]
        ax.hist(values, bins=60, color="#2B8C7E", edgecolor="white", linewidth=.3)
        ax.axvline(values.quantile(.99), color="#B23A48", ls="--", label="99th percentile")
        ax.set(title=title, xlabel="Power (W)", ylabel="Intervals")
        ax.grid(axis="y", alpha=.2); ax.legend(frameon=False)
    fig.suptitle("Power distributions (descriptive, not anomaly thresholds)")
    paths.append(_save(fig, out / "power-distribution.png"))

    fig, ax = plt.subplots(figsize=(8, 5.2))
    sc = ax.scatter(d["occupancy_fraction"], d[POWER], c=d["powerallphases_max_w"],
                    cmap="viridis", s=13, alpha=.42, linewidths=0)
    fig.colorbar(sc, ax=ax, label="Interval maximum (W)")
    ax.set(title="Occupancy fraction versus mean power",
           xlabel="Occupied fraction of interval", ylabel="Mean total power (W)")
    ax.grid(alpha=.2)
    paths.append(_save(fig, out / "occupancy-vs-power.png"))

    daily = d.groupby(["date", "is_weekend"], as_index=False).agg(
        daily_mean_w=(POWER, "mean"), daily_energy_wh=("energy_wh", "sum")
    )
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.8))
    for ax, col, title, ylabel in [
        (axes[0], "daily_mean_w", "Daily average power", "Power (W)"),
        (axes[1], "daily_energy_wh", "Daily energy", "Energy (Wh)"),
    ]:
        groups = [daily.loc[~daily.is_weekend, col], daily.loc[daily.is_weekend, col]]
        ax.boxplot(groups, tick_labels=[f"Weekday\nn={len(groups[0])}", f"Weekend\nn={len(groups[1])}"], showfliers=False)
        for xpos, vals in enumerate(groups, 1):
            ax.scatter(np.full(len(vals), xpos), vals, s=15, alpha=.35, color="#176B87")
        ax.set(title=title, ylabel=ylabel); ax.grid(axis="y", alpha=.2)
    fig.suptitle("Weekday/weekend comparison by day")
    paths.append(_save(fig, out / "weekday-weekend-comparison.png"))

    fig, ax = plt.subplots(figsize=(7.5, 5.6))
    sc = ax.scatter(d[POWER], d["powerallphases_max_w"], c=d["occupancy_fraction"],
                    cmap="plasma", s=14, alpha=.48, linewidths=0)
    fig.colorbar(sc, ax=ax, label="Occupancy fraction")
    upper = max(d[POWER].max(), d["powerallphases_max_w"].max())
    ax.plot([0, upper], [0, upper], color="black", ls=":", label="maximum = mean")
    ax.set(title="Interval mean versus maximum power", xlabel="Mean total power (W)",
           ylabel="Maximum total power (W)")
    ax.grid(alpha=.2); ax.legend(frameon=False)
    paths.append(_save(fig, out / "mean-vs-maximum-power.png"))

    hourly = d.groupby("hour").agg(mean_w=(POWER, "mean"), max_mean_w=("powerallphases_max_w", "mean"))
    fig, ax = plt.subplots(figsize=(10.5, 4.8))
    ax.plot(hourly.index, hourly.mean_w, marker="o", color="#176B87", label="Mean of interval means")
    ax.plot(hourly.index, hourly.max_mean_w, marker="o", color="#E07A3F", label="Mean of interval maxima")
    ax.set(title="Power by hour of day", xlabel="Hour (timezone unset)", ylabel="Power (W)", xticks=range(24))
    ax.grid(alpha=.2); ax.legend(frameon=False)
    paths.append(_save(fig, out / "hourly-power-pattern.png"))
    return paths


def _report(frame: pd.DataFrame, parquet_path: Path, figures: list[Path]) -> str:
    d = frame
    try:
        source_name = parquet_path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        source_name = parquet_path.name
    days = sorted(d.date.dt.strftime("%Y-%m-%d").unique())
    n = len(days); train_end = round(.60 * n); valid_end = round(.80 * n)
    partitions = [days[:train_end], days[train_end:valid_end], days[valid_end:]]
    changes = d.groupby("date")[POWER].diff().abs().dropna()
    unoccupied = d[d.occupancy_state == "unoccupied"]
    p99 = d[POWER].quantile(.99); p999max = d.powerallphases_max_w.quantile(.999)
    p99change = changes.quantile(.99)
    energy_resid = (d.energy_wh - d[POWER] * .25).abs().max()
    phase_sum = d[["powerl1_mean_w", "powerl2_mean_w", "powerl3_mean_w"]].sum(axis=1)
    phase_resid = (d[POWER] - phase_sum).abs().max()
    daily = d.groupby("date").agg(mean_w=(POWER, "mean"), energy_wh=("energy_wh", "sum"))
    day_type = d.groupby("is_weekend").agg(days=("date", "nunique"), intervals=(POWER, "size"),
                    mean_w=(POWER, "mean"), mean_interval_max=("powerallphases_max_w", "mean"),
                    occupancy=("occupancy_fraction", "mean"))
    occ = d.groupby("occupancy_state").agg(n=(POWER, "size"), mean_w=(POWER, "mean"),
            median_w=(POWER, "median"), p95_w=(POWER, lambda s: s.quantile(.95)),
            max_peak_w=("powerallphases_max_w", "max"))
    hourly = d.groupby("hour").agg(mean_w=(POWER, "mean"), mean_max=("powerallphases_max_w", "mean"),
                                   occupancy=("occupancy_fraction", "mean"))
    highest_hours = hourly.mean_w.nlargest(3)
    lowest_hour = int(hourly.mean_w.idxmin())
    weekday_mean = float(day_type.loc[False, "mean_w"])
    weekend_mean = float(day_type.loc[True, "mean_w"])
    largest_interval = d.loc[d[POWER].idxmax()]
    transition = d.assign(abs_change=d.groupby("date")[POWER].diff().abs()).nlargest(5, "abs_change")

    lines = [
        "# Exploratory data analysis — ECO Household 1", "",
        "## Scope and interpretation", "",
        f"Generated from {source_name}. This reads the existing Phase 2B Parquet; it does not modify it or train a model.",
        f"The {n} clean matched dates span {d.date.min().date()} through {d.date.max().date()}, in summer and winter blocks separated by a long gap. Time fields remain timezone-naive because the source has no absolute timestamp or UTC offset.",
        "All tails, high peaks, and large changes below are exploratory review candidates—not confirmed anomalies, labels, or operational thresholds.", "",
        "## Dataset verification", "",
        f"- Shape: **{len(d):,} rows × {d.shape[1]} columns**; **{n} dates**, 96 intervals per date.",
        f"- Date range: **{d.date.min().date()} to {d.date.max().date()}**.",
        f"- Missing values: **{int(d.isna().sum().sum())}**; duplicate date/interval keys: **{int(d.duplicated(['date', 'interval_start_second']).sum())}**.",
        f"- Mean total power: **{d[POWER].min():.2f}–{d[POWER].max():.2f} W**; interval maximum: **{d.powerallphases_max_w.min():.2f}–{d.powerallphases_max_w.max():.2f} W**.",
        f"- Occupancy fraction: **{d.occupancy_fraction.min():.2f}–{d.occupancy_fraction.max():.2f}**; state counts: {d.occupancy_state.value_counts().to_dict()}.",
        f"- Energy per interval: **{d.energy_wh.min():.2f}–{d.energy_wh.max():.2f} Wh**; max difference from mean power × 0.25 h: **{energy_resid:.3g} Wh**.",
        f"- Max difference between total mean power and sum of phase means: **{phase_resid:.3g} W**.", "",
        "### Electricity and occupancy feature ranges", "",
        "| Feature | Minimum | Maximum | Unit |", "| --- | ---: | ---: | --- |",
    ]
    for col, unit in [
        (POWER, "W"), ("powerallphases_max_w", "W"), ("powerallphases_min_w", "W"),
        ("powerallphases_std_w", "W"), ("energy_wh", "Wh/interval"),
        ("powerl1_mean_w", "W"), ("powerl2_mean_w", "W"), ("powerl3_mean_w", "W"),
        ("occupancy_fraction", "fraction"),
    ]:
        lines.append(f"| {col} | {d[col].min():.4f} | {d[col].max():.4f} | {unit} |")
    lines += ["", "### Schema and null counts", "", "| Column | dtype | Nulls |", "| --- | --- | ---: |"]
    lines += [f"| {c} | {dt} | {int(d[c].isna().sum())} |" for c, dt in d.dtypes.items()]
    desc = d[[POWER, "powerallphases_max_w", "powerallphases_std_w"]].describe(
        percentiles=[.25, .5, .75, .95, .99]
    )
    lines += ["", "## Overall electricity distribution", "",
        "Power is strongly right-skewed: most intervals are near lower household load while a smaller upper tail contains much larger means and peaks.",
        "", "| Statistic | Mean total power (W) | Interval maximum (W) | Within-interval std dev (W) |",
        "| --- | ---: | ---: | ---: |"]
    for key, label in [("mean", "Mean"), ("std", "Standard deviation"), ("min", "Minimum"),
                       ("25%", "25th percentile"), ("50%", "Median"), ("75%", "75th percentile"),
                       ("95%", "95th percentile"), ("99%", "99th percentile"), ("max", "Maximum")]:
        lines.append("| " + label + " | " + " | ".join(f"{desc.loc[key, c]:,.2f}" for c in desc.columns) + " |")
    lines += ["", f"Daily mean power median: **{daily.mean_w.median():,.2f} W** (range {daily.mean_w.min():,.2f}–{daily.mean_w.max():,.2f} W). Daily energy median: **{daily.energy_wh.median():,.2f} Wh** (range {daily.energy_wh.min():,.2f}–{daily.energy_wh.max():,.2f} Wh).", "",
        "## Daily and hourly patterns", "",
        f"Hourly mean interval power is highest at {', '.join(f'{int(h):02d}:00 ({v:.1f} W)' for h, v in highest_hours.items())}; the low is {lowest_hour:02d}:00 ({hourly.loc[lowest_hour, 'mean_w']:.1f} W). These describe only the observed date blocks.",
        "", "| Hour | Mean power (W) | Mean interval max (W) | Mean occupancy fraction |",
        "| ---: | ---: | ---: | ---: |"]
    for h, row in hourly.iterrows():
        lines.append(f"| {h:02d}:00 | {row.mean_w:.1f} | {row.mean_max:.1f} | {row.occupancy:.2f} |")
    lines += ["", "The daily profile plot shows median power and the 25th–75th percentile band at each time of day. Summer and winter observations are separated by a long gap, so this is not a controlled seasonal comparison.", "",
        "## Weekday versus weekend", "",
        "| Day type | Days | Intervals | Mean power (W) | Mean interval max (W) | Mean occupancy |",
        "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for weekend, row in day_type.iterrows():
        label = "Weekend" if weekend else "Weekday"
        lines.append(f"| {label} | {int(row.days)} | {int(row.intervals):,} | {row.mean_w:.2f} | {row.mean_interval_max:.2f} | {row.occupancy:.3f} |")
    lines += ["", f"Weekend mean interval power is {weekend_mean:.2f} W versus {weekday_mean:.2f} W on weekdays ({int(day_type.loc[True, 'days'])} weekend days, {int(day_type.loc[False, 'days'])} weekdays). This descriptive difference is not evidence of a stable weekend effect.", "",
        "## Occupancy context", "",
        "| Occupancy state | Intervals | Mean power (W) | Median power (W) | 95th percentile (W) | Highest interval max (W) |",
        "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for state in ["unoccupied", "mixed", "occupied"]:
        row = occ.loc[state]
        lines.append(f"| {state.title()} | {int(row.n):,} | {row.mean_w:.2f} | {row.median_w:.2f} | {row.p95_w:.2f} | {row.max_peak_w:.2f} |")
    lines += ["", f"Fully occupied intervals average more than fully unoccupied intervals, but distributions overlap. **{int((unoccupied[POWER] > p99).sum())} unoccupied intervals** exceed the overall 99th percentile of interval mean power ({p99:.1f} W); the highest unoccupied interval mean is {unoccupied[POWER].max():.1f} W and highest one-second peak is {unoccupied.powerallphases_max_w.max():.1f} W. These deserve contextual review; occupancy labels can be imperfect and background appliances can remain on.", "",
        "## Exploratory unusual readings and changes", "",
        f"- Mean power 99th percentile: **{p99:.1f} W**; interval maximum 99.9th percentile: **{p999max:.1f} W**. Highest interval mean: **{d[POWER].max():.1f} W**; highest one-second peak: **{d.powerallphases_max_w.max():.1f} W**.",
        f"- Absolute change between adjacent interval means within a date: 99th percentile **{p99change:.1f} W**; largest **{changes.max():.1f} W**.",
        "- These quantiles describe the observed tail, not anomaly cutoffs. High consumption may be legitimate appliance use; sharp transitions may be normal switching.", "",
        "### Highest sustained interval means (review candidates)", "",
        "| Date | Time | Mean power (W) | Interval max (W) | Occupancy fraction |",
        "| --- | --- | ---: | ---: | ---: |"]
    for _, row in d.nlargest(8, POWER).iterrows():
        lines.append(f"| {row.date.date()} | {row.time_of_day} | {row[POWER]:.2f} | {row.powerallphases_max_w:.2f} | {row.occupancy_fraction:.2f} |")
    lines += ["", f"The largest sustained interval is {largest_interval.date.date()} at {largest_interval.time_of_day}: mean {largest_interval[POWER]:,.2f} W and interval maximum {largest_interval.powerallphases_max_w:,.2f} W, with occupancy fraction {largest_interval.occupancy_fraction:.2f}. It is a high-use observation, not a confirmed fault.", "",
        "### Highest unoccupied interval means (review candidates)", "",
        "| Date | Time | Mean power (W) | Interval max (W) |", "| --- | --- | ---: | ---: |"]
    for _, row in unoccupied.nlargest(8, POWER).iterrows():
        lines.append(f"| {row.date.date()} | {row.time_of_day} | {row[POWER]:.2f} | {row.powerallphases_max_w:.2f} |")
    lines += ["", "### Largest adjacent-interval changes (review candidates)", "",
        "| Date | Current interval | Absolute mean-power change (W) | Current interval mean (W) | Occupancy fraction |",
        "| --- | --- | ---: | ---: | ---: |"]
    for _, row in transition.iterrows():
        lines.append(f"| {row.date.date()} | {row.time_of_day} | {row.abs_change:.2f} | {row[POWER]:.2f} | {row.occupancy_fraction:.2f} |")
    lines += ["", "Check appliance schedules, occupancy-label timing, and alignment before treating any of these as anomalies.", "",
        "## Feature recommendations for a future Isolation Forest", "",
        "| Feature | Recommendation | Reason |", "| --- | --- | --- |",
        "| powerallphases_mean_w | Include | Sustained load level. |",
        "| powerallphases_max_w | Include initially | Captures peaks that the mean can hide; assess sensitivity to one-second spikes. |",
        "| powerallphases_std_w | Include initially | Captures within-interval variability. |",
        "| powerallphases_min_w | Compare as optional | Could capture baseload drops, but likely overlaps with level/variability. |",
        "| energy_wh | Do not include with mean | At fixed 15 minutes it equals mean W × 0.25 h; choose one representation. |",
        "| powerl1/l2/l3_mean_w | Omit from first model alongside total | Their sum reconstructs total mean within rounding; add only for phase-imbalance analysis. |",
        "| occupancy_fraction | Include if available at inference; compare with no-occupancy model | Adds context, but labels may be imperfect and unavailable in deployment. Do not include state as a duplicate. |",
        "| Time of day | Encode as sine and cosine of 2π × second_of_day / 86,400 | Cyclic encoding keeps midnight adjacent to the day's end. Do not assign a timezone. |",
        "| Day of week | Use compact categorical/weekly cyclic encoding or weekend flag | day_of_week, day_name, and is_weekend overlap in information. |", "",
        f"Maximum mean-energy identity residual: {energy_resid:.3g} Wh; phase means reconstruct total mean within {phase_resid:.3g} W. A reasonable first candidate is mean, maximum, standard deviation, occupancy fraction (when reliable), and cyclic time-of-day. This report does not train or score an Isolation Forest.", "",
        "## Chronological evaluation recommendation", "",
        "Keep all intervals from a date in one partition. A reproducible 60/20/20 split over sorted clean dates is:", "",
        "| Partition | Date range | Days |", "| --- | --- | ---: |"]
    for name, part in zip(["Train", "Validation", "Test holdout"], partitions):
        lines.append(f"| {name} | {part[0]}–{part[-1]} | {len(part)} |")
    lines += ["", "This keeps the final 16 dates untouched for a later test. Training includes summer plus early winter; validation and test are winter-only. The seasonal gap limits generalization claims. Preserve the test block and collect more labeled dates across seasons before deployment conclusions.", "",
        "## Figures", ""]
    lines += [f"- {p.name}" for p in figures]
    lines += ["", "## Reproduce", "",
        "From the repository root, activate the project environment, install requirements-dev.txt, then run:",
        "", "    python -m scripts.eda_eco", "",
        "Options: --input PATH, --figures-dir PATH, and --report PATH. Matching environment variables are ECO_PARQUET_PATH, EDA_FIGURES_DIR, and EDA_REPORT_PATH.", ""]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path(os.getenv("ECO_PARQUET_PATH", DEFAULT_INPUT)))
    parser.add_argument("--figures-dir", type=Path, default=Path(os.getenv("EDA_FIGURES_DIR", ROOT / "reports/figures")))
    parser.add_argument("--report", type=Path, default=Path(os.getenv("EDA_REPORT_PATH", ROOT / "docs/eda-report.md")))
    args = parser.parse_args()
    frame = load_and_validate(args.input)
    figures = make_figures(frame, args.figures_dir)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(_report(frame, args.input, figures), encoding="utf-8")
    print(f"Verified {len(frame):,} rows across {frame.date.nunique()} dates; no missing values.")
    print(f"Wrote {len(figures)} figures to {args.figures_dir}")
    print(f"Wrote report to {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
