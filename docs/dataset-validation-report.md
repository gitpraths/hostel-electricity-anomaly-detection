# ECO Household 1 preprocessing validation report

Generated from the original supplied CSV exports. The script did not modify raw files.

## Summary

| Check | Result |
| --- | ---: |
| Electricity files discovered | 245 |
| Electricity dates with valid 86,400 × 16 files | 245 |
| Electricity input rows inspected | 21,168,000 |
| Occupancy files | 2 |
| Occupancy dates and 86,400-label rows | 85 |
| Dates present in both sources | 85 |
| Clean matched dates included | 79 |
| Matched dates excluded for -1 sentinel | 6 |
| Output interval | 15 minutes |
| Output interval records | 7,584 |

## Validation checks

- Non-finite electricity cells: 0.
- Nonnumeric electricity cells: 0.
- Electricity rows with wrong width: 0.
- Occupancy labels outside 0/1: 0.
- Occupancy rows with wrong width: 0.
- Electricity samples with -1 sentinel (rows, any channel): 76,928.
- Electricity files rejected: 0.
- Occupancy dates are aligned to electricity by filename date and sample position 0–86,399.
- Electricity files have no independent timestamps; no timezone/UTC offset was assigned.

### Sentinel dates

| Date | Rows with sentinel | Action |
| --- | ---: | --- |
| 2012-06-29 | 930 | not emitted (no complete clean match) |
| 2012-06-30 | 43 | not emitted (no complete clean match) |
| 2012-07-01 | 183 | not emitted (no complete clean match) |
| 2012-07-21 | 2,299 | excluded (matched date) |
| 2012-07-22 | 46 | excluded (matched date) |
| 2012-07-26 | 9,045 | excluded (matched date) |
| 2012-07-27 | 23,060 | excluded (matched date) |
| 2012-08-29 | 625 | not emitted (no complete clean match) |
| 2012-08-30 | 306 | not emitted (no complete clean match) |
| 2012-09-06 | 77 | not emitted (no complete clean match) |
| 2012-09-22 | 57 | not emitted (no complete clean match) |
| 2012-09-30 | 56 | not emitted (no complete clean match) |
| 2012-10-16 | 23 | not emitted (no complete clean match) |
| 2012-10-25 | 66 | not emitted (no complete clean match) |
| 2012-11-14 | 16 | not emitted (no complete clean match) |
| 2012-12-02 | 39,982 | not emitted (no complete clean match) |
| 2012-12-07 | 22 | excluded (matched date) |
| 2013-01-01 | 23 | excluded (matched date) |
| 2013-01-10 | 23 | not emitted (no complete clean match) |
| 2013-01-13 | 23 | not emitted (no complete clean match) |
| 2013-01-27 | 23 | not emitted (no complete clean match) |

### Date matching

#### Included dates

- 2012-07-15
- 2012-07-16
- 2012-07-17
- 2012-07-18
- 2012-07-20
- 2012-07-23
- 2012-07-24
- 2012-07-25
- 2012-07-28
- 2012-07-29
- 2012-07-30
- 2012-07-31
- 2012-08-01
- 2012-08-02
- 2012-08-03
- 2012-08-04
- 2012-08-05
- 2012-08-06
- 2012-08-07
- 2012-08-08
- 2012-08-09
- 2012-08-10
- 2012-08-12
- 2012-08-13
- 2012-08-14
- 2012-08-15
- 2012-08-16
- 2012-08-17
- 2012-08-18
- 2012-08-19
- 2012-08-20
- 2012-08-21
- 2012-08-23
- 2012-08-24
- 2012-08-25
- 2012-11-24
- 2012-11-25
- 2012-11-26
- 2012-11-27
- 2012-11-28
- 2012-11-29
- 2012-11-30
- 2012-12-01
- 2012-12-03
- 2012-12-04
- 2012-12-05
- 2012-12-06
- 2012-12-08
- 2012-12-09
- 2012-12-10
- 2012-12-11
- 2012-12-12
- 2012-12-13
- 2012-12-14
- 2012-12-15
- 2012-12-16
- 2012-12-17
- 2012-12-18
- 2012-12-19
- 2012-12-20
- 2012-12-21
- 2012-12-22
- 2012-12-23
- 2012-12-24
- 2012-12-25
- 2012-12-26
- 2012-12-27
- 2012-12-28
- 2012-12-29
- 2012-12-30
- 2012-12-31
- 2013-01-02
- 2013-01-03
- 2013-01-04
- 2013-01-05
- 2013-01-06
- 2013-01-07
- 2013-01-08
- 2013-01-09

#### Excluded matched dates

- 2012-07-21 (2,299 sentinel rows)
- 2012-07-22 (46 sentinel rows)
- 2012-07-26 (9,045 sentinel rows)
- 2012-07-27 (23,060 sentinel rows)
- 2012-12-07 (22 sentinel rows)
- 2013-01-01 (23 sentinel rows)

#### Electricity dates without occupancy

- 2012-06-01
- 2012-06-02
- 2012-06-03
- 2012-06-04
- 2012-06-05
- 2012-06-06
- 2012-06-07
- 2012-06-08
- 2012-06-09
- 2012-06-10
- 2012-06-11
- 2012-06-12
- 2012-06-13
- 2012-06-14
- 2012-06-15
- 2012-06-16
- 2012-06-17
- 2012-06-18
- 2012-06-19
- 2012-06-20
- 2012-06-21
- 2012-06-22
- 2012-06-23
- 2012-06-24
- 2012-06-25
- 2012-06-26
- 2012-06-27
- 2012-06-28
- 2012-06-29
- 2012-06-30
- 2012-07-01
- 2012-07-02
- 2012-07-03
- 2012-07-04
- 2012-07-05
- 2012-07-06
- 2012-07-07
- 2012-07-08
- 2012-07-09
- 2012-07-10
- 2012-07-11
- 2012-07-12
- 2012-07-13
- 2012-07-14
- 2012-07-19
- 2012-08-11
- 2012-08-22
- 2012-08-26
- 2012-08-27
- 2012-08-28
- 2012-08-29
- 2012-08-30
- 2012-08-31
- 2012-09-01
- 2012-09-02
- 2012-09-03
- 2012-09-04
- 2012-09-05
- 2012-09-06
- 2012-09-07
- 2012-09-08
- 2012-09-09
- 2012-09-10
- 2012-09-11
- 2012-09-12
- 2012-09-13
- 2012-09-14
- 2012-09-15
- 2012-09-16
- 2012-09-17
- 2012-09-18
- 2012-09-19
- 2012-09-20
- 2012-09-21
- 2012-09-22
- 2012-09-23
- 2012-09-24
- 2012-09-25
- 2012-09-26
- 2012-09-27
- 2012-09-28
- 2012-09-29
- 2012-09-30
- 2012-10-01
- 2012-10-02
- 2012-10-03
- 2012-10-04
- 2012-10-05
- 2012-10-06
- 2012-10-07
- 2012-10-08
- 2012-10-09
- 2012-10-10
- 2012-10-11
- 2012-10-12
- 2012-10-13
- 2012-10-14
- 2012-10-15
- 2012-10-16
- 2012-10-17
- 2012-10-18
- 2012-10-19
- 2012-10-20
- 2012-10-21
- 2012-10-22
- 2012-10-23
- 2012-10-24
- 2012-10-25
- 2012-10-26
- 2012-10-27
- 2012-10-28
- 2012-10-29
- 2012-10-30
- 2012-10-31
- 2012-11-01
- 2012-11-02
- 2012-11-03
- 2012-11-04
- 2012-11-05
- 2012-11-06
- 2012-11-07
- 2012-11-08
- 2012-11-09
- 2012-11-10
- 2012-11-11
- 2012-11-12
- 2012-11-13
- 2012-11-14
- 2012-11-15
- 2012-11-16
- 2012-11-17
- 2012-11-18
- 2012-11-19
- 2012-11-20
- 2012-11-21
- 2012-11-22
- 2012-11-23
- 2012-12-02
- 2013-01-10
- 2013-01-11
- 2013-01-12
- 2013-01-13
- 2013-01-14
- 2013-01-15
- 2013-01-16
- 2013-01-17
- 2013-01-18
- 2013-01-19
- 2013-01-20
- 2013-01-21
- 2013-01-22
- 2013-01-23
- 2013-01-24
- 2013-01-25
- 2013-01-26
- 2013-01-27
- 2013-01-28
- 2013-01-29
- 2013-01-30
- 2013-01-31

#### Occupancy dates without electricity

- None

## Input issues

No structural, numeric, or occupancy-label issues were found.

## Interpretation notes

- `-1` is the dataset's missing-data sentinel and was never used as a measurement.
- Sentinel-containing matching dates were excluded in full; no zeros were substituted and no interpolation was performed.
- Energy is calculated as the sum of one-second watt readings divided by 3,600, reported in Wh.
- Date and second-of-day are retained as wall-clock fields only. No timezone is inferred.
