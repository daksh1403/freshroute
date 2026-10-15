# Live AI evaluation

These are observed Gemini API requests using `gemma-4-26b-a4b-it`, not mocked inference. Inputs are synthetic and deliberately small. They do not establish real warehouse or handwriting accuracy.

| Case | Observed result | API latency |
|---|---|---|
| printed_inventory | 14/15 raw exact field matches (93.3%) | 22.668 s |
| handwriting_style | 14/15 raw exact field matches (93.3%) | 27.073 s |
| missing_quantity | Missing quantity was not fabricated; unresolved information was surfaced | 1.870 s |
| ambiguous_units | Boxes retained as boxes; no invented kg conversion | 8.227 s |
| clean_text | Structured text records returned with source references | 19.898 s |
| unrelated_image | 0 operational records (expected zero) | 4.113 s |
| natural_language_whatif | R-TAM delay of three hours parsed into a whitelisted operation | 3.076 s |

The exact-field scorer checks commodity, quantity, quantity unit, remaining-life value and life unit for each of three records. Both image cases differed only in the literal life-unit string `day` versus the expected label `days`. Both spellings convert correctly to hours in deterministic validation. We retain the raw exact-match result rather than relabeling it as perfect accuracy. The handwriting-style fixture is rendered with a handwriting font; actual human handwriting has not been evaluated.

## Real browser acceptance

The local Cloudflare Workers browser flow completed: real printed-image inference → confirmation blocked until checked → manual batch-ID edit audited → replacement inventory totaling 255 kg → real optimization → natural-language R-CHG delay → confirmed replanning → cited Gemma explanation.

Original imported-stock baseline and optimized net revenue were both 10470 INR. After the delay, optimized net revenue was 10215 INR. Both plans had zero constraint violations. This example demonstrates valid replanning; it does not claim that every optimization run improves the baseline.

A prior broad-context explanation request encountered a Google 504 deadline. The error was displayed and the core plan stayed usable. Explanation context is now restricted to up to fourteen relevant verified facts with a smaller output budget; the complete flow then passed. One initial evaluation request was interrupted by a local Worker reload and was rerun after the server stabilized. These failures are not counted as successful inference.

## Reproduce

Start `npx wrangler dev` with your own ignored `.dev.vars` key. Then run:

```sh
node scripts/check_gemma.mjs
node scripts/evaluate_ai.mjs
python -m pip install playwright
python scripts/test_ai_browser.py
```

Raw responses and browser measurements are saved locally under `reports/ai/` (ignored by Git). Unit tests use controlled inputs and mocks for failure paths; they are not counted as live model quality evidence. Latencies vary with provider load, quotas and connectivity.

## Hosted provider access

The initial global Worker deployment received Google's “User location is not supported” error. US-region placement then encountered Google internal errors. Targeting the Mumbai region (`aws:ap-south-1`) produced a successful real hosted Gemma 4 what-if request (2.305 s observed API latency). This is an operational deployment check, separate from the local extraction measurements above.
