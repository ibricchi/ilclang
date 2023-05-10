from pyllinliner.inlinercontroller import CallSite

from ilclang.utils.decision import DecisionSet
from ilclang.utils.logger import Logger


def decision_log(decision_file: str, decisions: DecisionSet) -> None:
    Logger.debug("Writing decisions to", decision_file)
    with open(decision_file, "w") as f:
        f.write(f"{decisions}")


def erased_log(erased_file: str, was_erased: list[CallSite]) -> None:
    Logger.debug("Writing erased callsites to", erased_file)
    with open(erased_file, "w") as f:
        for callsite in was_erased:
            f.write(f"{callsite}\n")


def callgraph_log(final_callgraph_file: str, callgraph: tuple[CallSite, ...]) -> None:
    Logger.debug("Writing final callgraph to", final_callgraph_file)
    with open(final_callgraph_file, "w") as f:
        for callsite in callgraph:
            f.write(f"{callsite.caller} -> {callsite.callee} @ {callsite.location}\n")


def result_log(log_file: str, result: str) -> None:
    Logger.debug("Writing log to", log_file)
    with open(log_file, "w") as f:
        f.write(result)
