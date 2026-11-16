"""gaeil-tidy: turn rough, mixed-style notes into runnable Gaeil code."""

from gaeil_tidy.tidy import TidyResult, tidy
from gaeil_tidy.translate import compile_gaeil, translate

__version__ = "0.1.0"
__all__ = ["TidyResult", "tidy", "translate", "compile_gaeil", "__version__"]
