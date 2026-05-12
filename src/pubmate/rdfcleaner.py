import logging
from pathlib import Path
from collections.abc import Iterable
from typing import Generator, Tuple

import rdflib
from rdflib.namespace import RDFS


logging.basicConfig(level=logging.INFO, format="::%(levelname)s:: %(message)s")
logger = logging.getLogger(__name__)

SCHEMA = rdflib.Namespace("http://schema.org/")


# ------------------------------------------------------------
# Translation cleanup
# ------------------------------------------------------------
def add_language(g: rdflib.Graph, base_namespace: str, property_map: dict[str, str]) -> None:
    if not (base_namespace.endswith("/") or base_namespace.endswith("#")):
        raise ValueError("base_namespace must end with '/' or '#'")

    def build_values_block() -> str:
        return " ".join(f'("{k}" <{v}>)' for k, v in property_map.items())

    TRANSLATIONS = f"<{base_namespace}hasTranslation>"
    PROPERTY_NAME = f"<{SCHEMA.identifier}>"
    LANGUAGE = f"<{SCHEMA.inLanguage}>"
    TRANSLATED_VALUE = f"<{base_namespace}hasTranslatedValue>"
    values_rows = build_values_block()

    logger.info("Running SPARQL CONSTRUCT to convert translations into language-tagged literals")

    construct_query = f"""
        CONSTRUCT {{
            ?subject ?predicate ?literal .
        }}
        WHERE {{
            ?subject {TRANSLATIONS} ?t .

            ?t {PROPERTY_NAME} ?propName ;
            {LANGUAGE} ?lang ;
            {TRANSLATED_VALUE} ?value .

            VALUES (?propName ?predicate) {{
                {values_rows}
            }}

            BIND( STRLANG(?value, ?lang) AS ?literal )
        }}
    """
    constructed = g.query(construct_query)

    for triple in constructed:
        g.add(triple)

    logger.info("Deleting original translation nodes")

    delete_query = f"""
        DELETE {{
            ?subject {TRANSLATIONS} ?t .
            ?t ?p ?o .
        }}
        WHERE {{
            ?subject {TRANSLATIONS} ?t .
            ?t ?p ?o .
        }}
    """
    g.update(delete_query)


def clean_graph(g: rdflib.Graph, base_namespace: str, property_map: dict[str, str]) -> None:
    logger.info("Cleaning graph: converting translation structures")
    add_language(g, base_namespace, property_map=property_map)


# ------------------------------------------------------------
# Graph I/O
# ------------------------------------------------------------
def read_graph(source: str, format: str | None = None) -> rdflib.Graph:
    """
    Load any RDF format rdflib supports.
    If format is None, rdflib will auto-detect based on file extension.
    """
    g = rdflib.Graph()
    logger.info(f"Loading RDF graph from {source}")

    g.parse(source, format=format)
    logger.info(f"Loaded {len(g)} triples")

    return g


def serialize_graph(g: rdflib.Graph, output_path: str) -> None:
    """
    Always serialize to Turtle (.ttl).
    Overwrites existing files.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info(f"Writing graph to {output_path}")
    g.serialize(destination=str(output_path), format="turtle")


# ------------------------------------------------------------
# Assertion splitting
# ------------------------------------------------------------
def expand_iri_or_curie(g: rdflib.Graph, value: str | rdflib.URIRef) -> rdflib.URIRef:
    if isinstance(value, rdflib.URIRef):
        return value

    try:
        return rdflib.URIRef(g.namespace_manager.expand_curie(value))
    except Exception:
        return rdflib.URIRef(value)


def _term_id(subject: rdflib.URIRef) -> str:
    subject_str = str(subject)
    return subject_str.split("#")[-1] if "#" in subject_str else subject_str.split("/")[-1]


def _copy_subject_description(
    source: rdflib.Graph,
    target: rdflib.Graph,
    subject: rdflib.term.Identifier,
    visited: set[rdflib.term.Identifier],
) -> None:
    if subject in visited:
        return

    visited.add(subject)

    for triple in source.triples((subject, None, None)):
        target.add(triple)

        _, _, obj = triple
        if isinstance(obj, rdflib.BNode):
            _copy_subject_description(source, target, obj, visited)


def _new_assertion_graph(g: rdflib.Graph) -> rdflib.Graph:
    assertion_graph = rdflib.Graph()
    for prefix, namespace in g.namespaces():
        assertion_graph.bind(prefix, namespace)
    return assertion_graph


def subjects_from_predicates(
    g: rdflib.Graph,
    predicates: Iterable[str | rdflib.URIRef],
) -> Generator[rdflib.URIRef, None, None]:
    seen: set[rdflib.URIRef] = set()

    for predicate_value in predicates:
        predicate = expand_iri_or_curie(g, predicate_value)
        logger.info(f"Finding subjects listed by predicate {predicate}")

        for _, _, subject in g.triples((None, predicate, None)):
            if not isinstance(subject, rdflib.URIRef):
                logger.warning(f"Ignoring non-IRI object selected by {predicate}: {subject}")
                continue

            if subject in seen:
                continue

            seen.add(subject)
            yield subject


def split_subjects_into_assertions(
    g: rdflib.Graph,
    subjects: Iterable[str | rdflib.URIRef],
) -> Generator[Tuple[str, rdflib.Graph], None, None]:
    seen: set[rdflib.URIRef] = set()

    for subject_value in subjects:
        subject = expand_iri_or_curie(g, subject_value)

        if subject in seen:
            continue
        seen.add(subject)

        if not list(g.triples((subject, None, None))):
            logger.warning(f"Skipping selected subject with no triples in graph: {subject}")
            continue

        term_id = _term_id(subject)
        logger.info(f"Creating assertion graph for {term_id}")

        assertion_graph = _new_assertion_graph(g)
        _copy_subject_description(g, assertion_graph, subject, set())

        yield term_id, assertion_graph


def split_into_assertions(
    g: rdflib.Graph,
    all_classes: set[str],
) -> Generator[Tuple[str, rdflib.Graph], None, None]:
    subjects: list[rdflib.URIRef] = []

    for clss in all_classes:
        parent = expand_iri_or_curie(g, clss)

        logger.info(f"Finding direct subclasses of {parent}")

        for subclass, _, _ in g.triples((None, RDFS.subClassOf, parent)):
            if isinstance(subclass, rdflib.URIRef):
                subjects.append(subclass)

    yield from split_subjects_into_assertions(g, subjects)
