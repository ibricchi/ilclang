from __future__ import annotations

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

from ilclang.utils.decision import DecisionSet, Decision
from ilclang.utils.decision_file import load_callsite_file, load_decision_file
from ilclang.utils.logger import Logger
from ilclang.utils.run_log import callgraph_log, decision_log, erased_log, result_log
from ilclang.utils.verbose import VerboseCallBacks

#############
# CALLBACKS #
#############


class ReplayInliningCallBacks(InliningControllerCallBacks):
    store_decisions: bool
    store_final_callgraph: bool
    allow_unknown_erases: bool

    id_map: dict[CallSite, int]
    decisions: DecisionSet
    callgraph: tuple[CallSite, ...]
    unknown: dict[int, CallSite]

    replay_decisions: DecisionSet
    replay_idx: int

    erase_ids: list[int]

    plugin_settings: PluginSettings

    def __init__(
        self,
        store_decisions: bool,
        store_final_callgraph: bool,
        allow_unknown_erases: bool,
        replay_decisions: DecisionSet,
        erase_decisions: list[CallSite],
        plugin_settings: PluginSettings,
    ) -> None:
        self.replay_decisions = replay_decisions
        self.replay_idx = 0

        self.erase_decisions = erase_decisions

        self.store_decisions = store_decisions
        self.store_final_callgraph = store_final_callgraph
        self.allow_unknown_erases = allow_unknown_erases

        self.id_map = {}
        if store_decisions:
            self.decisions = DecisionSet()
        if store_final_callgraph:
            self.callgraph = ()
        self.unknown = {}

        self.erase_ids = []

        self.plugin_settings = plugin_settings

    def advice(self, id: int, default: bool) -> bool:
        if self.replay_idx >= len(self.replay_decisions.decisions):
            if self.allow_unknown_erases:
                # We essentially erase the call sites that we don't know about
                # These should only be caused by a delete action not occuring due to
                # a change in our replay decisions
                return False
            else:
                assert False, "This should be unreachable"

        current_decision = self.replay_decisions.decisions[self.replay_idx]
        self.replay_idx += 1

        return current_decision.inlined

    def push(self, id: int, call_site: CallSite) -> None:
        # check that call site is in replay decisions
        cs_decision = self.replay_decisions.decision_for(call_site)
        if cs_decision is None:
            # check if call site is not in erase decisions
            if self.allow_unknown_erases:
                self.unknown[id] = call_site
            elif call_site in self.erase_decisions:
                self.erase_ids.append(id)
            else:
                assert (
                    False
                ), f"Call site {call_site} not in replay decisions or erase decisions"
        else:
            # add call site to id map
            self.id_map[call_site] = id

    def pop(self, defaultOrderID: int) -> int:
        # get call site at instruction index
        if self.replay_idx >= len(self.replay_decisions.decisions):
            if self.allow_unknown_erases:
                assert len(self.unknown) > 0, "No more replay decisions or unknown call sites, but plugin is still popping"
                return self.unknown.popitem()[0]
            else:
                assert False, f"Replay idx {self.replay_idx} >= len decisions {len(self.replay_decisions.decisions)}"
        next_decision = self.replay_decisions.decisions[self.replay_idx]
        call_site = next_decision.call_site

        assert (
            call_site in self.id_map
        ), f"Call site required for replay hasn't been pused yet, {call_site}"

        return self.id_map.pop(call_site)

    def erase(self, ID: int) -> None:
        if self.allow_unknown_erases:
            if ID in self.unknown:
                call_site = self.unknown.pop(ID)
                Logger.debug(f"Erasing from unknown set: {call_site.caller} -> {call_site.callee} @ {call_site.location}")
                self.replay_decisions.decisions.insert(
                    self.replay_idx, Decision(
                        call_site=call_site, inlined=False, modified=True
                    )
                )
                print("Trying to erase implicit duplicates created from erasure of: ", call_site)
                self.replay_decisions.remove_implicit_duplicates()
                if self.replay_decisions.decision_for(call_site) is not None:
                    self.replay_idx += 1
            else:
                # Find if ID is in instructions after current replay_idx
                instruction_idx = -1
                for i, decision in enumerate(self.replay_decisions.decisions[self.replay_idx:]):
                    if decision.call_site in self.id_map and self.id_map[decision.call_site] == ID:
                        instruction_idx = i
                        break
                assert instruction_idx == -1, f"Trying to erase call site {ID} not in unknown set or replay decisions"
                Logger.debug(f"Erasing from replay decisions: {ID}")
                self.replay_decisions.decisions.pop(self.replay_idx + instruction_idx)

            # if ID not in self.unknown:
            #     call_site = next(cs for cs, id in self.id_map.items() if id == ID)
            #     assert False, f"Call site {call_site.caller} -> {call_site.callee} @ {call_site.location} not in unknown call sites"
            # else:
            #     Logger.debug("Erasing unknown call site")
            # call_site = self.unknown.pop(ID)
            # self.replay_decisions.decisions.insert(
            #     self.replay_idx, Decision(
            #         call_site=call_site, inlined=False, modified=True
            #     )
            # )
            # print("Trying to erase implicit duplicates created from erasure of: ", call_site)
            # self.replay_decisions.remove_implicit_duplicates()
            # self.replay_idx += 1
        elif ID in self.erase_ids:
            self.erase_ids.remove(ID)
        else:
            call_site = next(cs for cs, id in self.id_map.items() if id == ID)
            assert False, f"Call site {call_site} not in erase decisions"


    def start(self) -> PluginSettings:
        return self.plugin_settings

    def end(self, callgraph: tuple[CallSite, ...]) -> None:
        assert self.replay_idx == len(self.replay_decisions.decisions), "Replay decisions not fully used"
        assert self.id_map == {}, "Not all call sites were popped"
        assert self.unknown == {}, f"Not all unknown call sites were erased, {self.unknown}"
        if self.store_final_callgraph:
            self.callgraph = self.callgraph + callgraph


#######
# API #
#######


def setup_parser(subparser: _SubParsersAction[ArgumentParser]) -> ArgumentParser:
    parser_replay = subparser.add_parser("replay", help="replay inlining decisions")
    parser_replay.add_argument("replay_file", type=str, help="path to replay file")
    parser_replay.add_argument("-au", "--allow-unknown-erases", action="store_true")
    parser_replay.add_argument(
        "erase_file", type=str, help="path to erase file", default=None
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
        "-dc", "--duplicate-calls", action="store_true", help="duplicate calls"
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
    erase_file = args.erase_file

    replay_decisions = load_decision_file(replay_file)
    erase_decisions = []
    if erase_file is not None:
        erase_decisions = load_callsite_file(erase_file)

    callbacks = ReplayInliningCallBacks(
        decision_file is not None,
        final_callgraph_file is not None,
        args.allow_unknown_erases,
        replay_decisions,
        erase_decisions,
        PluginSettings(
            report_callgraph_at_end=args.report_callgraph,
            include_module_ir_on_each_advice_reply=args.include_module_ir,
            no_inline=args.no_inline,
            no_duplicate_calls=not args.duplicate_calls,
            record_history=args.record_history,
        ),
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

    if decision_file is not None:
        decision_log(decision_file, callbacks.decisions)

    if args.erased is not None:
        erased_log(args.erased, callbacks.erase_decisions)

    if final_callgraph_file is not None:
        callgraph_log(final_callgraph_file, callbacks.callgraph)

    if log_file is not None:
        result_log(log_file, result.stdout_stderr_output)

    return result  # type: ignore
