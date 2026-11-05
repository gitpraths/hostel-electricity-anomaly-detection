# Data handling

Store authorized selected ECO exports locally under `raw/eco/` when available;
store derived outputs under `processed/`. These data directories are ignored by
Git. Keep provenance and schema notes with the data outside the repository or in
non-sensitive documentation. The supplied Household 1 exports currently live
in the specifically ignored `../database/01/` and
`../database/01_occupancy_csv (1)/` paths. No raw dataset is included in Git.

Run `python -m data.preprocess_eco` from the repository root to create the
15-minute Parquet output and metadata in `processed/`; see
`../docs/preprocessing.md` for configuration and report details.
