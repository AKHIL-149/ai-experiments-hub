# Chat Application (Full-stack)

A production-ready full-stack chat application with user authentication, real-time WebSocket streaming, conversation history, and multi-provider LLM support.

## Features

- **User Authentication**: Session-based auth with bcrypt password hashing
- **Multi-Conversation Management**: Create, list, update, and delete conversations
- **Real-Time Streaming**: Token-by-token LLM response streaming via WebSocket
- **Database Persistence**: SQLAlchemy ORM with SQLite (default) and PostgreSQL support
- **Multi-Provider LLM**: Ollama (local), OpenAI, and Anthropic support
- **Responsive UI**: Clean vanilla JavaScript frontend with no build step
- **Copy replies**: A Copy button under every finished assistant reply (hover, or Tab to it; always visible on touch screens) puts the reply on the clipboard exactly as the model wrote it - markdown, code and tables intact. It also works when the app is opened over plain `http://` on a network address, where browsers disable the clipboard API

## Tech Stack

**Backend**:
- FastAPI (async/await support)
- SQLAlchemy ORM
- bcrypt (password hashing)
- python-dotenv (configuration)

**Frontend**:
- Vanilla JavaScript (class-based architecture)
- WebSocket API
- No build step required

**LLM Providers**:
- Ollama (local, default)
- OpenAI API (optional)
- Anthropic API (optional)

## Installation

### Prerequisites

- Python 3.9+
- Ollama (for local LLM) - https://ollama.com

### Setup

1. **Install dependencies**:
```bash
cd python-projects/10-chat-application
pip install -r requirements.txt
```

2. **Configure environment**:
```bash
cp .env.example .env
# Edit .env with your configuration
```

3. **Start Ollama (for local LLM)**:
```bash
ollama serve
ollama pull llama3.2:3b
```

4. **Run the application**:
```bash
python server.py
```

5. **Open in browser**:
```
http://localhost:8000
```

## Configuration

Edit [.env](.env) to configure the application:

```bash
# Server
PORT=8000
HOST=127.0.0.1          # 0.0.0.0 serves other machines on your network (see Security)

# Database
DATABASE_URL=sqlite:///./data/database.db
# For PostgreSQL: postgresql://user:password@localhost/chatdb

# Session
SESSION_TTL_DAYS=30
COOKIE_SECURE=false  # Set to true in production with HTTPS

# CORS and WebSocket origins besides the page's own address
ALLOWED_ORIGINS=http://localhost:8000,http://127.0.0.1:8000

# Limits
MAX_MESSAGE_CHARS=20000
MAX_SYSTEM_PROMPT_CHARS=8000
LOGIN_MAX_FAILURES=10      # failed logins per username and client ...
LOGIN_WINDOW_SECONDS=300   # ... within this window, then HTTP 429 until it passes

# LLM Providers
OLLAMA_API_URL=http://localhost:11434
OLLAMA_NUM_CTX=8192        # context window asked from Ollama (its own default is 4096)
OPENAI_API_KEY=your_openai_key_here  # Optional
ANTHROPIC_API_KEY=your_anthropic_key_here  # Optional
```

Without `OLLAMA_NUM_CTX`, Ollama answers with a 4096-token window and silently drops the oldest text of a longer
conversation (the system prompt included). The server also sends the model only as much history as fits that
window (the newest messages; at most the last 20), so a long chat forgets its start on purpose rather than at random.

## Usage

### Registration and Login

1. Open http://localhost:8000
2. Click "Register" to create a new account
3. Enter username (3-50 chars, spaces around it are dropped; "Alice" and "alice" are the same name), email, and password (8 to 72 bytes: bcrypt ignores everything past byte 72, so longer passwords are refused rather than silently cut)
4. You'll be automatically logged in after registration

### Creating Conversations

1. Click the "+" button in the sidebar to create a new conversation
2. Type your message in the input box at the bottom
3. Press Enter or click "Send" to send the message
4. Watch the AI response stream in real-time

### Managing Conversations

- **Select Conversation**: Click on a conversation in the sidebar to open it
- **Delete Conversation**: Click the "×" button next to a conversation
- **Auto-Title**: Conversations are automatically titled based on the first message

### Logout

Click the "Logout" button in the sidebar footer to log out.

## API Endpoints

### Authentication
- `POST /api/auth/register` - Register new user
- `POST /api/auth/login` - Login user
- `POST /api/auth/logout` - Logout user
- `GET /api/auth/me` - Get current user info

### Conversations
- `POST /api/conversations` - Create new conversation
- `GET /api/conversations` - List user's conversations
- `GET /api/conversations/{id}` - Get conversation with messages
- `PATCH /api/conversations/{id}` - Update conversation
- `DELETE /api/conversations/{id}` - Delete conversation

List endpoints take `limit` (1-200 for conversations, 1-500 for messages) and `offset` (>= 0). A provider must be
`ollama`, `openai` or `anthropic`; titles are at most 200 characters, model names 100, system prompts
`MAX_SYSTEM_PROMPT_CHARS`. Invalid input returns HTTP 422 with `detail` as one readable sentence
(`"llm_provider: Input should be 'ollama', 'openai' or 'anthropic'"`).

### Messages
- `POST /api/conversations/{id}/messages` - Create message
- `GET /api/conversations/{id}/messages` - List messages

### WebSocket
- `WS /ws/{conversation_id}` - Real-time chat streaming

Send `{"type": "message", "content": "..."}`; receive `token` events, then `done` (or `error`). A blank message,
one over `MAX_MESSAGE_CHARS`, or a frame that is not a JSON object gets an `error` event and the socket stays open.
The socket is closed (code 1008) when the session ends or the conversation is deleted, and it is refused to a page
whose origin is neither the app's own address nor in `ALLOWED_ORIGINS`.

### Image generation
- `POST /api/generate-image` - `{"prompt", "provider": "stable-diffusion" | "dall-e", "width", "height"}`; sizes are
  64-1024 in steps of 8 (DALL-E gets the closest size it supports: 1024x1024, 1792x1024 or 1024x1792). One image is
  generated at a time, in a worker thread, so chats keep streaming meanwhile.

### Health
- `GET /api/health` - Health check and provider availability

## Development

### Project Structure

```
10-chat-application/
├── server.py                 # FastAPI application
├── requirements.txt          # Dependencies
├── .env.example              # Config template
├── README.md                 # This file
├── src/
│   └── core/
│       ├── database.py       # SQLAlchemy models
│       ├── auth_manager.py   # Authentication
│       └── llm_client.py     # Multi-provider LLM
├── templates/
│   └── index.html            # Main HTML template
├── static/
│   ├── app.js                # Frontend JavaScript
│   └── styles.css            # Application styles
├── data/
│   └── database.db           # SQLite database (gitignored)
└── tests/
    └── test_*.py             # Test suite
```

### Running Tests

```bash
pytest tests/ -v
```

The suite (about 160 tests) covers the Ollama error handling, the chat flow, reply rendering and the Copy
button, accounts and limits, the throttle, WebSocket safety (origin, malformed frames, ending the connection,
history budget), and the page's behaviour when the socket drops. The front-end tests run the real `static/*.js`
in Node with a small fake DOM, so they need `node` on the PATH (they are skipped without it); they check the
scripts' logic, not how the page looks. Image generation itself (the Stable Diffusion model) and the cloud
providers are not exercised by the tests.

### PostgreSQL Setup

For production, use PostgreSQL instead of SQLite:

1. Install PostgreSQL
2. Create a database: `createdb chatdb`
3. Update `.env`: `DATABASE_URL=postgresql://user:password@localhost/chatdb`
4. Run the application

## Security

- Passwords are hashed with bcrypt (12 rounds)
- Session tokens are 32-byte cryptographically secure strings
- HTTPOnly cookies prevent XSS attacks
- SameSite=Strict prevents CSRF attacks on the REST API. It does not stop a page on another port of `localhost`
  (which counts as the same site) from opening the WebSocket, so the socket checks the `Origin` header itself
- CORS restricted to allowed origins
- Input validation with Pydantic models, with size limits on every free-text field
- Failed logins are throttled per username and client (HTTP 429 with `Retry-After`), and an unknown username
  takes as long to reject as a wrong password, so login time does not reveal which usernames exist
- The server listens on `127.0.0.1` unless `HOST` says otherwise. The sign-in is a cookie over plain HTTP: if you
  set `HOST=0.0.0.0`, anyone on the network can reach the app and the model behind it
- SQLAlchemy ORM prevents SQL injection

## Multi-Provider LLM Support

### Ollama (Local, Default)

```bash
# Install and start Ollama
ollama serve
ollama pull llama3.2:3b
```

Ollama runs completely offline on http://localhost:11434

### OpenAI (Cloud)

Add to `.env`:
```bash
OPENAI_API_KEY=your_key_here
```

Models: `gpt-4o-mini`, `gpt-4o`, `gpt-3.5-turbo`

### Anthropic (Cloud)

Add to `.env`:
```bash
ANTHROPIC_API_KEY=your_key_here
```

Models: `claude-3-5-sonnet-20241022`, `claude-3-haiku-20240307`

## Troubleshooting

### Ollama not connecting

1. Check if Ollama is running: `curl http://localhost:11434/api/tags`
2. Start Ollama: `ollama serve`
3. Pull a model: `ollama pull llama3.2:3b`

### Database errors

Delete the database and restart:
```bash
rm data/database.db
python server.py
```

### WebSocket connection issues

1. Check browser console for errors
2. Ensure you're logged in (session cookie present)
3. Verify conversation exists and you own it

## Future Enhancements

- Conversation search and filtering
- Export conversations (Markdown, JSON, PDF)
- Message editing and regeneration
- Code syntax highlighting
- Dark mode
- Markdown rendering
- OAuth login (Google, GitHub)
- Team workspaces

## License

MIT License - See LICENSE file for details

## Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## Support

For issues and questions, please open an issue on GitHub.
