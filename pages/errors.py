"""Exceptions the library raises. conftest.py's report hook keys on
SystemBadStateError to mark a failure as a SYSTEM failure (unit unhealthy,
run lost) rather than a test failure."""


class SystemBadStateError(AssertionError):
    """The unit itself is unhealthy (controller/unit offline, recovery
    mode, a disconnected testbed, a datapath in ERROR, or a run whose
    results were lost), as opposed to a test finding wrong behaviour on a
    healthy unit."""


class PortsBusyError(RuntimeError):
    """Ports this test needs are held by someone else's testbed. The
    library never releases them; the `traffic_engine` fixture turns this
    into a skip."""
