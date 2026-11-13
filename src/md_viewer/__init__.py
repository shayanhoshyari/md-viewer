"""Serve local markdown and source files as browsable pages.

The public API is what this module exports in `__all__`; every other module is internal.
"""

from md_viewer.links import Link, check_links, link_problem, links_of

__all__ = ["Link", "check_links", "link_problem", "links_of"]
