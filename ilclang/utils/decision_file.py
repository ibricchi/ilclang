from __future__ import annotations

import re
from dataclasses import replace

from pyllinliner.inlinercontroller import CallSite

from ilclang.utils.decision import Decision, DecisionSet


def load_callsite_file(file_path: str) -> list[CallSite]:
    callsites = []
    with open(file_path, "r") as f:
        regex = r"CallSite\(caller=\'(.*)\', callee=\'(.*)\', location=\'(.*)\'\)"
        for line in f:
            if len(line.strip()) == 0:
                continue
            if match := re.search(regex, line):
                caller, callee, location = match.groups()
                callsites.append(
                    CallSite(caller=caller, callee=callee, location=location)
                )
            else:
                raise Exception(f"Could not parse line: {line}")
    return callsites


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
            if len(line.strip()) == 0:
                continue
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


def trickle_decision_flip(
    og_decisions: DecisionSet, call_site: CallSite
) -> list[DecisionSet]:
    og_decision = og_decisions.decision_for(call_site)
    assert og_decision is not None
    og_inlined = og_decision.inlined
    return trickle_decision_change(og_decisions, call_site, not og_inlined)


def trickle_decision_change(
    og_decisions: DecisionSet, call_site: CallSite, inlined: bool
) -> list[DecisionSet]:
    decisions = og_decisions.clone()

    # replace the original decision
    og_decision = decisions.decision_for(call_site)
    assert og_decision is not None
    decisions.replace_decision(og_decision, call_site, inlined, True)
    updated_decision = decisions.decision_for(call_site)
    assert updated_decision is not None

    # depending on inlining direction, recursively flip dependant
    # decisions
    if inlined:
        final = trickle_positive(decisions, updated_decision)
    else:
        final = trickle_negative(decisions, updated_decision)

    for f in final:
        f.remove_implicit_duplicates()

    return final


def pprint(call_site: CallSite, **kwargs) -> None:  # type: ignore
    print(f"{call_site.caller} -> {call_site.callee} @ {call_site.location}", **kwargs)


def dprint(decision: Decision, **kwargs) -> None:  # type: ignore
    print(
        f"{'[' if decision.modified else '('}{decision.call_site.caller} -> {decision.call_site.callee} @ {decision.call_site.location} : {'T' if decision.inlined else 'F'}{']' if decision.modified else ')'}",
        **kwargs,
    )


def trickle_negative(
    decisions: DecisionSet, updated_decision: Decision, depth: int = 0
) -> list[DecisionSet]:
    # tab_format = "  " * depth
    # find any decisions that are inlined in reference to the updated decision
    dependant_decisions = []
    for d in decisions.decisions:
        if f"@[{updated_decision.call_site.location}]" in d.call_site.location:
            dependant_decisions.append(d)

    # print out each dependant decision
    # print(f"\n{tab_format}Dependant Decisions:")
    # for d in dependant_decisions:
    #     print(tab_format, end="")
    #     dprint(d)

    new_call_sites = []
    for dd in dependant_decisions:
        # print(f"\n{tab_format}Proccessing dd: ", end="")
        # dprint(dd)
        new_dd_cs = replace(
            dd.call_site,
            caller=updated_decision.call_site.callee,
            location=dd.call_site.location.replace(
                f"@[{updated_decision.call_site.location}]", ""
            ),
        )
        new_call_sites.append((dd, new_dd_cs))

    # # print out each new call site
    # print(f"\n{tab_format}New Call Sites:")
    # for d, new_cs in new_call_sites:
    #     print(tab_format, end="")
    #     dprint(d, end=" ==> ")
    #     pprint(new_cs)

    # copy the decisions
    decisions = decisions.clone()

    # run replacements
    for d, new_cs in new_call_sites:
        # add the new decision
        decisions.replace_decision(d, new_cs, d.inlined, True)

    final_decision_sets = [decisions]
    conflicts_resolved = False
    i = 0
    while not conflicts_resolved:
        i += 1
        # print(f"\n{tab_format}-----STARTING SETS {i}-----")
        conflicts_resolved = True
        new_sets = []
        for ds in final_decision_sets:
            # # print out ds
            # for d in ds.decisions:
            #     print(tab_format, end="")
            #     dprint(d)
            # print()

            # find any conflicting locations
            conflicting_decisions = ds.get_next_conflicting_decisions()
            if conflicting_decisions is None:
                continue
            # print(f"\n{tab_format}Conflicting Decisions {conflicting_decisions[0]}")
            conflicts_resolved = False

            # find if all conflicting decisions share the same inlining decision
            inlined = [d for d in conflicting_decisions if d.inlined]
            not_inlined = [d for d in conflicting_decisions if not d.inlined]

            # select any decsisions that are repeated and can be safely removed
            for md in inlined[1:] + not_inlined[1:]:
                # print(f"{tab_format}Removing: ", end="")
                # dprint(md)
                ds.decisions.remove(md)

            # if there are decisions in both inlined and not_inlined, then
            # we have to split the decision set into two
            if inlined and not_inlined:
                # pprint(inlined[0].call_site)
                # clone decision set
                new_ds = ds.clone()
                # modify ds to only contain the inlined decision
                ds.decisions.remove(not_inlined[0])
                # modify new_ds to only contain the not_inlined decision
                new_ds.decisions.remove(inlined[0])
                # for any decisions that are inlined in reference to the old desicion remove them
                new_dss = trickle_negative(new_ds, not_inlined[0], depth + 1)
                # add new_ds to list of decision sets
                new_sets.extend(new_dss)
        # print(f"\n{tab_format}-----ENDING SETS {i}-----")
        # print(f"{tab_format}OG:")
        # for ds in final_decision_sets:
        #     for d in ds.decisions:
        #         print(tab_format, end="")
        #         dprint(d)
        #     print()
        # print(f"{tab_format}New:")
        for ns in new_sets:
            # for d in ns.decisions:
            #     print(tab_format, end="")
            #     dprint(d)
            # print()
            final_decision_sets.append(ns)

    return final_decision_sets


def trickle_positive(
    decisions: DecisionSet, trickle_decision: Decision
) -> list[DecisionSet]:
    # ensure that the trickle decision is inlined
    assert trickle_decision.inlined

    # look for any callsites that have callers that are the callee of this one
    referenced_decisions: list[Decision] = []
    trickle_idx = decisions.decisions.index(trickle_decision)
    for d in decisions.decisions[trickle_idx:]:
        cs = d.call_site
        if cs.caller == trickle_decision.call_site.callee:
            referenced_decisions.append(d)
    # for each referenced callsite add a new ammended decision
    new_decisions = []
    for d in referenced_decisions:
        # check if the caller is a callee anywhere else
        split_decision_location = (
            d.call_site.location.replace("[", "").replace("]", "").split("@")
        )
        split_og_location = (
            trickle_decision.call_site.location.replace("[", "")
            .replace("]", "")
            .split("@")
        )
        rev_split_location = split_og_location[::-1] + split_decision_location[::-1]

        if len(rev_split_location) == 1:
            new_location = rev_split_location[0]
        else:
            new_location = rev_split_location[0]
            for location in rev_split_location[1:]:
                new_location = f"{location}@[{new_location}]"

        new_decisions.append(
            Decision(
                call_site=replace(
                    d.call_site,
                    caller=trickle_decision.call_site.caller,
                    location=new_location,
                ),
                inlined=d.inlined,
                modified=True,
            )
        )

    new_decisions_sorted = sorted(
        new_decisions,
        key=lambda d: d.call_site.location.count("@"),
    )

    for i, d in enumerate(new_decisions_sorted):
        decisions.decisions.insert(trickle_idx + i + 1, d)

    return [decisions]
