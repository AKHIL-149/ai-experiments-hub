# 16 - Knowledge Graph Builder & Query System

Turns unstructured documents into a knowledge graph (entities, relationships, dates, and the exact quote behind every fact),
answers multi-hop questions over it, and shows it in a visual explorer.
Advanced evolution of Project 4 (RAG Knowledge Assistant).

**Status: all 8 steps are built (extraction and graph store; entity resolution; questions and graph-RAG; accounts and a background job queue; the web app; time; conflicts and claim checking; export).** Not verified: the Anthropic and OpenAI clients have never run against the live services, and the Cypher export was loaded into Neo4j Community 5.26.0 only (not Memgraph or other versions); see Known limits.

| Step | What | State |
|---|---|---|
| 1 | Extraction and graph store | done |
| 2 | Entity resolution ("Acme Corp" = "Acme Inc." = "ACME") | done |
| 3 | Queries and graph-RAG (multi-hop questions with cited sources) | done |
| 4 | Accounts and background job queue (pattern from project 15) | done |
| 5 | Visual explorer (React + D3.js, "Paper Light" theme) | done |
| 6 | Temporal facts ("who was CTO in 2021?") | done |
| 7 | Conflict detection and fact checking | done |
| 8 | Export (Cypher, CSV, JSON) and final docs | done |

## Decisions

| Topic | Decision |
|---|---|
| Language | Python backend (FastAPI), JavaScript frontend (React 19 + D3, built with Vite; the build is committed, so Node is only needed to change the UI) |
| LLM for extraction | Local Ollama `llama3.1:8b` (the newest Llama that runs fast on 64 GB; Llama 4 Scout is 67 GB and does not fit, Llama 3.3 70B fits but is slow). Claude and OpenAI are switchable in settings |
| Graph engine | NetworkX in memory, built from the database. No graph database server needed |
| Neo4j / Memgraph | Export only (step 8). Neither is installed here; for the one check, Neo4j Community 5.26.0 was downloaded, the script loaded into it and read back unchanged (see Export), then removed. **Memgraph was never tried** |
| Database | SQLite by default (any SQLAlchemy URL works). Alembic migrations run at startup (`alembic/versions`); a database made by steps 1-3 is adopted and upgraded |
| UI theme | "Paper Light" (background `#F7F6F2`, panels `#FFFFFF`, accent `#2F5FD0`; person `#2F5FD0`, organization `#0F9D8A`, place `#D9822B`, concept `#C2417C`) |

## Run it

```bash
cd python-projects/16-knowledge-graph-builder
pip install -r requirements.txt
ollama pull llama3.1:8b
cp .env.template .env        # optional, everything has a default
python3 server.py            # http://127.0.0.1:8016  (the web app; API docs at /docs)
```

```bash
# sign in once (the cookie is kept in cookies.txt), then use it on every call
curl -c cookies.txt -H 'Content-Type: application/json' -d '{"username":"ann","password":"correct horse"}' localhost:8016/api/auth/register
curl -b cookies.txt -F "file=@report.pdf" localhost:8016/api/documents        # .txt .md .pdf .docx
curl -b cookies.txt localhost:8016/api/documents/<id>                         # status, progress, stats
curl -b cookies.txt localhost:8016/api/graph                                  # nodes + edges
curl -b cookies.txt -OJ 'localhost:8016/api/export?format=csv'                # a zip of entities, facts and quotes (also json, cypher)
```

On your own machine you can skip sign-in with `REQUIRE_LOGIN=false` (everything then belongs to one local user).

The web app is at the same address (see Web app). Everything it does goes through the API below, so `/docs` and curl keep working.

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
6. **Double-check** (`VERIFY_FACTS=true`). A fact whose quote states it in the claim's own words, close together, in the claim's order, with nothing doubtful in the quote ("not", "might", "plans", "rumour") needs no model ("Veltra Dynamics is headquartered in Kellmar."). The rest get one short yes/no call, "is this statement true according to the quote?", which catches negations and plans ("did not acquire", "might buy"); it is not reliable at direction, which is why step 5 has the word-order check. Participle predicates are phrased with an "is" ("Sofia is born in Oslin"), because the bare "Sofia born in Oslin" made the model say no to true facts.
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

## Questions and graph-RAG (step 3)

`POST /api/ask {"question": "...", "mode": "auto|graph|subgraph|hybrid|vector", "document_id": null}` answers from the graph and cites the quotes behind every fact it used.

| Mode | What it does |
|---|---|
| `vector` | The baseline: the passages closest to the question (embeddings, `nomic-embed-text`), as a plain RAG assistant does. My own re-implementation with the same model and embeddings, not project 4's code |
| `subgraph` | Finds the entities the question names, collects the facts within 2 links, keeps the 30 that fit the question best |
| `graph` (= `auto`) | The model turns the question into a **chain of relations** ("acquired" backwards, then "founded" backwards); **code walks that chain** through the graph and keeps only the facts on the way; if the chain breaks it falls back to `subgraph` and tells the model so |
| `hybrid` | `graph` plus the closest passages |

How a question is handled:
1. **Entity linking** (no model): the question's words are matched to entity names and aliases, longest match first, then a part of a name ("Turing"), then near spellings. Question words and short words are ignored; a word shared by more than 3 names is too generic.
2. **Plan** (model): `{"start": ["Veltra Dynamics"], "steps": [{"relation": "acquired", "direction": "out"}, {"relation": "founded", "direction": "in"}]}`. "How is A connected to B?" is detected by wording and answered with the shortest paths between them, without asking the model for a plan.
3. **Walk** (code): each step keeps the facts whose predicate is close to the relation (same word stem, or embedding similarity above `PREDICATE_THRESHOLD`: "bought" finds "acquired"). A wrong direction is tried the other way round and reported. Only chains that reach the end are kept, so the model sees the facts on the path, not everything nearby.
4. **Answer** (model): it gets numbered facts (`F1`, with the source quote) and passages (`P1`), must answer only from them, may say "not found", and says which labels it used. Labels it was never given are dropped and reported. The reply includes the answer, the citations (fact, quote, document, passage), and the reasoning: entities found, the plan, each step's links, any fallback and why, which documents the evidence came from.

Without a model: `POST /api/query/chain` follows a chain you write, `GET /api/query/path?from=&to=` finds how two entities connect, `GET /api/query/link?q=` shows which entities a text is matched to. `GET /api/index/status` and `POST /api/index/rebuild` show and fill the embeddings (passages are embedded while a document is read; fact vectors are made on first use and kept).

### Measured: graph questions against passage search

Corpus: 18 short fictional documents (so the model cannot know the answers), read by the real pipeline into 30 facts; `eval/qa/`. Questions need 1 to 4 hops across documents, include list and "how are A and B connected" questions, and 5 that the documents cannot answer (including near-misses: "invested in" for "acquired", the CEO of the parent company, the relation the wrong way round). Answers are judged by whether the gold names appear (and for unanswerable ones, whether the system says it is not in the documents). All systems use `llama3.1:8b`, temperature 0.

| Correct answers | `vector` (passages) | `subgraph` | `graph` | `hybrid` |
|---|---|---|---|---|
| **Held-out set** (13 questions written before the final changes, run once) | 8 | 11 | **11** | 10 |
| 2+ hops (held-out, 7 questions) | 3 | 5 | 4 | 5 |
| Unanswerable (held-out, 4) | 2 | 3 | **4** | 2 |
| **Development set** (25 questions; prompts were tuned on it, so optimistic) | 14 | 20 | **23** | 23 |
| 2+ hops (development, 11 questions) | 5 | 10 | **10** | 10 |
| Unanswerable (development, 5) | 3 | 2 | **5** | 5 |
| Average seconds per answer | 1.5 | 2.1 | 2.7 | 2.9 |

What to take from it:
- **Questions that need facts from several documents** are where the graph wins: passage search answered 5 of 11 development questions with 2+ hops and 3 of 7 held-out ones; the graph modes 10 of 11 and 4-5 of 7. Passage search fails when no single passage is close to the whole question.
- **One-hop questions** are a tie (the passages answer them too).
- **"Not found"** was the weak spot of the first version: the graph modes gave plausible but unsupported answers ("Lena Marsh" as the CEO of Soro Labs; she heads its parent company), 1 of 5 correct against passage search's 3 of 5. Telling the model when the chain could not be followed, and a rule that a different entity or relation does not answer the question, brought it to 5 of 5 on the development set and 4 of 4 held-out. Those changes were made after seeing the development failures.
- The remaining misses are the planner's: a 4-hop question where it stopped one relation short (asked for the country, answered the city), and a question whose answer needs the same-university relation in both directions. `hybrid` was less reliable than `graph` on questions that cannot be answered, because near-miss passages invite an answer; that is why `auto` is `graph`.
- Runs vary by about one question (`vector` scored 15 and then 14 of 25 on the same questions).
- **It depends on extraction.** The first read of this corpus lost three facts to the double-check (a bug found by this evaluation, fixed in this step), and then the questions needing them failed. A fact the pipeline did not extract cannot be found; passage search does not have that dependency. The 38 questions are small numbers and the corpus is synthetic and short.

### Limits of question answering

- The plan comes from a small local model: it can pick the wrong relation or stop early on long chains (4+ hops were 1 of 3 correct in the graph modes).
- Relation matching uses word stems and embeddings; unusual wording of a relation can miss ("is employed by" for "works at" worked, but there are no guarantees).
- No aggregation (counts, "which is largest"), no comparison, and no reasoning with dates beyond what a fact states.
- The answer is generated text: a citation proves the quote was offered to the model, not that the answer follows from it.
- Questions about a scope other than one document or the whole graph are not supported.

## Accounts (step 4)

Every person has a private graph. Documents, entities, facts, aliases, merge suggestions and merge history belong to an account,
and every endpoint and every query is limited to the caller's own rows.

- **Sign-in** (`/api/auth/register`, `/login`, `/guest`, `/logout`, `/me`, `/config`): a random token in an HttpOnly, SameSite=Lax cookie (`kg_session`, `Secure` with `COOKIE_SECURE=true`). The database keeps only the SHA-256 of the token, so a leaked database holds nothing a browser can replay. Passwords are scrypt hashes; an unknown username and a wrong password take the same time and give the same answer.
- **Guests** get a temporary account (24 hours, 3 documents by default) and can turn it into a real account later without losing their documents. Expired guests and everything they own are deleted (hourly, and at startup).
- **The first real account adopts what was there before** (documents read before accounts existed have no owner). Guests never do.
- **Another account's id answers 404**, exactly like an id that does not exist (a 403 would confirm that it is there). This holds for documents, entities, facts, merge suggestions, merge history, searches and chains; an entity of another account cannot be merged with one of yours even by id.
- **A write from another website is refused** when the browser sends the cookie (`Origin`/`Referer` must be this site or in `ALLOWED_ORIGINS`). Scripts and curl send neither and pass.
- **Throttles:** 8 wrong passwords per username and per address in 10 minutes, 20 new accounts or guests per address per hour (HTTP 429).
- **Locks are per account:** a merge, undo, resolution run or index rebuild waits (HTTP 409) while one of the *same* account's documents is being read; other accounts are unaffected.
- `GET /api/health` is public and says only that the server is up; the model's state is shown to signed-in callers.
- There is no administrator: an account cannot see or change another's data, so there is nothing for one to do. Deleting an account (database level) deletes everything it owns.

Tested by signing in as two accounts and trying every endpoint with the other's ids, names and documents (`tests/test_isolation.py`), and by breaking every owner check in the code one at a time (72 of them): the tests caught 62 directly; the other 10 are second layers that another filter already covers (for example, facts are filtered by owner and so are entities, so removing either alone changes nothing).

## Background jobs (step 4)

Uploading a document does not read it in the request. It adds a **job** (a row in `jobs`) and returns at once with the job's place in the queue;
worker threads read documents one after another (`MAX_CONCURRENT_DOCUMENTS`, default 1: a local model answers one request at a time).

- **Fair between accounts.** Round robin: the account served least recently goes first, and an account never has two documents read at once.
  Ann uploads 3 documents, then Bob 2: they are read Ann, Bob, Ann, Bob, Ann (observed live). My first ordering, copied from project 15, let an
  account with a backlog keep jumping ahead of newer accounts (its next job is always "first in its own line" and older); the tests found that.
- **Limits.** An account may have `MAX_QUEUED_JOBS_PER_USER` (10) waiting or running jobs; more answers HTTP 429.
- **See and cancel:** `GET /api/jobs` (`?status=active|queued|running|completed|failed|cancelled`), `GET /api/jobs/{id}`, `POST /api/jobs/{id}/cancel`.
  Every document also carries its latest `job` (status, place in the queue, attempts). Cancelling a waiting job is immediate; a running one stops before its next model call and
  leaves nothing behind (no half-read facts). Reading again (`POST /api/documents/{id}/reprocess`) queues a new job. A document that is waiting or being read cannot be deleted.
- **Survives restarts.** Jobs are rows, so waiting jobs are still waiting after a restart. A running job beats a heartbeat from its own thread every 10 seconds (also during a long model call);
  one whose heartbeat is older than `JOB_STALE_SECONDS` (45) is put back in the queue, up to `JOB_MAX_ATTEMPTS` (2) tries, then marked failed with the reason. On a normal stop (SIGTERM) a running job is handed
  back to the queue and the try is not counted; documents left "pending" or "processing" with no job by an older version are marked interrupted at startup.
- **A model call is now capped** (`LLM_MAX_TOKENS`, 3072; the double-check 48). The live run of a long passage showed why: one generation ran past the 300 second timeout and the read failed. A reply cut off by the cap keeps every complete fact.
- Finished jobs older than 30 days are forgotten.

Measured live (llama3.1:8b, two accounts, real worker threads): five documents interleaved Ann, Bob, Ann, Bob, Ann; a cancel during a long passage took 55 seconds to take effect (one model call; before the fix a call could run for 5+ minutes);
`kill -9` of the server in the middle of a read was recovered after a restart (the job was re-queued by the reaper and read again, attempts 2, a heartbeat window of 20 seconds in that test); SIGTERM handed the job back in about 7 seconds with the try not counted.

Limits: one server process is the tested setup (the claiming is safe across processes, but I did not run two); a read cannot be interrupted in the middle of a model call, so cancel and shutdown wait for the current call (up to the call's cap, about a minute);
a very long passage of mixed content can take minutes to read (the model writes many facts and each is double-checked).

## Time (step 6)

A date in a document is stored as the text states it (`2019`, `2019-03`, `2019-03-15`), so each one is a **range of days**: `2019` means any day of 2019. A fact has a start and an end, and either can be missing. For a period, code compares ranges (no language model) and gives each fact one of five statuses:

| Status | Meaning | Example for 2021 |
|---|---|---|
| `during` | the stated dates surely cover the whole period | "from 2020 to 2022" |
| `overlaps` | they overlap it, or might (a year-only date, began or ended inside the period) | "from 2021", "from 2019 to 2021" |
| `open` | it began earlier and **no end is stated**: it may or may not still have held | "since 2016" |
| `outside` | it cannot have held then | "from 2012 to 2019", "since 2023" |
| `undated` | the text gives no date, so nothing can be said | "is the CTO of Orrin Dynamics" |

**Questions.** "Who was the CTO of Acme in 2021?", "... between 2015 and 2018", "... before March 2020", "which companies did Acme buy after 2018", "in the 1990s", "currently" are recognised with patterns, so the time is never a guess by the model. The time words are taken out before the question is planned, facts dated outside the period are left out of the chain walk, and every fact the model sees carries a tag with what its dates say. The model is told what the tags mean, and that an `open` fact is only a "possibly". If every fact the answer rests on is `open` or `undated`, **code** adds a caveat (`time_caveat`) to the answer, so it does not depend on how the model words it. If facts exist but all are dated outside the period the answer says so, with examples ("the graph has facts about this, but their dates put them outside 2021"), instead of a bare "not found". A year inside an entity's name ("Expo 2020", "2020 Summer Games") is not read as a time. Passage search (`vector`) does not use dates.

**Browsing.** The Graph screen has a time control (Any time, Now, or a year with a slider and arrows): facts dated outside the chosen year fade (dotted lines), entities with nothing left fade, and a line says how many facts hold, are open, undated or outside. Nothing is removed, so the picture does not rearrange. An entity's panel has a **Timeline** (its facts in time order, each with its status for the chosen year), Ask shows each citation's status and the time it read, and "Show them in the graph" opens the graph at that year.

### Measured

A small corpus of 12 dated documents read by the real model (`eval/temporal`, `llama3.1:8b`; 30 facts): **every date was extracted correctly** (including month precision and "since 2021" as a start with no end). Two question sets: 12 development questions (the caveat code was added after it showed one failure) and 12 held-out ones written before the first run and run once.

| Correct answers | `vector` (passages) | `subgraph` (facts around) | `graph` (chain) |
|---|---|---|---|
| Development (12: 7 "in YEAR", 1 range, 2 "currently", 1 unanswerable, 1 undated) | 8 | **12** | 11 |
| **Held-out** (12: 6 "in YEAR", 3 ranges, 1 "currently", 2 unanswerable) | 8 | **12** | 11 |
| Average seconds per answer | 1.5 | 1.7 | 2.3 |

Passage search does not use dates: it answered "not found" to 7 of the 24 questions (all of them "in YEAR" questions whose answer was in the documents) and gave the undated one as a bare name without a caveat. I did not look into why it missed them. The two misses of `graph` (one in each set) are not about reading dates:
- **Predicate wording** (development): "chief executive" in the question, "led" in the document, so the chain could not be followed ("nothing matches 'chief executive'"). The same weakness limited step 3.
- **An event looks like a state** (held-out): "which companies did Sable Group acquire after 2010?" gave "Northgate Audio" (acquired in 2008). An acquisition is stored as a fact that starts in 2008 with no end, which is the same shape as "led since 2018", so it is marked `open` ("may still have held") and the model chose it. The tags are right; the model read them wrongly. `subgraph` got this one right.

On these questions `subgraph` was as good as or better than `graph` (they are one-step questions; `graph` earned its place on multi-hop questions in step 3). I did not change the default.

### Limits of time

- **Events and states are not told apart.** "Acquired in 2019" and "led since 2019" are both a start with no end, so for a later year both are `open`. The answer says "no end date is stated"; it cannot say the acquisition ended.
- **No quarters, seasons, relative dates or "the 1990s" in documents.** "Last year", "since the merger", "Q3 2021" are not resolved (only years, months and days are stored). "In the nineties", "mid-2010s" in a question are not read.
- **One time per question.** "CEO in 2015 and CTO in 2018" uses the first time only.
- **Two overlapping holders are both returned.** "Who was CTO in 2021" can list a person who left in 2021 and one who started in 2021; deciding which is right (or that the documents contradict each other) is step 7.
- A start-only fact tagged `open` can be long over: only the text can say, and it did not.
- The time words are English.

## Conflicts and claim checking (step 7)

### Conflicts

Code looks for facts that cannot both be true. A person settles each one. Four shapes:

| Kind | Example |
|---|---|
| `different_object` | one subject, a relation that has one object at a time: "Harlow Textiles is headquartered in Dunmere" / "... in Valcross"; "Lorcan Adeyemi was born in Hollin" / "... in Carrowmere" |
| `different_value` | "Orrin Dynamics employs 340 people" / "... 410 people" |
| `different_holder` | a role with one holder at a time: "Rosalind Penge led Wick Dynamics (2010-2016)" / "Tomas Verhoven was chief executive of Wick Dynamics (2014-2019)" |
| `reversed` | the same relation written both ways round: "Sable acquired Pemberly" / "Pemberly acquired Sable" (also catches a direction the model got wrong) |

Which relations have "one at a time" is a **built-in list** of common ones (headquartered in, born / died in, CEO / CTO / CFO of, led, chaired, mayor / president of; written in different words they count as the same relation: "led" and "served as chief executive of"). A relation not in the list is asked about **once, as a bare word**, only when you tick "Ask the model too", and the answer is remembered (`predicate_kinds`); until then it is treated as "several are possible", so nothing is flagged by guesswork. "Founded", "acquired", "employs", "located in" (a city is in a region and a country), "studied at", "partnered with" are never flagged as having two answers.

Two facts only conflict if they can have held at the same time (`temporal.overlap_status`):
- a **handover** is not a conflict ("2012 to 2019" then "2019 to 2022"; "2019-06 to 2020-03" then "2020-03"): the comparison is as precise as both dates are written;
- both dates surely share time: **certain**;
- "since 2020" and "since 2023" with no end stated, a missing date, or no dates at all: **possible** (usually one replaced the other, or two documents disagree).

**Settling.** For each conflict you can: *trust the first* or *trust the second* (the other fact is left out of the graph, the lists, the timeline and answers, and stays in the database), *both are true* (dismissed, never flagged again), or, when one began clearly before the other and states no end, *the earlier one ended when the later began* (its end date is set to the later start). Every choice can be reopened and the old dates come back. Detection also runs after each document is read (code only, no model); an open conflict that no longer applies is removed, a settled one never is.

**Answers** built on facts that conflict say so: the model is told which facts contradict each other and to give both, and the response lists the conflicts (`conflicts`). The fact panel shows the conflicts a fact is in, or that it was left out.

### Checking a claim

`POST /api/check` or the **Check** screen: "Dana Reyes was CTO of Acme in 2021." The model only reads the claim into *subject - relation - object - dates* (a date that is not in the claim's own words is dropped; "X was founded by Y" is turned into "Y founded X"). **Code** then decides:

| Verdict | When |
|---|---|
| `supported` | a stored fact says the same (same relation, even in other words) with dates that do not clash |
| `supported_other_dates` | such a fact exists, but its dates do not fit the claim's |
| `contradicted` | the relation exists the other way round; a different value; or another object / another holder for a relation that has one at a time (the claim may name a person or place the documents do not know) |
| `not_found` | the documents do not say. Never "false". If they connect the two things another way, that fact is shown as `related` |
| `unclear` | the claim could not be read, or its subject is not in the documents |

Every verdict lists the facts and quotes it rests on.

### Measured

A small corpus of 16 documents with **planted conflicts and look-alikes** read by the real model (`eval/conflicts`, `llama3.1:8b`; 23 facts, every one extracted as written). I wrote the documents, the built-in list and the expectations, so this is a check of the mechanism on a small hand-made set, not a measurement of how well it does on real documents.

| | Result |
|---|---|
| Planted conflicts found (5) | **5 of 5**, each with the right kind (one has dates that surely overlap: certain; the other four are possible) |
| Look-alikes wrongly flagged (6: two handovers of leaders and mayors, a headquarters move, two founders, two "located in", partnered-with both ways) | **0 of 6** |
| Other conflicts flagged | 0 |
| The model's own opinion of each pair (`Ask the model too`) | 3 of 5 said they contradict; for the other two (a headquarters pair, and the two chief executives whose dates surely overlap) it said they are compatible. Its opinion is shown but never decides anything |
| The model's classification of the unfamiliar relation words (employs, acquired, founded, located in, partnered with, "and") | all "several possible", which is right for each |

Claim checks (8 development claims, 7 held-out written before the first run): development 8 of 8. **Held-out, first run: 5 of 7.** Both misses were one real bug that this run exposed: a claim in the passive ("Wick Dynamics was led by Greta Lund", "Delacroix Textiles was founded by Imogen Strand") was read as subject *Wick*, relation *was led by*, so it never matched the stored active fact (the second was even reported as "the other way round"). I fixed it by turning passive claims round the way the extraction already does, which left one claim (an unknown person named as a holder) as "the claim's subject is not in the documents", so I also made a holder the documents do not know clash with the holders they name. After both fixes the held-out claims give 7 of 7 and the development claims 8 of 8, **but the 7 of 7 is no longer a held-out number.** One claim was dropped before any run because whether "acquired in 2010" fits a fact starting in 2001 depends on reading an acquisition as an event or a state, which the system cannot tell apart.

### Limits

- **Which relations exclude each other is a short list plus the model's guess for the rest.** A relation outside the list (and not classified) is never flagged, so real conflicts in unusual wording are missed; and the model's classification of a word is a guess (not checked beyond the six words above).
- **A conflict needs overlapping or unknown time.** Facts that are only possible conflicts (no dates) are many on real documents; expect false alarms where two documents describe different moments without dates.
- **Facts that disagree only through a chain** ("A is in B", "B is in C", "A is in D") are not found. Neither are conflicts between a fact and the passage text.
- **Dates in claims.** A claim naming one date fits a fact that had begun by then and states no end (the text does not say it stopped). For an *event* ("acquired in 2020" against "acquired 2018, no end stated") that is wrong, for the same reason as in step 6.
- **A claim is checked against the facts that were extracted**, which miss about a quarter of what the text says (see Measured accuracy): "not in the documents" can mean "not extracted".
- Claims with two statements, or about quantities in other units ("3.4 thousand"), are read as one statement and compared as written (only the first number of a value is compared).
- The model reads the claim: a wrong reading gives a wrong verdict. The reading is shown ("Read as: ...") so you can see it.

## Web app (step 5)

Open `http://127.0.0.1:8016`. The server serves the built app from `frontend/dist`, so the sign-in cookie is same-origin (no CORS, no tokens in JavaScript).

| Screen | What you can do |
|---|---|
| **Sign in** | sign in, create an account, or continue as a guest (the page says what a guest gets: temporary, a few documents). A guest sees how long is left and can create an account to keep the documents |
| **Documents** | drop or choose files, or paste text; each card shows waiting / reading (passages done) / read / failed / cancelled, with the place in the queue; cancel, read again, delete (asks first), "View graph" for one document. Follows running jobs every 2 s |
| **Graph** | the knowledge graph, coloured by type (Paper Light palette), arrows from subject to object. Drag to move, scroll to zoom, double-click (or press `E`) to bring in a node's neighbours. Click an entity for its facts (details, links from and to it, aliases), a line for the fact with every source quote and its passage. Search (what is on screen and the whole graph), filter by type and document, find the shortest path between two entities, merge two entities, ask about an entity, or switch to a **List** (tables of the same data, which is also the text version for screen readers) |
| **Ask** | a question, a mode (graph / facts around / graph + passages / passages only) and a document to look in. "Compare with passage search" shows both answers side by side. Every citation shows its quote; "Show them in the graph" highlights the cited facts and dims the rest. "How this was answered" lists the entities found, the planned chain and each step |
| **Check** | type a claim; get supported / contradicted / not in the documents with the facts and quotes behind it (see Conflicts and claim checking) |
| **Review** | run the duplicate search (with or without the model's second opinion), merge a suggested pair keeping either name or mark it "different things", the merge history with Undo, the pairs kept apart, and the **Conflicts** tab: facts that cannot both be true, with both quotes, to trust one, keep both or end the earlier one |
| **Export** | download the graph as JSON, CSV or a Cypher script, for everything or for one document, with or without the quotes; says first how many entities, facts and quotes the file will hold and how many facts are left out by settled conflicts (see Export) |

How it is built: d3-force computes the layout, d3-zoom and d3-drag handle the pointer, and React draws the SVG (so labels, focus and clicks are ordinary DOM). Nodes keep their place when more of the graph is loaded. Screens are addressed by the URL fragment (`#/graph?entity=...`, `#/ask?q=...`), so reload, back and bookmarks work. Every graph node can be reached and operated with the keyboard (Tab, Enter or Space to select, `E` to expand).

Security: the page is sent with a strict Content-Security-Policy (scripts only from this server, no inline script, no framing, no outside connections), `nosniff`, `X-Frame-Options: DENY`. Text from documents is only ever rendered as text (a document containing `<script>` is shown as that text). Assets are named by their content and cached for a year; the page itself is never cached. A missing `/assets/...` file is a 404, never the page.

```bash
# change the UI
cd frontend
npm install
npm run dev        # http://127.0.0.1:5173, proxies /api to the server on 8016
npm test           # 360 component and unit tests (jsdom)
npm run build      # writes frontend/dist, which is committed: rebuild it after every change to frontend/src
```

Tested: 360 frontend tests (every screen, the graph drawing, the router and hooks, the API client) and 30 server tests for serving the app (`tests/test_web.py`: page, fallback, headers, assets, the gate still closed on `/api`). They were break-tested: 84 deliberate small bugs in the frontend sources and 32 in `src/web.py`, one at a time. The first round of the frontend missed 15 (the limit of 8 recent questions, the file input reset, the 8 second polling, the order of the list view, and similar); each got a test.
Checked by hand in a browser against the real extracted documents (25 entities, 30 facts): signing up, the graph, an entity panel, and the question "In which city is the university attended by the founder of Soro Labs?" answered "Kellmar" with two cited quotes while passage search said "The documents do not say".

Limits of the web app: not tested in Safari or Firefox (Chromium-based browser pane only); the graph is drawn as SVG, which stays smooth to a few hundred entities (it loads the 300 best connected and says so; the rest are reached by search or "Show neighbours") but would need canvas drawing for thousands; there are layout rules for narrow screens, but nothing was tried on a real phone (including dragging nodes with a finger); no automated browser test drives a real server end to end (the component tests mock the API, and the real run was by hand).

## Export (step 8)

Take the graph with you. Web app: the **Export** tab (or "Export" on a read document's card). API: `GET /api/export?format=json|csv|cypher`.

| Format | What you get |
|---|---|
| **JSON** (`knowledge-graph.json`) | everything in one file: entities (with their other names), facts (subject, predicate, object or plain value, dates, number of sources) and, under each fact, every quote with its document and whether the double-check confirmed it. Counts and scope are at the top. Best for your own code |
| **CSV** (`knowledge-graph.zip`) | three tables and a short README: `entities.csv`, `facts.csv`, `sources.csv` (one row per quote). Opens in a spreadsheet; the ids tie the tables together |
| **Cypher** (`knowledge-graph.cypher`) | a script that builds the graph in Neo4j or another Cypher database (below) |

Options (all formats): `document_id=` exports only the facts read from one document (with only that document's quotes) and `sources=false` leaves the quotes out. Cypher also takes `schema=false`, which leaves out the two `CREATE CONSTRAINT` lines. `GET /api/export/summary` says what a download would hold (entities, facts, plain-value facts, quotes, and how many facts are left out) without making it; the web app shows it before you download.

What is exported is what the app shows. Facts left out because you settled a conflict against them are not exported (their number is reported, and reopening the conflict brings them back). An entity is exported when it takes part in an exported fact; an entity with no facts is not. The same graph always gives the same bytes (everything is sorted), apart from the time written in the JSON and Cypher headers. Exports are made from the signed-in account's data only.

### The Cypher script

```
(:Entity:Person {id, name, type, aliases})                                         one node per entity; the second label is its type
(a)-[:LED {id, predicate, valid_from, valid_to, source_count, evidence, evidence_documents}]->(b)
(a)-[:EMPLOYS {...}]->(:Value {id, value})                                         a fact whose object is a plain value gets its own Value node
```

- The relationship type is the predicate in capitals ("was CTO of" becomes `WAS_CTO_OF`); the exact wording is kept in the `predicate` property. A predicate with no ASCII letters or digits becomes `RELATED_TO`. Different wordings are different types: "led" and "was CEO of" are not merged.
- Dates stay text (`'2019'`, `'2019-03'`): a period may be only a year, which no Cypher date type can say. Undated facts have no `valid_from` / `valid_to` at all.
- `evidence` and `evidence_documents` are lists of the same length: the quote at position *i* was read in the document at position *i*.
- Everything is `MERGE`d on its `id`, so running the script twice changes nothing. Entities and `Value` nodes come first, then the relationships. Each statement is one line ending in `;`, so a line-by-line loader works as well as `cypher-shell` or the Neo4j Browser.
- Text from the documents goes into the script as quoted strings with backslash, quote and every control character escaped, so no document text can end a string or add a statement. A test feeds it a quote that tries.
- The two constraint statements use Neo4j 5 syntax (accepted by 5.26.0). Memgraph and older Neo4j use another syntax (from memory, not tried): run the script with `schema=false` there and create an index on `Entity(id)` yourself (without one, loading a large graph is slow).

```bash
curl -b cookies.txt -o graph.cypher 'localhost:8016/api/export?format=cypher'
cypher-shell -u neo4j -p <password> -f graph.cypher           # tried on Neo4j 5.26 Community, see below
```

### Checked how, and what that does not show

- **A real Neo4j.** On 2026-11-17 I downloaded Neo4j Community 5.26.0 (the official tarball, checksum verified; Java 21, macOS on Apple silicon), started it on localhost with a throwaway password and tried the script two ways with the real `cypher-shell`, then deleted it all. (1) The export of the 16 conflict-corpus documents read by the real model: it loaded without errors into 26 entities, 2 `Value` nodes, 23 relationships and both constraints, exactly what the exporter reported; loading it again changed nothing. (2) `python3 -m eval.run_neo4j_check`, an awkward graph: quotes, backslashes, semicolons, `//` and `/* */`, backticks, `$`, braces, control characters, line and paragraph separators, emoji, CJK, a predicate with no ASCII letters, a predicate that looks like Cypher, a quote that tries to inject `DETACH DELETE`, a 5,000 character quote and plain values. It loaded twice without errors and every entity, alias, label, relationship type, property, date, quote and value read back over Neo4j's HTTP API equal to the source, with no stray nodes (the injection attempt is stored as plain text). The variant without the constraint lines also loaded, and the check can fail: with the escaping of backslashes broken on purpose, Neo4j's own parser rejected the script. The check erases the database it points at, so it refuses a non-empty one unless `--wipe` is given. It is a single run on one version, not a test suite that runs on every change.
- **A reader for the script's statements.** These checks need a database, so the unit tests do not. They read the script back with a small reader that understands only the statement shapes the exporter writes, rebuild the graph from it, and compare every entity, fact, date and quote with the source, including quotes with quotes, backslashes, newlines, tabs, control characters and a line trying to end its own string. They also check that running it twice gives the same graph, that nodes come before the relationships that need them and that every statement is one line. This runs everywhere and guards against regressions; the Neo4j run above is what shows a real database accepts the script.
- **A real run of the exporter**: the 16 conflict-corpus documents, read by the real model (26 entities, 23 facts, 2 with plain values), exported in all three formats and read by eye.
- **Spreadsheet formulas.** Documents are uploaded text, so a quote can start with `=`, `+`, `-` or `@` and a spreadsheet would run it as a formula. CSV cells starting with those characters (or a tab or carriage return) get a leading apostrophe. The cost is that a value such as `-5` is written `'-5`; the CSV README says so. JSON and Cypher are not changed.
- Downloads are sent as attachments with `Cache-Control: no-store` and `nosniff`, with a plain ASCII file name made from the document title (`knowledge-graph-q3-report.json`).
- Tests: 100 server tests (`tests/test_export.py`) and 31 frontend tests (`Export.test.jsx`, `export.test.js` and additions to the router, App and Documents tests), including that accounts never see each other's export and that every export URL answers 401 when signed out. They were break-tested: 125 deliberate bugs in the export code (every escape, the sorting, each spreadsheet-formula character, the file names, the options passed through, the owner check) and 54 in the screen. The first round missed 24 on the server (7 were redundant code or changes that cannot alter the output: 6 of them were simplified away, and one, the `charset` on the Cypher media type, is added by the framework anyway; the other 17 were real gaps: raw control characters left in a string passed my own reader, the order of quotes and aliases, the timestamp in the header, the zip's fixed time, trimming of file names) and 4 of 54 in the frontend (the address of the summary request, the Cypher default, choosing "All documents" again, passing the address's document to the screen); each got a test. It also found that the Cypher-only `schema` option was being added to the JSON and CSV links.

### Limits of export

- **Tried on one database.** Neo4j Community 5.26.0 only (above). Memgraph, other Neo4j versions (4.x, 2025.x), Enterprise features, the Neo4j Browser and large graphs were not tried. If the script fails on yours, the first thing to check is the constraint lines (`schema=false`).
- **Export only.** Nothing imports an export back. Merge history, conflicts (as records), search vectors, jobs and accounts are not exported; settled conflicts only show as "left out" facts.
- **Plain values are `Value` nodes**, not properties on the entity. That keeps dates and quotes, but a query for "the number of employees" must follow a relationship to a `Value`.
- **Relationship types follow the wording.** There is no synonym merging, so two ways of saying the same thing are two types; an export of a graph that was read with varied wording is untidier than the same graph after you merged and settled things.
- **The whole export is built in memory**, and the Cypher script has one statement per entity and per fact. That is fine for the sizes this tool reads (it takes hours per hundred thousand characters), and untested on millions of facts.
- Only English predicates produce readable relationship types.

## API

| Endpoint | |
|---|---|
| `POST /api/documents` (file) / `POST /api/documents/text` | add a document; a job reads it in the background |
| `GET /api/documents`, `GET /api/documents/{id}` | status, progress, stats, error |
| `POST /api/documents/{id}/reprocess` | read again (a new job; replaces what was read before) |
| `GET /api/jobs`, `GET /api/jobs/{id}`, `POST /api/jobs/{id}/cancel` | your jobs, their place in the queue, cancelling |
| `DELETE /api/documents/{id}` | remove it and every fact only it supported |
| `GET /api/graph?document_id=&type=&limit=&at=` | the most connected `limit` entities and links between them. With `at=2021` (or `2021-03`, `2021-03-15`, `now`) or `from=&to=` every fact also says what its dates mean for that period (`time`) |
| `GET /api/graph/stats` | counts by type, top predicates, the years the dates reach |
| `GET /api/entities?q=&type=`, `GET /api/entities/{id}` | search; facts going out of and into an entity, and its aliases |
| `GET /api/entities/{id}/neighborhood?depth=1..3` | everything within N links (also takes `at` / `from` / `to`) |
| `GET /api/entities/{id}/timeline` | every fact about the entity in time order, undated ones last (also takes `at` / `from` / `to`) |
| `GET /api/facts/{id}` | the fact, its dates, and every source quote with its passage |
| `POST /api/resolution/run` (`{"use_llm": false, "auto": true}`) | merge the safe pairs, refresh suggestions |
| `GET /api/resolution/suggestions?status=pending` | suggested merges with score, reasons, both entities' facts |
| `POST /api/resolution/suggestions/{id}/accept` (`{"keep_id"}` optional) / `.../reject` | decide a suggestion |
| `POST /api/entities/merge` (`{"keep_id", "absorb_id"}`) | merge by hand (refused for different types or entities a fact links) |
| `GET /api/resolution/merges`, `POST /api/resolution/merges/{id}/undo` | history and undo |
| `POST /api/ask` | answer a question with citations and the reasoning behind it |
| `GET /api/query/at?entity=&relation=&at=` (or `from=&to=`) | "who held this relation in that period", no model: facts that can have held, each with what its dates say; facts dated outside are only counted |
| `POST /api/conflicts/run` (`{"use_llm": false}`), `GET /api/conflicts?status=open\|resolved\|dismissed` | look for facts that cannot both be true; list them with both facts, dates and quotes |
| `POST /api/conflicts/{id}/resolve` (`{"resolution": "keep_a\|keep_b\|both\|succession"}`), `POST /api/conflicts/{id}/reopen` | settle one (nothing is deleted) or undo it |
| `POST /api/check` (`{"claim": "..."}`) | supported / contradicted / not in the documents, with the facts and quotes behind the verdict |
| `GET /api/export?format=json\|csv\|cypher&document_id=&sources=&schema=`, `GET /api/export/summary?document_id=` | download the graph as a file (JSON, a zip of CSV tables, or a Cypher script); what a download would hold |
| `GET /api/query/link?q=`, `GET /api/query/path?from=&to=`, `POST /api/query/chain` | entity linking, paths, chains of relations (no model) |
| `GET /api/index/status`, `POST /api/index/rebuild` | passage and fact embeddings |
| `GET /api/health` | whether the configured model is reachable and installed |

If the model is not
running, the document fails with "Cannot reach Ollama ... (ollama serve)" instead of hanging.

## Settings (`.env`)

See `.env.template`. The ones that matter: `LLM_PROVIDER` (ollama, anthropic, openai), `OLLAMA_MODEL`, `VERIFY_FACTS`,
`GLEANING_PASSES`, `AUTO_RESOLVE`, `RESOLUTION_USE_LLM`, `AUTO_DETECT_CONFLICTS`, `MAX_CONCURRENT_DOCUMENTS`, `MAX_QUEUED_JOBS_PER_USER`, `JOB_STALE_SECONDS`, `LLM_MAX_TOKENS`, `EMBEDDING_MODEL`, `INDEX_CHUNKS`, `ASK_MAX_FACTS`, `ASK_TOP_CHUNKS`, `ASK_MAX_HOPS`, `PREDICATE_THRESHOLD`, `CHUNK_CHARS`, `MAX_DOCUMENT_CHARS` (100,000), `MAX_UPLOAD_MB`. The Anthropic and OpenAI clients exist
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
| + double-check (the version of step 1) | 74% | 94% | 164 s |
| **+ double-check by wording first (default)** | **76%** | **95%** | 166 s |

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

What was never checked (read this first):
- **The Cypher export was loaded into Neo4j Community 5.26.0 and nothing else.** Memgraph, other Neo4j versions and big graphs were not tried, and the CSV was never loaded into any database (it was only opened as tables). See Export.
- **Only the local `llama3.1:8b` was used.** The Anthropic and OpenAI clients exist but never ran against the live services, and other local models were not tried.
- **Every accuracy number comes from small sets I wrote**, some of them tuned on while building (each section says which). They measure the mechanism; they do not predict accuracy on your documents.
- **The web app was only looked at in the Chromium-based browser pane**, by hand and with component tests that mock the API. No automated test drives a real server through a real browser.
- **Large inputs were not timed or load-tested**: long documents, thousands of entities, millions of facts in an export.

Limits of how it works:

- **Pronouns and long reference chains.** A fact is kept only if the subject and object are in the quote, or the sentence right
  before it. "He ... There he ..." chains lose facts. This is deliberate: guessing who "he" is would add wrong facts.
- **Speed.** About 25-45 seconds per short passage with the double-check and the second pass on an M1 Max. 100,000 characters
  is roughly an hour (an estimate from the short test documents; I have not timed a long one). Turn off `VERIFY_FACTS` or `GLEANING_PASSES` to trade accuracy for speed (about 20 s per passage).
- **The model still makes mistakes** the checks cannot see: a reversed fact whose quote is ambiguous ("the prize was awarded to
  Lena Hartmann" read as Lena awarding it) and some plans written as "might buy" got through in the evaluation.
- **Entity names are whatever the model wrote** (e.g. "journal Nature Photonics", "paper Computing Machinery and Intelligence"); resolution merges
  spellings of one name but does not clean up such prefixes.
- **One document is read at a time by default** (a local model answers one request at a time); see Background jobs.
- **Use HTTPS before exposing the server.** It speaks plain HTTP; sign-ins and passwords travel in the clear without a TLS proxy in front. Set `COOKIE_SECURE=true` once it is behind HTTPS. Registration is open by default (`ALLOW_REGISTRATION=false` closes it).
- Dates are only recorded when the quote states them; "last year" or "since the merger" are not resolved.
- English only (the prompts and the stop-word lists are English).

## Tests

```bash
python3 -m pytest                 # 962 tests, about 25 s, no model needed (a scripted fake model stands in)
python3 -m pytest -m ollama -s    # one live test against your local model (about 20 s)
```

The tests were break-tested: about 190 deliberate small bugs were put into the code one at a time (removing a check, flipping a
comparison, skipping a cleanup), and the tests caught all of them (the first round of the resolution code missed 12; each got a test or the dead code was deleted). Step 3's code (embeddings, entity linking, chain walking, question answering, the endpoints) accounts for about 70 of them; its first pass missed 11, each got a test or the dead code was deleted. Testing and the real-document run found four real problems, now fixed: a Latin-1
text file decoded as garbage, a duplicate source row that crashed storing a fact seen twice in one batch, and a name rule that
rejected most sentences saying "Turing" for "Alan Turing", and a word-order check that wrongly rejected
"Acme, founded by Maria, acquired Beta".

The step 4 job queue and its callers (`job_queue.py`, `api/jobs.py`, the model-call caps in `llm.py`, the cancellation checkpoints in `pipeline.py`, `api/documents.py`) were break-tested last, in one pass over 78 deliberate bugs: 68 were caught at once, 6 survived and 4 had to be re-aimed because the code had moved when accounts were added (3 of those were then caught, 1 survived). Of the 7 that got through, 5 were real gaps and each got a test: the queue order when jobs arrive out of age order, the JSON repair of a cut-off reply when an escaped quote is followed by a brace, the two cancellation checks between "read" and "search index" and between "search index" and "resolve names" (a stop there must undo the whole read), and, the one that mattered, **the owner in the lookup of an account's merged names**: the code was right, but deleting it went unnoticed because the tests ran as one user, and with it gone a later document using a merged name would create a duplicate entity for any signed-in account. The other 2 were guards that cannot trigger today (a job that still has a finish time cannot be purged; the "lost" outcome requeue is only reachable in a race); they got tests that pin them anyway.

Step 7's code (`conflicts.py`, `factcheck.py`, the endpoints, the screens) was break-tested too: about 115 deliberate bugs on the server side (the first round missed 32: boundary cases such as the mixed month/year comparison, the "president" entry of the list, a fact left out being compared again, and unscoped or unlocked endpoints; 5 of those are changes that cannot alter behaviour, the rest got tests) and 60 in the frontend (the first round missed 15, mostly wiring such as which address opens which screen and which parameters a request sends; each got a test).

Step 6's code (`temporal.py`, the dated index, the ask changes, the endpoints, the time controls) was break-tested too: about 75 deliberate bugs on the server side (the first round missed 18, one of them an equivalent change; the new tests also exposed a real bug: "In 2021, who led Acme?" left a stray comma in the question given to the planner) and 50 in the frontend (the first round missed 10 and one more after that); each got a test.

## Layout

```
server.py                    FastAPI app
src/core/                    settings, database, migrate (Alembic), auth, login_gate
src/models/graph.py          Document, Chunk, Entity, Fact, FactSource
src/models/resolution.py     EntityAlias, MergeSuggestion, MergeRecord
src/models/embedding.py      Embedding (passage and fact vectors)
src/models/user.py           User, UserSession
src/models/job.py            Job
alembic/                     migrations (0001 baseline of steps 1-3, 0002 accounts, 0003 jobs, 0004 conflicts)
src/services/                readers, chunker, llm (Ollama/Anthropic/OpenAI), extraction (prompts + checks),
                             pipeline (document -> graph), resolution (merge/suggest/undo), graph_store (NetworkX views), text_utils,
                             embedding (Ollama vectors, stored), graph_query (linking, paths, chain walk), ask (plan, answer, citations),
                             job_queue (claiming, fair order, heartbeat, cancel, recovery), cancel
src/api/                     auth.py, deps.py, documents.py, jobs.py, graph.py, resolution.py, query.py, conflicts.py, export.py
src/services/temporal.py     what dates say about a period; the time a question names; whether two periods can overlap
src/services/conflicts.py    finding, settling and undoing conflicts between facts
src/services/factcheck.py    checking a claim against the facts
src/services/export.py       JSON, CSV (zip) and Cypher output of the graph
eval/run_neo4j_check.py      loads an awkward graph's Cypher export into a scratch Neo4j and compares it field by field
src/models/conflict.py       Conflict, PredicateKind
src/web.py                   serves frontend/dist (page fallback, security headers, cached assets)
frontend/                    React + D3 app: src/ (components, lib, router, api client), tests/ (vitest), dist/ (the committed build)
eval/conflicts/              documents with planted conflicts, claims, results; run_conflict_eval.py
eval/temporal/               dated documents, two question sets, results; run_temporal_eval.py
eval/                        labelled documents (docs/), gold.json, scoring, run_eval.py, rescore.py, saved results;
                             entities.json + run_resolution_eval.py for resolution;
                             qa/ (18 documents, two question sets, saved results) + run_qa_eval.py for questions
tests/
```
