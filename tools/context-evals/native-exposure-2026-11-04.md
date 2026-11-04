# Native ai-rulez exposure against exposure.py, 2026-11-04

ai-rulez 5.10.0. agent-conventions at this branch; the consumers are their main checkouts as found (xberg `f9e24f8`,
sceptre `2924b5d`, liter-llm `56538e3`, alef `684c93e`, actions `a078260`), with the outputs already generated there.
Native figures come from `ai-rulez exposure` and `ai-rulez exposure leakage --areas <map>`, the map rendered for each
repository by `areas.py`. The exposure.py figure is its legacy estimate (start bytes / 3.9) without MCP schemas, since
the native report counts no MCP tool schemas.

| Repo | exposure.py claude (legacy, no MCP) | native start tokens | native / legacy | Leaks (exposure.py / native) |
|---|---:|---:|---:|---|
| agent-conventions | 4,000 | 4,180 | 1.045 | 0 / 0 |
| xberg | 4,420 | 4,591 | 1.039 | 0 / 0 |
| sceptre | 4,187 | 4,360 | 1.041 | 0 / 0 |
| liter-llm | 4,305 | 4,479 | 1.040 | 0 / 0 |
| alef | 4,312 | 4,483 | 1.040 | 0 / 0 |
| actions | 2,911 | 3,098 | 1.064 | 0 / 0 |

Both classify agent-conventions' 27 skills the same way: 18 at start, 8 path-gated, 1 user-only. The token estimates
differ by a constant factor of about 4%, which is an estimator choice, not a classification disagreement. The
`after-mcp-2026-10-26.md` totals (Claude 46,991, Codex 51,620) are not comparable: they include the measured MCP
server and predate the current outputs.

## Gaps that keep exposure.py as the gate

- **Codex.** `[exposure] harness` accepts only `claude`; there is no native Codex start figure, so the `codex=` budget
  stays in the action.
- **CLAUDE.md imports are counted but not leak-checked.** Since 5.9.8 the start budget counts `@AGENTS.md` (3,036
  of agent-conventions' 3,132 CLAUDE.md tokens), but `exposure leakage` and `AR9W0` read only the CLAUDE.md file
  itself. Control: adding `worktree` to the `sceptre` area reports one violation, in a skill listing, while AGENTS.md
  names it nine times. Every consumer's root CLAUDE.md is a single `@AGENTS.md` line, so the native check sees
  only skill and agent listings. An ai-rulez defect.
- **No equivalent of `names` or `[[accept]]` in an areas file.** A term without `_`, `/` or `.` matches as a whole
  word, so `xberg` matches inside `xberg-io`; domains.toml's `names` excludes such compounds. Native acceptances live
  in each consumer's `[[lint.accept]]`, not in the shared taxonomy. Once imports are checked, `xberg-io` in every
  root context would be reported unless this changes.
- **MCP tool schemas.** The native start figure leaves out the configured MCP servers' schemas (about 1.1k tokens for
  the restricted ai-rulez server), which exposure.py measures with `--measure-mcp`.

## What runs natively now

agent-conventions carries an `[exposure]` table: `areas_file = "tools/context-evals/exposure-areas.toml"` (rendered by
`areas.py --repo agent-conventions`, kept current by `test_areas.py`) and `start_budget = 4400`, about 5% above the
4,180 measured, as tight as the legacy `claude=5350` input. `validate` therefore runs `AR9W0`, `AR9W3`, `AR9W5` and
the `AR964` skill-listing row in this repository's CI. Controls: `start_budget = 4000` fails `AR9W3` (4,180, 180
over); adding `worktree` to an area fails `AR9W0` on the `agent-coordination` listing.
