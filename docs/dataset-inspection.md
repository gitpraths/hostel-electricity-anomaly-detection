# ECO dataset inspection — Household 1 (Phase 2A)

**Inspection scope:** the supplied files under `database/01/` and
`database/01_occupancy_csv (1)/`. The original files were read only. No
preprocessing outputs or model were created.

## Summary

| Item | Result |
| --- | ---: |
| Smart-meter daily CSV files | 245 |
| Smart-meter date coverage | 2012-06-01 through 2013-01-31 (245/245 calendar dates) |
| Smart-meter rows | 21,168,000 (86,400 in every file) |
| Smart-meter columns | 16 in every row, no header row |
| Occupancy CSV files | 2 (`01_summer.csv`, `01_winter.csv`) |
| Occupancy daily records | 85 (39 summer, 46 winter) |
| Occupancy day shape | 86,400 labels per date, plus a date field |
| Dates present in both sources | 85 |
| Electricity dates without occupancy labels | 160 |
| Occupancy dates without electricity files | 0 |
| Matching electricity days containing `-1` sentinel readings | 6 of 85 |

The dates match the ETH dissertation's published Household 1 coverage summary
(245 smart-meter days between 1 June 2012 and 31 January 2013). ETH describes
the daily smart-meter files as 1 Hz, 86,400-row files and documents `-1` as the
missing-data marker for longer gaps. [ETH ECO data description, Chapter 4](https://vs.inf.ethz.ch/publ/papers/beckel-2015-dissertation.pdf)

## Smart-meter inspection

All 245 files in `database/01/` have filenames parseable as `YYYY-MM-DD.csv`.
The dates are unique, contiguous, and cover 2012-06-01 through 2013-01-31.
Every file has exactly 86,400 rows; all 21,168,000 rows have 16 comma-separated
fields. A full scan found no nonnumeric or non-finite fields and no row-width
errors.

### Official field mapping

The 16 headerless columns correspond, in order, to the 16 aggregate variables
listed in the ETH documentation's Table 4.4. The official names below are
preserved exactly, including their spelling. [ETH ECO data description, Table 4.4](https://vs.inf.ethz.ch/publ/papers/beckel-2015-dissertation.pdf)

| Position (1-based) | Official variable name | Meaning | Unit |
| ---: | --- | --- | --- |
| 1 | `powerallphases` | Sum of real power over all phases | W |
| 2 | `powerl1` | Real power, phase 1 | W |
| 3 | `powerl2` | Real power, phase 2 | W |
| 4 | `powerl3` | Real power, phase 3 | W |
| 5 | `currentneutral` | Neutral current | A |
| 6 | `currentl1` | Current, phase 1 | A |
| 7 | `currentl2` | Current, phase 2 | A |
| 8 | `currentl3` | Current, phase 3 | A |
| 9 | `voltagel1` | Voltage, phase 1 | V |
| 10 | `voltagel2` | Voltage, phase 2 | V |
| 11 | `voltagel3` | Voltage, phase 3 | V |
| 12 | `phaseanglevoltagel21l` | Phase shift, voltage phase 2 relative to phase 1 | degrees |
| 13 | `phaseanglevoltagel31l` | Phase shift, voltage phase 3 relative to phase 1 | degrees |
| 14 | `phaseanglecurrentvoltagel1l` | Current/voltage phase shift, phase 1 | degrees |
| 15 | `phaseanglecurrentvoltagel2` | Current/voltage phase shift, phase 2 | degrees |
| 16 | `phaseanglecurrentvoltagel3` | Current/voltage phase shift, phase 3 | degrees |

### Smart-meter data quality

- The only non-finite/nonnumeric or structurally invalid fields found: **none**.
- The documented `-1` sentinel occurs in all 16 columns at the same aggregate
  row count of **76,928 samples** across the supplied 245 days. No other negative
  numeric readings were found. Do not interpret `-1` as physical electricity
  usage.
- The other observed values are finite. Observed ranges across non-sentinel
  values were: total real power 45.658–9,063.83 W; phase real power 7.185–
  5,614.49 W; current 0–27.1357 A; voltage 224–245 V; phase-angle fields
  0–359 degrees. Ranges are descriptive checks, not independent engineering
  limits.
- In the 85 matching dates, **79 days** contain no `-1` samples. Six matching
  days contain contiguous missing-data runs:

| Date | Missing seconds (`-1`) | Longest run | Start row (1-based) |
| --- | ---: | ---: | ---: |
| 2012-07-21 | 2,299 | 2,299 s | 36,422 |
| 2012-07-22 | 46 | 46 s | 73,026 |
| 2012-07-26 | 9,045 | 9,045 s | 77,356 |
| 2012-07-27 | 23,060 | 23,060 s | 1 |
| 2012-12-07 | 22 | 22 s | 28,795 |
| 2013-01-01 | 23 | 23 s | 15,948 |

  The missing rows are not suitable as ordinary numeric input. A later
  preprocessing decision should either exclude these dates for the first clean
  baseline or explicitly mask/interpolate only under a documented policy; the
  ETH export documentation itself distinguishes short filled gaps from longer
  gaps represented by `-1`.

## Occupancy inspection

Both occupancy files are wide CSV matrices. The first row is a header: first
field blank, followed by 86,400 time labels from `00:00:00` through `23:59:59`.
The time labels are surrounded by literal single-quote characters in the CSV
fields (for example, `'00:00:00'`); this is a formatting quirk to account for
when parsing the header. Each subsequent row has a date in `DD-Mon-YYYY` form
and exactly 86,400 label fields.

| File | Daily rows | First date | Last date | Label count/day |
| --- | ---: | --- | --- | ---: |
| `01_summer.csv` | 39 | 2012-07-15 | 2012-08-25 | 86,400 |
| `01_winter.csv` | 46 | 2012-11-24 | 2013-01-09 | 86,400 |

The 85 dates are unique with no duplicate date rows. Across all 7,344,000 label
cells, values are only `0` and `1`: **1,572,059 zeros** and **5,771,941 ones**.
No blank, missing, or other label values were found. ETH describes the occupancy
coding as 1 when a person is home and 0 otherwise. [ETH ECO data description, occupancy formatting](https://vs.inf.ethz.ch/publ/papers/beckel-2015-dissertation.pdf)

## Date matching

There are **85 overlapping dates**. The table lists every match, one date per
cell; all ranges are inclusive where shown as ranges.

| Summer matches | Winter matches |
| --- | --- |
| 2012-07-15 | 2012-11-24 |
| 2012-07-16 | 2012-11-25 |
| 2012-07-17 | 2012-11-26 |
| 2012-07-18 | 2012-11-27 |
| 2012-07-20 | 2012-11-28 |
| 2012-07-21 | 2012-11-29 |
| 2012-07-22 | 2012-11-30 |
| 2012-07-23 | 2012-12-01 |
| 2012-07-24 | 2012-12-03 |
| 2012-07-25 | 2012-12-04 |
| 2012-07-26 | 2012-12-05 |
| 2012-07-27 | 2012-12-06 |
| 2012-07-28 | 2012-12-07 |
| 2012-07-29 | 2012-12-08 |
| 2012-07-30 | 2012-12-09 |
| 2012-07-31 | 2012-12-10 |
| 2012-08-01 | 2012-12-11 |
| 2012-08-02 | 2012-12-12 |
| 2012-08-03 | 2012-12-13 |
| 2012-08-04 | 2012-12-14 |
| 2012-08-05 | 2012-12-15 |
| 2012-08-06 | 2012-12-16 |
| 2012-08-07 | 2012-12-17 |
| 2012-08-08 | 2012-12-18 |
| 2012-08-09 | 2012-12-19 |
| 2012-08-10 | 2012-12-20 |
| 2012-08-12 | 2012-12-21 |
| 2012-08-13 | 2012-12-22 |
| 2012-08-14 | 2012-12-23 |
| 2012-08-15 | 2012-12-24 |
| 2012-08-16 | 2012-12-25 |
| 2012-08-17 | 2012-12-26 |
| 2012-08-18 | 2012-12-27 |
| 2012-08-19 | 2012-12-28 |
| 2012-08-20 | 2012-12-29 |
| 2012-08-21 | 2012-12-30 |
| 2012-08-23 | 2012-12-31 |
| 2012-08-24 | 2013-01-01 |
| 2012-08-25 | 2013-01-02 |
|  | 2013-01-03 |
|  | 2013-01-04 |
|  | 2013-01-05 |
|  | 2013-01-06 |
|  | 2013-01-07 |
|  | 2013-01-08 |
|  | 2013-01-09 |

### Electricity dates without occupancy labels (160)

These ranges/dates are inclusive and exhaustive; no electricity date is omitted
from this list:

| Date range or date | Count |
| --- | ---: |
| 2012-06-01 through 2012-07-14 | 44 |
| 2012-07-19 | 1 |
| 2012-08-11 | 1 |
| 2012-08-22 | 1 |
| 2012-08-26 through 2012-08-31 | 6 |
| 2012-09-01 through 2012-09-30 | 30 |
| 2012-10-01 through 2012-10-31 | 31 |
| 2012-11-01 through 2012-11-23 | 23 |
| 2012-12-02 | 1 |
| 2013-01-10 through 2013-01-31 | 22 |
| **Total** | **160** |

There are no occupancy-only dates. Occupancy coverage contains gaps in July,
August, and December, then ends on 2013-01-09; it does not span the full
smart-meter period.

## Alignment, frequency, and clock limitations

- Smart-meter rows have no timestamp column. Per ETH's format description, row
  order represents 1 Hz samples for the day. Occupancy columns explicitly cover
  each second from midnight through 23:59:59. Therefore, the available alignment
  is by filename/date and row/column position (sample index 0–86,399), not by
  independently recorded timestamps.
- Both sources have exactly 86,400 positions per date, with no missing/extra
  second slots. There is no absolute timestamp or timezone field in the supplied
  smart-meter CSVs. The files alone cannot prove whether those positions should
  be interpreted as Swiss local time, UTC, or another clock convention. Keep
  them as date plus second-of-day until confirmed from the export provenance.
- Swiss daylight-saving transitions require care when converting to timezone-
  aware timestamps. These fixed 86,400-position files do not record an offset or
  repeated/skipped local times. The 2012-10-28 smart-meter day exists but has no
  occupancy record, so it is not part of the overlap. Do not invent DST offsets
  or infer absolute timestamps from the row number alone.
- The occupancy time header contains literal quote marks around each second
  label; data values themselves are plain `0`/`1`. Parser logic must handle the
  header quirk without shifting label positions.

## Recommendations for the first dataset slice

1. **Start with the 79 fully matched, sentinel-free days.** Exclude the six
   matching dates in the missing-sample table for the first baseline. This gives
   clean, 1 Hz electricity/occupancy alignment for initial analysis. Preserve
   the other matched dates for a later missing-data policy rather than silently
   converting `-1` to zero or interpolating long gaps.
2. **Keep time-of-day context.** Begin with `powerallphases` and its three
   phase-power components. Add time-of-day, weekday/weekend, and occupancy
   context. Voltage/current/phase-angle measurements can support power-quality
   or sensor-fault features, but add them after checking their utility and
   stability. Avoid feeding redundant derived fields without validation.
3. **Aggregate for initial behavior monitoring, while retaining spike
   information.** A 15-minute interval is a practical first resolution and is
   consistent with published ECO occupancy-feature analysis. For each interval,
   derive mean and maximum total power, variability (for example standard
   deviation or quantiles), and energy; use a short-resolution peak/count
   feature if brief high-load events matter. Do not discard raw 1 Hz data in the
   source layer. [ETH occupancy analysis paper](https://vs.inf.ethz.ch/publ/papers/kleiminger_ubicomp2015.pdf)
4. **Use occupancy as context, not as a substitute for electricity.** Align the
   0/1 occupancy label to each second, then derive an interval occupancy state
   or occupied fraction. Compare expected power patterns by occupancy state
   and time-of-day, while keeping unknown occupancy explicitly missing on the
   other 160 electricity dates. Do not train/evaluate as if unlabeled days were
   unoccupied. A later evaluation should hold out contiguous time blocks rather
   than randomly mixing adjacent seconds.
5. **Treat this as a household-specific pilot.** The 79 clean matched dates are
   adequate for inspection and a first baseline experiment, but they cover only
   Household 1 and have seasonal gaps. Verify generalization on later/new data
   before presenting the detector as suitable for hostel operations.

## Inconsistencies and decisions for preprocessing approval

- The supplied occupancy files encode times as CSV header labels with literal
  single quotes; handle this format explicitly.
- Electricity lacks timestamps/timezone metadata; confirm the intended clock
  convention if calendar-time conversion is needed.
- Six overlap days have documented `-1` missing runs (22 seconds to 23,060
  seconds). The initial recommendation is to exclude them from the clean first
  slice; decide later whether to add masking or another missing-data treatment.
- Occupancy is present for 85 of 245 electricity days, with 160 days lacking
  labels. Keep occupancy missing on those days.
- The supplied originals currently reside under `database/01/` and
  `database/01_occupancy_csv (1)/`. The existing `.gitignore` does not exclude
  these CSV paths by name, so do not stage them when initializing or committing
  the repository. A later repository-hygiene change should explicitly ignore
  the received raw-data locations or store raw exports outside the repository.

No preprocessing has been implemented. Approval is needed before starting the
next phase.
