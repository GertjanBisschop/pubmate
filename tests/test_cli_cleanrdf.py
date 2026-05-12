import rdflib
from click.testing import CliRunner
from rdflib.namespace import RDFS

from pubmate.cli import cleanrdf as cleanrdf_cli


def test_cleanrdf_cli_extracts_subjects_from_predicate(tmp_path) -> None:
    input_file = tmp_path / "input.ttl"
    output_dir = tmp_path / "out"
    input_file.write_text(
        """
        @prefix ex: <https://example.org/> .
        @prefix pehterms: <https://w3id.org/peh/terms/> .
        @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
        @prefix owl: <http://www.w3.org/2002/07/owl#> .

        [] a pehterms:EntityList ;
            pehterms:hasMatrixSubclass ex:child .

        ex:child a owl:Class ;
            rdfs:label "Child" ;
            rdfs:subClassOf ex:parent .
        """,
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        cleanrdf_cli.cli,
        [
            "--input-ontology-path",
            str(input_file),
            "--base-namespace",
            "https://w3id.org/peh/terms/",
            "--term-output-path",
            str(output_dir),
            "--subjects-from-predicate",
            "https://w3id.org/peh/terms/hasMatrixSubclass",
        ],
    )

    assert result.exit_code == 0, result.output

    output_file = output_dir / "child.ttl"
    assert output_file.exists()

    assertion = rdflib.Graph()
    assertion.parse(output_file)

    assert (
        rdflib.URIRef("https://example.org/child"),
        RDFS.label,
        rdflib.Literal("Child"),
    ) in assertion
    assert (
        rdflib.URIRef("https://example.org/child"),
        RDFS.subClassOf,
        rdflib.URIRef("https://example.org/parent"),
    ) in assertion


def test_cleanrdf_cli_serializes_duplicate_subject_once(tmp_path) -> None:
    input_file = tmp_path / "input.ttl"
    output_dir = tmp_path / "out"
    input_file.write_text(
        """
        @prefix ex: <https://example.org/> .
        @prefix pehterms: <https://w3id.org/peh/terms/> .
        @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
        @prefix owl: <http://www.w3.org/2002/07/owl#> .

        [] a pehterms:EntityList ;
            pehterms:hasMatrixSubclass ex:child .

        ex:child a owl:Class ;
            rdfs:label "Child" ;
            rdfs:subClassOf ex:parent .
        """,
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        cleanrdf_cli.cli,
        [
            "--input-ontology-path",
            str(input_file),
            "--base-namespace",
            "https://w3id.org/peh/terms/",
            "--term-output-path",
            str(output_dir),
            "--subject",
            "https://example.org/child",
            "--subjects-from-predicate",
            "https://w3id.org/peh/terms/hasMatrixSubclass",
        ],
    )

    assert result.exit_code == 0, result.output
    assert sorted(path.name for path in output_dir.glob("*.ttl")) == ["child.ttl"]
