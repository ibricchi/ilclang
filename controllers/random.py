from __future__ import annotations

import random
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
from utils.verbose import VerboseCallBacks

#############
# CALLBACKS #
#############


class RandomInliningCallBacks(InliningControllerCallBacks):
    store_decisions: bool
    store_final_callgraph: bool

    call_ids: list[int]
    call_sites: dict[int, CallSite]
    decisions: DecisionSet
    callgraph: tuple[CallSite, ...]
    flip_probability: float
    rng: random.Random

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
        if store_decisions:
            self.call_sites = {}
            self.decisions = DecisionSet()
        if store_final_callgraph:
            self.callgraph = ()

    def advice(self, id: int, default: bool) -> bool:
        if self.rng.random() < self.flip_probability:
            decison = not default
        else:
            decison = default

        if self.store_decisions:
            call_site = self.call_sites.pop(id)
            self.decisions.add_decision(call_site, decison, default != decison)

        return decison

    def push(
        self, id: int, call_site: CallSite, pgo_info: proto.PgoInfo | None
    ) -> None:
        self.call_ids.append(id)
        if self.store_decisions:
            self.call_sites[id] = call_site

    def pop(self, defaultOrderID) -> int:
        self.call_ids.remove(defaultOrderID)
        return defaultOrderID

    def erase(self, ID: int) -> None:
        self.call_ids.remove(ID)
        if self.store_decisions:
            self.call_sites.pop(ID)

    def start(self) -> PluginSettings:
        return PluginSettings(
            report_callgraph_at_end=self.store_final_callgraph,
        )

    def end(self, callgraph: tuple[CallSite, ...]) -> None:
        if self.store_final_callgraph:
            self.callgraph = self.callgraph + callgraph


#######
# API #
#######


def setup_parser(subparser):
    parser_radnom_inline = subparser.add_parser(
        "random-inline", help="randomly flip decision to inline"
    )
    parser_radnom_inline.add_argument(
        "flip_rate", type=float, help="rate of flipping decision"
    )
    parser_radnom_inline.add_argument("-s", "--seed", type=int, help="random seed")
    return parser_radnom_inline


def run_inlining(
    compiler: str,
    log_file: str | None,
    decision_file: str | None,
    final_callgraph_file: str | None,
    args: list[str],
    flip_probability: float,
    seed: int | None,
    verbose: bool = False,
) -> CompilationResult[CompilationOutputType]:
    callbacks = RandomInliningCallBacks(
        flip_probability,
        decision_file is not None,
        final_callgraph_file is not None,
        seed,
    )
    if verbose:
        callbacks = VerboseCallBacks(callbacks)

    stdout = tempfile.NamedTemporaryFile()
    stderr = tempfile.NamedTemporaryFile()

    command = shlex.join([compiler] + args)
    settings, files, comp_output = parse_compilation_setting_from_string(command)

    if settings.opt_level == OptLevel.O0:
        Logger.warn("Optimization level is O0, will run with clang defaults.")
        sp.run(command, shell=True, stdout=sp.PIPE, stderr=sp.STDOUT)
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
                object_files, comp_output, callbacks
            )
        elif len(object_files) == 0:
            assert len(source_files) > 0, "No source files or object files provided"
            assert len(source_files) == 1, "Multiple source files provided"
            source_file = source_files[0]
            result = controller.run_on_program_with_callbacks(
                source_file, comp_output, callbacks
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
