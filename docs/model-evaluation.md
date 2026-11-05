# Isolation Forest baseline evaluation — ECO Household 1

## Scope and safeguards

This is an unsupervised evaluation. ECO contains no verified anomaly labels for this task, so this report does not calculate classification accuracy, precision, recall, or F1. A flag means the model assigned an unusual score under this fitted baseline, not that a confirmed fault occurred.
The Parquet file was read only. The model and all thresholds were fit from training dates only. Validation and test dates were scored after fitting and were not used to fit features, model parameters, baseline statistics, or the selected threshold.

## Verified temporal split

| Partition | Dates | Date count | Record count |
| --- | --- | ---: | ---: |
| Train | 2012-07-15–2012-12-06 | 47 | 4,512 |
| Validation | 2012-12-08–2012-12-23 | 16 | 1,536 |
| Test holdout | 2012-12-24–2013-01-09 | 16 | 1,536 |

Whole dates remain together; no adjacent intervals were randomly split. The test block was not used for model or threshold selection.

## Configuration and score meaning

- Estimator: Isolation Forest, 300 trees, contamination 5.00%, random seed 42, max_samples auto.
- Score: anomaly_score = negative sklearn score_samples; **higher means more unusual**.
- Feature schema: version 1.0.0; both ordered branches are validated at load and inference.
- Selected threshold: occupancy model 0.589912; no-occupancy model 0.611365.
- Threshold derivation: occupancy=negative fitted IsolationForest offset (-offset_) from training scores; no-occupancy=negative fitted IsolationForest offset (-offset_) from training scores. Threshold provenance is recorded per branch in the model metadata.
- Baseline: hour-and-occupancy-conditioned median/MAD where training group size is adequate, falling back to hour then global training reference; fixed robust-z threshold 3.50.

No feature scaler is fitted. Time sine/cosine is a deterministic transform of second-of-day. Unknown occupancy routes to the separately trained model without occupancy; it is never changed to 0.

## Feature set

Occupancy-aware model: powerallphases_mean_w, powerallphases_max_w, powerallphases_std_w, occupancy_fraction, time_of_day_sin, time_of_day_cos. A separate no-occupancy estimator omits occupancy_fraction for rows where it is unknown.
Energy is omitted because at a fixed 15-minute interval it duplicates mean power × 0.25 hours. Phase means are omitted because their sum reconstructs total mean power within rounding.

## Unlabelled score and flag summaries

| Period | Records | Dates | IF flagged | IF rate | Robust flagged | Robust rate | Score median | Score p95 | Score p99 | Score max | Both flagged |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Validation | 1,536 | 16 | 102 | 6.64% | 231 | 15.04% | 0.45402 | 0.60160 | 0.67280 | 0.73623 | 86 |
| Test | 1,536 | 16 | 92 | 5.99% | 161 | 10.48% | 0.49807 | 0.59468 | 0.66076 | 0.70693 | 72 |

The IF flag rate changes by 0.65 percentage points from validation to test. This is a threshold/score stability description, not a performance metric against truth.

### Sensitivity to training-derived contamination cutoffs

The following thresholds are the 99th, 95th, and 90th percentiles of training scores (approximately 1%, 5%, and 10% training contamination). They are applied unchanged to validation and test scores; no evaluation-period threshold is selected.

| Period | Training quantile target | Cutoff | IF flagged rate |
| --- | ---: | ---: | ---: |
| Validation (known occupancy) | 0.01 | 0.659431 | 1.37% |
| Validation (known occupancy) | 0.05 | 0.589912 | 6.64% |
| Validation (known occupancy) | 0.10 | 0.560967 | 13.41% |
| Validation (occupancy unknown) | 0.01 | 0.671497 | n/a (no rows) |
| Validation (occupancy unknown) | 0.05 | 0.611365 | n/a (no rows) |
| Validation (occupancy unknown) | 0.10 | 0.586113 | n/a (no rows) |
| Test (known occupancy) | 0.01 | 0.659431 | 1.11% |
| Test (known occupancy) | 0.05 | 0.589912 | 5.99% |
| Test (known occupancy) | 0.10 | 0.560967 | 11.85% |
| Test (occupancy unknown) | 0.01 | 0.671497 | n/a (no rows) |
| Test (occupancy unknown) | 0.05 | 0.611365 | n/a (no rows) |
| Test (occupancy unknown) | 0.10 | 0.586113 | n/a (no rows) |

The occupancy-unknown branch has no rows in this ECO Parquet, but is available for inference when occupancy is missing. Changing contamination changes the training-derived flag cutoff; score rankings are evaluated without labels.

## High-scoring test intervals (review examples)

These are the ten highest test anomaly scores, whether or not they cross the selected threshold. They are not known faults.

| Date | Time | IF score | IF flag | Mean W | Peak W | Std W | Occupancy | Robust z | Context |
| --- | --- | ---: | --- | ---: | ---: | ---: | --- | ---: | --- |
| 2013-01-05 | 17:30:00 | 0.706929 | yes | 2157.5 | 4518.7 | 1635.2 | 1.00 | 5.51 | hour=17,occupancy=occupied |
| 2012-12-24 | 18:30:00 | 0.701232 | yes | 2109.9 | 4673.5 | 1331.0 | 1.00 | 11.67 | hour=18,occupancy=occupied |
| 2013-01-05 | 17:45:00 | 0.699381 | yes | 3534.0 | 5089.3 | 1187.5 | 1.00 | 9.64 | hour=17,occupancy=occupied |
| 2012-12-25 | 18:00:00 | 0.698277 | yes | 2542.9 | 5373.9 | 1190.4 | 1.00 | 14.32 | hour=18,occupancy=occupied |
| 2012-12-25 | 17:45:00 | 0.697747 | yes | 1986.9 | 5832.9 | 1263.2 | 1.00 | 5.00 | hour=17,occupancy=occupied |
| 2012-12-26 | 11:15:00 | 0.689674 | yes | 2748.4 | 5725.7 | 1047.1 | 1.00 | 6.95 | hour=11,occupancy=occupied |
| 2013-01-06 | 17:45:00 | 0.685501 | yes | 1940.8 | 3761.9 | 1578.8 | 1.00 | 4.86 | hour=17,occupancy=occupied |
| 2012-12-27 | 17:15:00 | 0.685293 | yes | 2085.6 | 3829.1 | 1401.5 | 1.00 | 5.30 | hour=17,occupancy=occupied |
| 2013-01-05 | 19:30:00 | 0.683696 | yes | 2948.7 | 4382.4 | 814.6 | 1.00 | 27.82 | hour=19,occupancy=occupied |
| 2013-01-06 | 17:30:00 | 0.679778 | yes | 1664.5 | 3857.5 | 1595.1 | 1.00 | 4.03 | hour=17,occupancy=occupied |

Each row can be described by its measured load, peak, variability, occupancy, and time. The IF score is not a feature attribution and cannot establish a cause. The robust baseline provides a more directly interpretable deviation from a training context median, but can miss multivariate combinations and depends on group support.

## Baseline comparison and limitations

The contextual median/MAD baseline is simple to explain and can compare a reading with a training reference for its hour and occupancy state. It detects unusual total mean power in either direction. It is less capable of detecting unusual combinations among mean, peak, and variability; sparse contexts fall back to broader groups.
Isolation Forest uses multiple electricity and context features and can find unusual combinations, but its ranking and cutoff are not causal explanations. Neither method is supervised or validated against confirmed anomalies. Differences in flag rates or overlap do not show which method is correct.
The dataset contains one household, 79 clean matched days, seasonal gaps, and only a winter validation/test block. Occupancy labels can be imperfect; live systems may not have occupancy. These results do not establish generalization to hostels or operational alert quality.

## Reproduce

From the repository root, activate the virtual environment, then run the evaluation command documented in docs/setup-ml.md. The report is regenerated from the Parquet and saved model.
