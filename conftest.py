import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:  # optional: doc tests over README/docs code blocks
    from sybil import Sybil
    from sybil.parsers.markdown import PythonCodeBlockParser

    pytest_collect_file = Sybil(
        parsers=[PythonCodeBlockParser()],
        patterns=["docs/*.md"],
    ).pytest()
except ImportError:
    pass
