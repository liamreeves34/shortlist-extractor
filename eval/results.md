# Results

One section per run of `eval.run`; newest last.

## rules (rules-1) on test, 2026-11-25

93 labeled postings (32 in the split left unlabeled: over the 3-per-organization cap, or empty). Intervals: 1000 bootstrap resamples of postings.

| Field | Metric | Score | 95% interval |
| --- | --- | --- | --- |
| title | exact | 0.968 | [0.925, 1.000] |
| organization | exact | 0.505 | [0.409, 0.602] |
| location | exact | 0.247 | [0.161, 0.333] |
| start_term | exact | 0.849 | [0.774, 0.914] |
| deadline | exact | 1.000 | [1.000, 1.000] |
| deadline_type | accuracy | 0.989 | [0.968, 1.000] |
| deadline_type | macro_f1 | 0.952 | [0.825, 1.000] |
| degree_levels | precision | 0.978 | [0.944, 1.000] |
| degree_levels | recall | 0.874 | [0.810, 0.936] |
| degree_levels | f1 | 0.923 | [0.882, 0.960] |
| citizenship | accuracy | 0.957 | [0.914, 0.989] |
| citizenship | macro_f1 | 0.711 | [0.530, 0.922] |
| clearance | accuracy | 1.000 | [1.000, 1.000] |
| clearance | macro_f1 | 1.000 | [1.000, 1.000] |
| work_mode | accuracy | 0.656 | [0.559, 0.742] |
| work_mode | macro_f1 | 0.590 | [0.486, 0.682] |
| pay | min | 0.839 | [0.763, 0.914] |
| pay | max | 0.828 | [0.753, 0.903] |
| pay | period | 0.667 | [0.581, 0.763] |
| skills | precision | 0.764 | [0.675, 0.844] |
| skills | recall | 0.455 | [0.376, 0.539] |
| skills | f1 | 0.570 | [0.494, 0.646] |

## teacher (teacher-2) on test, 2026-11-25

93 labeled postings (32 in the split left unlabeled: over the 3-per-organization cap, or empty). Intervals: 1000 bootstrap resamples of postings.

| Field | Metric | Score | 95% interval |
| --- | --- | --- | --- |
| title | exact | 0.828 | [0.742, 0.903] |
| organization | exact | 0.882 | [0.817, 0.946] |
| location | exact | 0.871 | [0.806, 0.935] |
| start_term | exact | 0.935 | [0.882, 0.978] |
| deadline | exact | 1.000 | [1.000, 1.000] |
| deadline_type | accuracy | 1.000 | [1.000, 1.000] |
| deadline_type | macro_f1 | 1.000 | [1.000, 1.000] |
| degree_levels | precision | 0.855 | [0.752, 0.946] |
| degree_levels | recall | 0.971 | [0.933, 1.000] |
| degree_levels | f1 | 0.909 | [0.847, 0.962] |
| citizenship | accuracy | 1.000 | [1.000, 1.000] |
| citizenship | macro_f1 | 1.000 | [1.000, 1.000] |
| clearance | accuracy | 1.000 | [1.000, 1.000] |
| clearance | macro_f1 | 1.000 | [1.000, 1.000] |
| work_mode | accuracy | 0.882 | [0.806, 0.935] |
| work_mode | macro_f1 | 0.885 | [0.813, 0.943] |
| pay | min | 1.000 | [1.000, 1.000] |
| pay | max | 1.000 | [1.000, 1.000] |
| pay | period | 1.000 | [1.000, 1.000] |
| skills | precision | 0.913 | [0.857, 0.957] |
| skills | recall | 0.839 | [0.778, 0.895] |
| skills | f1 | 0.875 | [0.829, 0.916] |

