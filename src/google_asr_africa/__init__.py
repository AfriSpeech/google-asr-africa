"""google_asr_africa: transcribe African-language speech with Google's free ASR.

The free `recognize_google` endpoint is a bit of a black box: it silently
folds ~everything into English when a language isn't actually supported. This
package ships a *verified* catalog of African languages that really transcribe
in their own orthography (probed against real audio), plus a resumable batched
transcriber and a probe to test candidates you want to add.
"""

from .transcribe import (
    STATUS_ERR,
    STATUS_OK,
    STATUS_REQ,
    STATUS_UNK,
    Result,
    transcribe_one,
    Transcripts,
    transcribe_folder,
)
from .languages import catalog, support_code, supported, supported_codes

__version__ = "0.1.1"

__all__ = [
    "catalog",
    "supported",
    "supported_codes",
    "support_code",
    "transcribe_one",
    "transcribe_folder",
    "Transcripts",
    "Result",
    "STATUS_OK",
    "STATUS_UNK",
    "STATUS_REQ",
    "STATUS_ERR",
    "__version__",
]