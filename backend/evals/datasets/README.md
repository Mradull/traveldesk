# Vera eval datasets (owner: Mradul, M3)

One JSON object per line. Every case has a unique `id` (`<suite>-NN`). Read by `evals/run_evals.py`.
All facts, amounts and rule ids come from `backend/data/expense_policy.txt` (VGS-FIN-TE-001 v2.0).
No real personal data: phone, email, PAN and card numbers are made up (4111 1111 1111 1111 is a public test card).

| File | Cases | Live LLM | Fields |
|---|---|---|---|
| routing.jsonl | 15 | no | `message`, `previous_intent` (null or intent), `expected_intent`, `expected_tools` |
| retrieval.jsonl | 12 | no | `query`, `expected_ref_id` (must be in the top 4 chunks) |
| policy_qa.jsonl | 12 | yes | `question`, `expected_keywords` (word for word in the answer), `expected_ref_ids` (any one cited) |
| platform_howto.jsonl | 5 | yes | same as policy_qa, GUIDE ids |
| weather_grounding.jsonl | 5 | no | `destination`, `question`, `days` (DailyForecast fields + `day_offset` from today) |
| weather_missing_inputs.jsonl | 4 | yes | `message`, `missing` (label only) |
| out_of_range.jsonl | 3 | no | `destination`, `start_offset`, `end_offset` (days from today), `note` |
| weather_failure.jsonl | 4 | no | `destination`, `start_offset`, `end_offset`, `failure` (`timeout`, `503`, `429`, `invalid_json`) |
| packing_grounding.jsonl | 4 | no | weather_grounding fields + `must_include`, `must_not_include` (checked in the checklist) |
| business_data_boundary.jsonl | 4 | no | `message`, `expected_keywords` |
| boundaries.jsonl | 4 | no | `message`, `expected_keywords`, `kind` (approve / book / safety / reimburse) |
| injection_pii.jsonl | 7 | no | `message`, `expected` (`blocked` or `masked`), `expected_reasons`, `must_not_contain` |
| memory.jsonl | 3 | yes | `turns` (sent in one session), `expected_keywords` (in the last reply) |
| session_boundary.jsonl | 2 | no | `first_message`, `first_reply`, `second_message`, `forbidden` |

Total: 84 cases.
