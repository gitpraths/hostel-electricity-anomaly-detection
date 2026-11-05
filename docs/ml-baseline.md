# Phase 3B ML baseline design

## Scope

This baseline models unusualness in the 15-minute Household 1 features. It is
unsupervised: the ECO records supplied here do not include verified anomaly
ground truth. A flagged interval is a review candidate, not a confirmed event.

## Date-grouped split

`ml/split.py` sorts unique dates and keeps complete days together:

| Partition | Dates | Days | Intervals |
| --- | --- | ---: | ---: |
| Train | 2012-07-15–2012-12-06 | 47 | 4,512 |
| Validation | 2012-12-08–2012-12-23 | 16 | 1,536 |
| Test | 2012-12-24–2013-01-09 | 16 | 1,536 |

The dates are chronologically ordered, but the source has gaps and seasonal
coverage limitations. Validation and test are only scored; all estimators,
robust statistics, and default cutoffs are fit on train.

## Features and occupancy

The ordered feature contract is versioned as **schema `1.0.0`**. The occupancy
branch order is mean power, maximum power, standard deviation, occupancy
fraction, time sine, and time cosine. The no-occupancy branch uses the same
order without occupancy fraction. Training, inference, and loading validate
this contract; renamed, reordered, unsupported, or estimator-mismatched
artifacts fail with a retraining instruction.

The known-occupancy Isolation Forest uses `powerallphases_mean_w`,
`powerallphases_max_w`, `powerallphases_std_w`, `occupancy_fraction`, and sine
and cosine of second-of-day. Energy is redundant with mean power for a fixed
15-minute interval; phase means are redundant with total mean power for this
baseline. Time is cyclic to avoid an artificial discontinuity at midnight.

Missing occupancy is never filled as zero. Two estimators are fit: one on
training rows with known occupancy, one without the occupancy feature on all
training rows. Inference routes each row to the appropriate estimator. This
supports missing occupancy later without conflating unknown with unoccupied.

## Isolation Forest settings and score

Defaults: 300 trees, `contamination=0.05`, `random_state=42`, and
`max_samples="auto"`. These are command-line configurable. There is no scaler:
Isolation Forest partitions feature values by random thresholds, and no
training-fitted transformation is currently needed. Time features are
deterministic.

`anomaly_score = -IsolationForest.score_samples(X)`, so larger scores mean more
unusual. The default decision threshold is `-offset_` from the fitted training
estimator. `--threshold-with-occupancy` and
`--threshold-without-occupancy` independently override those cutoffs; each
must be finite and in `[0, 1]`. Legacy `--threshold` applies one value to both
branches and cannot be combined with branch-specific options. The model
metadata records the selected cutoff for each branch, its derivation method,
and whether it was derived using training data only or supplied explicitly.
It also records the schema version, exact ordered features, training date and
record summary, configuration, and dataset/split information. The model also
records training-score 99th, 95th, and 90th percentile cutoffs for 1%, 5%,
and 10% sensitivity analysis; these cutoffs are never derived from validation or
test.

`AnomalyDetector.load()` requires the matching `.metadata.json` sidecar and
checks its schema, thresholds, configuration, and training summary against the
joblib artifact. Old artifacts without schema `1.0.0` must be retrained; do not
mix sidecars and model files from separate runs.

## Interpretable comparator

`ContextualRobustBaseline` scores absolute deviation of interval mean power
from the training median, divided by `1.4826 × MAD`. It prefers hour and
occupancy-state context when at least 20 training examples exist, then falls
back to hour, then global training reference. Unknown occupancy uses hour-only
context. A configurable modified-z threshold defaults to 3.5.

This baseline is easy to explain, but it considers only mean power and can miss
unusual combinations of peak, variability, and context. Isolation Forest can
rank multivariate combinations but gives no causal explanation. Neither is
validated against confirmed anomalies.

## Explanations and limitations

Inference returns score, threshold, chosen model branch, robust score and
context, plus an explanation string listing observed mean, peak, standard
deviation, occupancy fraction or unknown status, and time. These describe the
interval and do not identify its cause. The score is not a feature attribution.

This is one household and 79 clean matched dates with a seasonal gap. Occupancy
may be imperfect, and operational sensors may not provide it. Evaluation
stability on this dataset does not establish generalization to hostels or alert
quality. Human review and labelled operational data would be needed for those
claims.
