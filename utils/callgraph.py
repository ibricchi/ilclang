from __future__ import annotations

import networkx as nx
from dataclasses import dataclass, field
from copy import deepcopy
import pydot

from pyllinliner.inlinercontroller import CallSite
from utils.decision import DecisionSet

class CallGraph:
    callgraph: nx.MultiDiGraph

    def __init__(self):
        self.callgraph = nx.MultiDiGraph()

    def empty(self) -> bool:
        return self.callgraph.number_of_nodes() == 0

    def add_call_site(self, callsite: CallSite, **attr):
        # add nodes if not exist
        if not self.callgraph.has_node(callsite.caller):
            self.callgraph.add_node(callsite.caller)
        if not self.callgraph.has_node(callsite.callee):
            self.callgraph.add_node(callsite.callee)
        self.callgraph.add_edge(callsite.caller, callsite.callee, callsite = callsite, **attr)
    
    def pop_call_site(self, callsite: CallSite):
        key = [key for key in self.callgraph[callsite.caller][callsite.callee] if self.callgraph[callsite.caller][callsite.callee][key]["callsite"] == callsite]
        self.callgraph.remove_edge(callsite.caller, callsite.callee, key=key)

        # remove any isolated nodes
        if self.callgraph.degree(callsite.caller) == 0:
            self.callgraph.remove_node(callsite.caller)
        if self.callgraph.degree(callsite.callee) == 0:
            self.callgraph.remove_node(callsite.callee)
    
    def get_top_nodes(self):
        return [node for node in self.callgraph.nodes if self.callgraph.in_degree(node) == 0]

    def set_edge_labels(self, fn: callable):
        for (u, v, k, d) in self.callgraph.edges(data=True, keys=True):
            self.callgraph.edges[u, v, k]["label"] = fn(d)

    def to_dot_str(self):
        # workaround for https://github.com/pydot/pydot/issues/258#issuecomment-1276492779.
        G = deepcopy(self.callgraph)
        for (u, v, k, cs) in G.edges(data="callsite", keys=True):
            G.edges[u, v, k]["callsite"] = f"\"{cs}\""

        dot = nx.nx_pydot.to_pydot(G)
        return dot.to_string()

    @staticmethod
    def from_dot_str(dot: str):
        cg = CallGraph()
        dot = pydot.graph_from_dot_data(dot)[0]
        G = nx.drawing.nx_pydot.from_pydot(dot)
        for (u, v, k, cs) in G.edges(data="callsite", keys=True):
            cs_s = G.edges[u, v, k]["callsite"].strip("\"")
            caller, _, callee, _, loc = cs_s.split(" ")
            G.edges[u, v, k]["callsite"] = CallSite(caller, callee, loc)
        cg.callgraph = G
        return cg

    @staticmethod
    def from_list_and_decisions(callgraph: list[tuple[str, str, str]], decisions: DecisionSet):
        cg = CallGraph()
        for caller, callee, loc in callgraph:
            cs = CallSite(caller, callee, loc)
            if d := decisions.decision_for(cs):
                cg.add_call_site(cs, inlined = d.inlined)
            else:
                cg.add_call_site(cs, inlined = False)

