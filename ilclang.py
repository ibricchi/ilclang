#!/usr/bin/env python3

import argparse
import sys
import os

from utils.logger import Logger

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='ILC Compiler')
    parser.add_argument('-v', '--verbose', action='store_true', help='enable verbose output')

    subparsers = parser.add_subparsers(dest='mode', help='compilation mode', required=True)
    
    # subparser for no-inline mode
    parser_no_inline = subparsers.add_parser('no-inline', help='no inlining performed')

    # subparser for random-inline mode
    parser_random_inline = subparsers.add_parser('random-inline', help='randomly flip decision to inline')
    parser_random_inline.add_argument('flip_rate', type=float, help='rate of flipping decision')

    for p in [parser_no_inline, parser_random_inline]:
        p.add_argument('-p', '--prefix', type=str, help='path to folder containing clang', default='')
        p.add_argument('-l', '--log', type=str, help='log output file')
        p.add_argument('-d', '--decision', type=str, help='decision output file')
        p.add_argument('-fcg', '--final-callgraph', type=str, help='final callgraph output file')
        p.add_argument('-lto', help='run in lto mode', action='store_true')
        p.add_argument('-c', '--cli', nargs=argparse.REMAINDER, help='compiler arguments', required=True)

    args = parser.parse_args()

    if args.verbose:
        Logger.enable_debug = True

    if sys.argv[0].endswith('++'):
        compiler = os.path.join(args.prefix, 'clang++')
    else:
        compiler = os.path.join(args.prefix, 'clang')

    if args.mode == 'no-inline':
        from controllers.no_inline import run_no_inlining
        run_no_inlining(compiler, args.log, args.decision, args.final_callgraph, args.lto, args.cli)
    elif args.mode == 'random-inline':
        from controllers.random import run_random_inlining
        run_random_inlining(compiler, args.log, args.decision, args.final_callgraph, args.lto, args.cli, args.flip_rate)
    else:
        Logger.fatal(f"Invalid mode {args.mode}")
