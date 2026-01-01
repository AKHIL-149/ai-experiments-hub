"""Prompt templates for different content types."""

TEMPLATES = {
    "email": """Write a professional email based on this request: {prompt}

Requirements:
- Professional tone
- Clear and concise
- Appropriate greeting and closing
- Well-structured paragraphs""",

    "story": """Write a creative short story based on this idea: {prompt}

Requirements:
- Engaging narrative
- Clear beginning, middle, and end
- Descriptive language
- Around 300-500 words""",

    "poem": """Write a poem based on this theme: {prompt}

Requirements:
- Creative and evocative language
- Consider rhythm and flow
- Use imagery and metaphor
- Any poetic form is acceptable""",

    "code": """Help with this coding request: {prompt}

Requirements:
- Clear explanation of the approach
- Well-commented code if applicable
- Best practices
- Concise and practical""",
}


def get_template(template_name: str) -> str:
    """Get a prompt template by name."""
    if template_name not in TEMPLATES:
        available = ", ".join(TEMPLATES.keys())
        raise ValueError(f"Unknown template '{template_name}'. Available: {available}")
    return TEMPLATES[template_name]


def apply_template(template_name: str, prompt: str) -> str:
    """Apply a template to a user prompt."""
    template = get_template(template_name)
    return template.format(prompt=prompt)
