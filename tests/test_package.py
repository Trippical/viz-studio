def test_version_is_a_string():
    import viz
    assert isinstance(viz.__version__, str)
    assert viz.__version__ == "0.1.0"
