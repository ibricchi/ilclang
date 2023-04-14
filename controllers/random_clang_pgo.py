# type: ignore

from __future__ import annotations

import math
import random
import shlex
from dataclasses import dataclass, replace

from diopter.compiler import (  # OptLevel,
    CompilationOutputType,
    CompilationResult,
    ObjectCompilationOutput,
    SourceProgram,
    parse_compilation_setting_from_string,
)
from pyllinliner.inlinercontroller import (
    CallSite,
    InlinerController,
    InliningControllerCallBacks,
    PluginSettings,
    proto,
)

from utils.decision import DecisionSet
from utils.logger import Logger


@dataclass(frozen=True, kw_only=True)
class PGOInfo:
    caller_call_count: int
    callee_call_count: int
    max_call_count: int
    call_site_count: int


class RandomPGOClangInliningCallBacks(InliningControllerCallBacks):
    store_decisions: bool
    store_final_callgraph: bool

    call_ids: list[int]
    pgo_info: dict[str,]
    call_sites: dict[int, CallSite]
    decisions: DecisionSet
    callgraph: list[tuple[str, str, str]]

    flip_probability: float
    rng: random.Random

    @staticmethod
    def prob_modulator(
        caller_count: int, callee_count: int, max_call_count: int
    ) -> float:
        caller_importance_ratio = caller_count / max_call_count
        callee_importance_ratio = callee_count / max_call_count

        importance_ratio = max(caller_importance_ratio, callee_importance_ratio)

        return math.pow(math.sin(importance_ratio * math.pi / 2), 0.5)

    def __init__(
        self,
        flip_probability: float,
        store_decisions: bool,
        store_final_callgraph: bool,
        seed: int | None,
    ) -> None:
        self.flip_probability = flip_probability
        self.rng = random.Random(seed)

        self.store_decisions = store_decisions
        self.store_final_callgraph = store_final_callgraph

        self.call_ids = []
        self.pgo_info = {}
        if store_decisions:
            self.call_sites = {}
            self.decisions = DecisionSet()
        if store_final_callgraph:
            self.callgraph = []

    def advice(self, id: int, default: bool) -> bool:
        Logger.debug(f"Advice for {id} (default: {default})")

        pgo_info = self.pgo_info.pop(id)

        adjusted_flip_probability = self.flip_probability * self.prob_modulator(
            pgo_info.caller_call_count,
            pgo_info.callee_call_count,
            pgo_info.max_call_count,
        )

        if self.rng.random() > adjusted_flip_probability:
            decison = not default
        else:
            decison = default

        if self.store_decisions:
            call_site = self.call_sites.pop(id)
            self.decisions.add_decision(call_site, decison, default != decison)

        return decison

    def push(self, id: int, call_site: CallSite, extra_info: dict[str, object]) -> None:
        Logger.debug(
            f"Push {id} {call_site.caller} {call_site.callee} {call_site.location} {extra_info}"
        )
        self.call_ids.append(id)
        self.pgo_info[id] = PGOInfo(
            caller_call_count=extra_info["caller_call_count"],
            callee_call_count=extra_info["callee_call_count"],
            max_call_count=extra_info["max_call_count"],
            call_site_count=extra_info["call_site_count"],
        )
        if self.store_decisions:
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
            report_pgo_info=True,
        )

    def end(self, callgraph: list[tuple[str, str, str]]) -> None:
        Logger.debug("End")
        if self.store_final_callgraph:
            self.callgraph = self.callgraph + callgraph


class RandomPGOClangInliningCallBacksVerbose(RandomPGOClangInliningCallBacks):
    memory: dict[int, CallSite]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.memory = {}

    def advice(self, id: int, default: bool) -> bool:
        advice = super().advice(id, default)
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
        super().push(id, call_site, pgo_info)

    def pop(self) -> int:
        id = super().pop()
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
        return replace(super().start(), enable_debug_logs=True)

    def end(self, callgraph: tuple[CallSite, ...]) -> None:
        Logger.debug("End")
        for call_site in callgraph:
            Logger.debug(
                f"Callgraph {call_site.caller} -> {call_site.callee} @ {call_site.location}"
            )
        super().end(callgraph)


def run_random_clang_pgo(
    compiler: str,
    log_file: str | None,
    decision_file: str | None,
    final_callgraph_file: str | None,
    args: list[str],
    pgo_file: str,
    flip_probability: float,
    seed: int | None,
    verbose: bool = False,
) -> CompilationResult[CompilationOutputType]:
    callbacks = (
        RandomPGOClangInliningCallBacksVerbose(
            flip_probability,
            decision_file is not None,
            final_callgraph_file is not None,
            seed,
        )
        if verbose
        else RandomPGOClangInliningCallBacks(
            flip_probability,
            decision_file is not None,
            final_callgraph_file is not None,
            seed,
        )
    )

    command = shlex.join([compiler] + args)
    settings, files, comp_output = parse_compilation_setting_from_string(command)

    source_files = tuple(file for file in files if isinstance(file, SourceProgram))
    object_files = tuple(
        file for file in files if isinstance(file, ObjectCompilationOutput)
    )

    if len(source_files) == 0:
        assert len(object_files) > 0, "No source files or object files provided"
        settings = replace(
            settings,
            flags=settings.flags
            + (
                f"-fprofile-instr-use={pgo_file}",
                "-Wl,-mllvm",
                "-Wl,--disable-preinline",
            ),
        )
        controller = InlinerController(settings)
        result = controller.run_on_program_with_callbacks(
            object_files, comp_output, callbacks
        )
    elif len(object_files) == 0:
        assert len(source_files) > 0, "No source files or object files provided"
        assert len(source_files) == 1, "Multiple source files provided"
        settings = replace(
            settings,
            flags=settings.flags
            + (
                f"-fprofile-instr-use={pgo_file}",
                "-mllvm",
                "--disable-preinline",
            ),
        )
        controller = InlinerController(settings)
        source_file = source_files[0]
        result = controller.run_on_program_with_callbacks(
            source_file, comp_output, callbacks
        )

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

    return result
