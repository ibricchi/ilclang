from __future__ import annotations

from dataclasses import replace
from typing import IO, Callable, Concatenate, ParamSpec

from diopter.compiler import (
    CompilationOutput,
    CompilationOutputType,
    CompilationResult,
    CompilationSetting,
    ObjectCompilationOutput,
    SourceFile,
)
from pyllinliner.inlinercontroller import InlinerController, InliningControllerCallBacks

from ilclang.utils.logger import Logger

BaseFunctionCustomArgs = ParamSpec("BaseFunctionCustomArgs")
BaseFunctionArgs = Concatenate[
    InlinerController,
    SourceFile | tuple[ObjectCompilationOutput, ...],
    CompilationOutput,
    IO[bytes],
    IO[bytes],
    BaseFunctionCustomArgs,
]


def gen_run_impl_base(
    stdout: IO[bytes],
    stderr: IO[bytes],
    files: list[SourceFile | ObjectCompilationOutput],
    comp_output: CompilationOutput,
    settings: CompilationSetting,
    base_runner: Callable[BaseFunctionArgs, CompilationResult[CompilationOutputType]],
) -> Callable[BaseFunctionCustomArgs, CompilationResult[CompilationOutputType],]:
    controller = InlinerController(settings)
    source_files = tuple(file for file in files if isinstance(file, SourceFile))
    object_files = tuple(
        file for file in files if isinstance(file, ObjectCompilationOutput)
    )

    def run_impl(
        *args: BaseFunctionCustomArgs.args, **kwargs: BaseFunctionCustomArgs.kwargs
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
                result = base_runner(
                    controller,
                    object_files,
                    comp_output,
                    stdout,
                    stderr,
                    *args,
                    **kwargs,
                )
            elif len(object_files) == 0:
                assert len(source_files) > 0, "No source files or object files provided"
                assert len(source_files) == 1, "Multiple source files provided"
                source_file = source_files[0]
                result = base_runner(
                    controller,
                    source_file,
                    comp_output,
                    stdout,
                    stderr,
                    *args,
                    **kwargs,
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

    return run_impl


def gen_run_impl(
    stdout: IO[bytes],
    stderr: IO[bytes],
    files: list[SourceFile | ObjectCompilationOutput],
    comp_output: CompilationOutput,
    settings: CompilationSetting,
) -> Callable[[InliningControllerCallBacks], CompilationResult[CompilationOutputType]]:
    def simple_base_runner(
        controller: InlinerController,
        sources: SourceFile | tuple[ObjectCompilationOutput, ...],
        comp_output: CompilationOutput,
        stdout: IO[bytes],
        stderr: IO[bytes],
        callbacks: InliningControllerCallBacks,
    ) -> CompilationResult[CompilationOutputType]:
        return controller.run_on_program_with_callbacks(
            sources, comp_output, callbacks, stdout=stdout, stderr=stderr  # type: ignore
        )

    return gen_run_impl_base(
        stdout, stderr, files, comp_output, settings, simple_base_runner  # type: ignore
    )
