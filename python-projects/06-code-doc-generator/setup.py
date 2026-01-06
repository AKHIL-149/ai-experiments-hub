#!/usr/bin/env python3
"""Setup configuration for code-doc-generator package"""
from setuptools import setup, find_packages
from pathlib import Path

# Read long description from README
readme_file = Path(__file__).parent / "README.md"
long_description = readme_file.read_text(encoding="utf-8") if readme_file.exists() else ""

# Read version from src/__init__.py
version = {}
version_file = Path(__file__).parent / "src" / "__init__.py"
with open(version_file, encoding="utf-8") as f:
    for line in f:
        if line.startswith("__version__"):
            exec(line, version)
            break

setup(
    name="code-doc-generator",
    version=version.get("__version__", "0.6.5.4"),
    author="AI Experiments Hub",
    description="AI-powered code documentation generator with multi-language support",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/AKHIL-149/ai-experiments-hub",
    project_urls={
        "Bug Tracker": "https://github.com/AKHIL-149/ai-experiments-hub/issues",
        "Source Code": "https://github.com/AKHIL-149/ai-experiments-hub/tree/main/python-projects/06-code-doc-generator",
    },
    packages=["src"] + ["src." + pkg for pkg in find_packages("src")],
    package_dir={"src": "src"},
    include_package_data=True,
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Documentation",
        "Topic :: Software Development :: Code Generators",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
    python_requires=">=3.9",

    # Core dependencies (minimal)
    install_requires=[
        "javalang>=0.13.0",
        "python-dotenv>=1.0.0",
    ],

    # Optional dependencies
    extras_require={
        # AI features
        "ai": [
            "anthropic>=0.18.0",
            "openai>=1.12.0",
        ],

        # Web interface
        "web": [
            "fastapi>=0.109.0",
            "uvicorn>=0.27.0",
            "jinja2>=3.1.0",
            "python-multipart>=0.0.9",
        ],

        # Utilities
        "utils": [
            "tqdm>=4.66.0",
        ],

        # Development dependencies
        "dev": [
            "pytest>=7.4.0",
            "pytest-cov>=4.1.0",
            "black>=23.0.0",
            "flake8>=6.0.0",
        ],

        # All optional dependencies
        "all": [
            "anthropic>=0.18.0",
            "openai>=1.12.0",
            "fastapi>=0.109.0",
            "uvicorn>=0.27.0",
            "jinja2>=3.1.0",
            "python-multipart>=0.0.9",
            "tqdm>=4.66.0",
        ],
    },

    # Console script entry points
    entry_points={
        "console_scripts": [
            "doc-gen=doc_gen:main",
            "code-doc-generator=doc_gen:main",
        ],
    },

    # Package metadata
    keywords=[
        "documentation",
        "code-analysis",
        "ast",
        "llm",
        "ai",
        "docstring",
        "markdown",
        "python",
        "javascript",
        "java",
    ],
    license="MIT",
    zip_safe=False,
)
