from __future__ import annotations

import shlex
import subprocess as sp
from types import SimpleNamespace

from diopter.compiler import (
    CompilationOutputType,
    CompilationResult,
    ObjectCompilationOutput,
    OptLevel,
    SourceFile,
    parse_compilation_setting_from_string,
)
from pyllinliner.inlinercontroller import (
    CallSite,
    InlinerController,
    InliningControllerCallBacks,
    PluginSettings,
)

from utils.decision import DecisionSet
from utils.logger import Logger
from utils.run_log import callgraph_log, decision_log, result_log


class NoInliningCallBacks(InliningControllerCallBacks):
    store_decisions: bool
    store_final_callgraph: bool

    call_ids: list[int]
    call_sites: dict[int, CallSite]
    decisions: DecisionSet
    callgraph: tuple[CallSite, ...]

    def __init__(self, store_decisions: bool, store_final_callgraph: bool) -> None:
        Logger.debug(
            f"Initializing NoInliningCallBacks with {store_decisions} and {store_final_callgraph}"
        )
        self.store_decisions = store_decisions
        self.store_final_callgraph = store_final_callgraph

        self.call_ids = []
        if store_decisions:
            self.call_sites = {}
            self.decisions = DecisionSet()
        if store_final_callgraph:
            self.callgraph = ()

    def advice(self, id: int, default: bool) -> bool:
        Logger.debug(f"Advice {id} {default}")
        if self.store_decisions:
            call_site = self.call_sites.pop(id)
            self.decisions.add_decision(call_site, False)

            caller_name = call_site.caller
            if caller_name == "in_c_1":
                out = True
            else:
                out = False

            Logger.debug(
                f"{call_site.caller} -> {call_site.callee} {call_site.location} {out}"
            )

            return out
        return False

    def push(self, id: int, call_site: CallSite) -> None:
        Logger.debug(
            f"Pushing {id} {call_site.caller} {call_site.callee} {call_site.location}"
        )
        self.call_ids.append(id)
        if self.store_decisions:
            self.call_sites[id] = call_site

    def pop(self) -> int:
        Logger.debug(f"Poping {self.call_ids[0]}")
        return self.call_ids.pop(0)

    def erase(self, ID: int) -> None:
        Logger.debug(f"Erasing {ID}")
        self.call_ids.remove(ID)
        if self.store_decisions:
            self.call_sites.pop(ID)

    def start(self) -> PluginSettings:
        Logger.debug("Starting no inlining")
        return PluginSettings(
            report_callgraph_at_end=self.store_final_callgraph,
            # enable_debug_logs=True
        )

    def end(self, callgraph: tuple[CallSite, ...]) -> None:
        Logger.debug("Ending no inlining")
        if self.store_final_callgraph:
            Logger.debug("Received final callgraph")
            self.callgraph = self.callgraph + callgraph


def run_no_inlining(
    compiler: str,
    log_file: str | None,
    decision_file: str | None,
    final_callgraph_file: str | None,
    args: list[str],
) -> CompilationResult[CompilationOutputType]:
    callbacks = NoInliningCallBacks(
        decision_file is not None, final_callgraph_file is not None
    )

    command = shlex.join([compiler] + args)
    settings, files, comp_output = parse_compilation_setting_from_string(command)

    if settings.opt_level == OptLevel.O0:
        Logger.warn("Optimization level is O0, will run with clang defaults.")
        proc = sp.run(command, shell=True, stdout=sp.PIPE, stderr=sp.STDOUT)
        new_comp_output = SimpleNamespace()
        new_comp_output.stdout_stderr_output = proc.stdout.decode("utf-8")
        return new_comp_output  # type: ignore

    source_files = tuple(file for file in files if isinstance(file, SourceFile))
    object_files = tuple(
        file for file in files if isinstance(file, ObjectCompilationOutput)
    )

    controller = InlinerController(settings)

    if len(source_files) == 0:
        assert len(object_files) > 0, "No source files or object files provided"
        result = controller.run_on_program_with_callbacks(
            object_files, comp_output, callbacks
        )
    elif len(object_files) == 0:
        assert len(source_files) > 0, "No source files or object files provided"
        assert len(source_files) == 1, "Multiple source files provided"
        source_file = source_files[0]
        result = controller.run_on_program_with_callbacks(
            source_file, comp_output, callbacks
        )

    if decision_file is not None:
        decision_log(decision_file, callbacks.decisions)

    if final_callgraph_file is not None:
        callgraph_log(final_callgraph_file, callbacks.callgraph)

    if log_file is not None:
        result_log(log_file, result.stdout_stderr_output)

    return result  # type: ignore
