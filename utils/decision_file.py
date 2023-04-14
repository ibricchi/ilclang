from __future__ import annotations

import re

from pyllinliner.inlinercontroller import CallSite

from utils.decision import Decision, DecisionSet


def load_decision_file(file_path: str) -> DecisionSet:
    replay_decisions = DecisionSet()
    with open(file_path, "r") as f:
        # for each line the information from the regex:
        # [\(\[]CallSite\(caller=\'(.*)\', callee=\'(.*)\', location=\'(.*)\'\) : ([TF])[\)\]
        # is stored in the following variables:
        # caller = $1
        # callee = $2
        # location = $3
        # decision = $4 == "T"
        regex = r"([\(\[])CallSite\(caller=\'(.*)\', callee=\'(.*)\', location=\'(.*)\'\) : ([TF])[\)\]]"
        for line in f:
            if match := re.search(regex, line):
                fixed, caller, callee, location, decision = match.groups()
                replay_decisions.add_decision(
                    CallSite(caller=caller, callee=callee, location=location),
                    decision == "T",
                    fixed == "[",
                )
            else:
                raise Exception(f"Could not parse line: {line}")
    return replay_decisions


def remove_decision(decisions: DecisionSet, call_site: CallSite) -> DecisionSet:
    # copy the fixed decicions
    new_decisions = decisions.clone()
    # remove the decision
    decision_to_remove = new_decisions.decision_for(call_site)
    assert decision_to_remove is not None
    new_decisions.decisions.remove(decision_to_remove)

    rem_list = [call_site]
    while len(rem_list) != 0:
        # get the next call site to remove
        rem_cs = rem_list.pop(0)
        # look for any callsites that are inlined in reference to this one
        referenced = []
        for dec in new_decisions.decisions:
            cs = dec.call_site
            split_location = cs.location.split("@")
            if len(split_location) > 1:
                base_location = split_location[0]
                inlining_location = "@".join(split_location[1:])
                if f"[{rem_cs.location}]" == inlining_location:
                    referenced.append((base_location, dec))
                    rem_list.append(cs)
        # for each referenced callsite replace it with modified callsite
        for base_location, dec in referenced:
            cs = dec.call_site
            new_decisions.decisions.remove(dec)
            new_decisions.add_decision(
                CallSite(
                    caller=rem_cs.callee, callee=cs.callee, location=base_location
                ),
                dec.inlined,
                dec.modified,
            )

    return new_decisions


def trickle_decision_change(
    og_decisions: DecisionSet, call_site: CallSite, inlined: bool
) -> DecisionSet:
    decisions = og_decisions.clone_only_modified()

    # remove the original decision
    og_decision = decisions.decision_for(call_site)
    assert og_decision is not None
    decisions.decisions.remove(og_decision)

    # depending on inlining direction, recursively flip dependant
    # decisions
    if inlined:
        # look for any callsites that have callers that are the callee of this one
        referenced_cs: list[CallSite] = []
        for dec in decisions.decisions:
            cs = dec.call_site
            if cs.caller == call_site.callee:
                referenced_cs.append(cs)
        # for each referenced callsite add a new ammended decision
        for cs in referenced_cs:
            decisions.add_decision(
                CallSite(
                    caller=call_site.caller,
                    callee=cs.callee,
                    location=f"{cs.location}@[{call_site.location}]",
                ),
                dec.inlined,
                dec.modified,
            )
    else:
        reverse_list = [call_site]
        while len(reverse_list) != 0:
            # get the next call_site to use for reversal
            rev_cs = reverse_list.pop(0)
            # look for any callsites that are inlined in reference to this one
            referenced_dec: list[tuple[str, Decision]] = []
            for dec in decisions.decisions:
                cs = dec.call_site
                split_location = cs.location.split("@")
                if len(split_location) > 1:
                    base_location = split_location[0]
                    inlining_location = "@".join(split_location[1:])
                    if f"[{rev_cs.location}]" == inlining_location:
                        referenced_dec.append((base_location, dec))
                        reverse_list.append(cs)
            # for each referenced callsite add a new ammended decision
            for base_location, dec in referenced_dec:
                cs = dec.call_site
                decisions.add_decision(
                    CallSite(
                        caller=rev_cs.callee, callee=cs.callee, location=base_location
                    ),
                    dec.inlined,
                    dec.modified,
                )

    # add flipped decision
    decisions.add_decision(call_site, inlined, True)

    remove_conflicts(decisions)
    return decisions


# WARNING this function modifies the decisions passed in
def remove_conflicts(decisions: DecisionSet) -> None:
    location_map: dict[str, list[Decision]] = {}
    for dec in decisions.decisions:
        if dec.call_site.location not in location_map:
            location_map[dec.call_site.location] = []
        location_map[dec.call_site.location].append(dec)

    conflicting_sets = []
    for location in location_map:
        if len(location_map[location]) > 1:
            conflicting_sets.append(location_map[location])

    to_remove = []
    actual_conflict = None
    for conflict_set in conflicting_sets:
        # check if all decisions in the conflict set are the same
        all_same = True
        for dec in conflict_set:
            if dec.inlined != conflict_set[0].inlined:
                all_same = False
                break
        # here we keep one copy of the decision
        if all_same:
            to_remove += conflict_set[1:]
        # here we remove all copies of the decision so the compiler
        # takes a default decision
        elif actual_conflict is None:
            to_remove += conflict_set
    for dec in to_remove:
        decisions.decisions.remove(dec)
