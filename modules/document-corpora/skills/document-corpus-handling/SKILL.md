---
type: Playbook
title: Document Corpus Handling
description: "Partner and public-record document corpora: provenance, use vs redistribution, repo visibility, sha256 sharing, opaque ids, redaction, exact-bytes commit gates. Use when fetching, citing or committing corpus material."
paths:
  - "**/ATTRIBUTIONS.md"
  - "**/MANIFEST.csv"
  - "**/*corpus*"
  - "**/*corpus*/**"
  - ".gitmodules"
x-ai-rulez:
  kind: skill
  id: document-corpus-handling
  metadata:
    name: document-corpus-handling
---

# Document corpus handling

Design-partner document corpora arrive under a commercial agreement, but that says nothing about
the underlying material. **Know which you are holding before deciding anything.**

## Public records are not confidential data

Municipal corpora scraped from public authority websites are public records. US local-government
ordinances, agendas, minutes and resolutions are *edicts of government* and carry no copyright at
all; the test-documents repo's `ATTRIBUTIONS.md` vendors City of Sugar Land records into a
**public** repo on exactly that basis. For this class of material:

- Using it for testing, benchmarking and tuning is unproblematic.
- Rendering pages to PNG and reviewing them with vision is unproblematic, and is the **only**
  reliable way to adjudicate OCR output.
- Sharing by sha256 between agents is unproblematic.

Do not treat public-record material as radioactive. Over-caution has a real cost: it blocks the
page-level review that catches content-destroying extraction bugs no text metric detects.

## Two things still need a decision, not an assumption

1. *Redistribution is not the same question as use.* Edicts of government cover the authority's own
   official works. Third-party material merely **filed with** an authority (a contractor's bid, a
   consultant's report, a campaign-finance form completed by an individual) can retain the filer's
   copyright even though the authority publishes it. Bulk republication of personal details remains
   a live consideration under GDPR/CCPA-style regimes, which public availability weakens but does
   not fully answer. And the partner agreement governs independently of all of it.
2. *Repo visibility is a fact to check, not to infer.* `xberg-io/test_documents` is **public**. Run
   `gh repo view <repo> --json visibility` before proposing to commit corpus-derived bytes, and
   state the result when asking a human to approve; an approval given without it is not informed.

Nothing identifying a private corpus (its partner's name, filenames, manifests, sample documents)
lands in a public repo: not in code, tests, fixtures, comments, commit messages, PR descriptions or
docs. Use neutral placeholders (`<namespace>`, `internal-corpus`, `acme/foo.pdf`); private material
belongs in the private repo that owns it.

## Share by content hash, not by copy

Corpus objects live content-addressed in the private bucket:

```sh
gcloud storage cp gs://xberg-internal-test-documents/objects/<sha256> ./<local-name>
```

A sha256 identifies the exact file, lets another agent fetch it with credentials it already has,
and publishes nothing new. The corpus fetch script (`scripts/fetch_corpus.py --auth` in test_documents,
`test_documents/scripts/fetch_corpus.py` from xberg or xberg-enterprise) uses
Application Default Credentials for private buckets; without `--auth` it uses anonymous HTTPS and
will not serve them. Keep anything materialised out of git.

## Identify documents by opaque id, not filename

Corpus filenames are long, unstable and often embed a person's name, and a findings doc that names
files cannot be shared outward without a re-read. The id is `sha1(relpath)[:10]`, quoted alongside
the sha256 when the recipient needs the bytes. **`relpath` is relative to the corpus root**: hashing
an absolute path yields an id that matches nothing already published. Verify a new id against a
known pair before trusting a batch.

This applies to findings docs, commit messages, code comments and messages to other agents. When
quoting extracted text as evidence, prefer headings, numbers or boilerplate, and write a private
individual's name as `[NAME]`; an official acting in an official capacity (a mayor signing an
ordinance) is not a private individual.

## Gate the commit on exact bytes

Check everything a corpus-derived run writes with an exact-bytes search, not a text grep: a
filename can sit inside a generated PDF's metadata where a text search will not find it. Make the
check fail the commit, not just print — `[ "$BAD" = "0" ] || exit 1`. A printing-only check has
already let two filenames through.
