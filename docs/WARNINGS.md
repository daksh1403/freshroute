# FreshRoute warnings and operating notes

These notes collect the informational and warning messages associated with the dashboard. They also describe messages that depend on the current dataset or service response. Actual quantities, costs, constraint checks and validation rules are unchanged.

## Economic trade-offs

The optimizer maximizes the economic objective configured by the dataset. A higher-revenue plan can leave more stock to spoil than FEFO. Compare spoilage, demand fulfillment and net revenue before dispatching.

The original synthetic example earns 19,811 INR with FEFO and 21,123 INR with optimization, while modeled spoilage increases from zero to 110 kg. This is an economic trade-off under the supplied disposal penalties, not a claim that every metric improves.

## Markdown recommendations

No demand-response evidence is supplied with the demonstration data. Markdown suggestions do not create additional demand or add hypothetical revenue to the evaluated plan. Discount percentages are scenario recommendations, not proven sales improvements.

## Demonstration and evaluation

Example and benchmark inputs are synthetic. Their results validate software behavior; they do not establish real-world predictive performance. No official competition scoring function was supplied.

The handwriting-style fixture uses a font and is not an evaluation of real human handwriting. Recorded measurements and observed provider failures are described in [AI_EVALUATION.md](AI_EVALUATION.md).

## Replanning

A previous plan may remain feasible or become infeasible after a disruption. Its old revenue is not a valid achievable benchmark when the changed constraints invalidate its shipments. Inspect the recalculated plan and independent constraint results.

This is an unexecuted planning sandbox. It does not reallocate dispatched shipments or model committed execution state.

## AI service availability

Configuration of a model and API key does not guarantee provider availability. A real request verifies access. Google can return location restrictions, timeouts, quota errors or internal errors. The mathematical optimizer remains available when AI is unavailable.

The requested model is `gemma-4-26b-a4b-it`; the alternative supported model is `gemma-4-31b-it`. No Gemini model is substituted under Gemma branding.

## Extraction review and ambiguities

AI-extracted records need human review against the original source. Possible issues include missing source references, missing quantities, unknown commodities or destinations, unsupported units, missing or inconsistent currency, duplicate records and contradictory quantities.

Unknown box or crate weights are not converted into kilograms. Missing or unsupported shelf-life units require correction. Units and currency absent from their source quotation are cleared for manual correction. Buying prices are not silently treated as destination selling prices.

AI-prefixed batch IDs are generated system labels, not extracted source facts. Optional costs absent from reviewed records default to zero, as documented for ordinary imports. Append or replace must be selected explicitly, and confirmation is required before applying records.

The extraction audit and source-reference details retain the actual record-specific evidence. Invalid canonical data is rejected even when an informational banner is not displayed.

## Natural-language scenario proposals

Only whitelisted operations are supported: route delays and scaling capacity, demand, prices or inventory. Unknown targets, arbitrary code and unsupported operations are rejected. Missing or ambiguous selectors require clarification. A null selector means all targets of that type; review the exact proposed values before confirming.

Delivery deadlines, forecasting and other unsupported requests need clarification rather than an invented operation. A changed base scenario requires a fresh proposal. Failed replacement requests invalidate older confirmations.

## AI explanations and unavailable evidence

Questions can request information absent from the verified dataset or plan. In that case the model may return unavailable-evidence messages instead of an answer.

Explanation citations and numerical tokens are checked, but these checks do not prove semantic correctness. Model-generated interpretations require judgment. Inspect the exact cited facts, inputs, explicit assumptions and solver outputs.

## Data handling and runtime

Core planning runs in the browser. AI requests send the selected text/image or bounded evidence to Google through the Worker. Explicit data-sharing consent and review confirmations remain required.

The first browser load downloads the pinned Python, NumPy and SciPy runtime. External connectivity and provider quotas can affect startup and AI response times. The standalone Python solver can run without the AI service.
