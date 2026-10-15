# FreshRoute

This document describes the deterministic planning engine. See the main README for the AI workflow and Workers deployment.

Local, explainable allocation of perishable produce. Core solving does not require a network or dashboard. No organizer data or official score was supplied: the example and benchmark are **synthetic validation scenarios**, not predictive or real-world performance evidence.

## Run

Python 3.11 or newer:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
streamlit run app.py
```

```sh
python -m pytest -q
python -m freshroute solve examples/demo --output reports/demo
python -m freshroute benchmark --output reports/benchmark
python -m freshroute solve /path/to/scenario.json --output reports/imported
python -m freshroute solve /path/to/scenario.xlsx --output reports/imported
```

The dashboard opens at http://localhost:8501. JSON imports, CSV-table directories, and Excel workbooks use the same validation and optimization engine. Exported reports include the normalized input, baseline and optimized shipments, independently recomputed metrics, rejection reasons, markdown scenarios, and solver metadata. Dependencies are declared in `pyproject.toml`; `requirements-lock.txt` records the exact native environment used for verification. GitHub Actions repeats tests and benchmarks in a fresh Linux environment.

## Input contract

A JSON object contains `config`, `inventory`, `demand`, `routes`, and `resources`. A CSV directory contains `config.json` plus `inventory.csv`, `demand.csv`, `routes.csv`, and `resources.csv`. An Excel workbook contains those five sheet names; `config` is a single row. Empty JSON arrays are accepted. Empty CSV tables must retain headers. Workbook uploads and JSON uploads are supported in the app.

All quantities and capacities use one common `quantity_unit`; all money uses one `currency`. Time is in **hours**. No implicit conversion between kg, crates, days, or currencies occurs.

| Table | Required fields | Optional fields (default) |
|---|---|---|
| config | horizon_hours (>0), quantity_unit, currency | handling_hours (0), integer_quantities (false), as_of (for timestamps), label |
| inventory | batch_id, commodity, quantity, shelf_life_hours | handling_cost_per_unit (0), disposal_cost_per_unit (0), storage_cost_per_unit (0) |
| demand | destination_id, commodity, quantity, price_per_unit | min_arrival_life_hours (0) |
| routes | route_id, destination_id, resource_id, travel_hours, capacity, cost_per_unit | fixed_cost (0), commodity (empty = all) |
| resources | resource_id, capacity | |

Unique batch, route and resource IDs are required; `(destination_id, commodity)` must be unique in demand. Destination names are IDs; separate destination tables are unnecessary. Route destinations must occur in demand; route resources must exist. Missing critical fields, nonfinite/negative numbers, duplicate records, ambiguous aliases and unknown columns are rejected with a record/field message. Commodity labels are stripped and case-normalized; IDs remain case-sensitive. Additional columns can be explicitly mapped through the Python API or `--column-map mapping.json` (source-column to canonical-column, by table). Common aliases such as `qty`, `batch`, `destination`, `vehicle_id`, `remaining_shelf_life_hours`, and `unit_price` are accepted. Units are never guessed from values.

Inventory may supply timezone-aware `expires_at` instead of shelf life when `config.as_of` is timezone-aware. Expired timestamps normalize to zero remaining life. Conflicting expiry and remaining-life fields are rejected. Demand is **commodity/destination aggregate within this horizon**. Time-dependent demand must be aggregated deliberately before import; timestamps or extra demand columns are rejected rather than silently discarded. Optional costs absent from data are disclosed zero-cost assumptions, not imputed estimates.

## Model and assumptions

One planning decision at time zero; divisible quantities by default (or integral quantity units when requested). A route represents a single direct delivery service to one destination. `route.capacity` limits that service; `resource.capacity` is the total quantity budget shared by all routes on that resource over this planning wave. It does **not** simulate trip sequencing, return trips, vehicle packing, warehouse locations or a vehicle-routing problem. Define resource capacity accordingly. `fixed_cost` is charged once per activated route, independent of the number of batches loaded. Per-vehicle costs shared across multiple destinations need a different activation model and must not be entered as route costs.

Sales are assumed to occur immediately on arrival, up to documented demand. Travel plus handling must be strictly below shelf life, within the horizon, and leave at least the demand's minimum arrival shelf life. There is no stochastic deterioration or fabricated sell-through rate. Committed/dispatched state is not modeled: replan is an **unexecuted planning sandbox**; users must submit residual inventory, residual demand and available capacity for live operations.

For each feasible batch/route arc, choose nonnegative shipment `x[b,r]`. Constrain batch sums by stock, destination/commodity sums by demand, route sums by route capacity and resource sums by shared capacity. With fixed costs, add binary `y[r]` and `sum_b x[b,r] <= route.capacity * y[r]`.

Maximize net revenue:

```
sales - variable transport - activated route fixed costs - shipment handling
      - disposal of unshipped stock expiring by horizon
      - storage of unshipped stock surviving the horizon
```

Spoilage is deterministic under this disclosed horizon model. Unsold = all unshipped inventory, including both spoilage and viable remaining stock. `storage_cost_per_unit` is a cost for the whole horizon, not per hour. Purchase costs are sunk and excluded. Saved disposal/storage costs enter shipment objective coefficients; their initial-inventory constant is included in reported net revenue.

The sparse model uses SciPy/HiGHS MILP (continuous shipment variables unless configured integral; binary activation only where fixed cost is positive). See [SciPy solver documentation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.milp.html). A second solve preserves the primary economic objective with an economic objective floor at the primary optimum (acceptance tolerance 1e-9 currency units) and prefers expiring stock and stable sorted arc order. Inputs are sorted for reproducibility. This is a deterministic secondary preference, not a claim that every degenerate LP has a unique solution. Primary status, incumbent gap when supplied, runtime and tie-break status are reported; heuristic results are never called optimal. Each solve has a time limit; the secondary solve uses only the remaining budget. Candidate construction and baseline computation are outside solver time limits.

An empty shipment plan is always feasible because unmet demand is allowed. Mandatory minimum delivery obligations are unsupported. Solver failures or invalid incumbents trigger a validated fallback choosing the better economic result of FEFO, margin greedy, and no shipment. Independent evaluation checks every returned plan. Optimal results are checked against baseline and the empty plan; a material regression downgrades to fallback and exposes the issue.

## Baseline, evidence and discounts

The practical baseline processes batches FEFO, then sends each to its best currently feasible net contribution destination; fixed-route activation costs are considered for the quantity that fits. It stops economically harmful allocations, uses the same candidates and capacities, and never exceeds demand. It is a credible greedy strategy, but it does not coordinate scarce routes across future batches. All reported metrics use the same independent evaluator for both plans. Percentage change is null when the baseline is zero. Improvement in net revenue can trade off spoilage or service: the dashboard reports all metrics without hiding regressions.

Markdowns are scenario suggestions only. For unsold stock expiring within the horizon, evaluate 5%, 10%, and 15% against feasible route unit margins and allocated activation costs. Recommend the largest tested markdown with nonnegative incremental contribution; show a break-even demand-uplift ratio. Without elasticity evidence, additional sales are explicitly zero in the evaluated plan. If no economically viable route exists, report that a markdown cannot fix the logistics or margin issue. Benchmarks include zero/empty demand, excess supply, scarce capacity, high risk, delays, uneven demand and uneconomic markdown cases.

## Reproducible judge walkthrough

1. Launch the dashboard with the labeled synthetic example. Inspect inventory, prices, hours and capacity.
2. Generate the plan. Compare FEFO and optimized net revenue, fulfillment and spoilage using the displayed evaluator output.
3. Open the dispatch table and explanations; inspect route rejections and binding constraints.
4. In the disruption sandbox add travel delay and reduce capacity. Replan and inspect whether the previous plan is still feasible, the shipment deltas, and new metrics.
5. Download the structured report and CSVs. Run `python -m pytest -q` and the benchmark command to demonstrate independent constraint checks and tiny-case optimality verification.

## Boundaries

No official score adapter exists because none was supplied. The economic objective is replaceable in the engine, and metrics are separate. No demand forecasting, fitted elasticity, sensor accuracy, real-world validation, multi-period commitments or robust optimization is claimed. Large instances remain constrained by candidate count and available memory; use measured benchmark runtime on the actual target hardware. All UI values come from the current input and evaluated plans.


## Intelligence boundary

`cloudflare/intelligence.mjs` uses the official Google GenAI SDK with an explicit Gemma 4 allowlist. Images use inline data. Generated JSON is parsed by strict application contracts because schema-constrained Gemma output has not been verified. Text quotes must occur in the submitted text; quantities must agree with their quoted numbers. Image reading still requires human verification. Missing values are retained or reported as unresolved; they do not become inferred business facts.

`freshroute/intelligence.py` converts explicit units, prepares editable drafts, checks confirmation and known identifiers, and returns a new validated scenario. It never mutates the original. Unit conversions support grams, kilograms and tonnes; boxes and crates require operator-supplied information. Batch IDs beginning AI are generated labels, not OCR results. Optional costs absent from reviewed records are zero, as in other imports.

Natural-language changes are limited to named route delays and scaling capacity, demand, prices or stock. Unknown selectors, arbitrary fields, executable code and missing confirmation are rejected. Delivery deadlines and forecasting are unsupported and require clarification.

Evidence for explanations is rebuilt from the canonical scenario and independently evaluated plan. Model-supplied metrics are never trusted. A bounded selection of relevant facts is sent to Gemma. Returned citations must exist, and numerical tokens must occur in cited facts. These checks do not prove semantic entailment: model interpretations are labeled and their exact underlying evidence is inspectable.

## Workers deployment

Workers serves static assets and the `/api/ai/extract`, `/api/ai/ask`, `/api/ai/whatif`, `/api/ai/status` and `/api/health` endpoints. The Google key is a Worker secret. Regional placement targets `aws:ap-south-1` (Mumbai), where the actual hosted Gemma request was verified. A rate-limit binding caps AI requests at twelve per minute per client key. No database or uploaded-image storage is used. Provider calls have a 35-second timeout and at most two attempts for transient errors; malformed responses fail validation.

The browser runs the same Python optimizer through Pyodide. The default local build bundles pinned NumPy/SciPy wheels and checks SHA-256 hashes. Hosted builds are small: the Worker serves a fixed allowlist of pinned runtime assets through an edge cache backed by the Pyodide CDN. It is not an arbitrary URL proxy. Runtime fetching never includes business inputs or the Google key.

Use `npm run deploy`, then `npx wrangler secret put GEMINI_API_KEY`. For local development, copy `.dev.vars.example` to the ignored `.dev.vars`, add your key, run `npm run build` and `npx wrangler dev`. Live API checks are separate from deterministic tests: `node scripts/evaluate_ai.mjs` and `python scripts/test_ai_browser.py` use actual inference and incur the provider's normal quotas.
