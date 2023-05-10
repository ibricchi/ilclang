from dataclasses import replace
from typing import Any

from pyllinliner.inlinercontroller import (
    CallSite,
    InliningControllerCallBacks,
    PluginSettings,
)

from ilclang.utils.logger import Logger


class VerboseCallBacks(InliningControllerCallBacks):
    parent: InliningControllerCallBacks
    memory: dict[int, CallSite]
    verbose_verbose: bool

    def __getattr__(self, name: str) -> Any:
        if name in self.__dict__:
            return self.__dict__[name]
        return getattr(self.parent, name)

    def __init__(
        self, parent: InliningControllerCallBacks, verbose_verbose: bool
    ) -> None:
        self.parent = parent
        self.memory = {}
        self.verbose_verbose = verbose_verbose

    def advice(self, id: int, default: bool) -> bool:
        advice = self.parent.advice(id, default)
        call_site = self.memory[id]
        Logger.debug(
            f"Advice {call_site.caller} -> {call_site.callee} @ {call_site.location} = {advice} (default: {default})"
        )
        return advice

    def push(self, id: int, call_site: CallSite) -> None:
        Logger.debug(
            f"Push {call_site.caller} -> {call_site.callee} @ {call_site.location}"
        )
        self.memory.update({id: call_site})
        self.parent.push(id, call_site)

    def pop(self, defaultOrderID: int) -> int:
        id = self.parent.pop(defaultOrderID)
        call_site = self.memory[id]
        Logger.debug(
            f"Pop {call_site.caller} -> {call_site.callee} @ {call_site.location}"
        )
        return id

    def erase(
        self,
        id: int,
    ) -> None:
        call_site = self.memory[id]
        Logger.debug(
            f"Erase {call_site.caller} -> {call_site.callee} @ {call_site.location}"
        )
        self.parent.erase(id)

    def inlined(self, ID: int) -> None:
        call_site = self.memory[ID]
        Logger.debug(
            f"Inlined {call_site.caller} -> {call_site.callee} @ {call_site.location}"
        )

    def inlined_with_callee_deleted(self, ID: int) -> None:
        call_site = self.memory[ID]
        Logger.debug(
            f"Inlined with callee deleted {call_site.caller} -> {call_site.callee} @ {call_site.location} (callee deleted)"
        )

    def unsuccessful_inlining(self, ID: int) -> None:
        call_site = self.memory[ID]
        Logger.debug(
            f"Unsuccessful inlining {call_site.caller} -> {call_site.callee} @ {call_site.location}"
        )

    def unattempted_inlining(self, ID: int) -> None:
        call_site = self.memory[ID]
        Logger.debug(
            f"Unattempted inlining {call_site.caller} -> {call_site.callee} @ {call_site.location}"
        )

    def start(self) -> PluginSettings:
        Logger.debug("Start")
        default = self.parent.start()
        updated = replace(
            default,
            enable_debug_logs=self.verbose_verbose or default.enable_debug_logs,
        )
        return updated

    def end(self, callgraph: tuple[CallSite, ...]) -> None:
        Logger.debug("End")
        for call_site in callgraph:
            Logger.debug(
                f"Callgraph {call_site.caller} -> {call_site.callee} @ {call_site.location}"
            )
        self.parent.end(callgraph)
