# 16 - Knowledge Graph Builder & Query System

Turns unstructured documents into a knowledge graph (entities, relationships, dates, and the exact quote behind every fact),
and will answer multi-hop questions over it and show it in a visual explorer.
Advanced evolution of Project 4 (RAG Knowledge Assistant).

**Status: step 1 of 8 is built (extraction and graph store).** Nothing below the "Build plan" line is built yet.

| Step | What | State |
|---|---|---|
| 1 | Extraction and graph store (this README) | done |
| 2 | Entity resolution ("Acme Corp" = "Acme Inc." = "ACME") | not started |
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

Every number the pipeline refuses or repairs is counted per document (`stats.rejected`, `stats.adjusted`), so you can see what the checks did.

## API

| Endpoint | |
|---|---|
| `POST /api/documents` (file) / `POST /api/documents/text` | add a document, read in the background |
| `GET /api/documents`, `GET /api/documents/{id}` | status, progress, stats, error |
| `POST /api/documents/{id}/reprocess` | read again (replaces what was read before) |
| `DELETE /api/documents/{id}` | remove it and every fact only it supported |
| `GET /api/graph?document_id=&type=&limit=` | the most connected `limit` entities and links between them |
| `GET /api/graph/stats` | counts by type, top predicates |
| `GET /api/entities?q=&type=`, `GET /api/entities/{id}` | search; facts going out of and into an entity |
| `GET /api/entities/{id}/neighborhood?depth=1..3` | everything within N links |
| `GET /api/facts/{id}` | the fact, its dates, and every source quote with its passage |
| `GET /api/health` | whether the configured model is reachable and installed |

A document left "processing" by a restart is marked failed with a reason and can be read again. If the model is not
running, the document fails with "Cannot reach Ollama ... (ollama serve)" instead of hanging.

## Settings (`.env`)

See `.env.template`. The ones that matter: `LLM_PROVIDER` (ollama, anthropic, openai), `OLLAMA_MODEL`, `VERIFY_FACTS`,
`GLEANING_PASSES`, `CHUNK_CHARS`, `MAX_DOCUMENT_CHARS` (100,000), `MAX_UPLOAD_MB`. The Anthropic and OpenAI clients exist
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
- **Entities are matched by name only** (case, spacing, punctuation, leading articles). "Turing" and "Alan Turing" or
  "Acme Corp" and "Acme Inc." are separate entities until step 2. An entity name is whatever the model wrote, so two documents
  can disagree on spelling.
- **One document is read at a time** (a local model answers one request at a time). A real job queue comes in step 4.
- **No accounts, no login yet.** The server binds 127.0.0.1 by default. Do not expose it before step 4.
- Dates are only recorded when the quote states them; "last year" or "since the merger" are not resolved.
- English only (the prompts and the stop-word lists are English).

## Tests

```bash
python3 -m pytest                 # 179 tests, about 2 s, no model needed (a scripted fake model stands in)
python3 -m pytest -m ollama -s    # one live test against your local model (about 20 s)
```

The tests were break-tested: 69 deliberate small bugs were put into the code one at a time (removing a check, flipping a
comparison, skipping a cleanup), and the tests caught all 69. Testing and the real-document run found four real problems, now fixed: a Latin-1
text file decoded as garbage, a duplicate source row that crashed storing a fact seen twice in one batch, and a name rule that
rejected most sentences saying "Turing" for "Alan Turing", and a word-order check that wrongly rejected
"Acme, founded by Maria, acquired Beta".

## Layout

```
server.py                    FastAPI app
src/core/                    settings, database
src/models/graph.py          Document, Chunk, Entity, Fact, FactSource
src/services/                readers, chunker, llm (Ollama/Anthropic/OpenAI), extraction (prompts + checks),
                             pipeline (document -> graph), graph_store (NetworkX views), text_utils
src/api/                     documents.py, graph.py
eval/                        labelled documents (docs/), gold.json, scoring, run_eval.py, rescore.py, saved results
tests/
```
