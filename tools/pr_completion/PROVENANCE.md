# PR Completion helper provenance

`pr_watch.py` and `pr_land.py` are byte-for-byte copies of the installed
`pr-completion:take-pr-to-completion` skill's shipped scripts, accessed October
24, 2026. They implement the existing required release process, rather than a
project-specific replacement merge implementation.

Source skill:
`skill://plugins_6a567022b8c88191afc9e47c5eb59a7f/take-pr-to-completion/SKILL.md`.

SHA-256:

- `pr_land.py`: `b2f4b23b35689e4dd7e03286f643e9f5c307ac763b507382a9357c9a0fe12f5f`
- `pr_watch.py`: `e6052992fb8d7b853e2401cc11ffec9a9052975e672fc5174629e415dec3f415`

The hosted wrapper checks these hashes before use. The scripts remain unchanged;
the project does not assert a new upstream license or ownership of the skill.
Only `pr_land.py` may request a merge. No admin override, direct merge API,
protection bypass, custom check exclusion, or provider credential is introduced.
The wrapper, workflow integration and tests are project code.
