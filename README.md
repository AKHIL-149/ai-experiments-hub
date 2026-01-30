# AI Experiments Hub

A hands-on exploration of modern AI/ML development through practical projects. Starting with local LLMs (Ollama) and progressing to advanced applications - agents, RAG systems, multi-modal AI, and production deployments. Built for learning by doing, not following tutorials.

## Approach

Rather than following tutorials, I'm building actual tools I can use. Each project builds on previous concepts while introducing new techniques. The goal is to understand modern AI development through practice, not theory.

## Why Local-First

I'm starting with local models (Ollama) for two reasons:
1. No API costs while learning and experimenting
2. Complete control over data and privacy

Cloud APIs (Anthropic Claude, OpenAI) are available as an option for projects that need more power or specific capabilities like vision.

## Project Roadmap

### Phase 1: Foundations

**1. AI Text Generator** (Python)
- Basic LLM integration and prompt engineering
- CLI interface for generating various types of content
- Local: Ollama | Cloud: Anthropic/OpenAI

**2. Prompt Playground** (JavaScript)
- Web interface for testing and comparing prompts
- Side-by-side model comparison
- Local: Ollama API | Cloud: Multiple providers

**3. Smart Email Responder** (Python)
- Context-aware email draft generation
- Template system for different response types
- Practice with structured prompting

### Phase 2: Practical Applications

**4. Personal Knowledge Assistant** (Python)
- RAG implementation from scratch
- Document chunking and vector embeddings
- ChromaDB for similarity search
- Query my own documents and notes

**5. AI Workflow Automation** (JavaScript)
- Autonomous agents with function calling
- Web scraping and data extraction
- Scheduled automation tasks

**6. Code Documentation Generator** (Python)
- AST parsing for code analysis
- Automated documentation generation
- Support for multiple languages

### Phase 3: Multi-Modal

**7. Content Analyzer** (Python)
- Vision model integration
- OCR and image understanding
- Local: LLaVA | Cloud: Claude 3

**8. Voice Assistant** (JavaScript) ⚠️ In Progress
- Speech-to-text and text-to-speech
- Voice command processing
- Local: Whisper.cpp | Cloud: OpenAI Whisper
- _Note: Needs attention for better logical reasoning_

**9. Meeting Summarizer** (Python)
- Audio transcription pipeline
- Long-context summarization
- Action item extraction

### Phase 4: Production Systems

**10. Chat Application** (Full-stack) ⚠️ In Progress
- Complete chat interface with history
- User authentication and sessions
- WebSocket streaming
- Database integration
- Voice input (real-time speech-to-text)
- Image generation (Stable Diffusion + DALL-E)
- _Note: Core features working, image generation may take time on first run (~10min model download)_

**11. Research Assistant** (Python)
- Advanced RAG with web search
- Multi-source information synthesis
- Citation tracking
- ArXiv and web integration

**12. Content Moderation System** (Full-stack)
- Multi-modal classification
- Queue-based batch processing
- Admin dashboard
- Production-ready architecture

## Tech Stack

**Languages:** Python 3.11+, JavaScript (Node.js 18+)

**Local AI:**
- Ollama for LLM inference
- Sentence Transformers for embeddings
- Whisper.cpp for speech-to-text

**Cloud AI (Optional):**
- Anthropic Claude API
- OpenAI API

**Storage:**
- ChromaDB for vector storage
- PostgreSQL for application data

**Frameworks:**
- FastAPI for Python backends
- React for frontends
- LangChain where it makes sense (avoiding over-abstraction)

## Setup

Install Ollama:
```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3.2
```

Configure environment:
```bash
cp .env.example .env
# Edit .env with your settings
```

Python environment:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Project Structure

```
ai-experiments-hub/
├── python-projects/
│   ├── 01-text-generator/
│   ├── 02-email-responder/
│   ├── 04-rag-knowledge-assistant/
│   └── ...
└── javascript-projects/
    ├── 03-prompt-playground/
    ├── 05-workflow-automation/
    └── ...
```

## Progress

- [x] Project 1: AI Text Generator
- [x] Project 2: Prompt Playground
- [x] Project 3: Smart Email Responder
- [x] Project 4: Personal Knowledge Assistant
- [x] Project 5: AI Workflow Automation
- [ ] Project 6: Code Documentation Generator
- [ ] Project 7: Content Analyzer
- [ ] Project 8: Voice Assistant
- [ ] Project 9: Meeting Summarizer
- [ ] Project 10: Chat Application
- [ ] Project 11: Research Assistant
- [ ] Project 12: Content Moderation System

## Learning Resources

**Documentation:**
- [Ollama API](https://github.com/ollama/ollama/blob/main/docs/api.md)
- [Anthropic Claude](https://docs.anthropic.com/)
- [OpenAI Platform](https://platform.openai.com/docs)

**Courses:**
- DeepLearning.AI - ChatGPT Prompt Engineering
- Fast.ai - Practical Deep Learning
- Andrew Ng - Machine Learning Specialization

**Communities:**
- r/MachineLearning
- r/LocalLLaMA
- Ollama Discord

## Notes

This is a learning repository. Code quality will improve as I progress through projects. The focus is on understanding concepts through implementation, not building perfect production systems (at least initially).

Starting with local models keeps costs at zero while experimenting. Will transition to cloud APIs for projects that need specific capabilities or when deploying something for actual use.

## License

MIT License - see [LICENSE](LICENSE) file for details.

This is a learning repository. Feel free to use any code as reference for your own projects.
