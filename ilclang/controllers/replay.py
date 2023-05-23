from __future__ import annotations

import shlex
import subprocess as sp
import tempfile
from argparse import ArgumentParser
from argparse import Namespace as ANS
from argparse import _SubParsersAction
from dataclasses import replace
from types import SimpleNamespace
from typing import IO

from diopter.compiler import (
    CompilationOutput,
    CompilationOutputType,
    CompilationResult,
    ObjectCompilationOutput,
    OptLevel,
    SourceFile,
    parse_compilation_setting_from_string,
)
from pyllinliner.inlinercontroller import (
    InlinerController,
    PluginSettings,
    InlinerState,
    proto,
)

from ilclang.utils.decision import DecisionSet
from ilclang.utils.decision_file import load_decision_file
from ilclang.utils.logger import Logger
from ilclang.utils.run_log import callgraph_log, decision_log, erased_log, result_log
from ilclang.utils.runner import gen_run_impl_base

#######
# API #
#######


def setup_parser(subparser: _SubParsersAction[ArgumentParser]) -> ArgumentParser:
    parser_replay = subparser.add_parser("replay", help="replay inlining decisions")
    parser_replay.add_argument("replay_file", type=str, help="path to replay file")
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

    # IO
    stdout = tempfile.NamedTemporaryFile()
    stderr = tempfile.NamedTemporaryFile()

    replay_decisions = load_decision_file(replay_file).to_pyll_tuple()

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

    # generate a runner
    plugin_settings = PluginSettings(
        report_callgraph_at_end=False,
        enable_debug_logs=args.verbose_verbose,
        replay=replay_decisions,
        record_history=decision_file is not None,
    )

    final_decisions: DecisionSet = DecisionSet()

    def replay_base_runner(
        controller: InlinerController,
        sources: SourceFile | tuple[ObjectCompilationOutput, ...],
        comp_output: CompilationOutput,
        stdout: IO[bytes],
        stderr: IO[bytes],
    ) -> CompilationResult[CompilationOutputType]:
        nonlocal plugin_settings
        nonlocal final_decisions

        inliner, _ = controller.run_on_program_interactive(
            sources, comp_output, plugin_settings, stdout=stdout, stderr=stderr
        )

        while inliner.inliner_state is not InlinerState.Finish:
            while inliner.inliner_state is InlinerState.WaitForPopReply:
                default_order_id = inliner.defaultOrderNext()
                assert default_order_id is not None
                advice_request: proto.RequestAdvice | None = (
                    inliner.reply_to_pop_request(default_order_id, None)
                )
            if inliner.inliner_state is InlinerState.Finish:  # type: ignore
                break
            assert inliner.inliner_state is InlinerState.WaitForAdviceReply
            assert isinstance(advice_request, proto.RequestAdvice)
            inliner.reply_to_advice_request(
                advice_request.default_advice,
                push_callback=None,
                erase_callback=None,
                unattempted_callback=None,
                unsuccessful_callback=None,
                inlined_callback=None,
                inlined_with_callee_deleted_callback=None,
                end_callback=None,
            )

        if decision_file is not None:
            final_decisions = DecisionSet.from_pyll_tuple(inliner.inlining_history)
        return inliner.result()

    run_impl = gen_run_impl_base(
        stdout, stderr, files, comp_output, settings, replay_base_runner
    )
    result = run_impl()

    if decision_file is not None:
        decision_log(decision_file, final_decisions)

    if args.erased is not None:
        Logger.warn("Replay mode does not support erased file output.")
        # erased_log(args.erased, callbacks.erased)

    if final_callgraph_file is not None:
        Logger.warn("Replay mode does not support callgraph file output.")
        # callgraph_log(final_callgraph_file, callbacks.callgraph)

    if log_file is not None:
        result_log(log_file, result.stdout_stderr_output)

    return result  # type: ignore
