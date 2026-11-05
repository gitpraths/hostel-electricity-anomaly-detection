# Exploratory data analysis — ECO Household 1

## Scope and interpretation

Generated from data/processed/eco_household_1_15min.parquet. This reads the existing Phase 2B Parquet; it does not modify it or train a model.
The 79 clean matched dates span 2012-07-15 through 2013-01-09, in summer and winter blocks separated by a long gap. Time fields remain timezone-naive because the source has no absolute timestamp or UTC offset.
All tails, high peaks, and large changes below are exploratory review candidates—not confirmed anomalies, labels, or operational thresholds.

## Dataset verification

- Shape: **7,584 rows × 18 columns**; **79 dates**, 96 intervals per date.
- Date range: **2012-07-15 to 2013-01-09**.
- Missing values: **0**; duplicate date/interval keys: **0**.
- Mean total power: **50.70–5608.17 W**; interval maximum: **51.38–9063.83 W**.
- Occupancy fraction: **0.00–1.00**; state counts: {'occupied': 5923, 'unoccupied': 1545, 'mixed': 116}.
- Energy per interval: **12.67–1402.04 Wh**; max difference from mean power × 0.25 h: **0 Wh**.
- Max difference between total mean power and sum of phase means: **0.000339 W**.

### Electricity and occupancy feature ranges

| Feature | Minimum | Maximum | Unit |
| --- | ---: | ---: | --- |
| powerallphases_mean_w | 50.6992 | 5608.1734 | W |
| powerallphases_max_w | 51.3790 | 9063.8300 | W |
| powerallphases_min_w | 49.5200 | 2213.1900 | W |
| powerallphases_std_w | 0.2409 | 2177.8561 | W |
| energy_wh | 12.6748 | 1402.0433 | Wh/interval |
| powerl1_mean_w | 23.5712 | 3519.2255 | W |
| powerl2_mean_w | 16.0368 | 1663.1977 | W |
| powerl3_mean_w | 8.1519 | 1716.0693 | W |
| occupancy_fraction | 0.0000 | 1.0000 | fraction |

### Schema and null counts

| Column | dtype | Nulls |
| --- | --- | ---: |
| date | datetime64[s] | 0 |
| interval_start_second | int64 | 0 |
| time_of_day | str | 0 |
| hour | int64 | 0 |
| day_of_week | int64 | 0 |
| day_name | str | 0 |
| is_weekend | bool | 0 |
| powerallphases_mean_w | float64 | 0 |
| powerallphases_max_w | float64 | 0 |
| powerallphases_min_w | float64 | 0 |
| powerallphases_std_w | float64 | 0 |
| energy_wh | float64 | 0 |
| occupancy_fraction | float64 | 0 |
| occupancy_state | str | 0 |
| interval_seconds | int64 | 0 |
| powerl1_mean_w | float64 | 0 |
| powerl2_mean_w | float64 | 0 |
| powerl3_mean_w | float64 | 0 |

## Overall electricity distribution

Power is strongly right-skewed: most intervals are near lower household load while a smaller upper tail contains much larger means and peaks.

| Statistic | Mean total power (W) | Interval maximum (W) | Within-interval std dev (W) |
| --- | ---: | ---: | ---: |
| Mean | 290.61 | 682.01 | 151.81 |
| Standard deviation | 384.84 | 900.88 | 299.32 |
| Minimum | 50.70 | 51.38 | 0.24 |
| 25th percentile | 95.30 | 142.68 | 12.86 |
| Median | 133.89 | 231.05 | 21.26 |
| 75th percentile | 292.76 | 821.93 | 66.41 |
| 95th percentile | 1,190.74 | 2,517.30 | 965.01 |
| 99th percentile | 1,838.87 | 3,801.37 | 1,120.50 |
| Maximum | 5,608.17 | 9,063.83 | 2,177.86 |

Daily mean power median: **289.61 W** (range 101.86–534.54 W). Daily energy median: **6,950.61 Wh** (range 2,444.69–12,828.94 Wh).

## Daily and hourly patterns

Hourly mean interval power is highest at 22:00 (560.4 W), 21:00 (501.5 W), 17:00 (470.0 W); the low is 02:00 (101.1 W). These describe only the observed date blocks.

| Hour | Mean power (W) | Mean interval max (W) | Mean occupancy fraction |
| ---: | ---: | ---: | ---: |
| 00:00 | 168.0 | 358.5 | 0.90 |
| 01:00 | 111.1 | 241.6 | 0.90 |
| 02:00 | 101.1 | 196.3 | 0.90 |
| 03:00 | 105.1 | 228.7 | 0.90 |
| 04:00 | 145.9 | 411.1 | 0.90 |
| 05:00 | 213.0 | 626.3 | 0.90 |
| 06:00 | 182.6 | 482.0 | 0.91 |
| 07:00 | 296.5 | 848.1 | 0.91 |
| 08:00 | 351.2 | 955.9 | 0.83 |
| 09:00 | 340.0 | 855.2 | 0.66 |
| 10:00 | 293.3 | 732.6 | 0.57 |
| 11:00 | 429.7 | 1107.8 | 0.60 |
| 12:00 | 325.0 | 899.4 | 0.66 |
| 13:00 | 303.1 | 745.6 | 0.68 |
| 14:00 | 263.2 | 676.0 | 0.67 |
| 15:00 | 198.8 | 440.9 | 0.59 |
| 16:00 | 239.8 | 476.9 | 0.58 |
| 17:00 | 470.0 | 1040.8 | 0.69 |
| 18:00 | 422.4 | 994.9 | 0.80 |
| 19:00 | 320.5 | 619.1 | 0.83 |
| 20:00 | 322.0 | 762.6 | 0.86 |
| 21:00 | 501.5 | 954.7 | 0.89 |
| 22:00 | 560.4 | 1064.4 | 0.91 |
| 23:00 | 310.4 | 649.0 | 0.91 |

The daily profile plot shows median power and the 25th–75th percentile band at each time of day. Summer and winter observations are separated by a long gap, so this is not a controlled seasonal comparison.

## Weekday versus weekend

| Day type | Days | Intervals | Mean power (W) | Mean interval max (W) | Mean occupancy |
| --- | ---: | ---: | ---: | ---: | ---: |
| Weekday | 57 | 5,472 | 288.77 | 683.09 | 0.806 |
| Weekend | 22 | 2,112 | 295.36 | 679.21 | 0.744 |

Weekend mean interval power is 295.36 W versus 288.77 W on weekdays (22 weekend days, 57 weekdays). This descriptive difference is not evidence of a stable weekend effect.

## Occupancy context

| Occupancy state | Intervals | Mean power (W) | Median power (W) | 95th percentile (W) | Highest interval max (W) |
| --- | ---: | ---: | ---: | ---: | ---: |
| Unoccupied | 1,545 | 127.61 | 99.54 | 183.08 | 3315.03 |
| Mixed | 116 | 367.28 | 173.92 | 1282.73 | 5881.78 |
| Occupied | 5,923 | 331.62 | 155.65 | 1304.70 | 9063.83 |

Fully occupied intervals average more than fully unoccupied intervals, but distributions overlap. **2 unoccupied intervals** exceed the overall 99th percentile of interval mean power (1838.9 W); the highest unoccupied interval mean is 2408.7 W and highest one-second peak is 3315.0 W. These deserve contextual review; occupancy labels can be imperfect and background appliances can remain on.

## Exploratory unusual readings and changes

- Mean power 99th percentile: **1838.9 W**; interval maximum 99.9th percentile: **5476.2 W**. Highest interval mean: **5608.2 W**; highest one-second peak: **9063.8 W**.
- Absolute change between adjacent interval means within a date: 99th percentile **1538.9 W**; largest **4579.8 W**.
- These quantiles describe the observed tail, not anomaly cutoffs. High consumption may be legitimate appliance use; sharp transitions may be normal switching.

### Highest sustained interval means (review candidates)

| Date | Time | Mean power (W) | Interval max (W) | Occupancy fraction |
| --- | --- | ---: | ---: | ---: |
| 2012-11-24 | 17:45:00 | 5608.17 | 9063.83 | 1.00 |
| 2013-01-05 | 17:45:00 | 3533.98 | 5089.33 | 1.00 |
| 2012-12-28 | 09:45:00 | 3387.00 | 3581.03 | 1.00 |
| 2013-01-05 | 19:30:00 | 2948.72 | 4382.40 | 1.00 |
| 2012-12-05 | 17:15:00 | 2853.02 | 4540.77 | 1.00 |
| 2012-11-28 | 08:30:00 | 2758.37 | 4699.23 | 0.58 |
| 2012-12-26 | 11:15:00 | 2748.45 | 5725.73 | 1.00 |
| 2012-12-20 | 12:15:00 | 2693.66 | 3254.85 | 1.00 |

The largest sustained interval is 2012-11-24 at 17:45:00: mean 5,608.17 W and interval maximum 9,063.83 W, with occupancy fraction 1.00. It is a high-use observation, not a confirmed fault.

### Highest unoccupied interval means (review candidates)

| Date | Time | Mean power (W) | Interval max (W) |
| --- | --- | ---: | ---: |
| 2012-11-27 | 14:00:00 | 2408.70 | 2513.72 |
| 2012-12-19 | 10:30:00 | 2008.64 | 2522.83 |
| 2012-11-28 | 11:30:00 | 1609.22 | 3175.32 |
| 2012-11-28 | 09:00:00 | 1595.19 | 2574.84 |
| 2012-08-05 | 19:00:00 | 1580.37 | 2451.10 |
| 2012-12-18 | 09:15:00 | 1486.41 | 2307.89 |
| 2012-07-28 | 10:00:00 | 1473.24 | 2292.75 |
| 2012-07-16 | 10:00:00 | 1437.15 | 2331.93 |

### Largest adjacent-interval changes (review candidates)

| Date | Current interval | Absolute mean-power change (W) | Current interval mean (W) | Occupancy fraction |
| --- | --- | ---: | ---: | ---: |
| 2012-11-24 | 18:00:00 | 4579.81 | 1028.36 | 1.00 |
| 2012-11-24 | 17:45:00 | 4238.66 | 5608.17 | 1.00 |
| 2013-01-05 | 18:00:00 | 2957.08 | 576.90 | 1.00 |
| 2012-11-28 | 08:45:00 | 2401.41 | 356.96 | 0.00 |
| 2012-12-05 | 17:15:00 | 2311.12 | 2853.02 | 1.00 |

Check appliance schedules, occupancy-label timing, and alignment before treating any of these as anomalies.

## Feature recommendations for a future Isolation Forest

| Feature | Recommendation | Reason |
| --- | --- | --- |
| powerallphases_mean_w | Include | Sustained load level. |
| powerallphases_max_w | Include initially | Captures peaks that the mean can hide; assess sensitivity to one-second spikes. |
| powerallphases_std_w | Include initially | Captures within-interval variability. |
| powerallphases_min_w | Compare as optional | Could capture baseload drops, but likely overlaps with level/variability. |
| energy_wh | Do not include with mean | At fixed 15 minutes it equals mean W × 0.25 h; choose one representation. |
| powerl1/l2/l3_mean_w | Omit from first model alongside total | Their sum reconstructs total mean within rounding; add only for phase-imbalance analysis. |
| occupancy_fraction | Include if available at inference; compare with no-occupancy model | Adds context, but labels may be imperfect and unavailable in deployment. Do not include state as a duplicate. |
| Time of day | Encode as sine and cosine of 2π × second_of_day / 86,400 | Cyclic encoding keeps midnight adjacent to the day's end. Do not assign a timezone. |
| Day of week | Use compact categorical/weekly cyclic encoding or weekend flag | day_of_week, day_name, and is_weekend overlap in information. |

Maximum mean-energy identity residual: 0 Wh; phase means reconstruct total mean within 0.000339 W. A reasonable first candidate is mean, maximum, standard deviation, occupancy fraction (when reliable), and cyclic time-of-day. This report does not train or score an Isolation Forest.

## Chronological evaluation recommendation

Keep all intervals from a date in one partition. A reproducible 60/20/20 split over sorted clean dates is:

| Partition | Date range | Days |
| --- | --- | ---: |
| Train | 2012-07-15–2012-12-06 | 47 |
| Validation | 2012-12-08–2012-12-23 | 16 |
| Test holdout | 2012-12-24–2013-01-09 | 16 |

This keeps the final 16 dates untouched for a later test. Training includes summer plus early winter; validation and test are winter-only. The seasonal gap limits generalization claims. Preserve the test block and collect more labeled dates across seasons before deployment conclusions.

## Figures

- power-over-time.png
- daily-consumption-profile.png
- power-distribution.png
- occupancy-vs-power.png
- weekday-weekend-comparison.png
- mean-vs-maximum-power.png
- hourly-power-pattern.png

## Reproduce

From the repository root, activate the project environment, install requirements-dev.txt, then run:

    python -m scripts.eda_eco

Options: --input PATH, --figures-dir PATH, and --report PATH. Matching environment variables are ECO_PARQUET_PATH, EDA_FIGURES_DIR, and EDA_REPORT_PATH.
