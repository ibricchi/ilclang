from __future__ import annotations

from dataclasses import dataclass

@dataclass(frozen=True)
class CallSite:
    """
    A call site in the call graph
    """

    caller: str
    callee: str
    loc: str

    def __str__(self) -> str:
        return f"{self.caller} -> {self.callee} @ {self.loc}"