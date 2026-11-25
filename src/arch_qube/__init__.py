"""Architecture Qube — AI-powered Architecture Quality Gate."""
__version__ = "0.5.7"


def package_version() -> str:
    """The installed distribution's version, falling back to ``__version__`` when running from a
    source tree that was never installed. release-please bumps pyproject.toml and ``__version__``
    together, so both agree; the CLI, JSON and Markdown reports all read it from here (until
    0.5.7 each hardcoded "0.1.0")."""
    try:
        from importlib.metadata import PackageNotFoundError, version
        try:
            return version("arch-qube")
        except PackageNotFoundError:
            return __version__
    except ImportError:  # pragma: no cover
        return __version__
