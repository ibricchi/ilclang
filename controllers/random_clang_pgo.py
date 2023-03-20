from __future__ import annotations

import random
import shlex
import sys
import math

from dataclasses import dataclass, replace

from diopter.compiler import (
    AsyncCompilationResult,
    CompilationOutputType,
    ObjectCompilationOutput,
    ExeCompilationOutput,
    CompilationResult,
    CompilationSetting,
    CompilerExe,
    CompilerProject,
    OptLevel,
    SourceProgram,
    parse_compilation_setting_from_string,
)

from pyllinliner.inlinercontroller import (
    CallSite,
    InlineController,
    InliningControllerCallBacks,
    PluginSettings,
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
    pgo_info: dict[str, ]
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
        self.pgo_info = {}
        if store_decisions:
            self.call_sites = {}
            self.decisions = DecisionSet()
        if store_final_callgraph:
            self.callgraph = []

    def advice(self, id: int, default: bool) -> bool:
        Logger.debug(f"Advice for {id} (default: {default})")

        pgo_info = self.pgo_info.pop(id)

        caller_importance_ratio = pgo_info.caller_call_count / pgo_info.max_call_count
        callee_importance_ratio = pgo_info.callee_call_count / pgo_info.max_call_count

        importance_ratio = max(caller_importance_ratio, callee_importance_ratio)

        adjusted_flip_probability = self.flip_probability * math.pow(math.sin(importance_ratio * math.pi / 2), 0.5)

        if self.rng.random() > adjusted_flip_probability:
            decison = not default
        else:
            decison = default

        if self.store_decisions:
            call_site = self.call_sites.pop(id)
            self.decisions.add_decision(call_site, decison, default != decison)

        return decison

    def push(self, id: int, call_site: CallSite, extra_info: dict[str, object]) -> None:
        Logger.debug(f"Push {id} {call_site.caller} {call_site.callee} {call_site.location} {extra_info}")
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


def run_random_clang_pgo(
    compiler: str,
    log_file: str | None,
    decision_file: str | None,
    final_callgraph_file: str | None,
    args: list[str],
    pgo_file: str,
    flip_probability: float,
    seed: int|None
) -> CompilationResult[CompilationOutputType]:
    callbacks = RandomPGOClangInliningCallBacks(
        flip_probability, decision_file is not None, final_callgraph_file is not None, seed
    )

    command = shlex.join([compiler] + args)
    settings, files, comp_output = parse_compilation_setting_from_string(command)

    source_files = tuple(file for file in files if isinstance(file, SourceProgram))
    object_files = tuple(file for file in files if isinstance(file, ObjectCompilationOutput))


    if len(source_files) == 0:
        assert len(object_files) > 0, "No source files or object files provided"
        settings = replace(settings, flags=settings.flags + (
                f"-fprofile-instr-use={pgo_file}",
                "-Wl,-mllvm", "-Wl,--disable-preinline",
            ))
        controller = InlineController(settings)
        result = controller.run_on_program_with_callbacks(object_files, comp_output, callbacks)
    elif len(object_files) == 0:
        assert len(source_files) > 0, "No source files or object files provided"
        assert len(source_files) == 1, "Multiple source files provided"
        settings = replace(settings, flags=settings.flags + (
                f"-fprofile-instr-use={pgo_file}",
                "-mllvm", "--disable-preinline",
            ))
        controller = InlineController(settings)
        source_file = source_files[0]
        result = controller.run_on_program_with_callbacks(source_file, comp_output, callbacks)

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
