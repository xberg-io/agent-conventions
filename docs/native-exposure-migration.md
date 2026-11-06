# Native exposure migration

Status on 2026-11-06. The consumer gate stays `actions/context-exposure` (exposure.py, both presets). This repository
also runs the native Claude checks through `[exposure]` (see
[`native-exposure-2026-11-04.md`](../tools/context-evals/native-exposure-2026-11-04.md)).

## Upstream fixes are merged, not released

The four gaps recorded in the 2026-11-04 parity record are fixed on ai-rulez `main` and closed:
[536](https://github.com/Goldziher/ai-rulez/issues/536) (leakage scans `@path` imports) and
[537](https://github.com/Goldziher/ai-rulez/issues/537) (areas-file `exclude` and `[[accept]]`) in
[PR 541](https://github.com/Goldziher/ai-rulez/pull/541);
[538](https://github.com/Goldziher/ai-rulez/issues/538) (`--harness codex`, `codex_start_budget`) and
[539](https://github.com/Goldziher/ai-rulez/issues/539) (`mcp_server_tokens`) in
[PR 542](https://github.com/Goldziher/ai-rulez/pull/542). The latest release, 5.10.0, predates both. It rejects an
areas file with `exclude` (`AR9W5 unknown key "area.exclude"`, which turns every exposure rule off) and refuses
`--harness codex`. CI and the hooks run the latest release (org ADR-0015), so none of these keys can be committed
before a release that contains them.

## Parity against a build of `main`

ai-rulez `main` at `860f38b2`, built locally. Each consumer's main checkout as found (xberg `f9e24f8`, sceptre
`2924b5d`, liter-llm `56538e3`, alef `e05508f`, actions `97c0428`), and agent-conventions with the #8 module changes.
The areas file was `areas.py`'s output plus a per-area `exclude` of every compound in domains.toml's `names` and
terms that contains a word of the area, and the repository-scoped `[[accept]]` entries.

- **Claude leakage matches.** The 22 consumers with generated outputs agree with exposure.py's Claude preset. 20
  have no violation; sceptre's `OCR` occurrences are accepted, and they sit in `AGENTS.md`, imported by `CLAUDE.md`,
  so imports are scanned now. infra-release-runners, which is not gated, leaks in both with the same artifacts and
  terms; native also reads its generated banner comment (`Project: xberg-infra`), which exposure.py skips.
  paddle-to-onnx's `OCR` acceptance matches nothing in either tool, which native reports as stale (exit 2).
- **Start tokens.** Native Claude and Codex figures run 2-11% above exposure.py's legacy estimate (agent-conventions:
  Claude 4,316 against 4,137, Codex 4,998 against 4,551). The budgets must be re-measured on the release, not copied.

## Gaps that keep exposure.py as the gate

- **No release.** See above.
- **Codex leakage.** `exposure leakage` and `AR9W0` read only the Claude inventory, also under `harness = "codex"`.
  exposure.py checks the Codex preset too, whose listing holds the path-gated skills Claude hides; the
  `skill:xberg-brand-and-docs` acceptance applies there, in agent-conventions, crawlberg, docs-theme,
  html-to-markdown, liter-llm, sceptre and tree-sitter-language-pack.
- **A Git-ignored `.mcp.json` counts no servers.** Under the Claude harness `mcp_server_tokens` multiplies by zero
  when the root `.mcp.json` is ignored, which it is in every consumer (a generated output). Claude Code loads it
  regardless. Under Codex the ignored `.codex/config.toml` counts. Control: the same `.mcp.json` counts one server
  when it is not ignored.
- **Acceptances that match nothing.** An `[[accept]]` that matches nothing fails the run (`AR9I0`, exit 2), while
  exposure.py ignores an unused entry. domains.toml's acceptances are org-wide or per repository, so `areas.py` has
  to render each only where it matches: under Claude the brand-skill entry is stale in every consumer but
  infra-release-runners, and paddle-to-onnx's entry has to go.

The two upstream gaps need ai-rulez issues. Once a release carries 541 and 542 and they are fixed, move the
`exclude` and per-consumer `[[accept]]` rendering into `areas.py`, re-measure both budgets, and switch the action to
`ai-rulez exposure` (both harnesses) and `ai-rulez exposure leakage`.
