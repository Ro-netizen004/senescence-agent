# Human Reply Annotation

This directory contains the frozen starting materials for blinded human
validation of the automated claim linter used in the primary same-method null
experiment.

## Current status

**In progress.** No human-annotation result, agreement statistic, or adjudicated
label is available yet. Two study authors will independently annotate 156
replies: 78 governed and 78 matched ungoverned replies. The extraction uses
shuffle seed 42 and validates the per-arm counts before producing material.

## Public files

- `ANNOTATION_PROTOCOL.md`: prespecified label definitions and analysis plan.
- `extract_blinded_replies.py`: deterministic extractor with fail-closed arm
  parsing and count validation.
- `blinded_annotation_template.xlsx`: readable blank template with preserved
  reply formatting, dropdown labels, and an embedded rubric.
- `blinded_replies_annotator_1.xlsx` and
  `blinded_replies_annotator_2.xlsx`: byte-identical blank starting copies.

## Private files

`blinded_key.json` is excluded from Git and must not be opened until both
annotations are complete and frozen. Generated CSV working files are also
excluded. Partially completed workbooks must not be pushed.

## Planned final package

After both authors finish, freeze and checksum the original annotation files,
calculate raw agreement and Cohen's kappa before adjudication, retain the
pre-adjudication labels, create a separate consensus table, and compare the
consensus labels with the automated linter. Report the procedure as arm-blinded
annotation by two study authors, not as external expert review.
