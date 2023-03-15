from pyllinliner.inlinercontroller import InliningControllerCallBacks
from utils.callsite import CallGraph, CallSite


class TopDownCallBacks(InliningControllerCallBacks):
    callgraph: CallGraph

    def __init__(self) -> None:
        self.callgraph = CallGraph()

    def advice(self, id: int, default: bool) -> bool:
        self.callgraph.pop_call_site(id)
        return default

    def push(self, id: int, caller: str, callee: str, loc: str) -> None:
        call_site = CallSite(caller, callee, loc)
        self.callgraph.add_call_site(id, call_site)

    def pop(self) -> int:
        if len(self.callgraph.get_top_nodes()) > 0:
            top_node = self.callgraph.get_top_nodes()[0]
            outgoing = top_node.get_outgoing()[0]
            call_site_id = outgoing.call_site_id
            self.callgraph.mark_id_as_shadowed(call_site_id)
            return call_site_id
        else:
            # we may not have a top node if we only have recursive calls left
            # in this case, we just pick the call site with the least callers
            top = -1
            min_callers = 100000000
            for node in self.callgraph.nodes:
                if len(node.get_outgoing()) > 0 and len(node.get_incoming()) < min_callers:
                    top = node.get_outgoing()[0].call_site_id
                    min_callers = len(node.get_incoming())

            self.callgraph.mark_id_as_shadowed(top)
            return top

    def erase(self, ID: int) -> None:
        self.callgraph.pop_call_site(ID)
