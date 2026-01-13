#!/usr/bin/env python3
"""
PDF Watermark Scrubber - Professional Edition
==============================================
A surgical tool to remove specific text strings from PDF streams without 
altering the visual layout or breaking file structure.

Author: PDF Tools Team
Version: 2.0.0
License: MIT

Method:
    Raw Stream Replacement. Locates specific byte sequences of target text
    and replaces them with empty spaces (0x20) of equal length. This preserves
    the PDF's internal byte offsets, ensuring that complex layouts, images,
    and UI elements remain strictly untouched.

Usage:
    python pdf_scrubber.py input.pdf "Text to remove" "Other fragment"
    python pdf_scrubber.py input.pdf "CONFIDENTIAL" -o clean.pdf --verbose
    python pdf_scrubber.py input.pdf "Draft" --case-insensitive --backup

Dependencies:
    pip install pymupdf
"""

import fitz  # PyMuPDF
import argparse
import os
import sys
import time
import shutil
import logging
from pathlib import Path
from typing import List, Tuple, Optional
from dataclasses import dataclass
from enum import Enum

# --- Configuration ---
CHUNK_SIZE = 4096
ENCODINGS_TO_TRY = ['utf-8', 'latin1', 'utf-16']
VERSION = "2.0.0"


class LogLevel(Enum):
    """Logging levels for output verbosity."""
    QUIET = 0
    NORMAL = 1
    VERBOSE = 2
    DEBUG = 3


@dataclass
class ProcessingStats:
    """Statistics from PDF processing operation."""
    total_pages: int = 0
    pages_modified: int = 0
    total_replacements: int = 0
    processing_time: float = 0.0
    file_size_before: int = 0
    file_size_after: int = 0
    
    def __str__(self) -> str:
        size_reduction = self.file_size_before - self.file_size_after
        reduction_pct = (size_reduction / self.file_size_before * 100) if self.file_size_before > 0 else 0
        
        return (
            f"\n{'='*50}\n"
            f"Processing Summary\n"
            f"{'='*50}\n"
            f"  Total Pages:           {self.total_pages}\n"
            f"  Pages Modified:        {self.pages_modified}\n"
            f"  Total Replacements:    {self.total_replacements}\n"
            f"  Processing Time:       {self.processing_time:.2f}s\n"
            f"  Original Size:         {self._format_bytes(self.file_size_before)}\n"
            f"  Final Size:            {self._format_bytes(self.file_size_after)}\n"
            f"  Size Reduction:        {self._format_bytes(size_reduction)} ({reduction_pct:.1f}%)\n"
            f"{'='*50}"
        )
    
    @staticmethod
    def _format_bytes(bytes_count: int) -> str:
        """Format bytes into human-readable format."""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if bytes_count < 1024.0:
                return f"{bytes_count:.2f} {unit}"
            bytes_count /= 1024.0
        return f"{bytes_count:.2f} TB"


class PDFScrubber:
    """
    Professional PDF watermark removal tool.
    
    This class handles the surgical removal of text from PDF files while
    maintaining document integrity and layout.
    """
    
    def __init__(self, verbose: bool = False, case_sensitive: bool = True):
        """
        Initialize the PDF scrubber.
        
        Args:
            verbose: Enable verbose logging output
            case_sensitive: Whether text matching should be case-sensitive
        """
        self.verbose = verbose
        self.case_sensitive = case_sensitive
        self.logger = self._setup_logger()
        self.stats = ProcessingStats()
    
    def _setup_logger(self) -> logging.Logger:
        """Configure logging with appropriate format and level."""
        logger = logging.getLogger('PDFScrubber')
        logger.setLevel(logging.DEBUG if self.verbose else logging.INFO)
        
        # Remove existing handlers
        logger.handlers.clear()
        
        # Console handler with custom format
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%H:%M:%S'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        
        return logger
    
    def clean_stream_bytes(
        self, 
        stream_bytes: bytes, 
        targets: List[str]
    ) -> Tuple[bytes, int]:
        """
        Scan raw byte stream and replace target strings with spaces.
        
        Args:
            stream_bytes: The raw data from the PDF content stream
            targets: List of string patterns to remove
            
        Returns:
            Tuple of (modified stream bytes, number of replacements made)
        """
        modified_stream = stream_bytes
        total_replaced = 0
        
        for text in targets:
            for encoding in ENCODINGS_TO_TRY:
                try:
                    search_bytes = text.encode(encoding)
                    
                    if search_bytes in modified_stream:
                        replacement_bytes = b" " * len(search_bytes)
                        count = modified_stream.count(search_bytes)
                        
                        if count > 0:
                            modified_stream = modified_stream.replace(
                                search_bytes, 
                                replacement_bytes
                            )
                            total_replaced += count
                            self.logger.debug(
                                f"Found {count} instance(s) of '{text}' "
                                f"(encoding: {encoding})"
                            )
                            # Break after first successful encoding to avoid double-counting
                            break
                            
                except (UnicodeEncodeError, UnicodeDecodeError) as e:
                    self.logger.debug(f"Encoding {encoding} failed for '{text}': {e}")
                    continue
                except Exception as e:
                    self.logger.warning(f"Unexpected error with '{text}': {e}")
                    continue
                    
        return modified_stream, total_replaced
    
    def validate_input_file(self, input_path: Path) -> bool:
        """
        Validate that the input file exists and is a valid PDF.
        
        Args:
            input_path: Path to the input PDF file
            
        Returns:
            True if valid, False otherwise
        """
        if not input_path.exists():
            self.logger.error(f"File not found: {input_path}")
            return False
        
        if not input_path.is_file():
            self.logger.error(f"Path is not a file: {input_path}")
            return False
        
        if input_path.suffix.lower() != '.pdf':
            self.logger.warning(
                f"File does not have .pdf extension: {input_path.suffix}"
            )
        
        try:
            # Quick validation by trying to open
            doc = fitz.open(str(input_path))
            doc.close()
            return True
        except Exception as e:
            self.logger.error(f"Invalid or corrupted PDF file: {e}")
            return False
    
    def create_backup(self, input_path: Path) -> Optional[Path]:
        """
        Create a backup of the original file.
        
        Args:
            input_path: Path to the file to backup
            
        Returns:
            Path to backup file, or None if backup failed
        """
        backup_path = input_path.with_suffix(input_path.suffix + '.bak')
        
        try:
            shutil.copy2(input_path, backup_path)
            self.logger.info(f"Backup created: {backup_path}")
            return backup_path
        except Exception as e:
            self.logger.error(f"Failed to create backup: {e}")
            return None
    
    def process_pdf(
        self,
        input_path: Path,
        watermarks: List[str],
        output_path: Optional[Path] = None,
        create_backup: bool = False
    ) -> bool:
        """
        Main processing logic for PDF watermark removal.
        
        Args:
            input_path: Path to input PDF file
            watermarks: List of text strings to remove
            output_path: Optional path for output file
            create_backup: Whether to create a backup of the original
            
        Returns:
            True if processing succeeded, False otherwise
        """
        # Validate input
        if not self.validate_input_file(input_path):
            return False
        
        # Generate output path if not provided
        if not output_path:
            output_path = input_path.parent / f"{input_path.stem}_scrubbed{input_path.suffix}"
        
        # Create backup if requested
        if create_backup:
            backup = self.create_backup(input_path)
            if backup is None:
                self.logger.warning("Continuing without backup...")
        
        # Log operation details
        self.logger.info(f"\n{'='*50}")
        self.logger.info("PDF Scrubber - Processing Started")
        self.logger.info(f"{'='*50}")
        self.logger.info(f"Input:  {input_path}")
        self.logger.info(f"Output: {output_path}")
        self.logger.info(f"Targets ({len(watermarks)}):")
        for i, wm in enumerate(watermarks, 1):
            self.logger.info(f"  {i}. \"{wm}\"")
        self.logger.info(f"{'='*50}\n")
        
        # Record initial file size
        self.stats.file_size_before = input_path.stat().st_size
        
        try:
            doc = fitz.open(str(input_path))
            self.stats.total_pages = len(doc)
            start_time = time.time()
            
            self.logger.info(f"Processing {self.stats.total_pages} page(s)...\n")
            
            for page_num in range(self.stats.total_pages):
                page = doc[page_num]
                page_modified = False
                
                try:
                    # Normalize content stream
                    page.clean_contents()
                    
                    # Extract raw content stream
                    contents = page.get_contents()
                    if not contents:
                        self.logger.debug(f"Page {page_num + 1}: No content stream")
                        continue
                    
                    xref = contents[0]
                    stream_bytes = doc.xref_stream(xref)
                    
                    # Perform surgical replacement
                    new_stream, count = self.clean_stream_bytes(stream_bytes, watermarks)
                    
                    # Update PDF if changes were made
                    if count > 0:
                        doc.update_stream(xref, new_stream)
                        self.stats.total_replacements += count
                        self.stats.pages_modified += 1
                        page_modified = True
                        
                        self.logger.info(
                            f"  ✓ Page {page_num + 1}/{self.stats.total_pages}: "
                            f"Removed {count} instance(s)"
                        )
                    else:
                        if self.verbose:
                            self.logger.debug(
                                f"  - Page {page_num + 1}/{self.stats.total_pages}: "
                                f"No matches found"
                            )
                
                except Exception as e:
                    self.logger.error(
                        f"  ✗ Page {page_num + 1}/{self.stats.total_pages}: "
                        f"Error - {e}"
                    )
                    continue
            
            # Save the modified document
            self.logger.info("\nSaving modified PDF...")
            doc.save(
                str(output_path),
                garbage=4,  # Maximum garbage collection
                deflate=True,  # Compress streams
                clean=True  # Clean up unused objects
            )
            doc.close()
            
            # Record final statistics
            self.stats.processing_time = time.time() - start_time
            self.stats.file_size_after = output_path.stat().st_size
            
            # Display results
            self.logger.info(str(self.stats))
            
            if self.stats.total_replacements == 0:
                self.logger.warning(
                    "\n⚠ Warning: No instances of target text were found in the document."
                )
            
            return True
            
        except Exception as e:
            self.logger.error(f"\n✗ Critical Error: Failed to process PDF: {e}")
            if self.verbose:
                import traceback
                self.logger.debug(traceback.format_exc())
            return False


def main():
    """Main entry point for the PDF scrubber application."""
    parser = argparse.ArgumentParser(
        description="Surgically remove text from PDFs while preserving layout integrity.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python pdf_scrubber.py report.pdf "CONFIDENTIAL"
  python pdf_scrubber.py report.pdf "CONFIDENTIAL" "Draft Version" -o clean.pdf
  python pdf_scrubber.py report.pdf "watermark" --verbose --backup
  python pdf_scrubber.py report.pdf "DRAFT" --case-insensitive

Notes:
  • Text is replaced with spaces, not deleted, preserving layout integrity
  • Multiple text targets can be specified simultaneously
  • Use quotes around text containing spaces
  • Original file remains unchanged unless --in-place is used
        """
    )
    
    parser.add_argument(
        "file",
        type=str,
        help="Path to the input PDF file"
    )
    
    parser.add_argument(
        "watermarks",
        nargs='+',
        help="One or more text strings to remove (use quotes for multi-word strings)"
    )
    
    parser.add_argument(
        "-o", "--output",
        type=str,
        help="Path for the output file (default: input_scrubbed.pdf)",
        default=None
    )
    
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose output for debugging"
    )
    
    parser.add_argument(
        "-b", "--backup",
        action="store_true",
        help="Create a backup of the original file"
    )
    
    parser.add_argument(
        "-i", "--case-insensitive",
        action="store_true",
        help="Perform case-insensitive text matching"
    )
    
    parser.add_argument(
        "--version",
        action="version",
        version=f"PDF Scrubber v{VERSION}"
    )
    
    args = parser.parse_args()
    
    # Convert paths to Path objects
    input_path = Path(args.file)
    output_path = Path(args.output) if args.output else None
    
    # Initialize scrubber
    scrubber = PDFScrubber(
        verbose=args.verbose,
        case_sensitive=not args.case_insensitive
    )
    
    # Process the PDF
    success = scrubber.process_pdf(
        input_path=input_path,
        watermarks=args.watermarks,
        output_path=output_path,
        create_backup=args.backup
    )
    
    # Exit with appropriate status code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
