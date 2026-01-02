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
4. **Query**: Your question is embedded and similar chunks are retrieved
5. **Generation**: Retrieved context is used to generate a factual answer

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

### Check Statistics

View collection stats:
```bash
python assistant.py stats
```

### Clear Knowledge Base

Remove all documents:
```bash
python assistant.py clear
```

## Configuration

Create a `.env` file (optional):

```bash
OLLAMA_API_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
CHROMA_DB_PATH=./data/chroma
```

## Document Processing

The system chunks documents intelligently:
- Default chunk size: 500 characters
- Overlap: 50 characters
- Sentence-aware splitting when possible
- Preserves context across chunks

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

## Limitations

- Answers are only as good as your documents
- Works best with factual, structured content
- Large documents may need careful chunking
- Embedding model has context length limits
- No automatic document updates (re-add to update)
