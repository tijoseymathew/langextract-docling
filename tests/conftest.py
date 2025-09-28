"""Configuration for pytest that makes tests use langextract_docling instead of langextract."""

import importlib
import sys
from types import ModuleType


class LangextractMock(ModuleType):
  """A module that behaves like langextract but uses langextract_docling's extract function."""

  def __init__(self, original_module, docling_module):
    super().__init__(original_module.__name__)
    self._original_module = original_module
    self._docling_module = docling_module

    # Copy module attributes from the original module
    if hasattr(original_module, '__path__'):
      self.__path__ = original_module.__path__
    if hasattr(original_module, '__file__'):
      self.__file__ = original_module.__file__
    if hasattr(original_module, '__package__'):
      self.__package__ = original_module.__package__
    if hasattr(original_module, '__loader__'):
      self.__loader__ = original_module.__loader__

  def __getattr__(self, name):
    # Handle the extract function specially - use the one from langextract_docling
    if name == 'extract':
      return self._docling_module.extract
    # For all other attributes, delegate to the original langextract module
    return getattr(self._original_module, name)


def pytest_configure(config):
  """Configure pytest with custom settings."""
  # Import both the original langextract and langextract_docling
  original_langextract = importlib.import_module('langextract')
  import langextract_docling

  # Create a mock langextract module that uses langextract_docling's extract
  # but preserves all other functionality from the original langextract
  mock_langextract = LangextractMock(original_langextract, langextract_docling)

  # Replace the 'langextract' module in sys.modules with our mock
  sys.modules['langextract'] = mock_langextract
