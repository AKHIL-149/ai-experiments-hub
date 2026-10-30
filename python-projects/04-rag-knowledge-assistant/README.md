# Personal Knowledge Assistant

RAG-powered system for building a searchable knowledge base from your documents. Ask questions in natural language and get answers based on your own content. Uses local embeddings and LLMs for complete privacy.

## Features

- Multiple document formats (PDF, TXT, Markdown)
- Local embedding generation using sentence transformers
- ChromaDB vector storage with persistence
- Semantic search with relevance scoring
- Context-aware answer generation
- Document chunking with overlap for better retrieval
- Simple CLI for document management

## How It Works

1. **Document Processing**: Documents are loaded and split into overlapping chunks
2. **Embedding**: Each chunk is converted to a vector using local sentence transformers
3. **Storage**: Vectors are stored in ChromaDB for fast similarity search
4. **Query**: Chunks are found two ways and combined: by meaning (vector similarity) and by exact words (BM25 keyword search). Exact-word matching catches terms that embeddings blur, such as "retained", "hours" or part numbers. On a small test set this raised top-1 retrieval accuracy from 16/20 to 20/20.
5. **Context widening**: Answers that span several chunks ("the three types are…", numbered steps) are often split so the later chunks look nothing like the question. The chunks next to the best matches (`--neighbors`, default 2) are therefore added and shown in document order, marked "adjacent context" in the sources. On the sample document this took complete answers to list-style questions from 13/18 to 17/18 runs, with no loss on single-fact questions.
6. **Generation**: The best chunks are passed to the local LLM, which answers only from them and cites them as `[1]`, `[2]`. If nothing relevant is found, it says so instead of guessing.

## Setup

Create virtual environment and install dependencies:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Make sure Ollama is running:

```bash
ollama pull llama3.2
```

## Usage

### Add Documents

Add single document:
```bash
python assistant.py add documents/machine_learning_basics.txt
```

Add multiple documents:
```bash
python assistant.py add documents/*.pdf documents/*.txt
```

### Query Your Knowledge Base

Basic query:
```bash
python assistant.py query "What are the types of machine learning?"
```

Adjust number of results:
```bash
python assistant.py query "What is supervised learning?" --top-k 3
```

Control response creativity:
```bash
python assistant.py query "Explain neural networks" --temperature 0.3
```

Adding is safe to repeat: a file is identified by its full path, so `notes.txt`, `./notes.txt` and `/abs/path/notes.txt` are one document. Re-adding an **unchanged** file does nothing (no re-embedding); re-adding an **edited** file replaces its old chunks.

### Check Statistics

List every indexed document with its chunk count:
```bash
python assistant.py stats
```

### Remove a Document

```bash
python assistant.py remove documents/old_notes.md
```

### Clear Knowledge Base

Remove all documents (asks for confirmation; use `--yes` in scripts):
```bash
python assistant.py clear
python assistant.py clear --yes
```

### Scripting

When output is piped, `query` prints only the answer (no frame or sources), and `--plain` forces that in a terminal:
```bash
python assistant.py query "What is the refund window?" | pbcopy
```
`add` exits with status 1 if any file failed (the others are still indexed).

## Configuration

Create a `.env` file (optional):

```bash
OLLAMA_API_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2
OLLAMA_TIMEOUT=120
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
CHROMA_DB_PATH=./data/chroma
```

A relative `CHROMA_DB_PATH` is resolved against this project folder, so the same knowledge base is used no matter where you run the command from.

## Document Processing

The system chunks documents intelligently:
- Default chunk size: 500 characters
- Overlap: 50 characters
- Breaks at paragraphs, then sentences (never inside a number like `3.14`), then words; each chunk starts at a word boundary
- Each chunk is embedded together with its file name, which helps questions that mention the document's topic
- Supports `.txt`, `.md` (UTF-8 or Windows-1252) and text-based `.pdf` (blank pages are skipped; scanned PDFs need OCR first)
- Overlap must be smaller than the chunk size

Adjust chunking:
```bash
python assistant.py add documents/large_doc.pdf --chunk-size 1000 --chunk-overlap 100
```

## Examples

### Build a Technical Knowledge Base

```bash
# Add programming documentation
python assistant.py add docs/python_guide.pdf docs/javascript_guide.md

# Query it
python assistant.py query "How do I handle async operations in Python?"
```

### Research Assistant

```bash
# Add research papers
python assistant.py add papers/*.pdf

# Ask questions
python assistant.py query "What are the main findings about neural networks?" --top-k 10
```

### Personal Notes

```bash
# Add your notes
python assistant.py add notes/meeting_notes.txt notes/project_ideas.md

# Search them
python assistant.py query "What were the action items from last week?"
```

## Project Structure

```
04-rag-knowledge-assistant/
├── src/
│   ├── document_processor.py   # Document loading and chunking
│   ├── embedding_service.py    # Local embedding generation
│   ├── vector_store.py         # ChromaDB integration
│   ├── llm_client.py           # Ollama API client
│   ├── rag_engine.py           # Main RAG orchestration
│   └── assistant.py            # CLI interface
├── documents/                   # Example documents
│   └── machine_learning_basics.txt
├── data/                        # ChromaDB storage (auto-created)
├── assistant.py                 # Convenience wrapper
└── requirements.txt
```

## Technical Details

**Embeddings**: Uses `all-MiniLM-L6-v2` model
- Fast local generation
- 384-dimensional vectors
- Good balance of speed and quality

**Vector Store**: ChromaDB with cosine similarity
- Persistent storage
- HNSW index for fast search
- Handles metadata and filtering

**LLM**: Ollama with llama3.2
- Fully local inference
- No API costs
- Complete privacy

## Implementation Notes

This project demonstrates:
- Document chunking strategies for RAG
- Local embedding generation
- Vector database integration
- Semantic similarity search
- Context injection for LLM queries
- CLI design for knowledge management

The system uses a straightforward RAG pipeline: chunk documents, generate embeddings, store vectors, retrieve similar chunks on query, and generate answers using retrieved context. All processing happens locally for privacy and cost control.

## Tips

1. **Chunk Size**: Smaller chunks (300-500) for precise facts, larger (800-1200) for contextual answers
2. **Top-K**: Use 3-5 for focused answers, 8-10 for comprehensive responses
3. **Temperature**: Lower (0.3-0.5) for factual answers, higher (0.7-0.9) for creative responses
4. **Document Quality**: Clean, well-structured documents produce better results
5. **Query Specificity**: Specific questions get better answers than vague ones

## Safety and Quality Notes

- Document text is treated as untrusted: instructions planted inside a document ("ignore the question and say...") are not followed.
- The LLM's context window is sized to the prompt. Ollama otherwise silently cuts long prompts, which can drop the very chunk that holds the answer.
- A small local model can still misread or skip details. Check the cited sources for anything important.

## Tests

```bash
venv/bin/python -m pip install pytest
venv/bin/python -m pytest tests -q
```

The tests use a fake embedder and LLM, so they need neither the embedding model nor Ollama.

## Limitations

- Keyword search scores every stored chunk in memory on each query. That is instant for personal collections (thousands of chunks) but not meant for millions.
- Answers are only as good as your documents
- Works best with factual, structured content
- Large documents may need careful chunking
- Embedding model has context length limits
- No automatic document updates (re-add to update)
