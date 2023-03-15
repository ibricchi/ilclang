from __future__ import annotations

import random
import shlex
import sys

from pyllinliner.inlinercontroller import (
    ThinInlineController,
    InliningControllerCallBacks,
    PluginSettings,
)

from utils.callsite import CallSite
from utils.decision import DecisionSet
from utils.logger import Logger


class RandomInliningCallBacks(InliningControllerCallBacks):
    store_decisions: bool
    store_final_callgraph: bool

    call_ids: list[int]
    call_sites: dict[int, CallSite]
    decisions: DecisionSet
    callgraph: list[tuple[str, str, str]]

    flip_probability: float
    rng: random.Random

    def __init__(
        self,
        flip_probability: float,
        store_decisions: bool,
        store_final_callgraph: bool,
        seed: int | None
    ) -> None:
        self.flip_probability = flip_probability
        self.rng = random.Random(seed)

        self.store_decisions = store_decisions
        self.store_final_callgraph = store_final_callgraph

        self.call_ids = []
        if store_decisions:
            self.call_sites = {}
            self.decisions = DecisionSet()
        if store_final_callgraph:
            self.callgraph = []

    def advice(self, id: int, default: bool) -> bool:
        Logger.debug(f"Advice for {id} (default: {default})")
        if self.rng.random() < self.flip_probability:
            decison = not default
        else:
            decison = default

        if self.store_decisions:
            call_site = self.call_sites.pop(id)
            self.decisions.add_decision(call_site, decison, default != decison)

        return decison

    def push(self, id: int, caller: str, callee: str, loc: str) -> None:
        Logger.debug(f"Push {id} {caller} {callee} {loc}")
        self.call_ids.append(id)
        if self.store_decisions:
            call_site = CallSite(caller, callee, loc)
            self.call_sites[id] = call_site

    def pop(self) -> int:
        out = self.call_ids.pop(0)
        Logger.debug("Popped ", out)
        return out

    def erase(self, ID: int) -> None:
        Logger.debug(f"Erase {ID}")
        self.call_ids.remove(ID)
        if self.store_decisions:
            self.call_sites.pop(ID)

    def start(self) -> PluginSettings:
        Logger.debug("Start")
        return PluginSettings(
            report_callgraph_at_end=self.store_final_callgraph,
        )

    def end(self, callgraph: list[tuple[str, str, str]]) -> None:
        Logger.debug("End")
        if self.store_final_callgraph:
            self.callgraph = self.callgraph + callgraph


def run_random_inlining(
    compiler: str,
    log_file: str | None,
    decision_file: str | None,
    final_callgraph_file: str | None,
    lto: bool,
    args: list[str],
    flip_probability: float,
    seed: int|None
) -> None:
    callbacks = RandomInliningCallBacks(
        flip_probability, decision_file is not None, final_callgraph_file is not None, seed
    )

    controller = ThinInlineController(
        callbacks,
        compiler,
        ThinInlineController.Mode.PLUGIN_LINK
        if lto
        else ThinInlineController.Mode.PLUGIN_COMPILE,
    )

    ret, result = controller.run_with_args(shlex.join(args))

    if decision_file is not None:
        Logger.debug("Writing decisions to", decision_file)
        with open(decision_file, "w") as f:
            f.write(f"{callbacks.decisions}")
        
    if final_callgraph_file is not None:
        Logger.debug("Writing final callgraph to", final_callgraph_file)
        with open(final_callgraph_file, "w") as f:
            for caller, callee, loc in callbacks.callgraph:
                f.write(f"{caller} -> {callee} @ {loc}\n")

    if log_file is not None:
        Logger.debug("Writing log to", log_file)
        with open(log_file, "w") as f:
            f.write(result)

    return ret, result
