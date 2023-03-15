from __future__ import annotations

import networkx as nx
from dataclasses import dataclass, field
from copy import deepcopy
import pydot

from utils.callsite import CallSite
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


# class CallGraph:
#     """
#     A call graph that uses a pair of ID, callsite
#     to represent the call graph

#     map of id -> callsite
#     call_sites: dict[int, CallSite]

#     map of id -> edge
#     edges: dict[int, CallGraph.Edge]

#     list of nodes
#     nodes: list[CallGraph.Node]
#     """

#     call_sites: dict[int, CallSite]

#     top_nodes: list[CallGraph.Node]
#     nodes: list[CallGraph.Node]
#     edges: dict[int, CallGraph.Edge]

#     @dataclass
#     class Node:
#         name: str
#         incoming: list[CallGraph.Edge] = field(default_factory=list)
#         outgoing: list[CallGraph.Edge] = field(default_factory=list)

#         def get_incoming(self, allow_shadowed: bool = False) -> list[CallGraph.Edge]:
#             if allow_shadowed:
#                 return self.incoming
#             else:
#                 return [edge for edge in self.incoming if not edge.shadow]
        
#         def get_outgoing(self, allow_shadowed: bool = False) -> list[CallGraph.Edge]:
#             if allow_shadowed:
#                 return self.outgoing
#             else:
#                 return [edge for edge in self.outgoing if not edge.shadow]

#     @dataclass#
#     class Edge:
#         call_site_id: int
#         location: str
#         head: CallGraph.Node
#         tail: CallGraph.Node
#         shadow: bool = False

#         def __str__(self) -> str:
#             return f"{self.head.name} -> {self.tail.name} @ {self.location}"

#     def __init__(self) -> None:
#         self.call_sites = {}
#         self.top_nodes = []
#         self.nodes = []
#         self.edges = {}

#     def empty(self) -> bool:
#         return len(self.call_sites) == 0

#     def add_call_site(self, id: int, call_site: CallSite) -> None:
#         assert id not in self.edges
#         self.call_sites[id] = call_site

#         # check if caller is not in the graph
#         caller = next(
#             (node for node in self.nodes if node.name == call_site.caller), None
#         )
#         if caller is None:
#             caller = CallGraph.Node(call_site.caller)
#             self.nodes.append(caller)
#             self.top_nodes.append(caller)

#         # check if callee is not in the graph
#         callee = next(
#             (node for node in self.nodes if node.name == call_site.callee), None
#         )
#         if callee is None:
#             callee = CallGraph.Node(call_site.callee)
#             self.nodes.append(callee)

#         # add edge
#         edge = CallGraph.Edge(id, call_site.loc, caller, callee)
#         self.edges[id] = edge

#         # add edge to caller and callee
#         caller.outgoing.append(edge)
#         callee.incoming.append(edge)

#         # remove callee from top nodes
#         if callee in self.top_nodes:
#             self.top_nodes.remove(callee)

#     def mark_id_as_shadowed(self, id: int) -> None:
#         self.edges[id].shadow = True

#     def pop_call_site(self, id: int) -> CallSite:
#         assert id in self.edges

#         edges = self.edges.pop(id)
#         caller = edges.head
#         callee = edges.tail
        
#         # remove edge from caller and callee
#         if edges in caller.outgoing:
#             caller.outgoing.remove(edges)
#         if edges in callee.incoming:
#             callee.incoming.remove(edges)

#         if len(caller.incoming) == 0:
#             if len(caller.outgoing) == 0:
#                 self.nodes.remove(caller)
#             if caller in self.top_nodes:
#                 self.top_nodes.remove(caller)

#         if len(callee.incoming) == 0:
#             if len(callee.outgoing) == 0:
#                 self.nodes.remove(callee)
#             elif callee not in self.top_nodes:
#                 self.top_nodes.append(callee)

#         return self.call_sites.pop(id)

#     def get_top_nodes(self, allow_shadowed: bool = False) -> list[CallGraph.Node]:
#         if allow_shadowed:
#             return self.top_nodes
#         else:
#             return [node for node in self.top_nodes if len(node.get_outgoing(False)) != 0]

#     def __str__(self) -> str:
#         output = ""
#         for id, edge in self.edges.items():
#             output += f"{id} ) {edge}\n"
#         return output
