import pathlib
import pytest
from paperfetcher.core import parse_and_filter_papers
from paperfetcher.models import PaperResult

# Get path to the sample data file
TESTS_DIR = pathlib.Path(__file__).parent
SAMPLE_XML_PATH = TESTS_DIR / "sample_data.xml"

@pytest.fixture
def sample_xml_data() -> str:
    """Fixture to load the sample XML data from a file."""
    with open(SAMPLE_XML_PATH, 'r') as f:
        return f.read()

def test_parse_and_filter_papers_finds_company(sample_xml_data):
    """
    Tests that the parser correctly identifies and extracts a paper with a
    company-affiliated author.
    """
    results = parse_and_filter_papers(sample_xml_data)

    # We expect to find only one of the two papers in the sample XML
    assert len(results) == 1
    
    paper = results[0]
    assert isinstance(paper, PaperResult)
    assert paper.pubmed_id == "12345678"
    assert paper.title == "A groundbreaking study on novel therapeutics."
    assert paper.publication_date == "2023-Jan-N/A"
    
    # Check author and affiliation details
    assert len(paper.non_academic_authors) == 1
    assert paper.non_academic_authors[0] == "Jane Doe"
    
    assert len(paper.company_affiliations) == 1
    assert "PharmaCorp Inc." in paper.company_affiliations[0]
    
    # Check corresponding author email extraction
    assert paper.corresponding_author_email == "jane.doe@pharmaco.com"

def test_parse_and_filter_papers_ignores_academic(sample_xml_data):
    """
    Tests that the parser correctly ignores papers with only academic affiliations.
    """
    results = parse_and_filter_papers(sample_xml_data)
    
    # Ensure the academic-only paper is not in the results
    pmids_found = {p.pubmed_id for p in results}
    assert "98765432" not in pmids_found

def test_parse_and_filter_with_empty_data():
    """Tests that the function handles empty XML data gracefully."""
    results = parse_and_filter_papers("")
    assert results == []

def test_parse_and_filter_with_malformed_data():
    """Tests that the function handles malformed XML data gracefully."""
    malformed_xml = "<PubmedArticle><PMID>1</PMID><ArticleTitle>Test"
    results = parse_and_filter_papers(malformed_xml)
    assert results == []