# Configuration file for the Sphinx documentation builder.

import os
import sys

# The Python runtime of resident programs, whose docstrings the API
# reference of its classes is built from (sphinx.ext.autodoc). Its
# modules import only the standard library.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'engine')))

# -- Project information

project = 'DeBasher'
copyright = '2024, Daniel Ortiz-Martínez'
author = 'Daniel Ortiz-Martínez'

release = '0.1'
version = '0.1.0'

# -- General configuration

extensions = [
    'sphinx.ext.duration',
    'sphinx.ext.doctest',
    'sphinx.ext.autodoc',
    'sphinx.ext.autosummary',
    'sphinx.ext.intersphinx',
    'myst_parser'
]

intersphinx_mapping = {
    'python': ('https://docs.python.org/3/', None),
    'sphinx': ('https://www.sphinx-doc.org/en/master/', None),
}
intersphinx_disabled_domains = ['std']

templates_path = ['_templates']

# The *_doc.md files that generate_api_files.sh writes are only included
# into the pages of the API, never built as pages of their own.
exclude_patterns = ['*_doc.md']

html_static_path = ['_static']

# -- Options for HTML output

html_theme = 'sphinx_rtd_theme'

html_css_files = [
    'css/styles.css',
]

# -- Options for EPUB output
epub_show_urls = 'footnote'
