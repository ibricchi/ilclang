class Logger:
    enable_debug = False

    @staticmethod
    def info(*pos, **args) -> None:  # type: ignore
        print(*pos, **args)

    @staticmethod
    def debug(*pos, **args) -> None:  # type: ignore
        if Logger.enable_debug:
            # print in blue
            print("\033[94m", end="")
            print(*pos, **args)
            print("\033[0m", end="")

    @staticmethod
    def warn(*pos, **args) -> None:  # type: ignore
        print("\033[93m", end="")
        print(*pos, **args)
        print("\033[0m", end="")

    @staticmethod
    def error(*pos, **args) -> None:  # type: ignore
        print("\033[91m", end="")
        print(*pos, **args)
        print("\033[0m", end="")

    @staticmethod
    def fatal(*pos, **args) -> None:  # type: ignore
        print("\033[91m", end="")
        print(*pos, **args)
        print("\033[0m", end="")
        exit(1)
