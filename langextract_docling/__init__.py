"""Wrapper for langextract library.

This module wraps the langextract.extract method while passing through all other exports unchanged.
"""

from langextract import *

from langextract import extract as _original_extract


def extract(*args, **kwargs):
    """Wrapper around langextract.extract that adds a print statement."""
    print("Extracting document...")
    return _original_extract(*args, **kwargs)
