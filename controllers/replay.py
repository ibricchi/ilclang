from __future__ import annotations

import re
import shlex
import subprocess as sp
import tempfile
from dataclasses import replace
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
    proto,
)

from utils.decision import DecisionSet
from utils.logger import Logger
from utils.run_log import callgraph_log, decision_log, result_log


class ReplayInliningCallBacks(InliningControllerCallBacks):
    store_decisions: bool
    store_final_callgraph: bool

    call_ids: list[int]
    call_sites: dict[int, CallSite]
    decisions: DecisionSet
    callgraph: tuple[CallSite, ...]

    replay_decisions: DecisionSet

    def __init__(
        self,
        store_decisions: bool,
        store_final_callgraph: bool,
        replay_decisions: DecisionSet,
    ) -> None:
        self.replay_decisions = replay_decisions

        self.store_decisions = store_decisions
        self.store_final_callgraph = store_final_callgraph

        self.call_ids = []
        self.call_sites = {}
        if store_decisions:
            self.decisions = DecisionSet()
        if store_final_callgraph:
            self.callgraph = ()

    def advice(self, id: int, default: bool) -> bool:
        call_site = self.call_sites.pop(id)

        if cs_decision := self.replay_decisions.decision_for(call_site):
            decision = cs_decision.inlined
        else:
            decision = default

        if self.store_decisions:
            self.decisions.add_decision(call_site, decision)
        return decision

    def push(
        self, id: int, call_site: CallSite, pgo_info: proto.PgoInfo | None
    ) -> None:
        self.call_ids.append(id)
        self.call_sites[id] = call_site

    def pop(self) -> int:
        return self.call_ids.pop(0)

    def erase(self, ID: int) -> None:
        self.call_ids.remove(ID)
        self.call_sites.pop(ID)

    def start(self) -> PluginSettings:
        return PluginSettings(
            report_callgraph_at_end=self.store_final_callgraph,
            # enable_debug_logs=True
        )

    def end(self, callgraph: tuple[CallSite, ...]) -> None:
        if self.store_final_callgraph:
            self.callgraph = self.callgraph + callgraph


class ReplayInliningCallBacksVerbose(ReplayInliningCallBacks):
    memory: dict[int, CallSite]

    def __init__(self, *args, **kwargs) -> None:  # type: ignore
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


def run_replay_inlining(
    compiler: str,
    log_file: str | None,
    decision_file: str | None,
    final_callgraph_file: str | None,
    args: list[str],
    replay_file: str,
    verbose: bool = False,
) -> CompilationResult[CompilationOutputType]:
    replay_decisions = DecisionSet()
    with open(replay_file, "r") as f:
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
                req, caller, callee, location, decision = match.groups()
                if req == "[":
                    replay_decisions.add_decision(
                        CallSite(caller=caller, callee=callee, location=location),
                        decision == "T",
                        True,
                    )
            else:
                raise Exception(f"Could not parse line: {line}")

    callbacks = (
        ReplayInliningCallBacksVerbose(
            decision_file is not None,
            final_callgraph_file is not None,
            replay_decisions,
        )
        if verbose
        else ReplayInliningCallBacks(
            decision_file is not None,
            final_callgraph_file is not None,
            replay_decisions,
        )
    )

    stdout = tempfile.NamedTemporaryFile()
    stderr = tempfile.NamedTemporaryFile()

    command = shlex.join([compiler] + args)
    settings, files, comp_output = parse_compilation_setting_from_string(command)

    if settings.opt_level == OptLevel.O0:
        Logger.warn("Optimization level is O0, will run with clang defaults.")
        sp.run(command, shell=True, stdout=stdout, stderr=stderr)
        new_comp_output = SimpleNamespace()
        new_comp_output.stdout_stderr_output = (
            f"{stdout.read().decode('utf-8')}\n{stderr.read().decode('utf-8')}"
        )
        return new_comp_output  # type: ignore

    source_files = tuple(file for file in files if isinstance(file, SourceFile))
    object_files = tuple(
        file for file in files if isinstance(file, ObjectCompilationOutput)
    )

    controller = InlinerController(settings)

    try:
        if len(source_files) == 0:
            assert len(object_files) > 0, "No source files or object files provided"
            result = controller.run_on_program_with_callbacks(
                object_files, comp_output, callbacks, stdout=stdout, stderr=stderr  # type: ignore
            )
        elif len(object_files) == 0:
            assert len(source_files) > 0, "No source files or object files provided"
            assert len(source_files) == 1, "Multiple source files provided"
            source_file = source_files[0]
            result = controller.run_on_program_with_callbacks(
                source_file, comp_output, callbacks, stdout=stdout, stderr=stderr  # type: ignore
            )
    except Exception as e:
        stdout.seek(0)
        stderr.seek(0)
        Logger.info(stdout.read().decode())
        Logger.info(stderr.read().decode())
        raise e

    stdout.seek(0)
    stderr.seek(0)
    result = replace(
        result,
        stdout_stderr_output=f"{stdout.read().decode('utf-8')}\n{stderr.read().decode('utf-8')}",
    )

    if decision_file is not None:
        decision_log(decision_file, callbacks.decisions)

    if final_callgraph_file is not None:
        callgraph_log(final_callgraph_file, callbacks.callgraph)

    if log_file is not None:
        result_log(log_file, result.stdout_stderr_output)

    return result  # type: ignore
