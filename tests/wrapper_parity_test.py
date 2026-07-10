"""Tests that the wrapper extract() mirrors the upstream langextract signature."""

import importlib
import inspect

import langextract_docling

# Parameters the wrapper adds on top of the upstream signature. Extras must be
# keyword-only so they can never collide positionally with upstream parameters.
WRAPPER_ONLY_PARAMS = frozenset()


def _upstream_extract():
  """Returns the original langextract.extract, bypassing conftest's mock."""
  extraction = importlib.import_module("langextract.extraction")
  return extraction.extract


def test_wrapper_has_all_upstream_parameters():
  upstream = inspect.signature(_upstream_extract()).parameters
  wrapper = inspect.signature(langextract_docling.extract).parameters

  missing = set(upstream) - set(wrapper)
  assert (
      not missing
  ), f"wrapper is missing upstream parameters: {sorted(missing)}"


def test_wrapper_defaults_and_kinds_match_upstream():
  upstream = inspect.signature(_upstream_extract()).parameters
  wrapper = inspect.signature(langextract_docling.extract).parameters

  mismatched = {
      name: (wrapper[name].default, param.default)
      for name, param in upstream.items()
      if wrapper[name].default != param.default
  }
  assert (
      not mismatched
  ), f"wrapper defaults diverge from upstream (wrapper, upstream): {mismatched}"

  wrong_kind = {
      name: (wrapper[name].kind, param.kind)
      for name, param in upstream.items()
      if wrapper[name].kind != param.kind
  }
  assert (
      not wrong_kind
  ), f"wrapper parameter kinds diverge from upstream: {wrong_kind}"


def test_wrapper_extra_parameters_are_known_and_keyword_only():
  upstream = inspect.signature(_upstream_extract()).parameters
  wrapper = inspect.signature(langextract_docling.extract).parameters

  extras = set(wrapper) - set(upstream)
  assert extras <= WRAPPER_ONLY_PARAMS, (
      "unexpected wrapper-only parameters:"
      f" {sorted(extras - WRAPPER_ONLY_PARAMS)}"
  )
  not_kw_only = [
      name
      for name in extras
      if wrapper[name].kind is not inspect.Parameter.KEYWORD_ONLY
  ]
  assert (
      not not_kw_only
  ), f"wrapper-only parameters must be keyword-only: {not_kw_only}"
