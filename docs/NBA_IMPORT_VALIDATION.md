# NBA normalized-import validation finding A

Verified October 20, 2026. This is a software validation finding and a read-only
integrity scan of retained input. It introduces no model evaluation or promotion.

## Reproduction before the fix

On clean `main` at `5d19fa344de5ceaa6e7cc550f0ac8ac832458202`, constructing an
`NBAPlayerGame` with `points=12`, `fgm=5`, `fga=8`, `fg2m=2`, `fg3m=2`,
`fg3a=4`, `ftm=2`, `fta=2`, valid identities/clocks and otherwise coherent
nonnegative counts succeeded. Although `5 != 2+2`, `audit_rows([row])` returned
`identity_failures={}`. The points identity and made/attempt inequalities passed,
so neither detected the inconsistent total field goals.

An import-only check serialized nine such synthetic rows with distinct event
IDs and consecutive dates. `read_normalized_panel` accepted all nine. No forecast
or score was produced. A minimal form of the original failure is:

```python
from dataclasses import replace
from multisport_lab.nba_data import audit_rows, normalize_sdv_row

# Given a valid source row with FGM=4, FG3M=2, PTS=12 and FTM=2:
valid = normalize_sdv_row(source_row)  # derives FG2M=2
contradictory = replace(valid, fgm=5)  # formerly accepted
audit_rows([contradictory])["identity_failures"]  # formerly {}
```

Both existing source adapters already derive `FG2M=FGM−FG3M`. The gap concerned
caller-supplied/serialized normalized rows and missing independent audit coverage;
it was not evidence that either adapter had generated contradictory components.

## Repair and regression checks

`NBAPlayerGame` now rejects a supplied contradiction whenever all three counts
are known: **FGM must equal FG2M + FG3M**. Missing counts remain missing and
cannot pass as zeros. `audit_rows` independently reports
`fgm_component_identity` for contradictory legacy/unchecked rows, including rows
whose participation is UNKNOWN.
The normalized-panel importer inherits constructor rejection; no importer,
cohort, preparation-script or scientific-protocol behavior was otherwise changed.

Regression tests cover constructor rejection, preserved missingness, the
independent audit and rejection of a tampered serialized normalized row that
still passes the separate points and attempt identities. The source-adapter and
preparation tests continue to check their existing derivation paths.

Commands:

```bash
python3 -m unittest discover -s tests -p test_nba_data.py -v
python3 -m unittest discover -s tests -p test_prepare_nba_panel.py -v
python3 -m unittest discover -s tests -v
python3 -m multisport_lab.demo
```

The focused NBA suite passed **14 tests** and preparation suite passed **five**.
A concurrent integration snapshot passed **101 tests** in 0.098 seconds; the
demo returned `OFFLINE_EXAMPLES_ONLY`. The integration handoff records the final
combined count. These checks do not establish sports accuracy, live quote
admission or qualification.

## Existing frozen data and evidence

Before editing, an independent JSONL scan of
`/tmp/nml-nba-audit/normalized.jsonl` checked all **26,645 rows** for the supplied
field-goal identity. It found **zero contradictions**. The retained input's
SHA-256 remains
`489b7148db26cc68e3096cacc1c6960d2b7652d0a82755c215efbd6a96876c8c`.
After the repair, constructing each retained normalized row with the stricter
validator and passing all rows to `audit_rows` also produced zero identity
failures; this was import validation only.
This finding therefore establishes a validation gap, with no observed corruption
of that frozen panel. It does not verify every other property of the input or
retroactively create historical pregame availability.

The original R0 receipts are preserved byte-for-byte:

| File | SHA-256 |
| --- | --- |
| `evidence/research/r0-protocol.json` | `12f9c2ace25c9975748e519fec13d878484756b0257261ddacb7274cf767d939` |
| `evidence/research/r0-pilot.json` | `8594245a6f7a9369c1c211567477229ceb83579ad60f29e1533003021b6b9aaa` |

The R0 evaluation was not rerun. Existing results retain their original source
hashes and development-only scope; repairing validation adds no new performance
evidence.
