#!/usr/bin/env python3

import argparse
import os
import sys

from diopter.compiler import CompilationOutputType, CompilationResult

from utils.logger import Logger


def main() -> None:
    parser = argparse.ArgumentParser(description="ILC Compiler")
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="enable verbose output"
    )

    subparsers = parser.add_subparsers(
        dest="mode", help="compilation mode", required=True
    )

    # subparser for no-inline mode
    parser_no_inline = subparsers.add_parser("no-inline", help="no inlining performed")

    # subparser for random-inline mode
    parser_random_inline = subparsers.add_parser(
        "random-inline", help="randomly flip decision to inline"
    )
    parser_random_inline.add_argument(
        "flip_rate", type=float, help="rate of flipping decision"
    )
    parser_random_inline.add_argument("-s", "--seed", type=int, help="random seed")

    # subparser for random-clang-pgo mode
    parser_random_clang_pgo = subparsers.add_parser(
        "random-clang-pgo", help="randomly flip decision to inline"
    )
    parser_random_clang_pgo.add_argument("pgo_file", type=str, help="path to pgo file")
    parser_random_clang_pgo.add_argument(
        "flip_rate", type=float, help="rate of flipping decision"
    )
    parser_random_clang_pgo.add_argument("-s", "--seed", type=int, help="random seed")

    for p in [parser_no_inline, parser_random_inline, parser_random_clang_pgo]:
        p.add_argument(
            "-p",
            "--prefix",
            type=str,
            help="path to folder containing clang",
            default="",
        )
        p.add_argument("-l", "--log", type=str, help="log output file")
        p.add_argument("-d", "--decision", type=str, help="decision output file")
        p.add_argument(
            "-fcg", "--final-callgraph", type=str, help="final callgraph output file"
        )
        p.add_argument(
            "-c",
            "--cli",
            nargs=argparse.REMAINDER,
            help="compiler arguments",
            required=True,
        )

    args = parser.parse_args()

    if args.verbose:
        Logger.enable_debug = True

    if sys.argv[0].endswith("++"):
        compiler = os.path.join(args.prefix, "clang++")
    else:
        compiler = os.path.join(args.prefix, "clang")

    result: CompilationResult[CompilationOutputType]  # type: ignore
    if args.mode == "no-inline":
        from controllers.no_inline import run_no_inlining

        result = run_no_inlining(
            compiler, args.log, args.decision, args.final_callgraph, args.cli
        )
    elif args.mode == "random-inline":
        from controllers.random import run_random_inlining

        result = run_random_inlining(
            compiler,
            args.log,
            args.decision,
            args.final_callgraph,
            args.cli,
            args.flip_rate,
            args.seed,
        )
    elif args.mode == "random-clang-pgo":
        from controllers.random_clang_pgo import run_random_clang_pgo  # type: ignore

        result = run_random_clang_pgo(
            compiler,
            args.log,
            args.decision,
            args.final_callgraph,
            args.cli,
            args.pgo_file,
            args.flip_rate,
            args.seed,
        )
    else:
        Logger.fatal(f"Invalid mode {args.mode}")

    stdout = result.stdout_stderr_output
    if not args.verbose:
        new_stdout = []
        for line in stdout.splitlines():
            if "DEBUG (PLUGIN):" in line:
                continue
            else:
                new_stdout.append(line)
        stdout = "\n".join(new_stdout)

    stdout.strip()

    if stdout != "":
        Logger.info(stdout)


def prof_main() -> None:
    import cProfile
    import pstats
    from pstats import SortKey

    cProfile.run("main()", "restats")
    p = pstats.Stats("restats")

    p.sort_stats(SortKey.TIME)
    p.dump_stats(filename="restats")


if __name__ == "__main__":
    # prof_main()
    main()
