"""Actionable errors that the review app can display without a traceback."""


class ReviewError(ValueError):
    """Configuration or local dataset input cannot be used for review."""
