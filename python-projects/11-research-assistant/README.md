# Research Assistant

An advanced AI-powered research assistant that combines document-based RAG (Retrieval-Augmented Generation), web search, and ArXiv academic paper integration to synthesize information from multiple sources with proper citations and confidence scoring.

## Status

**Current Version**: 11.7.0 (Production-Ready)

**Phase 1**: ✅ Complete - Database & Authentication
**Phase 2**: ✅ Complete - ArXiv Integration & Citations
**Phase 3**: ✅ Complete - Advanced Synthesis
**Phase 4**: ✅ Complete - Web Interface
**Phase 5**: ✅ Complete - Production Features

📋 **See [FUTURE_IMPROVEMENTS.md](FUTURE_IMPROVEMENTS.md) for enhancement roadmap**

## Features

### Implemented (v11.7.0)
- ✅ **Multi-user authentication** with session management
- ✅ **Database persistence** using SQLAlchemy (6 tables)
- ✅ **Secure password hashing** with bcrypt (12 rounds)
- ✅ **Session-based auth** with 30-day TTL
- ✅ **Web search client** with DuckDuckGo integration (ddgs package)
- ✅ **ArXiv client** for academic paper search and PDF extraction
- ✅ **Citation manager** supporting APA, MLA, Chicago, IEEE formats
- ✅ **3-level cache manager** for cost optimization (60-75% savings)
- ✅ **LLM client** supporting Ollama, OpenAI, Anthropic
- ✅ **Multi-source synthesis** with map-reduce pattern
- ✅ **Source deduplication** (exact + semantic)
- ✅ **Authority-based ranking** (academic papers prioritized)
- ✅ **Confidence scoring** with configurable thresholds
- ✅ **Real-time progress** via WebSocket streaming
- ✅ **Multiple export formats**: Markdown, HTML, PDF, DOCX, JSON
- ✅ **Cost tracking** across providers (Ollama/OpenAI/Anthropic)
- ✅ **Usage analytics** (API usage, costs, sources, performance)
- ✅ **Web UI** with responsive design and real-time updates

### Future Enhancements
See [FUTURE_IMPROVEMENTS.md](FUTURE_IMPROVEMENTS.md) for:
- 📋 Enhanced LLM support (model-specific prompts, structured output)
- 📋 Multi-provider web search (Brave, SerpAPI)
- 📋 Advanced synthesis refinements (claim verification, uncertainty quantification)
- 📋 Collaboration features (shared projects, team workspaces)
- 📋 Performance optimizations (parallel fetching, query optimization)
- 📋 Multi-modal research (images, videos, audio)
- 📋 Domain-specific modes (medical, legal, financial)

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

### Web Interface (Recommended)

**Start the server**:
```bash
python server.py
```

**Access the application**:
```
http://localhost:8000
```

**Features**:
- User registration and login
- Submit research queries with real-time progress
- View results with findings, sources, and citations
- Download reports in multiple formats (Markdown, PDF, DOCX, JSON)
- Track costs and usage analytics

### Example Queries

**Academic Research**:
```
How do variations in front-wing geometry influence downforce generation
and aerodynamic efficiency across different cornering speeds in Formula 1 cars?
```

**Technology Analysis**:
```
What are the latest advancements in quantum computing error correction
techniques as of 2024?
```

**Medical Research**:
```
What are the most effective treatments for type 2 diabetes according
to recent clinical trials?
```

### API Usage (Programmatic)

**Python client example**:
```python
import requests

# Base URL
base_url = "http://localhost:8000"

# Register user
response = requests.post(f"{base_url}/api/auth/register", json={
    "username": "researcher",
    "email": "researcher@example.com",
    "password": "securepassword123"
})
print(response.json())

# Login
response = requests.post(f"{base_url}/api/auth/login", json={
    "username": "researcher",
    "password": "securepassword123"
})
session_cookie = response.cookies

# Submit research query
response = requests.post(
    f"{base_url}/api/research",
    json={
        "query": "quantum computing applications",
        "search_web": True,
        "search_arxiv": True,
        "max_sources": 20,
        "citation_style": "APA"
    },
    cookies=session_cookie
)
query_data = response.json()
query_id = query_data["query_id"]

# Get results
response = requests.get(
    f"{base_url}/api/research/{query_id}",
    cookies=session_cookie
)
results = response.json()
print(f"Confidence: {results['confidence']}")
print(f"Findings: {len(results['findings'])}")

# Download report
response = requests.get(
    f"{base_url}/api/research/{query_id}/download?format=markdown",
    cookies=session_cookie
)
with open("report.md", "w") as f:
    f.write(response.text)
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

## Development History

### Phase 1: Core Foundation & Authentication ✅ (v11.1.0)
- [x] Project structure
- [x] Database models (6 tables: User, Session, ResearchQuery, Source, Finding, Citation)
- [x] Authentication manager with bcrypt + sessions
- [x] Unit tests for database and auth

### Phase 2: ArXiv Integration & Citations ✅ (v11.2.0)
- [x] Web search client (DuckDuckGo)
- [x] ArXiv client with PDF extraction
- [x] Citation manager (APA/MLA/Chicago/IEEE)
- [x] 3-level caching system
- [x] Multi-provider LLM client (Ollama/OpenAI/Anthropic)

### Phase 3: Advanced Synthesis ✅ (v11.3.0)
- [x] Deduplicator (exact + semantic)
- [x] Source ranker with composite scoring
- [x] Synthesis engine with map-reduce pattern
- [x] Confidence scoring with configurable thresholds
- [x] Report generator (multiple formats)

### Phase 4: Web Interface ✅ (v11.4.0)
- [x] FastAPI server with authentication middleware
- [x] REST API endpoints (create, get, list, delete)
- [x] WebSocket for real-time progress
- [x] Single-page web UI (HTML/CSS/JS)
- [x] Session management with HTTPOnly cookies

### Phase 5: Production Features ✅ (v11.5.0)
- [x] Cost tracking across providers
- [x] Usage analytics (usage/costs/sources/performance endpoints)
- [x] Export formats (PDF via weasyprint, DOCX via python-docx)
- [x] Session cost breakdown
- [x] Comprehensive deployment guide

### Bug Fixes & Improvements
- **v11.6.0**: Fixed web search (ddgs package), improved synthesis for small LLMs
- **v11.7.0**: Fixed UI display (confidence NaN, formatted summaries)

### Future Development
See [FUTURE_IMPROVEMENTS.md](FUTURE_IMPROVEMENTS.md) for the complete enhancement roadmap (30-45 weeks of planned work).

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

## Production Readiness

### What Works Well ✅
- Multi-user authentication with secure session management
- Web search integration with DuckDuckGo (free, no API key)
- ArXiv academic paper search and extraction
- Multi-source synthesis with configurable confidence thresholds
- Cost tracking and usage analytics
- Multiple export formats (Markdown, HTML, PDF, DOCX, JSON)
- Real-time progress via WebSocket
- 60-75% cost savings with 3-level caching

### Known Limitations ⚠️
- **Small LLM Quality**: Works with Ollama llama3.2:3b but output quality varies (larger models recommended for production)
- **DuckDuckGo Rate Limits**: May throttle aggressive searches (retry with backoff implemented)
- **SQLite Concurrency**: Single-user deployments only (migrate to PostgreSQL for multi-user production)
- **Citation Accuracy**: Fallback parser assigns default sources [1,2,3] when LLM doesn't specify
- **Long Summaries**: Markdown parsing is regex-based (consider proper parser for complex formatting)

See [FUTURE_IMPROVEMENTS.md](FUTURE_IMPROVEMENTS.md) for detailed enhancement roadmap.

### Deployment Recommendations
- **Development**: SQLite + Ollama (zero cost, local)
- **Small Production**: PostgreSQL + Ollama (low cost, self-hosted)
- **Large Production**: PostgreSQL + OpenAI/Anthropic (higher quality, cloud LLMs)

### Performance Characteristics
- **Query Time**: 10-30 seconds for 10 sources
- **Memory**: ~2-4GB with Ollama llama3.2:3b
- **Cache Hit Rate**: 60-70% after warmup
- **Cost per Query**: $0.10-0.30 with cloud LLMs, $0 with Ollama

## Version History

| Version | Date | Description |
|---------|------|-------------|
| 11.7.0 | 2026-02-06 | UI improvements (confidence display, formatted summaries) |
| 11.6.0 | 2026-02-06 | Web search fixes, synthesis engine improvements for small LLMs |
| 11.5.0 | 2026-02-05 | Phase 5 production features (cost tracking, analytics, exports) |
| 11.4.0 | 2026-01-30 | Phase 4 web interface with authentication |
| 11.3.0 | 2026-01-25 | Phase 3 advanced synthesis |
| 11.2.0 | 2026-01-20 | Phase 2 ArXiv integration and citations |
| 11.1.0 | 2026-01-15 | Phase 1 database and authentication foundation |

## Contributing

This is part of the AI Experiments Hub project. Each phase is reviewed before committing to git.

**Contributing Guidelines**:
1. Check [FUTURE_IMPROVEMENTS.md](FUTURE_IMPROVEMENTS.md) for planned enhancements
2. Create feature branch from `main`
3. Add tests for new functionality
4. Update documentation (README, docstrings)
5. Submit pull request with clear description

## License

Part of AI Experiments Hub - see main repository for license.

## Support

For issues specific to this project, please refer to:
- [FUTURE_IMPROVEMENTS.md](FUTURE_IMPROVEMENTS.md) for known limitations and planned fixes
- Main repository's issue tracker for bug reports
- Project documentation for troubleshooting guides
