from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CallSite:
    """
    A call site in the call graph
    """

    caller: str
    callee: str
    loc: str

    def __str__(self) -> str:
        return f"{self.caller} -> {self.callee} @ {self.loc}"


class CallGraph:
    """
    A call graph that uses a pair of ID, callsite
    to represent the call graph

    map of id -> callsite
    call_sites: dict[int, CallSite]

    map of id -> edge
    edges: dict[int, CallGraph.Edge]

    list of nodes
    nodes: list[CallGraph.Node]
    """

    call_sites: dict[int, CallSite]

    top_nodes: list[CallGraph.Node]
    nodes: list[CallGraph.Node]
    edges: dict[int, CallGraph.Edge]

    @dataclass
    class Node:
        name: str
        incoming: list[CallGraph.Edge] = field(default_factory=list)
        outgoing: list[CallGraph.Edge] = field(default_factory=list)

        def get_incoming(self, allow_shadowed: bool = False) -> list[CallGraph.Edge]:
            if allow_shadowed:
                return self.incoming
            else:
                return [edge for edge in self.incoming if not edge.shadow]
        
        def get_outgoing(self, allow_shadowed: bool = False) -> list[CallGraph.Edge]:
            if allow_shadowed:
                return self.outgoing
            else:
                return [edge for edge in self.outgoing if not edge.shadow]

    @dataclass
    class Edge:
        call_site_id: int
        location: str
        head: CallGraph.Node
        tail: CallGraph.Node
        shadow: bool = False

        def __str__(self) -> str:
            return f"{self.head.name} -> {self.tail.name} @ {self.location}"

    def __init__(self) -> None:
        self.call_sites = {}
        self.top_nodes = []
        self.nodes = []
        self.edges = {}

    def empty(self) -> bool:
        return len(self.call_sites) == 0

    def add_call_site(self, id: int, call_site: CallSite) -> None:
        assert id not in self.edges
        self.call_sites[id] = call_site

        # check if caller is not in the graph
        caller = next(
            (node for node in self.nodes if node.name == call_site.caller), None
        )
        if caller is None:
            caller = CallGraph.Node(call_site.caller)
            self.nodes.append(caller)
            self.top_nodes.append(caller)

        # check if callee is not in the graph
        callee = next(
            (node for node in self.nodes if node.name == call_site.callee), None
        )
        if callee is None:
            callee = CallGraph.Node(call_site.callee)
            self.nodes.append(callee)

        # add edge
        edge = CallGraph.Edge(id, call_site.loc, caller, callee)
        self.edges[id] = edge

        # add edge to caller and callee
        caller.outgoing.append(edge)
        callee.incoming.append(edge)

        # remove callee from top nodes
        if callee in self.top_nodes:
            self.top_nodes.remove(callee)

    def mark_id_as_shadowed(self, id: int) -> None:
        self.edges[id].shadow = True

    def pop_call_site(self, id: int) -> CallSite:
        assert id in self.edges

        edges = self.edges.pop(id)
        caller = edges.head
        callee = edges.tail
        
        # remove edge from caller and callee
        if edges in caller.outgoing:
            caller.outgoing.remove(edges)
        if edges in callee.incoming:
            callee.incoming.remove(edges)

        if len(caller.incoming) == 0:
            if len(caller.outgoing) == 0:
                self.nodes.remove(caller)
            if caller in self.top_nodes:
                self.top_nodes.remove(caller)

        if len(callee.incoming) == 0:
            if len(callee.outgoing) == 0:
                self.nodes.remove(callee)
            elif callee not in self.top_nodes:
                self.top_nodes.append(callee)

        return self.call_sites.pop(id)

    def get_top_nodes(self, allow_shadowed: bool = False) -> list[CallGraph.Node]:
        if allow_shadowed:
            return self.top_nodes
        else:
            return [node for node in self.top_nodes if len(node.get_outgoing(False)) != 0]

    def __str__(self) -> str:
        output = ""
        for id, edge in self.edges.items():
            output += f"{id} ) {edge}\n"
        return output
