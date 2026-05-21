def test_engine_libraries_importable():
    import astronomy  # noqa: F401  (the cosinekitty package imports as `astronomy`, not astronomy_engine)
    import lunar_python  # noqa: F401
    import anthropic  # noqa: F401
