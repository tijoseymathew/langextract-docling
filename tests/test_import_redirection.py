"""Test to verify that langextract imports are redirected to langextract_docling."""

def test_import_redirection():
    """Test that importing langextract actually gives us langextract_docling."""
    import langextract
    import langextract_docling
    
    # They should be the same module
    assert langextract == langextract_docling
    
    # The extract function should be the one from langextract_docling
    assert langextract.extract == langextract_docling.extract
    assert langextract.extract.__name__ == "extract"
    
    # Let's check that the function has the right signature by checking if it has 
    # parameters that are specific to langextract_docling
    import inspect
    sig = inspect.signature(langextract.extract)
    params = list(sig.parameters.keys())
    
    # Check that it has at least the basic parameters from the original function
    assert 'text_or_documents' in params or 'text_or_documents' in params
    assert 'prompt_description' in params
    
    # Check that it has some parameters specific to the enhanced version
    # like the pdf processing capability
    assert 'fetch_urls' in params  # This is a keyword-only parameter in the enhanced version