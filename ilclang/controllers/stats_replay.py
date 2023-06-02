from __future__ import annotations

import random
import shlex
import subprocess as sp
import tempfile
from argparse import ArgumentParser
from argparse import Namespace as ANS
from argparse import _SubParsersAction
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
)

from ilclang.utils.decision import DecisionSet
from ilclang.utils.decision_file import load_callsite_file, load_decision_file
from ilclang.utils.logger import Logger
from ilclang.utils.run_log import callgraph_log, decision_log, erased_log, result_log
from ilclang.utils.verbose import VerboseCallBacks

#############
# CALLBACKS #
#############


class StatsReplayInliningCallBacks(InliningControllerCallBacks):
    store_decisions: bool
    store_final_callgraph: bool

    rng: random.Random

    stats: dict[str, object]

    replay_decisions: DecisionSet
    replay_idx: int
    plugin_settings: PluginSettings
    flip_rate: float | None

    call_sites: dict[int, CallSite]
    call_ids: dict[CallSite, int]
    decisions: DecisionSet
    callgraph: tuple[CallSite, ...]
    was_erased: list[CallSite]

    def __init__(
        self,
        store_decisions: bool,
        store_final_callgraph: bool,
        replay_decisions: DecisionSet,
        plugin_settings: PluginSettings,
        flip_rate: float | None = None,
        seed: int | None = None,
    ) -> None:
        self.store_decisions = store_decisions
        self.store_final_callgraph = store_final_callgraph

        self.rng = random.Random(seed)

        # setup stats
        self.stats = {}
        self.stats["only_replay"] = True
        self.stats["erasures"] = 0
        self.stats["pushes"] = 0
        self.stats["pops"] = 0
        self.stats["order_change"] = 0
        self.stats["advice"] = 0
        self.stats["advice_true"] = 0
        self.stats["advice_false"] = 0
        self.stats["flipped_advice"] = 0
        self.stats["flipped_to_true"] = 0
        self.stats["flipped_to_false"] = 0
        self.stats["inlined"] = 0
        self.stats["inlined_with_callee_deleted"] = 0
        self.stats["unsuccesful_inlining"] = 0

        self.replay_decisions = replay_decisions
        self.replay_idx = 0
        self.plugin_settings = plugin_settings
        self.flip_rate = flip_rate

        self.call_sites = {}
        self.call_ids = {}
        self.decisions = DecisionSet()
        self.was_erased = []

        if store_final_callgraph:
            self.callgraph = ()

    def advice(self, id: int, default: bool) -> bool:
        self.stats["advice"] += 1
        # get call site for id
        call_site = self.call_sites.pop(id)
        self.call_ids.pop(call_site)
        # check if call site is in replay decisions
        if decision := self.replay_decisions.decision_for(call_site):
            self.replay_idx += 1
            if decision.inlined != default:
                self.stats["flipped_advice"] += 1
                if decision.inlined:
                    self.stats["flipped_to_true"] += 1
                else:
                    self.stats["flipped_to_false"] += 1
            dec = decision.inlined
        elif self.flip_rate is not None:
            r = self.rng.random()
            if r < self.flip_rate:
                dec = not default
                if dec:
                    self.stats["flipped_to_true"] += 1
                else:
                    self.stats["flipped_to_false"] += 1
            else:
                dec = default
        else:
            dec = default

        if dec:
            self.stats["advice_true"] += 1
        else:
            self.stats["advice_false"] += 1
        self.decisions.add_decision(call_site, dec)
        return dec

    def push(self, id: int, call_site: CallSite) -> None:
        self.stats["pushes"] += 1
        self.call_sites[id] = call_site
        self.call_ids[call_site] = id

    def pop(self, defaultOrderID: int) -> int:
        self.stats["pops"] += 1
        # check if we still have decisions to replay
        if self.replay_idx < len(self.replay_decisions.decisions):
            replay_callsite = self.replay_decisions.decisions[self.replay_idx].call_site
            assert replay_callsite in self.call_ids, "Replay decision not in call_ids"
            if self.call_ids[replay_callsite] != defaultOrderID:
                self.stats["order_change"] += 1
            return self.call_ids[replay_callsite]
        else:
            self.stats["only_replay"] = False
            return defaultOrderID

    def erase(self, ID: int) -> None:
        self.stats["erasures"] += 1
        self.was_erased.append(self.call_sites[ID])
        call_site = self.call_sites.pop(ID)
        self.call_ids.pop(call_site)

    def start(self) -> PluginSettings:
        return self.plugin_settings

    def end(self, callgraph: tuple[CallSite, ...]) -> None:
        if self.store_final_callgraph:
            self.callgraph = self.callgraph + callgraph

    def inlined(self, ID: int) -> None:
        self.stats["inlined"] += 1

    def inlined_with_callee_deleted(self, ID: int) -> None:
        self.stats["inlined_with_callee_deleted"] += 1

    def unsuccesful_inlining(self, ID: int) -> None:
        self.stats["unsuccesful_inlining"] += 1


#######
# API #
#######


def setup_parser(subparser: _SubParsersAction[ArgumentParser]) -> ArgumentParser:
    parser_replay = subparser.add_parser(
        "stats-replay", help="replay inlining decisions"
    )
    parser_replay.add_argument("replay_file", type=str, help="path to replay file")
    parser_replay.add_argument("stats_file", type=str, help="path to stats file")
    parser_replay.add_argument(
        "-fr", "--flip-rate", type=float, help="flip rate", default=None
    )
    parser_replay.add_argument(
        "-s", "--seed", type=int, help="random seed", default=None
    )
    parser_replay.add_argument(
        "-rcg", "--report-callgraph", action="store_true", help="report final callgraph"
    )
    parser_replay.add_argument(
        "-imi", "--include-module-ir", action="store_true", help="include module IR"
    )
    parser_replay.add_argument(
        "-ni", "--no-inline", action="store_true", help="do not inline"
    )
    parser_replay.add_argument(
        "-rh", "--record-history", action="store_true", help="record history"
    )
    return parser_replay


def run_inlining(
    compiler: str,
    args: ANS,
) -> CompilationResult[CompilationOutputType]:
    log_file = args.log
    decision_file = args.decision
    final_callgraph_file = args.final_callgraph
    cli_args = args.cli
    replay_file = args.replay_file
    stats_file = args.stats_file

    replay_decisions = load_decision_file(replay_file)

    callbacks = StatsReplayInliningCallBacks(
        decision_file is not None,
        final_callgraph_file is not None,
        replay_decisions,
        PluginSettings(
            report_callgraph_at_end=args.report_callgraph,
            include_module_ir_on_each_advice_reply=args.include_module_ir,
            no_inline=args.no_inline,
            record_history=args.record_history,
        ),
        flip_rate=args.flip_rate,
    )
    if args.verbose or args.verbose_verbose:
        callbacks = VerboseCallBacks(callbacks, args.verbose_verbose)  # type: ignore

    stdout = tempfile.NamedTemporaryFile()
    stderr = tempfile.NamedTemporaryFile()

    command = shlex.join([compiler] + cli_args)
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

    with open(stats_file, "w") as f:
        for key, value in callbacks.stats.items():
            f.write(f"{key}: {value}\n")

    if decision_file is not None:
        decision_log(decision_file, callbacks.decisions)

    if args.erased is not None:
        erased_log(args.erased, callbacks.was_erased)

    if final_callgraph_file is not None:
        callgraph_log(final_callgraph_file, callbacks.callgraph)

    if log_file is not None:
        result_log(log_file, result.stdout_stderr_output)

    return result  # type: ignore
