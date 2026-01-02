# Smart Email Responder

AI-powered tool for generating contextual email responses. Uses templates and structured prompting to create professional, appropriate replies to various types of emails.

## Features

- 8 pre-built email response templates
- Context-aware generation
- Support for custom instructions
- Read emails from files or command line
- Professional tone management
- Save responses to files

## Setup

Create virtual environment and install dependencies:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Make sure Ollama is running with a model available:

```bash
ollama pull llama3.2
```

## Available Templates

- **professional** - Standard professional business response
- **casual** - Friendly, conversational response
- **decline** - Politely decline a request
- **accept** - Accept an invitation or request
- **follow_up** - Follow up on previous communication
- **thank_you** - Express gratitude
- **inquiry_response** - Answer questions or inquiries
- **apology** - Apologize for an issue

List all templates:
```bash
python respond.py --list-templates
```

## Usage

### Basic Response

```bash
python respond.py --template professional "Can we meet next Tuesday?"
```

### From File

```bash
python respond.py --template accept --file examples/meeting_request.txt
```

### With Custom Instructions

```bash
python respond.py --template decline \
  --instructions "Suggest meeting next week instead" \
  --file examples/meeting_request.txt
```

### Save to File

```bash
python respond.py --template thank_you \
  --file examples/thank_you_opportunity.txt \
  --output my_response.txt
```

### Adjust Creativity

```bash
python respond.py --template casual \
  --temperature 0.9 \
  "Thanks for the code review!"
```

## Examples

### Accept Meeting Request

```bash
python respond.py --template accept --file examples/meeting_request.txt
```

### Thank Someone

```bash
python respond.py --template thank_you --file examples/thank_you_opportunity.txt
```

### Respond to Inquiry

```bash
python respond.py --template inquiry_response --file examples/project_inquiry.txt
```

### Polite Decline

```bash
python respond.py --template decline \
  --instructions "Suggest alternative time" \
  "Would you like to present at our conference next month?"
```

## Template Details

Each template is optimized for specific scenarios:

**Professional**: General business communication, formal requests, work-related matters

**Casual**: Friends, informal colleagues, relaxed business relationships

**Decline**: Turning down invitations, requests, proposals - maintains goodwill

**Accept**: Confirming meetings, accepting invitations, agreeing to requests

**Follow Up**: Gentle reminders, checking status, maintaining conversation

**Thank You**: Expressing gratitude, acknowledging help, showing appreciation

**Inquiry Response**: Answering questions, providing information, being helpful

**Apology**: Addressing mistakes, acknowledging issues, making amends

## Tips

1. **Be Specific**: More context in the email leads to better responses
2. **Custom Instructions**: Use `--instructions` to guide tone and content
3. **Template Selection**: Choose the template that best matches your intent
4. **Temperature**: Lower (0.3-0.5) for formal, higher (0.8-1.0) for creative
5. **Review Before Sending**: Always review and personalize the generated response

## Project Structure

```
02-email-responder/
├── src/
│   ├── responder.py           # Main CLI application
│   ├── email_templates.py     # Response templates
│   └── llm_client.py          # Ollama API client
├── examples/
│   ├── meeting_request.txt
│   ├── thank_you_opportunity.txt
│   └── project_inquiry.txt
├── respond.py                 # Convenience wrapper
└── requirements.txt
```

## Implementation Notes

This project demonstrates:
- Template-based prompt engineering
- Structured prompt construction
- Context extraction and management
- CLI design for text processing
- Professional tone adaptation

The templates use carefully crafted prompts that guide the model to produce contextually appropriate responses while maintaining the desired tone and style.
