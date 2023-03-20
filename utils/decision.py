from __future__ import annotations

from dataclasses import dataclass

from pyllinliner.inlinercontroller import CallSite


@dataclass()
class Decision:
    """
    Wrapper to hold decision state

    modified is an extra value we can set to inform the DecisionSet
    class not to change this decision

    for unmodified: (caller -> callee @ location : taken?)
    for modified: [caller -> callee @ location : taken?]

    """

    call_site: CallSite
    inlined: bool
    modified: bool

    def short_hand(self) -> str:
        taken_str = "T" if self.inlined else "F"
        if self.modified:
            return f"[{taken_str}]"
        else:
            return f"({taken_str})"

    def __str__(self) -> str:
        taken_str = "T" if self.inlined else "F"
        output = "[" if self.modified else "("
        output += f"{self.call_site} : {taken_str}"
        output += "]" if self.modified else ")"
        return output

    def clone(self) -> Decision:
        return Decision(self.call_site, self.inlined, self.modified)


# never let this type be instanciated directly
class DecisionSet:
    """
    A base class for sets of decisions

    A set of decisions must be able to generate a new set of decisions
    from the current set of decisions by implmenting the get_next_decision_set
    or return None if there are no new decisions to be made
    """

    decisions: list[Decision]

    def __init__(self) -> None:
        self.decisions: list[Decision] = []

    def reset(self) -> None:
        self.decisions = []

    def clone(self) -> DecisionSet:
        new_decisions = DecisionSet()
        for d in self.decisions:
            new_decisions.decisions.append(d.clone())
        return new_decisions

    def clone_only_fixed(self) -> DecisionSet:
        new_decisions = DecisionSet()
        for d in self.decisions:
            if d.modified:
                new_decisions.decisions.append(d.clone())
        return new_decisions

    def add_decision(
        self, call_site: CallSite, inlined: bool, fixed: bool = False
    ) -> None:
        self.decisions.append(Decision(call_site, inlined, fixed))

    def short_hand(self) -> str:
        return "".join(d.short_hand() for d in self.decisions)

    def decision_for(self, call_site: CallSite) -> Decision | None:
        for d in self.decisions:
            if d.call_site == call_site:
                return d
        return None

    def __str__(self) -> str:
        output = ""
        # output = "{\n"
        for d in self.decisions:
            output += f"{d}\n"
        # output += "}"
        return output
