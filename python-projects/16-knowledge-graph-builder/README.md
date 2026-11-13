# 16 - Knowledge Graph Builder & Query System

Turns unstructured documents into a knowledge graph (entities, relationships, dates, and the exact quote behind every fact),
and will answer multi-hop questions over it and show it in a visual explorer.
Advanced evolution of Project 4 (RAG Knowledge Assistant).

**Status: steps 1 and 2 of 8 are built (extraction and graph store; entity resolution).** The rest is not built yet.

| Step | What | State |
|---|---|---|
| 1 | Extraction and graph store | done |
| 2 | Entity resolution ("Acme Corp" = "Acme Inc." = "ACME") | done |
| 3 | Queries and graph-RAG (multi-hop questions with cited sources) | not started |
| 4 | Accounts and background job queue (pattern from project 15) | not started |
| 5 | Visual explorer (React + D3.js, "Paper Light" theme) | not started |
| 6 | Temporal facts ("who was CTO in 2021?") | not started |
| 7 | Conflict detection and fact checking | not started |
| 8 | Export (Cypher, CSV, JSON) and final docs | not started |

## Decisions

| Topic | Decision |
|---|---|
| Language | Python backend (FastAPI), JavaScript frontend (React + D3.js, later) |
| LLM for extraction | Local Ollama `llama3.1:8b` (the newest Llama that runs fast on 64 GB; Llama 4 Scout is 67 GB and does not fit, Llama 3.3 70B fits but is slow). Claude and OpenAI are switchable in settings |
| Graph engine | NetworkX in memory, built from the database. No graph database server needed |
| Neo4j / Memgraph | Export only (step 8). Neither is installed here, so the export will be checked for valid syntax but **not against a live database** |
| Database | SQLite by default (any SQLAlchemy URL works). Tables are created at startup; migrations arrive with accounts in step 4 |
| UI theme | "Paper Light" (background `#F7F6F2`, panels `#FFFFFF`, accent `#2F5FD0`; person `#2F5FD0`, organization `#0F9D8A`, place `#D9822B`, concept `#C2417C`) |

## Run it

```bash
cd python-projects/16-knowledge-graph-builder
pip install -r requirements.txt
ollama pull llama3.1:8b
cp .env.template .env        # optional, everything has a default
python3 server.py            # http://127.0.0.1:8016  (API docs at /docs)
```

```bash
curl -F "file=@report.pdf" localhost:8016/api/documents        # .txt .md .pdf .docx
curl localhost:8016/api/documents/<id>                         # status, progress, stats
curl localhost:8016/api/graph                                  # nodes + edges
```

There is no UI yet (step 5): use `/docs` or curl.

## How a document becomes a graph

1. **Read** the file (txt, md, pdf, docx) or pasted text into plain text. Scanned PDFs have no text and are refused with that reason.
2. **Chunk** it into passages of about 1,500 characters on sentence boundaries, with overlap.
3. **Ask the model** for facts: `subject | predicate | object`, start and end dates, and an exact quote from the passage.
4. **A second "what did you miss?" call** per passage (`GLEANING_PASSES=1`). Small local models stop early; this raised recall from 71% to 79% in the evaluation below.
5. **Check every fact in code** and refuse what the passage does not back up:
   - the quote must really be in the passage; it is replaced by the exact original wording
   - subject and object must appear in the quote (no pronouns, no invented names). If the quote only says "He" or "Turing", the previous sentence may be added to the quote when it holds the name
   - values (amounts, counts) must appear in the quote
   - dates must appear in the quote, otherwise the date is dropped and the fact is kept
   - passive wording ("was founded by") is turned around so the subject is always the one doing it
   - a word-order check rejects relations written the wrong way round, without calling the model
   - vague predicates ("is", "has", "related to") are refused
6. **Double-check with the model** (`VERIFY_FACTS=true`): one short yes/no call per fact, "is this statement true according to the quote?". It catches negations and plans ("did not acquire", "might buy"); it is not reliable at direction, which is why step 5 has the word-order check.
7. **Store**: entities (matched by normalised name, leading "the/a/an" removed), facts, and one source row per quote (document, passage, exact text, whether the double-check passed). The same fact found again only adds a source. The same statement with and without a date becomes one fact; different periods stay different facts.
8. **Resolve entities** (see "Entity resolution" below): merge the same name written differently, suggest the unsure pairs.

Every number the pipeline refuses or repairs is counted per document (`stats.rejected`, `stats.adjusted`), so you can see what the checks did.

## Entity resolution (step 2)

The same thing is often written differently: "Acme Corp", "ACME", "The Acme Company"; "Alan Turing", "Turing", "Dr. Alan M. Turing";
"IBM", "International Business Machines". After every document, and whenever you call `POST /api/resolution/run`, entities are
compared and sorted into three groups:

| Group | What happens | Examples |
|---|---|---|
| **Safe** | merged automatically | the same name apart from case, accents, punctuation, titles (people), company suffixes, a leading "the" ("Acme Corp" / "ACME", "ETH Zurich" / "ETH Zürich", "Henric III" / "King Henric III of Vestland" when no other "Henric III of ..." exists); a surname or first name in the same document as exactly one matching full name ("Turing" with "Alan Turing") |
| **Unsure** | recorded as a **suggestion** with a score and the reasons; a person accepts or rejects it | one name inside another ("Acme" / "Acme Labs"), initials ("IBM"), small spelling differences ("Nordwind" / "Nordwin"), a surname that fits two people ("Brandt" with Jonas and Elena) |
| **Never** | not merged and not suggested | different types (person / organization), names that differ in a number or letter ("Widget-X" / "Widget-W", "Henric II" / "Henric III", "Apollo 11" / "Apollo 13"), "of" parts that differ ("Henric III of Vestland" / "... of Karelia"), two entities that a fact links to each other, a pair a person rejected |

- **Aliases.** The merged name is kept as an alias, so a later document that says "ACME" lands on "Acme Corp" without creating a duplicate.
- **Undo.** Every merge is recorded with what it moved; `POST /api/resolution/merges/{id}/undo` restores the entity, its facts and sources, its name and type exactly (tested by comparing the whole database before the merge and after the undo). Facts or documents deleted in the meantime are simply not restored.
- **Same fact twice.** When a merge brings two copies of one fact together they become one fact with all the sources; an undated copy joins a dated one; different periods stay separate.
- **Second opinion from the model** (optional, `RESOLUTION_USE_LLM=true` or `use_llm` on the run call): a "yes" raises a suggestion's score, a "no" lowers it a little. It never merges anything by itself.
- Merges, accepts, rejects and undos wait (HTTP 409) while a document is being read, so they cannot collide with it.

### Measured

53 hand-labelled entities in 29 groups (names that are one real thing), including look-alikes designed to trip it
(`eval/entities.json`; synthetic, written by the project author). Run `python3 -m eval.run_resolution_eval [--llm]`.
Pairs are counted after the automatic merges, so "Acme Corp", "ACME" and "Acme Inc." make one group and one doubtful link to "Acme Labs" counts once.

| | Automatic merges: correct | True pairs it handles by itself | Unsure pairs: found | Suggestions that were right |
|---|---|---|---|---|
| Rules only | **18 of 18 (100%)** | 44% (18 of 41) | 93% | 72% |
| Rules + `llama3.1:8b` opinion | 18 of 18 | 44% | 86% | 86% |

- The model's "no" was often wrong (it said no to "IBM" / "International Business Machines" and "Turing" / "Alan Turing"; used as a veto it cut
  suggestion recall from 93% to 29%), while its "yes" was right every time. That is why it only nudges the score and is off by default.
- One automatic merge was wrong in the first version of the benchmark ("Henric III" with "Henric III of Karelia"); the rule now only
  merges a bare name when no differently-qualified namesake exists.
- **On real extractions** (the six evaluation documents plus the Turing text, read by the model): 58 entities, 0 merges, 0 wrong merges,
  1 suggestion ("Kestrel Institute" / "Kestrel Institute's Quantum Lab", correctly left for a person). The model already wrote names
  consistently there, so this run shows the resolver does no harm, not that it finds many duplicates. On three small documents that
  name things differently ("Acme Corporation"/"Acme Corp", "Dr. Alan Turing"/"Alan M. Turing") it merged both pairs and kept the aliases.
- 53 entities and 14 unsure pairs are small numbers: one pair moves a percentage by 7 points.

### Limits of resolution

- **Name-based.** It does not know that "Big Blue" is IBM or that "the Iron Lady" is Thatcher; there is no knowledge outside the documents.
- **Two different people with the same full name** are merged (the names are identical, so nothing can tell them apart). Undo is the remedy.
- The kept display name is the fuller one and can include a title ("Dr. Alan Turing").
- Every run compares all candidate pairs; it was tested on dozens of entities, not on tens of thousands. A word shared by more than 200 names (like "University") is not used to pair entities.
- No UI for reviewing suggestions yet (step 5): use `/docs` or curl.

## API

| Endpoint | |
|---|---|
| `POST /api/documents` (file) / `POST /api/documents/text` | add a document, read in the background |
| `GET /api/documents`, `GET /api/documents/{id}` | status, progress, stats, error |
| `POST /api/documents/{id}/reprocess` | read again (replaces what was read before) |
| `DELETE /api/documents/{id}` | remove it and every fact only it supported |
| `GET /api/graph?document_id=&type=&limit=` | the most connected `limit` entities and links between them |
| `GET /api/graph/stats` | counts by type, top predicates |
| `GET /api/entities?q=&type=`, `GET /api/entities/{id}` | search; facts going out of and into an entity, and its aliases |
| `GET /api/entities/{id}/neighborhood?depth=1..3` | everything within N links |
| `GET /api/facts/{id}` | the fact, its dates, and every source quote with its passage |
| `POST /api/resolution/run` (`{"use_llm": false, "auto": true}`) | merge the safe pairs, refresh suggestions |
| `GET /api/resolution/suggestions?status=pending` | suggested merges with score, reasons, both entities' facts |
| `POST /api/resolution/suggestions/{id}/accept` (`{"keep_id"}` optional) / `.../reject` | decide a suggestion |
| `POST /api/entities/merge` (`{"keep_id", "absorb_id"}`) | merge by hand (refused for different types or entities a fact links) |
| `GET /api/resolution/merges`, `POST /api/resolution/merges/{id}/undo` | history and undo |
| `GET /api/health` | whether the configured model is reachable and installed |

A document left "processing" by a restart is marked failed with a reason and can be read again. If the model is not
running, the document fails with "Cannot reach Ollama ... (ollama serve)" instead of hanging.

## Settings (`.env`)

See `.env.template`. The ones that matter: `LLM_PROVIDER` (ollama, anthropic, openai), `OLLAMA_MODEL`, `VERIFY_FACTS`,
`GLEANING_PASSES`, `AUTO_RESOLVE`, `RESOLUTION_USE_LLM`, `CHUNK_CHARS`, `MAX_DOCUMENT_CHARS` (100,000), `MAX_UPLOAD_MB`. The Anthropic and OpenAI clients exist
but were **never run against the live services**.

## Measured accuracy

Six short documents with 38 hand-labelled facts that must be found (company news, biographies, a product spec,
fictional history, science, and a "traps" document with negations, plans and rumours). Model: `llama3.1:8b`, temperature 0.
Run it yourself: `python3 -m eval.run_eval --model llama3.1:8b --verify --gleaning 1`.

| Configuration | Found (recall) | Correct among what it returned (precision) | Time for the 6 documents |
|---|---|---|---|
| First version: basic prompt, basic checks | 47% | 77% | |
| Checks only (no second pass, no double-check) | 71% | 93% | 112 s |
| + "what did you miss?" pass | 79% | 90% | 134 s |
| **+ double-check (default)** | **74%** | **94%** | 164 s |

Among the facts it found, the relationship wording matched my list of accepted wordings every time and the dates were
exactly right 94% of the time (17 of 18).

How much to trust these numbers:
- **They are optimistic.** I tuned the prompt and the checks while looking at these same six documents. Treat them as a
  measure of what the checks do, not as accuracy on your documents.
- Only 38 facts: a difference of one or two facts moves a percentage by 3-5 points.
- Two things in my own scoring were corrected after the first runs and the saved outputs were re-scored without calling the model
  (`eval/rescore.py`): a reversed fact I had wrongly listed as acceptable, and missing spelling variants of a king's name.
  The scorer ignores descriptor words ("Widget-X sensor" = "Widget-X").
- On a seventh text I did not tune on (a 1,200-character biography of Alan Turing), the default settings returned 16 facts.
  I checked them by hand: 13 were right, 1 was credited to the wrong subject ("Turing introduced the imitation game", the text
  says the paper did) and 2 had oddly placed dates (a graduation year stored as an end date). It missed roughly a third of the stated facts, mostly in sentences that start
  with "He" or "There" two sentences after the name.

## Known limits

- **Pronouns and long reference chains.** A fact is kept only if the subject and object are in the quote, or the sentence right
  before it. "He ... There he ..." chains lose facts. This is deliberate: guessing who "he" is would add wrong facts.
- **Speed.** About 25-45 seconds per short passage with the double-check and the second pass on an M1 Max. 100,000 characters
  is roughly an hour (an estimate from the short test documents; I have not timed a long one). Turn off `VERIFY_FACTS` or `GLEANING_PASSES` to trade accuracy for speed (about 20 s per passage).
- **The model still makes mistakes** the checks cannot see: a reversed fact whose quote is ambiguous ("the prize was awarded to
  Lena Hartmann" read as Lena awarding it) and some plans written as "might buy" got through in the evaluation.
- **Entity names are whatever the model wrote** (e.g. "journal Nature Photonics", "paper Computing Machinery and Intelligence"); resolution merges
  spellings of one name but does not clean up such prefixes.
- **One document is read at a time** (a local model answers one request at a time). A real job queue comes in step 4.
- **No accounts, no login yet.** The server binds 127.0.0.1 by default. Do not expose it before step 4.
- Dates are only recorded when the quote states them; "last year" or "since the merger" are not resolved.
- English only (the prompts and the stop-word lists are English).

## Tests

```bash
python3 -m pytest                 # 267 tests, about 3 s, no model needed (a scripted fake model stands in)
python3 -m pytest -m ollama -s    # one live test against your local model (about 20 s)
```

The tests were break-tested: 125 deliberate small bugs were put into the code one at a time (removing a check, flipping a
comparison, skipping a cleanup), and the tests caught all of them (the first round of the resolution code missed 12; each got a test or the dead code was deleted). Testing and the real-document run found four real problems, now fixed: a Latin-1
text file decoded as garbage, a duplicate source row that crashed storing a fact seen twice in one batch, and a name rule that
rejected most sentences saying "Turing" for "Alan Turing", and a word-order check that wrongly rejected
"Acme, founded by Maria, acquired Beta".

## Layout

```
server.py                    FastAPI app
src/core/                    settings, database
src/models/graph.py          Document, Chunk, Entity, Fact, FactSource
src/models/resolution.py     EntityAlias, MergeSuggestion, MergeRecord
src/services/                readers, chunker, llm (Ollama/Anthropic/OpenAI), extraction (prompts + checks),
                             pipeline (document -> graph), resolution (merge/suggest/undo), graph_store (NetworkX views), text_utils
src/api/                     documents.py, graph.py, resolution.py
eval/                        labelled documents (docs/), gold.json, scoring, run_eval.py, rescore.py, saved results;
                             entities.json + run_resolution_eval.py for resolution
tests/
```
