# The data catalog (`tic-catalog/1`)

One file per live program, listing every dataset it stores: what the store is, where it is, its format, method
version, licence, cadence, first date and independent copies. `schema.json` defines an entry, and
`tests/test_catalog.py` checks every entry against it.

## Reading a field

Each field is one of two shapes:

- **Measured:** `{"value": ..., "status": "measured", "how": "..."}`. `how` says what was read. The reading holds as of
  the file's `measured_at`.
- **Unverified:** `{"value": null, "status": "unverified", "why": "..."}`. Nobody has measured it. It is never filled
  with an estimate.

## What the fields mean

- `location`: `kind` is one of `git`, `github-release`, `object-store`, `document-store`, `database`, `key-value`,
  `site` or `local`. Private stores are described by kind only.
- `schema`: the store's format as observed, usually its file types.
- `method_version`: the versions on the live feed's items. Older stored rows may differ.
- `licence`: `registry:<program>` points at that program's `terms` in `vocab/programs.json`.
- `cadence`: the median gap between recent writes, when there are enough to measure.
- `first_date`: the earliest evidence named in `how`. A first commit or upload can be later than the data it holds.
- `independent_copies`: a lower bound. It counts copies confirmed in separate places; a second copy on the same account
  is not independent.
