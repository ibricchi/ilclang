from __future__ import annotations

import os
import shlex
import tempfile
from argparse import ArgumentParser
from argparse import Namespace as ANS
from argparse import _SubParsersAction
from dataclasses import replace

from diopter.compiler import (
    CompilationOutputType,
    CompilationResult,
    ObjectCompilationOutput,
    OptLevel,
    SourceFile,
    parse_compilation_setting_from_string,
)
from pyllinliner.inlinercontroller import (
    InlinerController,
    InliningControllerCallBacks,
    PluginSettings,
)

from ilclang.controllers.default import DefaultInliningCallBacks
from ilclang.controllers.replay import ReplayInliningCallBacks
from ilclang.utils.decision_file import trickle_decision_flip
from ilclang.utils.logger import Logger
from ilclang.utils.run_log import decision_log
from ilclang.utils.verbose import VerboseCallBacks

#######
# API #
#######


def setup_parser(subparser: _SubParsersAction[ArgumentParser]) -> ArgumentParser:
    parser_perm = subparser.add_parser("perm", help="perm inlining decisions")
    parser_perm.add_argument(
        "flips", help="How many decisions to filp per permutation", type=int
    )
    return parser_perm


def run_inlining(
    compiler: str,
    args: ANS,
) -> CompilationResult[CompilationOutputType]:
    # log_file = args.log
    # decision_file = args.decision
    # final_callgraph_file = args.final_callgraph
    cli_args = args.cli

    stdout = tempfile.NamedTemporaryFile()
    stderr = tempfile.NamedTemporaryFile()

    command = shlex.join([compiler] + cli_args)
    settings, files, comp_output = parse_compilation_setting_from_string(command)

    if settings.opt_level == OptLevel.O0:
        Logger.fatal("This mode cannot be run with optimization level 0")

    source_files = tuple(file for file in files if isinstance(file, SourceFile))
    object_files = tuple(
        file for file in files if isinstance(file, ObjectCompilationOutput)
    )

    controller = InlinerController(settings)

    def run_impl(
        callbacks: InliningControllerCallBacks,
    ) -> CompilationResult[CompilationOutputType]:
        # first we clear the stdout and stderr files
        stdout.seek(0)
        stderr.seek(0)
        stdout.truncate(0)
        stderr.truncate(0)

        try:
            # then we run the program
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

        return result  # type: ignore

    # check if out directory exists
    if not os.path.exists("out"):
        os.makedirs("out")

    # run the default inlining to get the baseline decisions
    default_callbacks = DefaultInliningCallBacks(True, False)
    if args.verbose or args.verbose_verbose:
        default_callbacks = VerboseCallBacks(default_callbacks, args.verbose_verbose)  # type: ignore

    run_impl(default_callbacks)
    # default_result = run_impl(default_callbacks)

    default_decisions = default_callbacks.decisions
    default_erase = default_callbacks.was_erased
    # store the default decisions
    default_decisoin_file = "out/default_decisions.log"
    decision_log(default_decisoin_file, default_decisions)
    Logger.info("==========================")
    Logger.info("Default Decisions")
    for decision in default_decisions.decisions:
        Logger.info(decision)
    Logger.info("==========================")

    # TODO generatlize for mor than one flip
    # run each permutation
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
                False, False, new_decisions, default_erase, PluginSettings()
            )
            if args.verbose or args.verbose_verbose:
                replay_callbacks = VerboseCallBacks(
                    replay_callbacks, args.verbose_verbose
                )  # type: ignore
            replay_result = run_impl(replay_callbacks)
            Logger.debug(replay_result.stdout_stderr_output)
        next_to_flip += 1

    return replace(replay_result, stdout_stderr_output="")
