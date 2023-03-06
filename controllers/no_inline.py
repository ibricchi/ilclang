from __future__ import annotations

import shlex

from pyllinliner.inlinercontroller import (
    ThinInlineController,
    InliningControllerCallBacks,
    PluginSettings,
)

from utils.callgraph import CallSite
from utils.decision import DecisionSet
from utils.logger import Logger


class NoInliningCallBacks(InliningControllerCallBacks):
    store_decisions: bool
    store_final_callgraph: bool
 
    call_ids: list[int]
    call_sites: dict[int, CallSite]
    decisions: DecisionSet
    callgraph: list[tuple[str, str, str]]

    def __init__(self, store_decisions: bool, store_final_callgraph: bool) -> None:
        Logger.debug(f"Initializing NoInliningCallBacks with {store_decisions} and {store_final_callgraph}")
        self.store_decisions = store_decisions
        self.store_final_callgraph = store_final_callgraph

        self.call_ids = []
        if store_decisions:
            self.call_sites = {}
            self.decisions = DecisionSet()
        if store_final_callgraph:
            self.callgraph = []

    def advice(self, id: int, default: bool) -> bool:
        if self.store_decisions:
            call_site = self.call_sites.pop(id)
            self.decisions.add_decision(call_site, False)
        return False

    def push(self, id: int, caller: str, callee: str, loc: str) -> None:
        self.call_ids.append(id)
        if self.store_decisions:
            call_site = CallSite(caller, callee, loc)
            self.call_sites[id] = call_site

    def pop(self) -> int:
        return self.call_ids.pop(0)

    def erase(self, ID: int) -> None:
        self.call_ids.remove(ID)
        if self.store_decisions:
            self.call_sites.pop(ID)

    def start(self) -> PluginSettings:
        return PluginSettings(
            report_callgraph_at_end=self.store_final_callgraph,
        )

    def end(self, callgraph: list[tuple[str, str, str]]) -> None:
        if self.store_final_callgraph:
            Logger.debug("Received final callgraph")
            self.callgraph = self.callgraph + callgraph


def run_no_inlining(
    compiler: str,
    log_file: str | None,
    decision_file: str | None,
    final_callgraph_file: str | None,
    lto: bool,
    args: list[str],
) -> None:
    callbacks = NoInliningCallBacks(decision_file is not None, final_callgraph_file is not None)

    controller = ThinInlineController(
        callbacks,
        compiler,
        ThinInlineController.Mode.PLUGIN_LINK
        if lto
        else ThinInlineController.Mode.PLUGIN_COMPILE,
    )

    result = controller.run_with_args(shlex.join(args))

    if decision_file is not None:
        Logger.info("Writing decisions to", decision_file)
        with open(decision_file, "w") as f:
            f.write(f"{callbacks.decisions.to_string()}")
        
    if final_callgraph_file is not None:
        Logger.debug("Writing final callgraph to", final_callgraph_file)
        with open(final_callgraph_file, "w") as f:
            for caller, callee, loc in callbacks.callgraph:
                f.write(f"{caller} -> {callee} @ {loc}\n")

    if log_file is not None:
        Logger.debug("Writing log to", log_file)
        with open(log_file, "w") as f:
            f.write(result)
    Logger.debug(result)
