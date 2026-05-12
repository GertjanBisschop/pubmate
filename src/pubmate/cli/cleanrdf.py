import logging
import click

from pubmate import rdfcleaner as rdfcleaner


logging.basicConfig(level=logging.INFO, format="::%(levelname)s:: %(message)s")
logger = logging.getLogger(__name__)


@click.command()
@click.option("--input-ontology-path", required=True)
@click.option("--base-namespace", required=True)
@click.option("--term-output-path", required=True)
@click.option("--term-parent-class")
@click.option(
    "--parent-subclasses", multiple=True, help="Additional parent classes whose subclasses should be included."
)
@click.option("--subject", multiple=True, help="Subject IRI or CURIE to extract. May be provided multiple times.")
@click.option(
    "--subjects-from-predicate",
    multiple=True,
    help="Predicate IRI or CURIE whose IRI objects should be extracted. May be provided multiple times.",
)
def cli(
    input_ontology_path: str,
    base_namespace: str,
    term_output_path: str,
    term_parent_class: str | None = None,
    parent_subclasses: tuple[str, ...] | None = None,
    subject: tuple[str, ...] | None = None,
    subjects_from_predicate: tuple[str, ...] | None = None,
):
    g = rdfcleaner.read_graph(input_ontology_path)
    property_map = {
        "label": "http://www.w3.org/2000/01/rdf-schema#label",
        "name": "http://www.w3.org/2000/01/rdf-schema#label",
        "short_name": "http://schema.org/alternateName",
    }
    rdfcleaner.clean_graph(g, base_namespace=base_namespace, property_map=property_map)

    counter = 0
    parent_classes = set(parent_subclasses or ())
    if term_parent_class is not None:
        parent_classes.add(term_parent_class)

    if not parent_classes and not subject and not subjects_from_predicate:
        raise click.UsageError(
            "Provide --term-parent-class, --parent-subclasses, --subject, or --subjects-from-predicate."
        )

    selected_subjects = list(subject or ())
    selected_subjects.extend(rdfcleaner.subjects_from_predicates(g, subjects_from_predicate or ()))

    assertions = list(rdfcleaner.split_into_assertions(g, parent_classes))
    assertions.extend(rdfcleaner.split_subjects_into_assertions(g, selected_subjects))

    seen_term_ids: set[str] = set()
    for term_id, assertion in assertions:
        if term_id in seen_term_ids:
            continue
        seen_term_ids.add(term_id)
        output_path = f"{term_output_path}/{term_id}.ttl"
        rdfcleaner.serialize_graph(assertion, output_path)
        counter += 1

    logger.info(f"Processing complete: serialized {counter} assertions")


if __name__ == "__main__":
    cli()
