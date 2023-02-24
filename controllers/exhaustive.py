from __future__ import annotations

import os

from pyllinliner.compiler_wrapper import CompileCommand
<<<<<<< HEAD
from pyllinliner.inlinercontroller import InliningControllerCallBacks, run_compiler_with_inliner_callbacks
from utils.callgraph import CallGraph, CallSite
=======
from pyllinliner.inlinerserver import run_server_with_callbacks
>>>>>>> 61bc516 (Implement a random based inline controller)
from utils.decision import DecisionSet
from utils.top_down_callbacks import TopDownCallBacks


class ExhaustiveDecisionSet(DecisionSet):
    def get_next_decisions(self) -> ExhaustiveDecisionSet | None:
        new_decision_set = ExhaustiveDecisionSet()
        found_unfixed = False
        for decision in self.decisions:
            if decision.modified:
                new_decision_set.decisions.append(decision.clone())
            else:
                found_unfixed = True
                decision.modified = True
                new_decision = decision.clone()
                new_decision.inlined ^= True
                new_decision_set.decisions.append(new_decision)
                break
        if found_unfixed:
            return new_decision_set
        else:
            return None


class ExhaustiveInliningCallBacks(TopDownCallBacks):
    decisions: ExhaustiveDecisionSet
    instructions: ExhaustiveDecisionSet

    def __init__(self, instructions: ExhaustiveDecisionSet) -> None:
        super().__init__()
        self.decisions = ExhaustiveDecisionSet()
        self.instructions = instructions

    def advice(self, id: int, default: bool) -> bool:
        call_site = self.callgraph.pop_call_site(id)
        instruction = next(
            (d for d in self.instructions.decisions if d.call_site == call_site), None
        )
        if instruction is None:
            self.decisions.add_decision(call_site, False)
            return False
        else:
            self.decisions.add_decision(call_site, instruction.inlined, True)
            return instruction.inlined


class DecisionHistory:
    decisions: list[ExhaustiveDecisionSet]

    def __init__(self) -> None:
        self.decisions = []

    def get_next_decisions(self) -> ExhaustiveDecisionSet | None:
        if len(self.decisions) == 0:
            return ExhaustiveDecisionSet()
        else:
            for decision in self.decisions:
                next_decision = decision.get_next_decisions()
                if next_decision is not None:
                    return next_decision
            return None

    def short_hand(self) -> str:
        return "\n".join([d.short_hand() for d in self.decisions])


def run_exhaustive_search(
    server_socket: str,
    plugin_socket: str,
    compile_command: CompileCommand,
    output_file: str,
) -> None:
    decision_history = DecisionHistory()
    best_size = 10000000000
    best_decisions: DecisionSet | None = None
    while instructions := decision_history.get_next_decisions():
        callbacks = ExhaustiveInliningCallBacks(instructions)
        run_compiler_with_inliner_callbacks(
            server_socket, plugin_socket, compile_command, callbacks
        )
        file_size = os.path.getsize(output_file)
        print(f"{callbacks.decisions.short_hand()}: {file_size}")
        if file_size < best_size:
            best_size = file_size
            best_decisions = callbacks.decisions.clone()
        decision_history.decisions.append(callbacks.decisions)
    if best_decisions is not None:
        print(f"Best decisions: {best_decisions.short_hand()}")
    else:
        print("No decisions found")
