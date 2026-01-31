# Research Assistant

An advanced AI-powered research assistant that combines document-based RAG (Retrieval-Augmented Generation), web search, and ArXiv academic paper integration to synthesize information from multiple sources with proper citations and confidence scoring.

## Status

**Phase 1**: ✅ Complete - Database & Authentication
**Phase 2**: 🚧 In Progress - ArXiv Integration & Citations
**Phase 3**: 📋 Planned - Advanced Synthesis
**Phase 4**: 📋 Planned - Web Interface
**Phase 5**: 📋 Planned - Production Features

## Features

### Current (Phase 1)
- ✅ **Multi-user authentication** with session management
- ✅ **Database persistence** using SQLAlchemy (6 tables)
- ✅ **Secure password hashing** with bcrypt (12 rounds)
- ✅ **Session-based auth** with 30-day TTL

### Planned
- 🚧 **Multi-source research**: Web + ArXiv + Documents
- 🚧 **Intelligent synthesis**: Cross-source deduplication, authority ranking
- 🚧 **Citation management**: APA, MLA, Chicago, IEEE formats
- 🚧 **Confidence scoring**: Strict verification (3+ sources, ≥0.8 confidence)
- 🚧 **3-level caching**: 60-75% cost savings
- 🚧 **Real-time progress**: WebSocket streaming
- 🚧 **Multiple export formats**: Markdown, HTML, PDF, JSON

## Project Structure

```
11-research-assistant/
├── research.py                 # CLI entry point
├── server.py                   # FastAPI web server (Phase 4)
├── requirements.txt            # Python dependencies
├── .env.example                # Configuration template
├── src/
│   ├── core/
│   │   ├── database.py         # ✅ SQLAlchemy models (6 tables)
│   │   ├── auth_manager.py     # ✅ Authentication & sessions
│   │   ├── research_orchestrator.py   # Phase 2
│   │   ├── web_search_client.py       # Phase 1-2
│   │   ├── arxiv_client.py            # Phase 2
│   │   ├── synthesis_engine.py        # Phase 3
│   │   └── citation_manager.py        # Phase 2
│   ├── services/
│   │   ├── embedding_service.py       # Phase 1-2
│   │   ├── vector_store.py            # Phase 1-2
│   │   ├── cache_manager.py           # Phase 1-2
│   │   ├── retry_handler.py           # Phase 2
│   │   └── progress_tracker.py        # Phase 3
│   └── utils/
│       ├── pdf_extractor.py           # Phase 2
│       ├── source_ranker.py           # Phase 3
│       ├── deduplicator.py            # Phase 3
│       └── report_generator.py        # Phase 3
├── templates/
│   └── index.html              # Web UI (Phase 4)
├── static/
│   └── research.js             # Frontend (Phase 4)
├── data/
│   ├── cache/                  # Cached results
│   ├── chroma/                 # Vector database
│   ├── documents/              # User uploads
│   ├── papers/                 # ArXiv PDFs
│   └── database.db             # SQLite database
└── tests/
    ├── test_database.py        # ✅ Database model tests
    └── test_auth.py            # ✅ Authentication tests
```

## Installation

### Prerequisites

- Python 3.11+
- pip

### Setup

1. **Clone the repository** (if not already cloned)
   ```bash
   cd ai-experiments-hub/python-projects/11-research-assistant
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

5. **Initialize database**
   ```bash
   python -c "from src.core.database import DatabaseManager; DatabaseManager().create_tables()"
   ```

## Configuration

Edit `.env` file with your settings:

### Required Settings
```bash
# Database
DATABASE_URL=sqlite:///./data/database.db

# Session
SESSION_TTL_DAYS=30

# LLM Provider (choose one)
OLLAMA_API_URL=http://localhost:11434  # Local, free
# or
OPENAI_API_KEY=your_key_here
# or
ANTHROPIC_API_KEY=your_key_here
```

### Optional Settings
```bash
# Verification level
DEFAULT_VERIFICATION_LEVEL=strict  # strict, standard, or lenient

# Citation style
DEFAULT_CITATION_STYLE=APA  # APA, MLA, Chicago, or IEEE

# Caching
ENABLE_CACHE=true
SEARCH_CACHE_TTL_DAYS=7
```

## Usage

### Phase 1 (Current): Authentication & Database

**Test authentication**:

```python
from src.core.database import DatabaseManager, User
from src.core.auth_manager import AuthManager

# Initialize
db_manager = DatabaseManager()
db_manager.create_tables()
auth_manager = AuthManager()

# Create database session
db_session = db_manager.get_session()

# Register user
success, user, error = auth_manager.register_user(
    db_session,
    username="testuser",
    email="test@example.com",
    password="securepassword123"
)

if success:
    print(f"User created: {user.username}")

    # Create session
    success, session, error = auth_manager.create_session(db_session, user)
    if success:
        print(f"Session token: {session.id}")

        # Validate session
        valid, user, error = auth_manager.validate_session(db_session, session.id)
        if valid:
            print(f"Session valid for user: {user.username}")
```

### Phase 2+ (Planned): Research Operations

**CLI usage** (coming soon):
```bash
# Register user
python research.py register --username myuser --email user@example.com

# Login
python research.py login --username myuser

# Perform research
python research.py query "quantum computing applications" \
    --sources web,arxiv,documents \
    --max-results 20 \
    --citations APA \
    --output report.md
```

**Web interface** (Phase 4):
```bash
# Start server
python server.py

# Open browser
open http://localhost:8000
```

## Database Schema

### Users Table
- `id`: UUID primary key
- `username`: Unique username (3-50 chars)
- `email`: Unique email address
- `password_hash`: Bcrypt hashed password
- `created_at`, `updated_at`: Timestamps

### Sessions Table
- `id`: Session token (32 bytes)
- `user_id`: Foreign key to users
- `expires_at`: Expiration timestamp
- `last_accessed`: Last access timestamp

### ResearchQuery Table
- `id`: UUID primary key
- `user_id`: Foreign key to users
- `query_text`: Research question
- `status`: pending, processing, completed, failed
- `search_web`, `search_arxiv`, `search_documents`: Boolean flags
- `max_sources`: Maximum sources to retrieve
- `verification_level`: strict, standard, or lenient
- `summary`: Generated research summary
- `confidence_score`: Overall confidence (0-1)

### Source Table
- `id`: UUID primary key
- `query_id`: Foreign key to research_queries
- `source_type`: web, arxiv, or document
- `title`, `url`, `authors`: Source metadata
- `content`: Extracted text
- `content_hash`: SHA256 for deduplication
- `relevance_score`, `authority_score`: Scoring metrics

### Finding Table
- `id`: UUID primary key
- `query_id`: Foreign key to research_queries
- `finding_text`: Key finding statement
- `finding_type`: fact, argument, statistic, etc.
- `confidence`: Confidence score (0-1)
- `source_ids`: JSON list of supporting sources

### Citation Table
- `id`: UUID primary key
- `query_id`: Foreign key to research_queries
- `source_id`: Foreign key to sources
- `citation_text`: Quoted text
- `citation_style`: APA, MLA, Chicago, IEEE
- `formatted_citation`: Fully formatted citation string

## Testing

**Run tests**:
```bash
# All tests
pytest tests/ -v

# Specific test file
pytest tests/test_auth.py -v

# With coverage
pytest tests/ --cov=src --cov-report=html
```

**Current test coverage**:
- ✅ Database models (User, Session, ResearchQuery, Source, Finding, Citation)
- ✅ Authentication (registration, login, session management)
- 🚧 Research operations (Phase 2+)

## Architecture

### Authentication Flow
```
1. User registers → bcrypt hash password → store in database
2. User logs in → verify password → create session token
3. Session token stored in cookie (HTTPOnly, Secure, SameSite)
4. Each request → validate session → get user
5. User logs out → delete session
```

### Research Flow (Phase 2+)
```
1. User submits query → create ResearchQuery record
2. Search sources:
   - Web search (DuckDuckGo)
   - ArXiv papers
   - User documents (RAG)
3. Deduplicate sources (SHA256 + embedding similarity)
4. Rank sources (relevance + authority + recency)
5. Synthesize findings (map-reduce pattern)
6. Generate citations (APA/MLA/Chicago/IEEE)
7. Calculate confidence scores
8. Export report (Markdown/HTML/PDF/JSON)
```

### Caching Strategy (Phase 2+)
- **Level 1**: Search results (7-day TTL)
- **Level 2**: Content extraction (30-day TTL)
- **Level 3**: Synthesis results (14-day TTL)

**Expected savings**: 60-75% cost reduction after warmup

## Security

- ✅ **Password hashing**: bcrypt with 12 rounds
- ✅ **Session tokens**: 32-byte cryptographically secure random
- ✅ **Session expiration**: 30-day TTL (configurable)
- ✅ **Input validation**: Username, email, password constraints
- ✅ **SQL injection protection**: SQLAlchemy ORM
- 🚧 **CORS**: Restricted origins (Phase 4)
- 🚧 **Rate limiting**: 100 req/min per user (Phase 4)
- 🚧 **HTTPOnly cookies**: Prevent XSS (Phase 4)

## Development Roadmap

### Phase 1: Core Foundation & Authentication ✅
- [x] Project structure
- [x] Database models (6 tables)
- [x] Authentication manager
- [x] Unit tests for database and auth

### Phase 2: ArXiv Integration & Citations 🚧
- [ ] Web search client (DuckDuckGo)
- [ ] ArXiv client
- [ ] Citation manager (APA/MLA/IEEE)
- [ ] RAG engine (from Project 04)
- [ ] Basic CLI

### Phase 3: Advanced Synthesis 📋
- [ ] Deduplicator
- [ ] Source ranker
- [ ] Synthesis engine (map-reduce)
- [ ] Confidence scoring
- [ ] Report generator

### Phase 4: Web Interface 📋
- [ ] FastAPI server
- [ ] REST API endpoints
- [ ] WebSocket for progress
- [ ] Web UI

### Phase 5: Production Features 📋
- [ ] Batch processing
- [ ] Progress resumption
- [ ] Cost tracking
- [ ] Export formats (PDF, DOCX)
- [ ] User management UI

## Verification Levels

### Strict (Default)
- Minimum sources per finding: **3**
- Minimum confidence: **0.8**
- Only high-authority sources (academic papers + .edu/.gov)
- Full citation tracing required

### Standard
- Minimum sources per finding: **2**
- Minimum confidence: **0.6**
- Mix of web + papers + documents
- Citations for key claims

### Lenient
- Minimum sources per finding: **1**
- Minimum confidence: **0.4**
- Include all source types
- Optional citations

## Citation Styles

### Supported Formats
- **APA** (American Psychological Association)
- **MLA** (Modern Language Association)
- **Chicago** (Chicago Manual of Style)
- **IEEE** (Institute of Electrical and Electronics Engineers)

### Example Output

**APA**:
```
Smith, J., & Jones, M. (2024). Quantum Computing Applications.
arXiv preprint arXiv:2401.12345.
```

**MLA**:
```
Smith, John, and Mary Jones. "Quantum Computing Applications."
arXiv preprint arXiv:2401.12345 (2024).
```

## Troubleshooting

### Database Issues

**Problem**: `sqlite3.OperationalError: no such table`
**Solution**: Initialize database tables
```bash
python -c "from src.core.database import DatabaseManager; DatabaseManager().create_tables()"
```

**Problem**: `sqlite3.OperationalError: database is locked`
**Solution**: Close other database connections or use PostgreSQL for production

### Authentication Issues

**Problem**: `bcrypt.checkpw` fails
**Solution**: Ensure password is encoded as bytes
```python
bcrypt.checkpw(password.encode('utf-8'), hash.encode('utf-8'))
```

**Problem**: Session expires too quickly
**Solution**: Increase `SESSION_TTL_DAYS` in `.env`

## Contributing

This is part of the AI Experiments Hub project. Each phase is reviewed before committing to git.

## License

Part of AI Experiments Hub - see main repository for license.

## Support

For issues specific to this project, please refer to the main repository's issue tracker.
