"""A small NetworkX knowledge graph of regulation relationships.

The graph holds the facts that are awkward to retrieve from free text:

    scheme -> department          (handled_by)
    scheme -> eligibility rule    (requires_eligibility)
    scheme -> required document   (requires_document)
    scheme -> circular reference  (defined_in)

It supplements vector search; it does not replace it. The graph is cheap to
build, so it is rebuilt from the regulation records rather than stored on disk.
"""

import re
from collections.abc import Iterable, Mapping

from ai_modules.regulation_rag.errors import RagError

# Relationship names used on the graph edges.
HANDLED_BY = "handled_by"
REQUIRES_ELIGIBILITY = "requires_eligibility"
REQUIRES_DOCUMENT = "requires_document"
DEFINED_IN = "defined_in"

_SPLIT_LIST = re.compile(r"[;\n]|,(?=\s)")


def _split_items(value: str | None) -> list[str]:
    """Split "Aadhaar, Income Proof" into separate items."""
    if not value:
        return []
    parts = [part.strip(" .;,") for part in _SPLIT_LIST.split(value)]
    return [part for part in parts if part]


def build_graph(records: Iterable[Mapping]):
    """Build the graph from regulation records.

    Each record is a mapping with a scheme_name and, optionally, department,
    eligibility_criteria, required_documents and circular_reference.
    """
    try:
        import networkx as nx
    except ImportError as error:
        raise RagError(
            "networkx is not installed. Install it with: pip install -r requirements.txt"
        ) from error

    graph = nx.MultiDiGraph()

    for record in records:
        scheme = (record.get("scheme_name") or "").strip()
        if not scheme:
            continue

        graph.add_node(scheme, kind="scheme")

        department = (record.get("department") or "").strip()
        if department:
            graph.add_node(department, kind="department")
            graph.add_edge(scheme, department, relation=HANDLED_BY)

        circular = (record.get("circular_reference") or "").strip()
        if circular:
            graph.add_node(circular, kind="circular")
            graph.add_edge(scheme, circular, relation=DEFINED_IN)

        for rule in _split_items(record.get("eligibility_criteria")):
            graph.add_node(rule, kind="eligibility")
            graph.add_edge(scheme, rule, relation=REQUIRES_ELIGIBILITY)

        for document in _split_items(record.get("required_documents")):
            graph.add_node(document, kind="document")
            graph.add_edge(scheme, document, relation=REQUIRES_DOCUMENT)

    return graph


_SENTENCE = {
    HANDLED_BY: "{scheme} is handled by the {target} department.",
    DEFINED_IN: "{scheme} is defined in {target}.",
    REQUIRES_ELIGIBILITY: "{scheme} eligibility includes: {target}.",
    REQUIRES_DOCUMENT: "{scheme} requires the document: {target}.",
}


def graph_context(graph, scheme_names: Iterable[str], limit: int = 12) -> list[str]:
    """Describe what the graph knows about these schemes, as short sentences."""
    if graph is None:
        return []

    lines: list[str] = []
    for scheme in dict.fromkeys(scheme_names):  # de-duplicate, keep order
        if not scheme or scheme not in graph:
            continue
        for _, target, data in graph.out_edges(scheme, data=True):
            template = _SENTENCE.get(data.get("relation"))
            if template:
                lines.append(template.format(scheme=scheme, target=target))
            if len(lines) >= limit:
                return lines
    return lines


class KnowledgeGraphService:
    """Holds the graph in memory and rebuilds it when regulations change."""

    def __init__(self, records: Iterable[Mapping] | None = None) -> None:
        self._graph = None
        if records is not None:
            self.refresh(records)

    def refresh(self, records: Iterable[Mapping]) -> None:
        """Rebuild the graph from the current regulation records."""
        self._graph = build_graph(records)

    @property
    def graph(self):
        return self._graph

    def context_for(self, scheme_names: Iterable[str], limit: int = 12) -> list[str]:
        """Graph facts about the schemes that retrieval found."""
        if self._graph is None:
            return []
        return graph_context(self._graph, scheme_names, limit=limit)
