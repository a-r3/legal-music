"""Legal music source adapters."""
from .archive import InternetArchiveSource
from .bandcamp import BandcampSource
from .ccmixter import CCMixterSource
from .fma import FreeMusicArchiveSource
from .incompetech import IncompetechSource
from .jamendo import JamendoSource
from .pixabay import PixabaySource
from .ytdlp_source import YouTubeAudioLibrarySource

__all__ = [
    "InternetArchiveSource",
    "BandcampSource",
    "FreeMusicArchiveSource",
    "JamendoSource",
    "PixabaySource",
    "CCMixterSource",
    "IncompetechSource",
    "YouTubeAudioLibrarySource",
]
