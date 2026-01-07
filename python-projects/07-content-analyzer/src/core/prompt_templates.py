"""Prompt templates for improved vision analysis accuracy."""

# Default detailed description prompt
DEFAULT_PROMPT = """Describe this image in detail. Focus on:
1. The main subject or object
2. Colors and visual characteristics
3. Setting or environment
4. Any text, logos, or identifying features
5. Notable details or unique elements

Be specific and factual."""

# Prompt templates for specific use cases
PROMPT_TEMPLATES = {
    'vehicle': """Analyze this image and identify:
1. Type of vehicle (car, truck, motorcycle, racing car, etc.)
2. Make, model, or team (if visible)
3. Color scheme and livery
4. Any visible sponsors, logos, or numbers
5. Condition and distinguishing features

Be precise and mention if you're uncertain about any details.""",

    'document': """Analyze this document image:
1. Type of document (form, letter, receipt, etc.)
2. Any visible text or headings
3. Layout and structure
4. Logos or official marks
5. Overall condition and quality

Focus on factual observations.""",

    'object': """Identify and describe the main object:
1. What is it? (be specific)
2. Material and construction
3. Color and finish
4. Size and proportions (relative)
5. Condition and notable features
6. Any text, brands, or labels

Avoid speculation - state only what you can see clearly.""",

    'scene': """Describe this scene:
1. Location type (indoor/outdoor, urban/rural, etc.)
2. Main elements and their arrangement
3. Lighting and time of day
4. Weather conditions (if outdoor)
5. Human activity or presence
6. Notable landmarks or features

Provide a balanced, factual description.""",

    'person': """Describe what you observe:
1. Number of people
2. Activities or poses
3. Clothing and accessories
4. Setting and context
5. Visible emotions or expressions
6. Any interactions

Focus on observable details, not assumptions.""",

    'technical': """Provide a technical analysis:
1. Subject identification
2. Composition and framing
3. Lighting quality
4. Color balance and saturation
5. Focus and clarity
6. Technical quality assessment

Be objective and specific.""",

    'simple': """In 2-3 sentences, describe:
- What is the main subject?
- What are the key visual features?
- What is the setting or context?"""
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
