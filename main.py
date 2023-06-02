#!/usr/bin/env python3
import argparse
import os
import sys

from diopter.compiler import CompilationOutputType, CompilationResult

from ilclang.controllers import (
    default,
    full_replay,
    no_inline,
    perm,
    random,
    replay,
    stats_replay,
    test,
)
from ilclang.utils.logger import Logger


def main() -> None:
    parser = argparse.ArgumentParser(description="ILC Compiler")
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="enable verbose output",
    )
    parser.add_argument(
        "-vv",
        "--verbose-verbose",
        action="store_true",
        help="enable verbose output for c++ plugin aswell",
    )

    # add subparser
    subparsers = parser.add_subparsers(
        dest="mode", help="compilation mode", required=True
    )
    parser_default = default.setup_parser(subparsers)
    parser_no_inline = no_inline.setup_parser(subparsers)
    parser_random_inline = random.setup_parser(subparsers)
    parser_full_replay = full_replay.setup_parser(subparsers)
    parser_perm = perm.setup_parser(subparsers)
    parser_replay = replay.setup_parser(subparsers)
    parser_stats_replay = stats_replay.setup_parser(subparsers)
    parser_test = test.setup_parser(subparsers)

    for p in [
        parser_default,
        parser_no_inline,
        parser_random_inline,
        parser_full_replay,
        parser_perm,
        parser_replay,
        parser_stats_replay,
        parser_test,
    ]:
        p.add_argument(
            "-p",
            "--prefix",
            type=str,
            help="path to folder containing clang",
            default="",
        )
        p.add_argument("-l", "--log", type=str, help="log output file")
        p.add_argument("-d", "--decision", type=str, help="decision output file")
        p.add_argument("-e", "--erased", type=str, help="erased output file")
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

    if args.verbose or args.verbose_verbose:
        Logger.enable_debug = True

    if sys.argv[0].endswith("++"):
        compiler = os.path.join(args.prefix, "clang++")
    else:
        compiler = os.path.join(args.prefix, "clang")

    result: CompilationResult[CompilationOutputType]  # type: ignore
    if args.mode == "no-inline":
        result = no_inline.run_inlining(compiler, args)
    elif args.mode == "random-inline":
        result = random.run_inlining(compiler, args)
    elif args.mode == "default":
        result = default.run_inlining(compiler, args)
    elif args.mode == "full-replay":
        result = full_replay.run_inlining(compiler, args)
    elif args.mode == "perm":
        result = perm.run_inlining(compiler, args)
    elif args.mode == "replay":
        result = replay.run_inlining(compiler, args)
    elif args.mode == "stats-replay":
        result = stats_replay.run_inlining(compiler, args)
    elif args.mode == "test":
        result = test.run_inlining(compiler, args)
    else:
        Logger.fatal(f"Invalid mode {args.mode}")

    stdout = result.stdout_stderr_output
    if not args.verbose and not args.verbose_verbose:
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
