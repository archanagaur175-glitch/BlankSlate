def test_package_imports() -> None:
    import blankslate  # noqa: F401

    assert blankslate.__version__


def test_placeholder() -> None:
    assert (1 + 1) == 2
