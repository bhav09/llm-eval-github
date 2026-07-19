# Ground Truth Methodology

## Pipeline

1. **Rules engine (v1)** — native label mapping + heuristics
2. **LLM adjudicator** — ambiguous queue only (`deepseek-v4-pro`)
3. **Human calibration** — stratified sample in `human_calibration.json`

## Volumes

- Total issues: 534
- Rules HIGH: 267
- Rules MED: 95
- Rules LOW: 172
- LLM queue: 267
- LLM resolved (Tier B): 267
- Scored set size: 125 (Tier A: 57, Tier B: 68)

## Per-class scored counts

{
  "question": 25,
  "documentation": 12,
  "other": 13,
  "security": 25,
  "enhancement": 25,
  "bug": 25
}

## Limitations

- Maintainer labels are noisy silver standard
- Sparse classes may have low counts
- LLM adjudicator must not be used as an eval comparison model
