# Native ai-rulez exposure against exposure.py, 2026-11-06

The parity record that retires `exposure.py` as the consumer gate
([issue #4](https://github.com/xberg-io/agent-conventions/issues/4)). ai-rulez 5.11.0, built from `main` at
`9ef6dfaf` before its release (PRs 541 and 542, #546); exposure.py at agent-conventions `9578f9f`, the last commit
that has it. agent-conventions is this branch, generated with that build; the consumers are their main checkouts as
found, with the outputs already generated there (xberg `f9e24f8`, xberg-enterprise `7c3fa8c`, crawlberg `796f958`,
html-to-markdown `d9450cf`, liter-llm `56538e3`, tree-sitter-language-pack `c753c62`, sceptre `2924b5d`, alef
`75bb740`, actions `97c0428`, paddle-to-onnx `391276e`). Native leakage used the map `areas.py --repo NAME` renders
at this branch. Both estimators divide bytes by 3.9; exposure.py's figures here are its legacy estimate. Rerun with the
released 5.11.0 (`npx -y ai-rulez@latest`), every native figure and leak result below is unchanged.

## agent-conventions

| Check | exposure.py | Native | Recorded |
|---|---:|---:|---:|
| Claude start tokens, no MCP | 4,137 | 4,319 | 4,000 / 4,180 (11-04) |
| Codex start tokens, no MCP | 4,551 | 4,998 | - |
| Claude start tokens with the ai-rulez server | 5,282 (measured, 1,145) | 5,469 (`mcp_server_tokens = 1150`) | 5,145 against `claude=5350` (11-04) |
| Codex start tokens with the ai-rulez server | 5,696 (measured) | 6,148 | - |
| Claude skills at start / path-gated / user-only | 20 / 8 / 1 | 20 / 8 / 1 | 18 / 8 / 1 (11-04) |
| Codex skills at start | 26 | 29 | - |
| Leaks (Claude, Codex) | 0, 0 (1 accepted, Codex) | 0 (Claude inventory only) | 0 |
| Descriptions over 250 characters | 0 | 0 (listing lines, max 240) | 0 |
| Collisions | no check | 0 of 0 pairs | - |
| `validate --strict --no-local`, 8 configurations | - | no findings | - |

Start tokens by kind, Claude, no MCP: instructions 2,972 against 3,158 (CLAUDE.md with the imported AGENTS.md),
skills 1,096 against 1,090, agents 69 against 68, MCP server names 0 against 3. Codex: AGENTS.md 2,969 against 3,062,
skills 1,513 (26) against 1,933 (29). The recorded 11-04 figures differ by the content changed since.

## Consumers

Start tokens without MCP. Leaks are violations after acceptances; every consumer here has none in either tool.

| Repo | Claude exposure.py | Claude native | Codex exposure.py | Codex native | Accepted (exposure.py Claude/Codex; native) |
|---|---:|---:|---:|---:|---|
| xberg | 4,420 | 4,597 | 6,040 | 6,181 | 0/0; 0 |
| xberg-enterprise | 4,774 | 4,954 | 5,681 | 6,177 | 0/0; 0 |
| crawlberg | 4,401 | 4,562 | 5,319 | 5,374 | 0/1; 0 |
| html-to-markdown | 4,382 | 4,564 | 5,298 | 5,363 | 0/1; 0 |
| liter-llm | 4,305 | 4,485 | 4,814 | 5,184 | 0/1; 0 |
| tree-sitter-language-pack | 4,377 | 4,565 | 4,938 | 5,322 | 0/1; 0 |
| sceptre | 4,187 | 4,363 | 4,592 | 4,968 | 1/2; 2 |
| alef | 4,312 | 4,489 | 4,817 | 5,323 | 0/0; 0 |
| actions | 2,911 | 3,101 | 3,515 | 3,612 | 0/0; 0 |
| paddle-to-onnx | 3,913 | 4,091 | 4,466 | 4,759 | 0/0; stale before this branch |

The other ten consumers with generated outputs (assets, docs-theme, homebrew-tap, infra, internal-docs,
scoop-bucket, sdks, test-apps, test_documents, agent-conventions' main checkout) agree the same way: no leaks in
either tool, native start tokens 4-5% above exposure.py for Claude and 5-10% for Codex. Across all twenty: Claude
4-7%, Codex 1-11%.

Against `after-mcp-2026-10-26.md`, whose nine repositories include the measured ai-rulez server: exposure.py
reproduces it (Claude 47,229 against 46,991, Codex 51,884 against 51,620, +0.5% from content since). Native with
`--mcp-server-tokens 1150` gives Claude 55,780 and Codex 61,304; without MCP the two tools give Claude 39,680
against 38,069 and Codex 47,504 against 45,014.

## Disagreements and which classifier is wrong

1. **HTML comments.** exposure.py strips `<!-- -->` before counting; native counts them, so the generated banner adds
   about 90 tokens per generated root file (CLAUDE.md and AGENTS.md). Neither is proven: whether Claude Code and Codex
   load comments was not probed. Native is the conservative side; the budgets are measured natively, so it does not gate
   wrongly.
2. **Codex skills with `allow_implicit_invocation: false`.** exposure.py drops a Codex skill whose SKILL.md says
   `disable-model-invocation: true`; native lists every `.agents/skills` skill, since the `agents/openai.yaml`
   policy is not modelled upstream. The frontmatter key is Claude's, so exposure.py is right only because ai-rulez
   writes both for the same skills. Native over-counts (3 skills here); an ai-rulez gap, not filed.
3. **Codex listing line.** Native counts the skill's path in each Codex listing line, as Codex's listing does;
   exposure.py counts `name: description`. exposure.py is wrong.
4. **MCP schemas.** exposure.py starts the named server and measures it (1,145 tokens for the restricted ai-rulez
   server) and counts every other server as 0 (`playwright` in xberg, crawlberg, html-to-markdown, liter-llm,
   tree-sitter-language-pack and alef). Native charges a fixed `mcp_server_tokens` per configured server, so
   `playwright` counts as 1,150. Both are wrong for `playwright`; native is the closer bound, and the per-server
   figure is a model choice, not a defect.
5. **Compounds and imports.** With the 11-04 map (no `exclude`), 5.11.0 reports `xberg` three times in
   agent-conventions' AGENTS.md (`xberg-io`), which exposure.py skips through `names`. Not a disagreement once
   areas.py renders `names` and the other domains' compound terms as `exclude`: the leak sets match in every
   consumer. Native scans the imported AGENTS.md now (#536), which closes the 11-04 gap.
6. **Word boundary.** exposure.py treats `_` as part of a word, native does not (`invoice` matches
   `INVOICE_ID`). No occurrence in any consumer; native is the stricter and matches ai-rulez's documented rule.
7. **Stale acceptances.** paddle-to-onnx's `OCR` acceptance matches nothing in either tool. exposure.py ignores it,
   native fails it (`AR9I0`, exit 2). Native is right; the entry is removed from domains.toml. The brand skill's
   `xberg` acceptance holds only where Codex lists the path-gated skill, so it carries `harnesses = ["codex"]` and is
   not rendered for the Claude map, where it would be stale in every consumer.
8. **Codex leakage.** exposure.py checks the Codex preset; native `exposure leakage` reads the Claude inventory under
   either harness ([Goldziher/ai-rulez#545](https://github.com/Goldziher/ai-rulez/issues/545), open). AGENTS.md is
   still covered through Claude's `@AGENTS.md` import; the path-gated skills only Codex lists are not. Today the one
   Codex-only occurrence is the accepted brand skill, so the leak sets agree; the coverage gap stays until #545 is
   fixed. An ai-rulez defect.
9. **Description length.** ai-rulez has no gate-owned equivalent: `AR802` follows each consumer's
   `[lint.description] max_length` (default 1024). The action keeps the 250-character bound itself, on the listing
   lines `exposure inventory` reports for every invocable skill and agent (path-gated ones too, as Codex lists them).
   The two agree in every consumer: none in agent-conventions, and crawlberg's and liter-llm's checkouts carry a
   254-character `alef` skill that both flag (alef's current copy is 231).

## Controls

Each check failed on purpose once, with the released 5.11.0:

- A `liter-llm` line appended to the generated AGENTS.md: `exposure leakage` reports `AR9W0` at `AGENTS.md:149`
  (an imported file) and the action exits 1.
- `start_budget = 5000` (5,469 measured): `ai-rulez exposure` exits 2, `OVER by 469`; `codex_start_budget = 6000`
  (6,148): `exposure --harness codex` exits 2, `OVER by 148`.
- sceptre, which sets no `start_budget`: the action fails closed (`start_budget is not set`) and warns for Codex;
  its two `OCR` occurrences are reported as accepted.
- A 400-character description on the path-gated `adr-authoring` skill: the action fails, `listed description over 250
  characters: .claude/skills/adr-authoring/SKILL.md (400 characters)`.
- ai-rulez 5.10.0 on `PATH`: the action stops, `context-exposure needs ai-rulez >= 5.11.0, found 5.10.0`.
- The 11-04 map without `exclude`: three `AR9W0` violations, as above.

## Not done: pinning ai-rulez

The issue's last item asks to pin ai-rulez in `ai-rulez-validation.yml`. It conflicts with org ADR-0015: ai-rulez is
never pinned and always runs at its latest release (`npx -y ai-rulez@latest`, `setup-ai-rulez@v1`). A release can
change the gate without a config change; that is the accepted cost of the ADR, and this record is re-measured on the
release instead.
