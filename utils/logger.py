class Logger:
    enable_debug = False
    
    @staticmethod
    def info(*args) -> None:
        print(*args)
    
    @staticmethod
    def debug(*args) -> None:
        if Logger.enable_debug:
            # print in blue
            print(f"\033[94m", end="")
            print(*args)
            print(f"\033[0m", end="")
    
    @staticmethod
    def warn(*args) -> None:
        print(f"\033[93m", end="")
        print(*args)
        print(f"\033[0m", end="")

    @staticmethod
    def error(*args) -> None:
        print(f"\033[91m", end="")
        print(*args)
        print(f"\033[0m", end="")

    @staticmethod
    def fatal(*args) -> None:
        print(f"\033[91m", end="")
        print(*args)
        print(f"\033[0m", end="")
        exit(1)