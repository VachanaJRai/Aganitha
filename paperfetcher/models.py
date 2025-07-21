from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class PaperResult:
    """
    Represents a single filtered research paper result.
    """
    pubmed_id: str
    title: str
    publication_date: str
    non_academic_authors: List[str] = field(default_factory=list)
    company_affiliations: List[str] = field(default_factory=list)
    corresponding_author_email: Optional[str] = None

    def to_csv_row(self) -> List[str]:
        """Converts the dataclass instance to a list of strings for CSV writing."""
        return [
            self.pubmed_id,
            self.title,
            self.publication_date,
            "; ".join(self.non_academic_authors),
            "; ".join(self.company_affiliations),
            self.corresponding_author_email or "N/A",
        ]

    @staticmethod
    def get_csv_header() -> List[str]:
        """Returns the header row for the CSV output."""
        return [
            "PubmedID",
            "Title",
            "Publication Date",
            "Non-academic Author(s)",
            "Company Affiliation(s)",
            "Corresponding Author Email",
        ]