import csv
import logging
import sys
from typing import List, Optional

import typer
from rich.console import Console
from rich.logging import RichHandler

from paperfetcher.core import find_papers
from paperfetcher.models import PaperResult

# Initialize Typer app and Rich console
app = typer.Typer(
    name="get-papers-list",
    help="A tool to fetch PubMed papers with authors from pharma/biotech companies."
)
console = Console(stderr=True)


def _setup_logging(debug: bool) -> None:
    """Configures logging for the application."""
    log_level = "DEBUG" if debug else "INFO"
    logging.basicConfig(
        level=log_level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=console, rich_tracebacks=True)],
    )

def _write_to_csv(results: List[PaperResult], output_file: Optional[str]) -> None:
    """Writes the results to a CSV file or prints to the console."""
    if not results:
        logging.info("No matching papers found to write.")
        return

    writer_target = open(output_file, 'w', newline='', encoding='utf-8') if output_file else sys.stdout
    
    try:
        writer = csv.writer(writer_target)
        writer.writerow(PaperResult.get_csv_header())
        for paper in results:
            writer.writerow(paper.to_csv_row())
    finally:
        if output_file and writer_target:
            writer_target.close()
            logging.info(f"Results successfully saved to {output_file}")
    
    if not output_file:
         logging.info("CSV output printed to console.")


@app.command()
def main(
    query: str = typer.Argument(
        ...,
        help="The search query for PubMed (e.g., 'crispr therapeutics[title]')."
    ),
    file: Optional[str] = typer.Option(
        None,
        "--file",
        "-f",
        help="Path to the output CSV file. If not provided, prints to console.",
    ),
    debug: bool = typer.Option(
        False,
        "--debug",
        "-d",
        help="Enable debug logging.",
        is_flag=True,
    ),
):
    """
    Fetches research papers from PubMed based on a query,
    filters for authors affiliated with pharmaceutical or biotech companies,
    and outputs the results to a CSV file or the console.
    """
    _setup_logging(debug)
    
    try:
        results = find_papers(query)
        _write_to_csv(results, file)
    except Exception as e:
        logging.error(f"An unexpected error prevented the program from completing: {e}")
        raise typer.Exit(code=1)

if __name__ == "__main__":
    app()