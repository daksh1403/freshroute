# Contributing to FreshRoute

Clone the repo, create a branch and follow the setup in the README. Keep changes focused, open a pull request and include the checks you actually ran.

The optimizer is the source of numerical truth. AI code must propose data or explain verified outputs; it must never create allocations, bypass confirmation, fabricate measurements or substitute another model under Gemma branding.

Run `python -m pytest -q`, `npm run test:ai`, and the synthetic benchmark before changing the engine or AI contracts. Add a regression test when fixing a numerical or validation bug. Real API checks are separate and require your own ignored `.dev.vars` file. Never commit keys, warehouse records, or user images.

Please label synthetic examples, keep dependencies small and explain changes to assumptions. Original code is MIT licensed; bundled libraries and Gemma remain covered by their own licenses and terms.
