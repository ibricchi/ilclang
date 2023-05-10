from __future__ import annotations

from dataclasses import replace
from tempfile import _TemporaryFileWrapper
from typing import Callable

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


def gen_run_impl(
    stdout: _TemporaryFileWrapper[bytes],
    stderr: _TemporaryFileWrapper[bytes],
    files: list[SourceFile | ObjectCompilationOutput],
    comp_output: CompilationOutput,
    settings: CompilationSetting,
) -> Callable[[InliningControllerCallBacks], CompilationResult[CompilationOutputType]]:
    controller = InlinerController(settings)
    source_files = tuple(file for file in files if isinstance(file, SourceFile))
    object_files = tuple(
        file for file in files if isinstance(file, ObjectCompilationOutput)
    )

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

    return run_impl
