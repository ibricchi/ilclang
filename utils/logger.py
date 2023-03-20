class Logger:
    enable_debug = False
    
    @staticmethod
    def info(*pos, **args) -> None:
        print(*pos, **args)
    
    @staticmethod
    def debug(*pos, **args) -> None:
        if Logger.enable_debug:
            # print in blue
            print(f"\033[94m", end="")
            print(*pos, **args)
            print(f"\033[0m", end="")
    
    @staticmethod
    def warn(*pos, **args) -> None:
        print(f"\033[93m", end="")
        print(*pos, **args)
        print(f"\033[0m", end="")

    @staticmethod
    def error(*pos, **args) -> None:
        print(f"\033[91m", end="")
        print(*pos, **args)
        print(f"\033[0m", end="")

    @staticmethod
    def fatal(*pos, **args) -> None:
        print(f"\033[91m", end="")
        print(*pos, **args)
        print(f"\033[0m", end="")
        exit(1)