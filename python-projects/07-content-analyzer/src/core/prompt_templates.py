"""Prompt templates for improved vision analysis accuracy."""

# Default concise description prompt
DEFAULT_PROMPT = """Describe this image concisely. State: what it is, key visual details, and any notable text or features. Keep response brief and factual."""

# Prompt templates for specific use cases
PROMPT_TEMPLATES = {
    'vehicle': """Identify the vehicle: type, make/model (if visible), color, and any logos/numbers. Be brief and factual.""",

    'document': """Identify document type, key visible text/headings, and any logos. Keep response concise.""",

    'object': """Identify the object: what it is, material/color, and any visible text or brands. Be brief.""",

    'scene': """Describe the scene: location type, main elements, lighting/time, and notable features. Keep it concise.""",

    'person': """Describe: number of people, their activity, clothing, and setting. Be brief and factual.""",

    'technical': """Provide brief technical analysis: subject, composition, lighting, color, and image quality.""",

    'simple': """In 1-2 sentences: what is this, and what are the key visual features?"""
}


def get_prompt(template_name: str = None, custom_prompt: str = None) -> str:
    """Get a prompt for vision analysis.

    Args:
        template_name: Name of template ('vehicle', 'document', 'object', etc.)
        custom_prompt: Custom user-provided prompt (takes precedence)

    Returns:
        str: Formatted prompt
    """
    if custom_prompt:
        return custom_prompt

    if template_name and template_name in PROMPT_TEMPLATES:
        return PROMPT_TEMPLATES[template_name]

    return DEFAULT_PROMPT


def list_templates() -> dict:
    """List all available prompt templates.

    Returns:
        dict: Template names and their first line descriptions
    """
    templates = {}
    for name, prompt in PROMPT_TEMPLATES.items():
        # Get first line as description
        first_line = prompt.strip().split('\n')[0]
        templates[name] = first_line

    return templates
