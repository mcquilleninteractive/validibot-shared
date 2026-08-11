"""Repository-wide pytest configuration for bounded property tests.

The default Hypothesis profile remains suitable for interactive development.
CI explicitly selects the smaller ``ci`` profile so pull-request cost stays
predictable while Hypothesis still records and shrinks every failure.
"""

from __future__ import annotations

import os
from datetime import timedelta

from hypothesis import settings

settings.register_profile(
    "ci",
    max_examples=75,
    deadline=timedelta(milliseconds=500),
)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "default"))
