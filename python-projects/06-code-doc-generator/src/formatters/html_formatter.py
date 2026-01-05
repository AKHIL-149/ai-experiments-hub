"""HTML documentation formatter with Bootstrap styling"""
from pathlib import Path
from typing import List
from datetime import datetime
import html
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from parsers.models import ParsedModule, FunctionInfo, ClassInfo, ParameterInfo
from formatters.base_formatter import BaseFormatter


class HTMLFormatter(BaseFormatter):
    """
    Generates HTML documentation with Bootstrap 5 styling.

    Features:
    - Responsive Bootstrap 5 design
    - Syntax highlighting with Prism.js
    - Collapsible sections
    - Client-side search
    - Table of contents with smooth scrolling
    """

    def __init__(self, theme: str = "light", include_search: bool = True):
        """
        Initialize HTML formatter.

        Args:
            theme: Color theme ('light' or 'dark')
            include_search: Whether to include search functionality
        """
        self.theme = theme
        self.include_search = include_search

    def supports_batch(self) -> bool:
        """HTML formatter supports batch processing"""
        return True

    def format(self, parsed_module: ParsedModule, output_path: str) -> str:
        """Generate HTML documentation for single module"""
        content = self._generate_html([parsed_module], single_file=True)
        return self._safe_write(output_path, content)

    def format_batch(self, parsed_modules: List[ParsedModule], output_path: str) -> str:
        """Generate combined HTML documentation for multiple modules"""
        if not parsed_modules:
            raise ValueError("No modules provided for batch formatting")

        content = self._generate_html(parsed_modules, single_file=False)
        return self._safe_write(output_path, content)

    def _generate_html(self, modules: List[ParsedModule], single_file: bool) -> str:
        """Generate complete HTML document"""
        title = Path(modules[0].file_path).name if single_file else "Project Documentation"

        html_parts = [
            self._html_header(title),
            '<body data-bs-spy="scroll" data-bs-target="#toc-nav">',
            self._navbar(title),
            '<div class="container-fluid">',
            '<div class="row">',
        ]

        # Sidebar with TOC
        html_parts.append(self._sidebar_toc(modules))

        # Main content
        html_parts.append('<main class="col-md-9 ms-sm-auto col-lg-10 px-md-4">')

        for i, module in enumerate(modules):
            if i > 0:
                html_parts.append('<hr class="my-5">')
            html_parts.append(self._format_module(module))

        html_parts.extend([
            '</main>',
            '</div>',
            '</div>',
            self._html_footer(),
            '</body>',
            '</html>'
        ])

        return "\n".join(html_parts)

    def _html_header(self, title: str) -> str:
        """Generate HTML head section"""
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{html.escape(title)}</title>

    <!-- Bootstrap 5 CSS -->
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">

    <!-- Prism.js for syntax highlighting -->
    <link href="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/themes/prism-okaidia.min.css" rel="stylesheet">

    <!-- Bootstrap Icons -->
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.0/font/bootstrap-icons.css">

    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            padding-top: 56px;
        }}

        .sidebar {{
            position: fixed;
            top: 56px;
            bottom: 0;
            left: 0;
            z-index: 100;
            padding: 48px 0 0;
            box-shadow: inset -1px 0 0 rgba(0, 0, 0, .1);
            overflow-y: auto;
        }}

        .sidebar-sticky {{
            position: relative;
            top: 0;
            height: calc(100vh - 48px);
            padding-top: .5rem;
            overflow-x: hidden;
            overflow-y: auto;
        }}

        .sidebar .nav-link {{
            font-size: 0.9rem;
            font-weight: 400;
            color: #333;
        }}

        .sidebar .nav-link:hover {{
            color: #0d6efd;
        }}

        .sidebar .nav-link.active {{
            color: #0d6efd;
            font-weight: 600;
        }}

        .code-signature {{
            background: #f8f9fa;
            border-left: 4px solid #0d6efd;
            padding: 1rem;
            margin: 1rem 0;
            font-family: 'Courier New', monospace;
            overflow-x: auto;
        }}

        .badge-complexity {{
            font-size: 0.75rem;
        }}

        .ai-explanation {{
            background: #e7f3ff;
            border-left: 4px solid #0d6efd;
            padding: 1rem;
            margin: 1rem 0;
        }}

        .ai-explanation::before {{
            content: "\\f4a4";
            font-family: "Bootstrap Icons";
            margin-right: 0.5rem;
            color: #0d6efd;
        }}

        .param-table {{
            font-size: 0.9rem;
        }}

        main {{
            padding-top: 20px;
        }}

        .search-box {{
            position: sticky;
            top: 56px;
            background: white;
            padding: 1rem;
            border-bottom: 1px solid #dee2e6;
            z-index: 99;
        }}
    </style>
</head>"""

    def _navbar(self, title: str) -> str:
        """Generate navigation bar"""
        search_bar = ""
        if self.include_search:
            search_bar = '''
            <input class="form-control me-2" type="search" id="searchInput"
                   placeholder="Search documentation..." aria-label="Search">
            '''

        return f'''
<nav class="navbar navbar-dark bg-dark fixed-top">
    <div class="container-fluid">
        <a class="navbar-brand" href="#">
            <i class="bi bi-book"></i> {html.escape(title)}
        </a>
        <div class="d-flex">
            {search_bar}
            <span class="navbar-text">
                <small>Generated {datetime.now().strftime("%Y-%m-%d %H:%M")}</small>
            </span>
        </div>
    </div>
</nav>'''

    def _sidebar_toc(self, modules: List[ParsedModule]) -> str:
        """Generate sidebar table of contents"""
        toc_items = []

        for module in modules:
            module_name = Path(module.file_path).name
            module_id = self._make_id(module_name)

            toc_items.append(f'''
            <li class="nav-item">
                <a class="nav-link" href="#{module_id}">
                    <i class="bi bi-file-code"></i> {html.escape(module_name)}
                </a>
            </li>''')

            # Add functions and classes
            if module.functions:
                for func in module.functions[:5]:  # Limit to first 5
                    func_id = self._make_id(f"{module_name}-{func.name}")
                    toc_items.append(f'''
                <li class="nav-item ms-3">
                    <a class="nav-link text-muted" href="#{func_id}">
                        <i class="bi bi-box"></i> {html.escape(func.name)}()
                    </a>
                </li>''')

            if module.classes:
                for cls in module.classes[:5]:  # Limit to first 5
                    cls_id = self._make_id(f"{module_name}-{cls.name}")
                    toc_items.append(f'''
                <li class="nav-item ms-3">
                    <a class="nav-link text-muted" href="#{cls_id}">
                        <i class="bi bi-box2"></i> {html.escape(cls.name)}
                    </a>
                </li>''')

        return f'''
<nav id="toc-nav" class="col-md-3 col-lg-2 d-md-block bg-light sidebar">
    <div class="sidebar-sticky pt-3">
        <ul class="nav flex-column">
            {"".join(toc_items)}
        </ul>
    </div>
</nav>'''

    def _format_module(self, module: ParsedModule) -> str:
        """Format module documentation"""
        module_name = Path(module.file_path).name
        module_id = self._make_id(module_name)

        parts = [f'<section id="{module_id}" class="mb-5">']

        # Module header
        parts.append(f'''
        <h1 class="display-4">
            <i class="bi bi-file-code"></i> {html.escape(module_name)}
            <span class="badge bg-secondary fs-6">{html.escape(module.language)}</span>
        </h1>
        <p class="text-muted"><code>{html.escape(module.file_path)}</code></p>
        ''')

        # AI summary or docstring
        if module.ai_summary:
            parts.append(f'<div class="ai-explanation">{html.escape(module.ai_summary)}</div>')
        elif module.module_docstring:
            parts.append(f'<div class="alert alert-info">{html.escape(module.module_docstring)}</div>')

        # Statistics
        parts.append(f'''
        <div class="row mb-4">
            <div class="col-md-4">
                <div class="card">
                    <div class="card-body">
                        <h5 class="card-title"><i class="bi bi-box"></i> Functions</h5>
                        <p class="card-text display-6">{len(module.functions)}</p>
                    </div>
                </div>
            </div>
            <div class="col-md-4">
                <div class="card">
                    <div class="card-body">
                        <h5 class="card-title"><i class="bi bi-box2"></i> Classes</h5>
                        <p class="card-text display-6">{len(module.classes)}</p>
                    </div>
                </div>
            </div>
            <div class="col-md-4">
                <div class="card">
                    <div class="card-body">
                        <h5 class="card-title"><i class="bi bi-arrow-down-up"></i> Imports</h5>
                        <p class="card-text display-6">{len(module.imports)}</p>
                    </div>
                </div>
            </div>
        </div>
        ''')

        # Functions section
        if module.functions:
            parts.append('<h2 class="mt-5 mb-4"><i class="bi bi-box"></i> Functions</h2>')
            for func in module.functions:
                parts.append(self._format_function(func, module_name))

        # Classes section
        if module.classes:
            parts.append('<h2 class="mt-5 mb-4"><i class="bi bi-box2"></i> Classes</h2>')
            for cls in module.classes:
                parts.append(self._format_class(cls, module_name))

        parts.append('</section>')
        return "\n".join(parts)

    def _format_function(self, func: FunctionInfo, module_name: str) -> str:
        """Format function documentation"""
        func_id = self._make_id(f"{module_name}-{func.name}")

        # Build signature
        params = ", ".join([self._format_param_sig(p) for p in func.parameters])
        return_type = f" -> {html.escape(func.return_type)}" if func.return_type else ""
        async_marker = "async " if func.is_async else ""

        parts = [f'<div id="{func_id}" class="card mb-4">']
        parts.append('<div class="card-body">')

        # Function header
        parts.append(f'''
        <h4 class="card-title">
            <code>{async_marker}{html.escape(func.name)}({params}){return_type}</code>
            <small class="text-muted">Line {func.line_number}</small>
        </h4>
        ''')

        # Decorators
        if func.decorators:
            badges = " ".join([f'<span class="badge bg-info">{html.escape(d)}</span>' for d in func.decorators])
            parts.append(f'<div class="mb-2">{badges}</div>')

        # Complexity
        if func.complexity:
            color = "success" if func.complexity == "Simple" else "warning" if func.complexity == "Medium" else "danger"
            parts.append(f'<span class="badge bg-{color} badge-complexity">Complexity: {func.complexity}</span>')

        # AI explanation or docstring
        if func.ai_explanation:
            parts.append(f'<div class="ai-explanation mt-3">{html.escape(func.ai_explanation)}</div>')
        elif func.docstring:
            parts.append(f'<div class="alert alert-secondary mt-3">{html.escape(func.docstring)}</div>')

        # Parameters table
        if func.parameters:
            parts.append(self._format_parameters_table(func.parameters))

        parts.append('</div></div>')
        return "\n".join(parts)

    def _format_class(self, cls: ClassInfo, module_name: str) -> str:
        """Format class documentation"""
        cls_id = self._make_id(f"{module_name}-{cls.name}")

        inheritance = ""
        if cls.base_classes:
            bases = ", ".join([html.escape(b) for b in cls.base_classes])
            inheritance = f'<small class="text-muted">extends {bases}</small>'

        parts = [f'<div id="{cls_id}" class="card mb-4 border-primary">']
        parts.append('<div class="card-body">')

        # Class header
        parts.append(f'''
        <h4 class="card-title">
            <i class="bi bi-box2"></i> <code>{html.escape(cls.name)}</code>
            {inheritance}
            <small class="text-muted">Line {cls.line_number}</small>
        </h4>
        ''')

        # Decorators (for Java interfaces/enums)
        if cls.decorators:
            badges = " ".join([f'<span class="badge bg-primary">{html.escape(d)}</span>' for d in cls.decorators])
            parts.append(f'<div class="mb-2">{badges}</div>')

        # AI explanation or docstring
        if cls.ai_explanation:
            parts.append(f'<div class="ai-explanation mt-3">{html.escape(cls.ai_explanation)}</div>')
        elif cls.docstring:
            parts.append(f'<div class="alert alert-secondary mt-3">{html.escape(cls.docstring)}</div>')

        # Attributes
        if cls.attributes:
            parts.append('<h5 class="mt-3">Attributes</h5>')
            parts.append('<ul class="list-unstyled">')
            for attr in cls.attributes[:10]:
                attr_type = attr.get('type', '')
                type_badge = f'<span class="badge bg-light text-dark">{html.escape(attr_type)}</span>' if attr_type else ''
                parts.append(f'<li><code>{html.escape(attr["name"])}</code> {type_badge}</li>')
            if len(cls.attributes) > 10:
                parts.append(f'<li class="text-muted">... and {len(cls.attributes) - 10} more</li>')
            parts.append('</ul>')

        # Methods (collapsed by default)
        if cls.methods:
            parts.append('<h5 class="mt-3">Methods</h5>')
            parts.append('<div class="accordion" id="methods-accordion">')
            for i, method in enumerate(cls.methods):
                parts.append(self._format_method_accordion(method, cls_id, i))
            parts.append('</div>')

        parts.append('</div></div>')
        return "\n".join(parts)

    def _format_method_accordion(self, method: FunctionInfo, cls_id: str, index: int) -> str:
        """Format method in accordion"""
        method_id = f"{cls_id}-method-{index}"
        params = ", ".join([p.name for p in method.parameters])

        return f'''
        <div class="accordion-item">
            <h2 class="accordion-header" id="{method_id}-header">
                <button class="accordion-button collapsed" type="button"
                        data-bs-toggle="collapse" data-bs-target="#{method_id}"
                        aria-expanded="false" aria-controls="{method_id}">
                    <code>{html.escape(method.name)}({params})</code>
                </button>
            </h2>
            <div id="{method_id}" class="accordion-collapse collapse"
                 aria-labelledby="{method_id}-header">
                <div class="accordion-body">
                    {html.escape(method.ai_explanation or method.docstring or "No description available")}
                </div>
            </div>
        </div>'''

    def _format_parameters_table(self, parameters: List[ParameterInfo]) -> str:
        """Format parameters as HTML table"""
        rows = []
        for param in parameters:
            type_badge = f'<code>{html.escape(param.type_hint)}</code>' if param.type_hint else '<span class="text-muted">Any</span>'
            default = f'<code>{html.escape(str(param.default_value))}</code>' if param.default_value else '<span class="text-muted">Required</span>'
            desc = html.escape(param.description) if param.description else '<span class="text-muted">-</span>'

            rows.append(f'''
            <tr>
                <td><strong><code>{html.escape(param.name)}</code></strong></td>
                <td>{type_badge}</td>
                <td>{default}</td>
                <td>{desc}</td>
            </tr>''')

        return f'''
        <h5 class="mt-3">Parameters</h5>
        <table class="table table-sm table-hover param-table">
            <thead>
                <tr>
                    <th>Name</th>
                    <th>Type</th>
                    <th>Default</th>
                    <th>Description</th>
                </tr>
            </thead>
            <tbody>
                {"".join(rows)}
            </tbody>
        </table>'''

    def _format_param_sig(self, param: ParameterInfo) -> str:
        """Format parameter for signature"""
        parts = [html.escape(param.name)]
        if param.type_hint:
            parts.append(f": {html.escape(param.type_hint)}")
        if param.default_value:
            parts.append(f" = {html.escape(str(param.default_value))}")
        return "".join(parts)

    def _html_footer(self) -> str:
        """Generate HTML footer with scripts"""
        search_script = ""
        if self.include_search:
            search_script = '''
            <script>
                // Simple client-side search
                document.getElementById('searchInput').addEventListener('input', function(e) {
                    const searchTerm = e.target.value.toLowerCase();
                    const cards = document.querySelectorAll('.card');

                    cards.forEach(card => {
                        const text = card.textContent.toLowerCase();
                        if (text.includes(searchTerm)) {
                            card.style.display = '';
                        } else {
                            card.style.display = 'none';
                        }
                    });
                });
            </script>'''

        return f'''
    <!-- Bootstrap 5 JS -->
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>

    <!-- Prism.js for syntax highlighting -->
    <script src="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/prism.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/components/prism-python.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/components/prism-javascript.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/components/prism-java.min.js"></script>

    {search_script}

    <script>
        // Smooth scroll for anchor links
        document.querySelectorAll('a[href^="#"]').forEach(anchor => {{
            anchor.addEventListener('click', function (e) {{
                e.preventDefault();
                const target = document.querySelector(this.getAttribute('href'));
                if (target) {{
                    target.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
                }}
            }});
        }});
    </script>'''

    def _make_id(self, text: str) -> str:
        """Create HTML-safe ID from text"""
        return text.lower().replace(' ', '-').replace('.', '-').replace('/', '-')
