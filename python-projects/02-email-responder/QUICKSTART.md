# Quick Start - Smart Email Responder

Get started with AI-powered email responses in 2 minutes.

## Setup

```bash
cd python-projects/02-email-responder

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

## See Available Templates

```bash
python respond.py --list-templates
```

You'll see 8 templates:
- professional, casual, decline, accept
- follow_up, thank_you, inquiry_response, apology

## Quick Examples

### 1. Respond to a Meeting Request

```bash
python respond.py --template accept --file examples/meeting_request.txt
```

### 2. Quick Professional Reply

```bash
python respond.py --template professional "Can we schedule a call next week?"
```

### 3. Polite Decline with Custom Instructions

```bash
python respond.py --template decline \
  --instructions "Suggest alternative next month" \
  "Would you like to speak at our event?"
```

### 4. Thank Someone

```bash
python respond.py --template thank_you --file examples/thank_you_opportunity.txt
```

### 5. Answer an Inquiry

```bash
python respond.py --template inquiry_response --file examples/project_inquiry.txt
```

### 6. Save Response to File

```bash
python respond.py --template accept \
  --file examples/meeting_request.txt \
  --output my_response.txt
```

## Tips

**Choose the Right Template:**
- Business email → `professional`
- Friend/colleague → `casual`
- Can't make it → `decline`
- Confirm attendance → `accept`
- Need follow up → `follow_up`
- Show appreciation → `thank_you`
- Answer questions → `inquiry_response`
- Fix a mistake → `apology`

**Customize Responses:**
Use `--instructions` to add specific details:
```bash
python respond.py --template professional \
  --instructions "Mention that I'll bring the slides" \
  "See you at the meeting tomorrow"
```

**Adjust Tone:**
- More formal: `--temperature 0.3`
- Balanced: `--temperature 0.7` (default)
- More casual: `--temperature 1.0`

## Common Workflows

**Email from File:**
1. Save incoming email to a text file
2. Choose appropriate template
3. Generate response
4. Review and personalize

**Quick Inline:**
1. Copy email text
2. Paste directly in command
3. Generate and use

**Batch Processing:**
Create multiple responses and save to files for review later.

## Next Steps

- Try different templates with the same email
- Experiment with custom instructions
- Adjust temperature to see tone changes
- Create your own example emails in `examples/`

The generated responses are starting points - always review and personalize before sending!
