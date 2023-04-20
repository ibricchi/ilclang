#!/usr/bin/env python3

from controllers import default, no_inline, random, random_clang_pgo, replay


def main() -> None:
    import argparse
    import os
    import sys

    from diopter.compiler import CompilationOutputType, CompilationResult

    from utils.logger import Logger

    parser = argparse.ArgumentParser(description="ILC Compiler")
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="enable verbose output"
    )

    # add subparser
    subparsers = parser.add_subparsers(
        dest="mode", help="compilation mode", required=True
    )
    parser_default = default.setup_parser(subparsers)
    parser_no_inline = no_inline.setup_parser(subparsers)
    parser_random_inline = random.setup_parser(subparsers)
    parser_random_clang_pgo = random_clang_pgo.setup_parser(subparsers)
    parser_replay = replay.setup_parser(subparsers)

    for p in [
        parser_default,
        parser_no_inline,
        parser_random_inline,
        parser_random_clang_pgo,
        parser_replay,
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

    # add test subparser
    parser_test = subparsers.add_parser("test", help="test mode")
    parser_test.add_argument("replay_file", type=str, help="path to replay file")

    args = parser.parse_args()

    if args.verbose:
        Logger.enable_debug = True

    if sys.argv[0].endswith("++"):
        compiler = os.path.join(args.prefix, "clang++")
    else:
        compiler = os.path.join(args.prefix, "clang")

    result: CompilationResult[CompilationOutputType]  # type: ignore
    if args.mode == "no-inline":
        result = no_inline.run_inlining(
            compiler,
            args.log,
            args.decision,
            args.final_callgraph,
            args.cli,
            verbose=args.verbose,
        )
    elif args.mode == "random-inline":
        result = random.run_inlining(
            compiler,
            args.log,
            args.decision,
            args.final_callgraph,
            args.cli,
            args.flip_rate,
            args.seed,
            verbose=args.verbose,
        )
    elif args.mode == "random-clang-pgo":
        result = random_clang_pgo.run_inlining(
            compiler,
            args.log,
            args.decision,
            args.final_callgraph,
            args.cli,
            args.pgo_file,
            args.flip_rate,
            args.seed,
            verbose=args.verbose,
        )
    elif args.mode == "default":
        result = default.run_inlining(
            compiler,
            args.log,
            args.decision,
            args.final_callgraph,
            args.cli,
            verbose=args.verbose,
        )
    elif args.mode == "replay":
        result = replay.run_inlining(
            compiler,
            args.log,
            args.decision,
            args.final_callgraph,
            args.cli,
            args.replay_file,
            verbose=args.verbose,
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
