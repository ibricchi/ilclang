from pyllinliner.compiler_wrapper import CompileCommand, CompilerConfig


class ToggleableCompilerWrapper(CompileCommand):
    use_plugin: bool

    def __init__(self, arguments: str, config: CompilerConfig) -> None:
        super().__init__(arguments, config)
        self.use_plugin = True

    def disable_plugin(self) -> None:
        if self.use_plugin:
            self.use_plugin = False
            self.command.remove(f"-fpass-plugin={self.config.plugin_path}")

    def enable_plugin(self) -> None:
        if not self.use_plugin:
            self.use_plugin = True
            self.command.append(f"-fpass-plugin={self.config.plugin_path}")
