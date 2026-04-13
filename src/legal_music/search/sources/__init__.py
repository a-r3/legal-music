"""Legal music source adapters."""
from .archive import InternetArchiveSource
from .bandcamp import BandcampSource
from .fma import FreeMusicArchiveSource
from .jamendo import JamendoSource
from .pixabay import PixabaySource

__all__ = [
    "InternetArchiveSource",
    "BandcampSource",
    "FreeMusicArchiveSource",
    "JamendoSource",
    "PixabaySource",
]
