from __future__ import annotations

import random
import shlex
import subprocess as sp
import tempfile
from argparse import ArgumentParser
from argparse import Namespace as ANS
from argparse import _SubParsersAction
from types import SimpleNamespace

from diopter.compiler import (
    CompilationOutputType,
    CompilationResult,
    OptLevel,
    parse_compilation_setting_from_string,
)
from pyllinliner.inlinercontroller import (
    CallSite,
    InliningControllerCallBacks,
    PluginSettings,
)

from ilclang.controllers.replay import ReplayInliningCallBacks
from ilclang.utils.decision import DecisionSet
from ilclang.utils.decision_file import trickle_decision_flip
from ilclang.utils.logger import Logger
from ilclang.utils.run_log import callgraph_log, decision_log, erased_log, result_log
from ilclang.utils.runner import gen_run_impl
from ilclang.utils.verbose import VerboseCallBacks

#############
# CALLBACKS #
#############


class TestInliningCallBacks(InliningControllerCallBacks):
    call_ids: list[int]
    call_sites: dict[int, CallSite]
    decisions: DecisionSet
    callgraph: tuple[CallSite, ...]
    was_erased: list[CallSite]

    def __init__(self) -> None:
        self.call_ids = []
        self.call_sites = {}
        self.decisions = DecisionSet()
        self.was_erased = []
        self.callgraph = ()
        self.seed = random.randint(0, 1000000)
        # self.seed = 970056
        print(f"seed: {self.seed}")
        self.rng = random.Random(self.seed)

    def advice(self, id: int, default: bool) -> bool:
        decision = default

        # call_site = self.call_sites[id]
        # if call_site.caller != "f":
        #     decision = False
        # else:
        # randomly set decision to true or false
        decision = self.rng.choice([True, False])

        self.decisions.add_decision(self.call_sites[id], decision)
        return decision

    def push(self, id: int, call_site: CallSite) -> None:
        self.call_ids.append(id)
        self.call_sites[id] = call_site

    def pop(self, defaultOrderID: int) -> int:
        self.call_ids = list(
            sorted(self.call_ids, key=lambda id: self.call_sites[id].caller)
        )
        # randomly select a call site to pop
        # import random
        # idx = self.rng.randint(0, len(self.call_ids) - 1)
        return self.call_ids.pop()

    def erase(self, ID: int) -> None:
        self.call_ids.remove(ID)
        self.was_erased.append(self.call_sites.pop(ID))

    def start(self) -> PluginSettings:
        return PluginSettings(
            report_callgraph_at_end=True,
            # no_duplicate_calls=False,
        )

    def end(self, callgraph: tuple[CallSite, ...]) -> None:
        self.callgraph = self.callgraph + callgraph


#######
# API #
#######


def setup_parser(subparser: _SubParsersAction[ArgumentParser]) -> ArgumentParser:
    return subparser.add_parser("test", help="test inlining")


def get_binary_text_size(binary_path: str) -> int:
    # get the text section size of the binary
    return int(
        sp.run(
            f"""objdump -h {binary_path}  | awk '$2==".text"{{print strtonum("0x"$3)}}'""",
            shell=True,
            stdout=sp.PIPE,
        )
        .stdout.decode("utf8")
        .strip()
    )


def run_inlining(
    compiler: str,
    args: ANS,
) -> CompilationResult[CompilationOutputType]:
    # Basic setup
    log_file = args.log
    decision_file = args.decision
    erased_file = args.erased
    final_callgraph_file = args.final_callgraph
    cli_args = args.cli

    # IO
    stdout = tempfile.NamedTemporaryFile()
    stderr = tempfile.NamedTemporaryFile()

    # parse command
    command = shlex.join([compiler] + cli_args)
    settings, files, comp_output = parse_compilation_setting_from_string(command)

    # at O0 we don't use the callbacks
    if settings.opt_level == OptLevel.O0:
        Logger.warn("Optimization level is O0, will run with clang defaults.")
        sp.run(command, shell=True, stdout=stdout, stderr=stderr)
        new_comp_output = SimpleNamespace()
        new_comp_output.stdout_stderr_output = (
            f"{stdout.read().decode('utf-8')}\n{stderr.read().decode('utf-8')}"
        )
        return new_comp_output  # type: ignore

    # generate a runner
    run_impl = gen_run_impl(stdout, stderr, files, comp_output, settings)

    # create the default callbacks
    callbacks = TestInliningCallBacks()
    if args.verbose or args.verbose_verbose:
        callbacks = VerboseCallBacks(callbacks, args.verbose_verbose)  # type: ignore

    # run inlining
    result = run_impl(callbacks)  # type: ignore

    # run permutations
    default_decisions = callbacks.decisions
    Logger.info("--------------------------")
    Logger.info("Original")
    for decision in default_decisions.decisions:
        Logger.info(decision)
    Logger.info("--------------------------")
    # exit(1)
    default_erase = callbacks.was_erased
    next_to_flip = 0
    while len(default_decisions.decisions) > next_to_flip:
        new_decisions_arr = trickle_decision_flip(
            default_decisions, default_decisions.decisions[next_to_flip].call_site
        )

        for version in range(0, len(new_decisions_arr)):
            new_decisions = new_decisions_arr[version]

            Logger.info("--------------------------")
            Logger.info(f"Flip {next_to_flip} Version {version}")
            for decision in new_decisions.decisions:
                Logger.info(decision)
            Logger.info("--------------------------")
            # store instructions
            new_decision_file = f"out/instructions_{next_to_flip}_v_{version}.log"
            decision_log(new_decision_file, new_decisions)
            # run the replay inlining
            replay_callbacks = ReplayInliningCallBacks(
                False,
                False,
                new_decisions,
                default_erase,
                PluginSettings(
                    report_callgraph_at_end=True,
                    # no_duplicate_calls=False,
                ),
            )
            if args.verbose or args.verbose_verbose:
                replay_callbacks = VerboseCallBacks(
                    replay_callbacks, args.verbose_verbose
                )  # type: ignore
            replay_result = run_impl(replay_callbacks)  # type: ignore
            Logger.debug(replay_result.stdout_stderr_output)
        next_to_flip += 1

    # log results
    if decision_file is not None:
        decision_log(decision_file, callbacks.decisions)

    if erased_file is not None:
        erased_log(erased_file, callbacks.was_erased)

    if final_callgraph_file is not None:
        callgraph_log(final_callgraph_file, callbacks.callgraph)

    if log_file is not None:
        result_log(log_file, result.stdout_stderr_output)

    return result
