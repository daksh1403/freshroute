# FreshRoute AI — Multimodal Supply Chain Intelligence

## One-line pitch

Turn a stock-note photo into human-verified inventory, a mathematically optimized produce delivery plan, and evidence-backed answers with Gemma 4.

## Project description

We built FreshRoute for PS 07 at Bugged Out! — IEEE RAS VIT Chennai. Produce allocation gets difficult when short shelf life, uneven market demand, changing prices and shared transport capacity interact. A spreadsheet-only solver also assumes the operator has already converted every note and photograph into clean data.

FreshRoute Intelligence uses the actual `gemma-4-26b-a4b-it` model through the Gemini API and official Google GenAI SDK to read selected text or images. It returns candidate inventory, demand and market-price records with source quotes, missing fields and ambiguities. The operator checks the source, edits the proposed canonical records, chooses append or replace, and confirms. Python then validates the scenario before SciPy/HiGHS computes an allocation. Gemma never invents the dispatch quantities.

The dashboard compares that plan with a feasible first-expire-first-out baseline using identical inputs. It exposes transport expenditure, net revenue, spoilage, viable leftovers, fulfillment and independent constraint checks. Gemma can answer questions from a bounded selection of recomputed facts, with inspectable citations and numerical checks. Natural-language disruptions become whitelisted operations; after confirmation, the same optimizer replans and reports real changes.

Our 23-scenario synthetic optimization benchmark recorded zero constraint violations and no revenue regressions versus FEFO. The original synthetic example improves net revenue from 19,811 to 21,123 INR while increasing spoilage from zero to 110 kg; the UI explicitly shows that trade-off. Two small synthetic image fixtures each scored 14/15 raw exact field matches; the mismatch was `day` versus `days`, which the deterministic unit conversion handles. These are small software demonstrations, not real-world accuracy claims.

A live browser test completed image extraction, blocked an unconfirmed import, recorded a manual correction, optimized the reviewed 255 kg inventory, interpreted and applied a confirmed route delay, and produced a cited Gemma explanation. The resulting plans had zero constraint violations. The app runs on Cloudflare Workers with the optimization engine in a Pyodide browser worker. AI failure does not disable the standalone optimizer.

## Technologies used

Gemma 4 (`gemma-4-26b-a4b-it`), Gemini API, official `@google/genai` JavaScript SDK, Cloudflare Workers and Static Assets, Python, SciPy/HiGHS, NumPy, pandas, Pyodide/WebAssembly, JavaScript, HTML/CSS, openpyxl, Streamlit/Plotly for the original local dashboard, pytest, Node test runner, Playwright and GitHub Actions.

## Google DeepMind — Best Use of Gemma 4

Gemma is the input and interpretation layer of our workflow, rather than a decorative summary button. We use its visual and text understanding to turn stock-note images and messages into candidate operational records with field-level source references and ambiguity reporting. Real requests use `gemma-4-26b-a4b-it`; we do not substitute a Gemini model and call it Gemma. The application shows the requested model, returned version and measured latency.

The same model interprets constrained natural-language what-if requests and explains verified optimization evidence. Its outputs cannot directly mutate stock or create shipment allocations. Strict application schemas, explicit human confirmation, known-target checks, deterministic unit conversion, exact solver calculations, and evidence citation checks connect flexible language understanding to a reproducible mathematical system. Live API and browser measurements are documented in `docs/AI_EVALUATION.md`, including observed failure modes and limitations.

## DigitalOcean — Best Open-Source AI Project

FreshRoute's original source is public and MIT licensed. Developers can reuse the extraction contracts, confirmation boundary, canonical scenario adapters, evidence generation and standalone optimizer. The source includes labeled examples, test fixtures, a synthetic benchmark, contribution instructions and separate live-versus-mocked checks. Gemma's open-weight model family contributes materially through the hosted Gemini API integration; our license does not relicense Gemma, the API or third-party dependencies.

We are submitting this as an open-source AI project. We do not claim to have trained a model, built an original model harness, implemented an Agent Skill Open Standard integration, or used DigitalOcean infrastructure. Sponsor eligibility must be checked against this event's final published rules.

## 60–90 second demonstration script

Open the actual app and allow the Python runtime to finish loading before the presentation. Network/model latency can affect the duration; there are no prerecorded solver or AI responses in this sequence.

- **0–10 seconds:** “FreshRoute helps distribute produce before it spoils. Our extra challenge was getting stock out of a notebook and into a trustworthy optimizer.” Open AI inventory import and select the labeled printed-note image.
- **10–35 seconds:** Run Gemma extraction. “This is a real Gemma 4 request. We preserve source words and missing values. The model proposes records; it cannot dispatch stock.” Show the source references and make or inspect a manual correction.
- **35–50 seconds:** Choose replace, confirm the reviewed records and optimize. “These numbers come from HiGHS, with a FEFO comparison and independent constraint checks.” Inspect actual revenue, spoilage and fulfillment, without promising an improvement on every example.
- **50–70 seconds:** Ask “What if route R-CHG is delayed by three hours?” Inspect the structured proposal, confirm and run the actual updated optimizer.
- **70–90 seconds:** Ask Gemma about the updated plan. Open a cited source fact and the zero-violation result. “Language and vision help us understand the input; deterministic math remains the numerical source of truth.”

## Required links

- Public repository: https://github.com/daksh1403/freshroute
- Cloudflare Workers deployment: https://freshroute.dakshx.workers.dev/
- No demo video has been recorded or published. Do not submit a fabricated video URL.

Hosted optimization and photo-to-validated-optimization passed browser checks. A separate hosted browser run completed confirmed natural-language what-if optimization and a cited Gemma explanation. The first combined hosted run encountered a Google internal error, so it is recorded as a failure; the complete local sequence passed. See `docs/AI_EVALUATION.md` for exact scope and reproduce the live checks before judging.
