from __future__ import annotations

from dataclasses import dataclass

from pyllinliner.inlinercontroller import CallSite, InliningDecision


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

    def clone_only_modified(self) -> DecisionSet:
        new_decisions = DecisionSet()
        for d in self.decisions:
            if d.modified:
                new_decisions.decisions.append(d.clone())
        return new_decisions

    def add_decision(
        self, call_site: CallSite, inlined: bool, fixed: bool = False
    ) -> None:
        self.decisions.append(Decision(call_site, inlined, fixed))

    def replace_decision(
        self,
        decision: Decision,
        call_site: CallSite,
        inlined: bool,
        fixed: bool = False,
    ) -> None:
        # get index of decision to replace
        idx = self.decisions.index(decision)
        assert idx is not None, f"Could not find decision {decision}"
        self.decisions[idx] = Decision(call_site, inlined, fixed)

    def short_hand(self) -> str:
        return "".join(d.short_hand() for d in self.decisions)

    def decision_for(self, call_site: CallSite) -> Decision | None:
        for d in self.decisions:
            if d.call_site == call_site:
                return d
        return None

    def decision_from_location(self, location: str) -> Decision | None:
        for d in self.decisions:
            if d.call_site.location == location:
                return d
        return None

    def remove_implicit_duplicates(self) -> None:
        seen_locations: dict[str, dict[str, list[str]]] = {}

        buildable_decisions = []
        for d in self.decisions:
            original_caller = d.call_site.caller
            original_callee = d.call_site.callee
            original_location = d.call_site.location
            found_build = False
            # check if we have seen any other calls from this caller
            if original_caller in seen_locations:
                # loop through all calls from this caller
                for callee, locations in seen_locations[original_caller].items():
                    # check if we have seen other calls from this callee
                    if callee in seen_locations:
                        # loop through all the calls from the callee
                        for callee_callee, callee_locations in seen_locations[
                            callee
                        ].items():
                            if callee_callee != original_callee:
                                continue
                            # loop through every combination of the locations
                            for location in locations:
                                for callee_location in callee_locations:
                                    # simple combination case
                                    combined_location = (
                                        f"{callee_location}@[{location}]"
                                    )
                                    # check if callee_location contains a ']' in it
                                    if "]" in callee_location:
                                        b_idx = callee_location.index("]")
                                        callee_base_location = callee_location[:b_idx]
                                        callee_end_location = callee_location[b_idx:]
                                        combined_location = f"{callee_base_location}@[{location}]{callee_end_location}"
                                    if combined_location == original_location:
                                        buildable_decisions.append(d)
                                        found_build = True
                                    if found_build:
                                        break
                                if found_build:
                                    break
                            if found_build:
                                break
                    if found_build:
                        break

            if original_caller not in seen_locations:
                seen_locations[original_caller] = {}
            if original_callee not in seen_locations[original_caller]:
                seen_locations[original_caller][original_callee] = []
            seen_locations[original_caller][original_callee].append(original_location)

        for d in buildable_decisions:
            referenced_decisions = []
            for dd in self.decisions:
                if f"@[{d.call_site.location}]" in dd.call_site.location:
                    referenced_decisions.append(dd)
            print("Removing", d, "and", referenced_decisions)
            self.decisions.remove(d)
            for rd in referenced_decisions:
                self.decisions.remove(rd)

    def get_next_conflicting_decisions(self) -> list[Decision] | None:
        """
        Return a list of decisions with same conflicting location
        """
        seen = set()
        location_to_use = None
        for d in self.decisions:
            if d.call_site.location in seen:
                location_to_use = d.call_site.location
                break
            seen.add(d.call_site.location)
        if location_to_use is None:
            return None
        return [d for d in self.decisions if d.call_site.location == location_to_use]

    def save(self, path: str) -> None:
        with open(path, "w") as f:
            f.write(str(self))

    def to_pyll_tuple(self) -> tuple[InliningDecision, ...]:
        return (InliningDecision(d.call_site, d.inlined) for d in self.decisions)

    @staticmethod
    def from_pyll_tuple(pyll_decisions: tuple[InliningDecision, ...]) -> DecisionSet:
        ds = DecisionSet()
        for d in pyll_decisions:
            ds.add_decision(d.callsite, d.inlined)
        return ds

    def __str__(self) -> str:
        output = ""
        # output = "{\n"
        for d in self.decisions:
            output += f"{d}\n"
        # output += "}"
        return output
