from dataclasses import replace

from pyllinliner.inlinercontroller import (
    CallSite,
    InliningControllerCallBacks,
    PluginSettings,
    proto,
)

from utils.logger import Logger


class VerboseCallBacks(InliningControllerCallBacks):
    parent: InliningControllerCallBacks
    memory: dict[int, CallSite]

    def __init__(self, parent: InliningControllerCallBacks) -> None:
        self.parent = parent
        self.memory = {}

    def advice(self, id: int, default: bool) -> bool:
        advice = self.parent.advice(id, default)
        call_site = self.memory[id]
        Logger.debug(
            f"Advice {call_site.caller} -> {call_site.callee} @ {call_site.location} = {advice} (default: {default})"
        )
        return advice

    def push(
        self, id: int, call_site: CallSite, pgo_info: proto.PgoInfo | None
    ) -> None:
        Logger.debug(
            f"Push {call_site.caller} -> {call_site.callee} @ {call_site.location}"
        )
        self.memory.update({id: call_site})
        self.parent.push(id, call_site, pgo_info)

    def pop(self, defaultOrderID: int) -> int:
        id = self.parent.pop(defaultOrderID)
        call_site = self.memory[id]
        Logger.debug(
            f"Pop {call_site.caller} -> {call_site.callee} @ {call_site.location}"
        )
        return id

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
        return replace(self.parent.start(), enable_debug_logs=True)

    def end(self, callgraph: tuple[CallSite, ...]) -> None:
        Logger.debug("End")
        for call_site in callgraph:
            Logger.debug(
                f"Callgraph {call_site.caller} -> {call_site.callee} @ {call_site.location}"
            )
        self.parent.end(callgraph)
