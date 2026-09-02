project = "MacBlend"
copyright = "2024-2026, Manuel Houben"
author = "Manuel Houben"
release = "2.2.1"

extensions = [
    "sphinx.ext.mathjax",
    "myst_parser",
]

source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}

templates_path = ["templates"]
exclude_patterns = []

html_theme = "furo"
html_title = project
html_logo = "static/icon.png"
html_favicon = "static/icon.png"
html_static_path = ["static"]
html_css_files = ["theme_overrides.css"]
html_theme_options = {
    "source_repository": "https://github.com/ManuelHouben/macblend/",
    "source_branch": "main",
    "source_directory": "documentation/pages/",
    "navigation_with_keys": True,
    "light_css_variables": {
        "color-brand-primary": "#265787",
        "color-brand-content": "#265787",
    },
    "dark_css_variables": {
        "color-brand-primary": "#8cb4ff",
        "color-brand-content": "#8cb4ff",
    },
}

myst_heading_anchors = 3
myst_enable_extensions = [
    "colon_fence",
    "dollarmath",
]
