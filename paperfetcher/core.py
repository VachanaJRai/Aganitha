import logging
import re
import xml.etree.ElementTree as ET
from typing import List, Optional, Tuple, Dict, Any

import httpx

from paperfetcher.models import PaperResult

# --- Constants ---
BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
ESEARCH_URL = f"{BASE_URL}esearch.fcgi"
EFETCH_URL = f"{BASE_URL}efetch.fcgi"
MAX_UIDS_PER_REQUEST = 200 # Max UIDs allowed per efetch POST request

# Heuristic list to identify non-academic/corporate affiliations
COMPANY_KEYWORDS = [
    "inc", "ltd", "llc", "corp", "corporation", "pharmaceuticals",
    "therapeutics", "biotech", "biosciences", "diagnostics",
    "labs", "laboratories", "gmbh", "ag", "s.a."
]

logger = logging.getLogger(__name__)

def search_pubmed(query: str, max_ret: int = 100) -> List[str]:
    """
    Searches PubMed for a given query and returns a list of PubMed IDs (PMIDs).

    Args:
        query: The search term, using PubMed's advanced query syntax.
        max_ret: The maximum number of records to retrieve.

    Returns:
        A list of PubMed ID strings.
        
    Raises:
        httpx.HTTPStatusError: If the API returns a non-200 status.
        Exception: For other network or parsing errors.
    """
    params = {
        "db": "pubmed",
        "term": query,
        "retmode": "json",
        "retmax": str(max_ret),
        "usehistory": "y",
    }
    logger.debug(f"Executing eSearch with query: '{query}'")
    try:
        with httpx.Client() as client:
            response = client.get(ESEARCH_URL, params=params)
            response.raise_for_status()
            data = response.json()
            
            if "esearchresult" not in data or "idlist" not in data["esearchresult"]:
                logger.warning("No results found or malformed API response.")
                return []

            pmids = data["esearchresult"]["idlist"]
            logger.info(f"Found {len(pmids)} PMIDs from search.")
            return pmids
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error during PubMed search: {e.response.status_code} - {e.response.text}")
        raise
    except Exception as e:
        logger.error(f"An unexpected error occurred during PubMed search: {e}")
        raise

def fetch_paper_details(pmids: List[str]) -> str:
    """
    Fetches detailed information for a list of PMIDs in XML format.
    Batches requests to respect API limits.

    Args:
        pmids: A list of PubMed IDs.

    Returns:
        A string containing the concatenated XML data for all articles.
        
    Raises:
        httpx.HTTPStatusError: If the API returns a non-200 status.
    """
    if not pmids:
        return ""

    all_xml_data = ""
    # Batch PMIDs to stay within API limits
    for i in range(0, len(pmids), MAX_UIDS_PER_REQUEST):
        batch = pmids[i:i + MAX_UIDS_PER_REQUEST]
        logger.debug(f"Fetching details for batch of {len(batch)} PMIDs.")
        params: Dict[str, Any] = {
            "db": "pubmed",
            "id": ",".join(batch),
            "retmode": "xml",
        }
        try:
            # Using a longer timeout for potentially large requests
            with httpx.Client(timeout=30.0) as client:
                response = client.post(EFETCH_URL, data=params)
                response.raise_for_status()
                # Use response.text which handles encoding based on headers
                all_xml_data += response.text
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error fetching paper details: {e.response.status_code}")
            raise
    return all_xml_data

def _is_company_affiliation(affiliation: str) -> bool:
    """Checks if an affiliation string likely belongs to a company."""
    if not affiliation:
        return False
    # **RELAXED FILTERING**: The keyword list is a strong enough heuristic.
    # The check for "university" was too strict and could exclude valid
    # biotech companies spun out of universities or located in science parks.
    affiliation_lower = affiliation.lower()
    return any(keyword in affiliation_lower for keyword in COMPANY_KEYWORDS)

def _get_publication_date(article_node: ET.Element) -> str:
    """Extracts a structured publication date from the ArticleDate or PubDate element."""
    date_node = article_node.find(".//PubDate")
    if date_node is not None:
        year = date_node.findtext("Year", "N/A")
        month = date_node.findtext("Month", "N/A")
        day = date_node.findtext("Day", "N/A")
        return f"{year}-{month}-{day}"
    return "N/A"
    
def _get_corresponding_author_email(author_list_node: ET.Element) -> Optional[str]:
    """Finds the corresponding author and extracts their email if available."""
    for author_node in author_list_node.findall("./Author"):
        # Check for CorrespondingAuthor attribute in newer records
        is_corr_attr = author_node.get("CorrespondingAuthor", "N") == "Y"
        
        # Fallback check for affiliation text in older records
        is_corr_text = False
        affiliation_text_node = author_node.find(".//Affiliation")
        affiliation_text = "".join(affiliation_text_node.itertext()).strip() if affiliation_text_node is not None else ""

        if affiliation_text and "Corresponding" in affiliation_text:
            is_corr_text = True

        if is_corr_attr or is_corr_text:
            # Email is often at the end of the affiliation string
            if affiliation_text and "@" in affiliation_text:
                words = affiliation_text.replace('(', ' ').replace(')', ' ').split()
                for word in reversed(words):
                    if "@" in word:
                        return word.strip(".;,")
    return None

def parse_and_filter_papers(xml_data: str) -> List[PaperResult]:
    """
    Parses XML data from PubMed and filters for papers with company-affiliated authors.

    Args:
        xml_data: A string containing the XML data from an efetch query.

    Returns:
        A list of PaperResult objects that meet the filtering criteria.
    """
    if not xml_data.strip():
        return []

    results: List[PaperResult] = []
    try:
        # Clean the XML data by removing all XML and DOCTYPE declarations.
        cleaned_xml = re.sub(r'<\?xml[^>]*\?>', '', xml_data, flags=re.I)
        cleaned_xml = re.sub(r'<!DOCTYPE[^>]*>', '', cleaned_xml, flags=re.I)
        cleaned_xml = cleaned_xml.strip()
        xml_to_parse = f"<root>{cleaned_xml}</root>"
        root = ET.fromstring(xml_to_parse)
    except ET.ParseError as e:
        logger.error(f"Failed to parse XML: {e}")
        logger.debug(f"Problematic XML data (first 500 chars): {xml_data[:500]}")
        return []

    for article_node in root.findall(".//PubmedArticle"):
        paper_id_node = article_node.find(".//PMID")
        title_node = article_node.find(".//ArticleTitle")
        author_list_node = article_node.find(".//AuthorList")

        if paper_id_node is None or title_node is None or author_list_node is None:
            continue

        pubmed_id = paper_id_node.text or "N/A"
        title = "".join(title_node.itertext()).strip() or "No Title"
        publication_date = _get_publication_date(article_node)
        
        non_academic_authors: List[str] = []
        company_affiliations: List[str] = []

        for author_node in author_list_node.findall("./Author"):
            # **IMPROVED AFFILIATION EXTRACTION**
            # Affiliation text can be fragmented or in different locations.
            # This finds the main affiliation node and joins all its text pieces.
            affiliation_node = author_node.find(".//Affiliation")
            if affiliation_node is not None:
                affiliation_text = "".join(affiliation_node.itertext()).strip()
                logger.debug(f"Checking affiliation: '{affiliation_text}'") # Log for easier debugging

                if _is_company_affiliation(affiliation_text):
                    last_name = author_node.findtext(".//LastName", "")
                    fore_name = author_node.findtext(".//ForeName", "")
                    author_name = f"{fore_name} {last_name}".strip()
                    
                    if author_name:
                        non_academic_authors.append(author_name)
                    if affiliation_text not in company_affiliations:
                        company_affiliations.append(affiliation_text)

        if non_academic_authors:
            email = _get_corresponding_author_email(author_list_node)
            paper = PaperResult(
                pubmed_id=pubmed_id,
                title=title,
                publication_date=publication_date,
                non_academic_authors=non_academic_authors,
                company_affiliations=company_affiliations,
                corresponding_author_email=email,
            )
            results.append(paper)
            logger.debug(f"Filtered paper added: {pubmed_id} - {title[:50]}...")
            
    logger.info(f"Filtered {len(results)} papers with company affiliations.")
    return results

def find_papers(query: str) -> List[PaperResult]:
    """
    The main orchestrator function. Searches, fetches, and filters papers.

    Args:
        query: The PubMed search query.

    Returns:
        A list of `PaperResult` objects.
    """
    logger.info(f"Starting paper fetch for query: '{query}'")
    try:
        pmids = search_pubmed(query)
        if not pmids:
            return []
        
        xml_data = fetch_paper_details(pmids)
        if not xml_data:
            return []
            
        filtered_papers = parse_and_filter_papers(xml_data)
        return filtered_papers
    except Exception as e:
        logger.critical(f"A critical error occurred in the main workflow: {e}")
        return []
