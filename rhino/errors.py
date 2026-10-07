"""One exception type for every 'the input was wrong' case, so front ends can show it verbatim."""


class Fail(Exception):
    """A validation or consistency failure. The message is written for the person at the keyboard."""
