"""Email response templates for different contexts."""

TEMPLATES = {
    "professional": {
        "description": "Professional business response",
        "prompt": """Generate a professional email response based on the following context.

Original Email:
{email_body}

Instructions:
- Maintain a professional and courteous tone
- Address all points mentioned in the original email
- Be concise and clear
- Include appropriate greeting and closing
- {custom_instructions}

Generate the email response:"""
    },

    "casual": {
        "description": "Casual/friendly response",
        "prompt": """Generate a casual, friendly email response based on the following context.

Original Email:
{email_body}

Instructions:
- Use a warm, friendly tone
- Address the main points naturally
- Keep it conversational but respectful
- {custom_instructions}

Generate the email response:"""
    },

    "decline": {
        "description": "Politely decline a request",
        "prompt": """Generate a polite email declining the request in the original email.

Original Email:
{email_body}

Instructions:
- Be polite and respectful
- Clearly but gently decline the request
- Provide a brief reason if appropriate
- Thank them for their understanding
- {custom_instructions}

Generate the email response:"""
    },

    "accept": {
        "description": "Accept an invitation or request",
        "prompt": """Generate an email accepting the invitation or request.

Original Email:
{email_body}

Instructions:
- Express enthusiasm and appreciation
- Confirm acceptance clearly
- Address any logistics mentioned
- Professional yet warm tone
- {custom_instructions}

Generate the email response:"""
    },

    "follow_up": {
        "description": "Follow up on a previous email",
        "prompt": """Generate a follow-up email based on the context.

Original Email:
{email_body}

Instructions:
- Politely remind about the previous communication
- Restate the key points or request
- Maintain professional courtesy
- Express understanding of their busy schedule
- {custom_instructions}

Generate the email response:"""
    },

    "thank_you": {
        "description": "Thank you response",
        "prompt": """Generate a thank you email based on the context.

Original Email:
{email_body}

Instructions:
- Express genuine gratitude
- Be specific about what you're thanking them for
- Keep it warm and sincere
- Appropriate length (not too brief, not too long)
- {custom_instructions}

Generate the email response:"""
    },

    "inquiry_response": {
        "description": "Respond to an inquiry",
        "prompt": """Generate a response to an inquiry or question.

Original Email:
{email_body}

Instructions:
- Directly address the inquiry
- Provide helpful information
- Be clear and organized
- Offer to provide additional help if needed
- {custom_instructions}

Generate the email response:"""
    },

    "apology": {
        "description": "Apologize for an issue",
        "prompt": """Generate an email apologizing for the issue mentioned.

Original Email:
{email_body}

Instructions:
- Acknowledge the issue sincerely
- Take appropriate responsibility
- Explain steps to resolve (if applicable)
- Express commitment to preventing recurrence
- {custom_instructions}

Generate the email response:"""
    }
}


def get_template(template_name: str) -> dict:
    """Get email template by name."""
    if template_name not in TEMPLATES:
        available = ", ".join(TEMPLATES.keys())
        raise ValueError(f"Unknown template '{template_name}'. Available: {available}")
    return TEMPLATES[template_name]


def list_templates() -> list:
    """List all available templates with descriptions."""
    return [
        {
            "name": name,
            "description": template["description"]
        }
        for name, template in TEMPLATES.items()
    ]


def build_prompt(template_name: str, email_body: str, custom_instructions: str = "") -> str:
    """Build a complete prompt from template."""
    template = get_template(template_name)

    if not custom_instructions:
        custom_instructions = "No additional instructions"

    return template["prompt"].format(
        email_body=email_body.strip(),
        custom_instructions=custom_instructions
    )
