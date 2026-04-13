"""legal-music: find and download music from permitted sources only."""
from .cli import main
from .constants import VERSION

__version__ = VERSION
__all__ = ["main", "__version__", "VERSION"]
