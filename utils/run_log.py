from utils.logger import Logger
from utils.decision import DecisionSet

def decision_log(decision_file: str, decisions: DecisionSet):
    Logger.debug("Writing decisions to", decision_file)
    with open(decision_file, "w") as f:
        f.write(f"{decisions}")

def callgraph_log(final_callgraph_file: str, callgraph: list[tuple[str, str, str]]):
    Logger.debug("Writing final callgraph to", final_callgraph_file)
    with open(final_callgraph_file, "w") as f:
        for caller, callee, loc in callgraph:
            f.write(f"{caller} -> {callee} @ {loc}\n")

def result_log(log_file: str, result: str):
    Logger.debug("Writing log to", log_file)
    with open(log_file, "w") as f:
        f.write(result)
