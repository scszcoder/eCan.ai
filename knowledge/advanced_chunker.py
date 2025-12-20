"""
Advanced Universal Table Chunker for LightRAG

Supports multiple table formats:
- Markdown tables
- CSV/TSV files
- JSON tables
- Excel (via Markdown conversion)

Provides intelligent chunking with metadata support.
"""

from typing import List, Dict, Any, Optional
import re
import json
from utils.logger_helper import logger_helper as logger


class UniversalTableChunker:
    """Universal table chunker supporting multiple formats"""
    
    def __init__(self, tokenizer, chunk_token_size: int, chunk_overlap_token_size: int):
        """
        Initialize the chunker
        
        Args:
            tokenizer: LightRAG Tokenizer instance
            chunk_token_size: Maximum chunk token size
            chunk_overlap_token_size: Overlap token size (currently unused for table chunking)
        """
        self.tokenizer = tokenizer
        self.chunk_token_size = chunk_token_size
        self.chunk_overlap_token_size = chunk_overlap_token_size
        # Import here to avoid circular dependency
        try:
            from knowledge.lightrag_launcher import get_stop_controller
            self.stop_controller = get_stop_controller()
        except ImportError:
            # Fallback if launcher not available (e.g., in tests)
            self.stop_controller = None

    def _check_stop(self):
        """Check if stop is requested and raise exception if so."""
        if self.stop_controller and self.stop_controller.is_stop_requested():
            logger.info("[TableChunker] 🛑 Stop requested, aborting chunking operation")
            raise InterruptedError("Chunking operation cancelled by user")
    
    def chunk(self, content: str) -> List[Dict[str, Any]]:
        """
        Intelligently detect content type and chunk accordingly
        
        Args:
            content: Document content
            
        Returns:
            List of chunk dictionaries with keys: tokens, content, chunk_order_index
        """
        self._check_stop()
        
        # Detect content type and chunk accordingly
        if self._is_markdown_table(content):
            logger.info("[TableChunker] Detected Markdown table format")
            return self._chunk_markdown_table(content)
        elif self._is_excel_sheet_format(content):
            logger.info("[TableChunker] Detected Excel sheet format (LightRAG extraction)")
            return self._chunk_excel_sheet(content)
        elif self._is_csv_like(content):
            logger.info("[TableChunker] Detected CSV/TSV format")
            return self._chunk_csv(content)
        elif self._is_json_table(content):
            logger.info("[TableChunker] Detected JSON table format")
            return self._chunk_json_table(content)
        else:
            # Fallback to standard chunking
            logger.debug("[TableChunker] Using standard text chunking (no table detected)")
            return self._chunk_plain_text(content)
    
    # ==================== Format Detection ====================
    
    def _is_markdown_table(self, content: str) -> bool:
        """
        Detect if content is a Markdown table
        
        Features: Contains | separators and --- separator lines
        """
        lines = content.strip().split('\n')
        if len(lines) < 3:
            return False
        
        # Check if there are enough pipe symbol lines
        pipe_lines = sum(1 for line in lines if '|' in line)
        if pipe_lines < 3:
            return False
        
        # Check if there is a separator line (e.g., |---|---|)
        has_separator = any(
            '|' in line and '---' in line 
            for line in lines[:10]  # Only check first 10 lines
        )
        
        return has_separator
    
    def _is_excel_sheet_format(self, content: str) -> bool:
        """
        Detect if content is LightRAG's Excel extraction format.
        
        Format: "Sheet: SheetName\n" followed by tab-separated data rows
        """
        lines = content.strip().split('\n')
        if len(lines) < 3:
            return False
        
        # Check for "Sheet:" pattern in first few lines
        has_sheet_marker = any(line.strip().startswith('Sheet:') for line in lines[:5])
        if not has_sheet_marker:
            return False
        
        # Check for tab-separated data rows after sheet marker
        tab_lines = 0
        for line in lines:
            if line.strip().startswith('Sheet:'):
                continue
            if '\t' in line and line.count('\t') >= 1:
                tab_lines += 1
        
        return tab_lines >= 2
    
    def _is_csv_like(self, content: str) -> bool:
        """
        Detect if content is CSV/TSV format
        
        Features: Consistent delimiters (comma or tab)
        """
        lines = content.strip().split('\n')
        if len(lines) < 2:
            return False
        
        # Check delimiter count in first line
        first_line = lines[0]
        tab_count = first_line.count('\t')
        comma_count = first_line.count(',')
        
        # At least 2 delimiters to be considered a table
        if tab_count < 2 and comma_count < 2:
            return False
        
        # Check if first few lines have consistent delimiter count
        delimiter = '\t' if tab_count > comma_count else ','
        first_count = first_line.count(delimiter)
        
        consistent_count = 0
        for line in lines[1:min(5, len(lines))]:
            if line.count(delimiter) == first_count:
                consistent_count += 1
        
        return consistent_count >= min(3, len(lines) - 1)
    
    def _is_json_table(self, content: str) -> bool:
        """
        Detect if content is JSON table format
        
        Features: JSON format with table keywords like rows/columns/data
        """
        try:
            data = json.loads(content.strip())
            
            # Check if it contains table-related keys
            if isinstance(data, dict):
                keys = set(data.keys())
                table_keys = {'rows', 'columns', 'data', 'sheet', 'table'}
                return bool(keys & table_keys)
            
            # Check if it's an array of rows
            if isinstance(data, list) and len(data) > 0:
                if isinstance(data[0], dict):
                    return True
            
            return False
        except (json.JSONDecodeError, ValueError):
            return False
    
    # ==================== Markdown Table Chunking ====================
    
    def _chunk_markdown_table(self, content: str) -> List[Dict[str, Any]]:
        """
        Chunk Markdown table
        
        Strategy:
        1. Extract header (title + column names + separator line)
        2. Chunk by data rows, each chunk includes header
        3. Dynamically calculate rows per chunk to stay within token limit
        """
        lines = content.strip().split('\n')
        
        # Extract header and data rows
        header_lines = []
        data_lines = []
        in_header = True
        
        for line in lines:
            if in_header:
                header_lines.append(line)
                # Separator line marks end of header
                if '|' in line and '---' in line:
                    in_header = False
            else:
                # Skip empty lines
                if line.strip():
                    data_lines.append(line)
        
        if not header_lines or not data_lines:
            # Not a standard table, fallback
            logger.warning("[TableChunker] Invalid Markdown table structure, falling back to plain text")
            return self._chunk_plain_text(content)
        
        # Calculate header token count
        header_text = '\n'.join(header_lines)
        header_tokens = len(self.tokenizer.encode(header_text))
        
        # Token space reserved for data (10 token buffer for safety)
        max_data_tokens = self.chunk_token_size - header_tokens - 10
        
        if max_data_tokens < 100:
            # Header too long to repeat in every chunk
            # Use simplified chunking without header repetition
            logger.info(f"[TableChunker] Header too long ({header_tokens} tokens), using simplified chunking without header repetition")
            return self._chunk_table_without_header_repeat(header_lines, data_lines)
        
        # Chunk by rows
        chunks = []
        current_lines = []
        current_tokens = 0
        chunk_index = 0
        
        for line in data_lines:
            self._check_stop()
            line_tokens = len(self.tokenizer.encode(line))
            
            # If adding this line exceeds limit and we have content, create a chunk
            if current_tokens + line_tokens > max_data_tokens and current_lines:
                chunk_content = header_text + '\n' + '\n'.join(current_lines)
                chunks.append({
                    'tokens': header_tokens + current_tokens,
                    'content': chunk_content.strip(),
                    'chunk_order_index': chunk_index,
                })
                chunk_index += 1
                current_lines = []
                current_tokens = 0
            
            current_lines.append(line)
            current_tokens += line_tokens
        
        # Last chunk
        if current_lines:
            chunk_content = header_text + '\n' + '\n'.join(current_lines)
            chunks.append({
                'tokens': header_tokens + current_tokens,
                'content': chunk_content.strip(),
                'chunk_order_index': chunk_index,
            })
        
        logger.info(f"[TableChunker] ✅ Generated {len(chunks)} chunks from Markdown table ({len(data_lines)} data rows)")
        return chunks if chunks else self._chunk_plain_text(content)
    
    def _chunk_table_without_header_repeat(self, header_lines: List[str], data_lines: List[str]) -> List[Dict[str, Any]]:
        """
        Chunk table data without repeating header in every chunk.
        
        For wide tables where header is too large to repeat.
        First chunk contains header, subsequent chunks only contain data with row references.
        """
        chunks = []
        chunk_index = 0
        
        # Extract table title from header (## Sheet: xxx or similar)
        table_title = ""
        for line in header_lines:
            if line.startswith('#'):
                table_title = line.strip()
                break
        if not table_title:
            table_title = "## Table Data"
        
        # First chunk: include full header + as much data as fits
        header_text = '\n'.join(header_lines)
        header_tokens = len(self.tokenizer.encode(header_text))
        
        current_lines = []
        current_tokens = header_tokens
        first_chunk = True
        start_row = 1
        
        for row_idx, line in enumerate(data_lines):
            self._check_stop()
            line_tokens = len(self.tokenizer.encode(line))
            
            if current_tokens + line_tokens > self.chunk_token_size - 20:
                # Create chunk
                if first_chunk:
                    chunk_content = header_text + '\n' + '\n'.join(current_lines)
                    first_chunk = False
                else:
                    chunk_content = f"{table_title} (Rows {start_row}-{start_row + len(current_lines) - 1})\n\n" + '\n'.join(current_lines)
                
                chunks.append({
                    'tokens': current_tokens,
                    'content': chunk_content.strip(),
                    'chunk_order_index': chunk_index,
                })
                chunk_index += 1
                start_row = row_idx + 1
                current_lines = []
                current_tokens = len(self.tokenizer.encode(f"{table_title} (Rows)"))
            
            current_lines.append(line)
            current_tokens += line_tokens
        
        # Last chunk
        if current_lines:
            if first_chunk:
                chunk_content = header_text + '\n' + '\n'.join(current_lines)
            else:
                chunk_content = f"{table_title} (Rows {start_row}-{start_row + len(current_lines) - 1})\n\n" + '\n'.join(current_lines)
            
            chunks.append({
                'tokens': current_tokens,
                'content': chunk_content.strip(),
                'chunk_order_index': chunk_index,
            })
        
        logger.info(f"[TableChunker] ✅ Generated {len(chunks)} chunks (no header repeat, {len(data_lines)} data rows)")
        return chunks
    
    # ==================== Excel Sheet Format Chunking (Adaptive) ====================
    
    def _chunk_excel_sheet(self, content: str) -> List[Dict[str, Any]]:
        """
        Chunk LightRAG's Excel extraction format using Adaptive Vertical Partitioning.
        
        Format: "Sheet: SheetName\n" followed by tab-separated data rows.
        
        Strategy:
        1. Parse and Clean: Remove empty trailing columns (fixes 16k column issue).
        2. Analyze: Determine if table is "Wide" (row > chunk_size) or "Long".
        3. Partition:
           - If Wide: Split columns into groups (Vertical Partitioning), preserving Key Column.
           - If Long: Standard row-based chunking.
        """
        # 1. Parse content into sheets
        sheets = []
        current_sheet = None
        current_rows = []
        
        for line in content.split('\n'):
            line = line.rstrip('\r\n') # Keep tabs for now
            if not line: continue
            
            if line.strip().startswith('Sheet:'):
                if current_sheet and current_rows:
                    sheets.append((current_sheet, current_rows))
                current_sheet = line.strip()[6:].strip()
                current_rows = []
            else:
                if current_sheet is not None:
                    current_rows.append(line)
        
        if current_sheet and current_rows:
            sheets.append((current_sheet, current_rows))
            
        if not sheets:
            logger.warning("[TableChunker] No valid sheets found, fallback to text")
            return self._chunk_plain_text(content)
            
        all_chunks = []
        chunk_index = 0
        
        for sheet_name, raw_rows in sheets:
            self._check_stop()
            if not raw_rows: continue
            
            # 2. Smart Parsing & Cleaning
            # Convert to list of lists and find max non-empty column index
            parsed_rows = [row.split('\t') for row in raw_rows]
            
            # Find the index of the last non-empty column across ALL rows
            # This is crucial for fixing the "16382 columns" ghost data issue
            max_col_idx = 0
            for row in parsed_rows:
                for i in range(len(row) - 1, -1, -1):
                    if row[i] and row[i].strip():
                        max_col_idx = max(max_col_idx, i)
                        break
            
            # Trim all rows to max_col_idx + 1
            cleaned_rows = [row[:max_col_idx+1] for row in parsed_rows]
            
            if not cleaned_rows: continue
            
            # 3. Adaptive Partitioning
            sheet_chunks = self._chunk_adaptive_vertical_partitioning(
                sheet_name, 
                cleaned_rows, 
                start_chunk_index=chunk_index
            )
            
            all_chunks.extend(sheet_chunks)
            chunk_index += len(sheet_chunks)
            
        logger.info(f"[TableChunker] ✅ Generated {len(all_chunks)} chunks from {len(sheets)} sheets (Adaptive Strategy)")
        return all_chunks if all_chunks else self._chunk_plain_text(content)

    def _chunk_adaptive_vertical_partitioning(
        self, 
        sheet_name: str, 
        rows: List[List[str]], 
        start_chunk_index: int
    ) -> List[Dict[str, Any]]:
        """
        Core logic for Adaptive Vertical Partitioning.
        """
        if not rows: return []
        
        chunks = []
        chunk_idx = start_chunk_index
        
        # Assume first row is header
        header = rows[0]
        data_rows = rows[1:]
        
        # Calculate token size of a typical row
        # We sample a few rows to get average width
        sample_rows = data_rows[:5] if data_rows else [header]
        avg_row_text = '\t'.join(['sample'] * len(header)) # approximate
        if sample_rows:
             avg_row_text = '\t'.join(sample_rows[0])
             
        row_tokens = len(self.tokenizer.encode(avg_row_text))
        
        # Strategy Selection
        if row_tokens > self.chunk_token_size * 0.8:
            # === Wide Table Strategy (Vertical Partitioning) ===
            logger.info(f"[TableChunker] Sheet '{sheet_name}' is WIDE ({row_tokens} tokens/row). Using Vertical Partitioning.")
            
            # Identify Key Column (Column 0)
            key_col_idx = 0
            key_header = header[0] if header else "Key"
            
            # Group remaining columns
            # We construct partitions: [Key, Col 1..N], [Key, Col N+1..M], ...
            current_partition = []
            current_tokens = 0
            
            # Initial setup for key column
            key_tokens = len(self.tokenizer.encode(key_header + "\n" + "sample")) * 2 # Buffer
            
            # Iterate columns starting from 1
            col_indices = range(1, len(header))
            
            partitions = [] # List of column index lists
            current_batch = []
            
            # Estimate tokens per column roughly
            # This is complex, so we use a simpler greedy approach:
            # Accumulate columns until we hit a safety limit (e.g. 500 tokens) to allow for many rows
            # We want each chunk to hold at least 5-10 rows preferably
            
            target_tokens_per_row = self.chunk_token_size // 10  # Aim for 10 rows per chunk
            
            accumulated_tokens = key_tokens
            
            for col_i in col_indices:
                self._check_stop()
                # Estimate column width
                col_text = header[col_i] + "\n" + (data_rows[0][col_i] if data_rows else "")
                col_toks = len(self.tokenizer.encode(col_text))
                
                if accumulated_tokens + col_toks > target_tokens_per_row and current_batch:
                    partitions.append(current_batch)
                    current_batch = []
                    accumulated_tokens = key_tokens
                
                current_batch.append(col_i)
                accumulated_tokens += col_toks
            
            if current_batch:
                partitions.append(current_batch)
                
            if not partitions: # Single column table or just key
                partitions = [[]] 

            # Generate chunks for each partition
            for part_cols in partitions:
                self._check_stop()
                # Construct sub-table for this partition
                sub_header = [header[key_col_idx]] + [header[i] for i in part_cols]
                sub_data = []
                for row in data_rows:
                    sub_row = [row[key_col_idx]] + [row[i] for i in part_cols if i < len(row)]
                    sub_data.append(sub_row)
                
                # Recursively chunk this narrower table
                # We use the standard MD chunker logic on this sub-table
                part_chunks = self._chunk_standard_table(
                    sheet_name, 
                    sub_header, 
                    sub_data, 
                    chunk_idx,
                    title_suffix=f"(Cols {part_cols[0]}-{part_cols[-1]})" if part_cols else ""
                )
                chunks.extend(part_chunks)
                chunk_idx += len(part_chunks)
                
        else:
            # === Standard Strategy (Row-based Chunking) ===
            # Table fits width-wise, just chunk by rows
            logger.info(f"[TableChunker] Sheet '{sheet_name}' is Standard ({row_tokens} tokens/row). Using Row Chunking.")
            chunks = self._chunk_standard_table(sheet_name, header, data_rows, chunk_idx)
            
        return chunks

    def _chunk_standard_table(
        self, 
        sheet_name: str, 
        header: List[str], 
        data_rows: List[List[str]], 
        start_index: int,
        title_suffix: str = ""
    ) -> List[Dict[str, Any]]:
        """
        Chunks a table that fits within width limits.
        Converts to Markdown and chunks by rows.
        """
        chunks = []
        current_lines = []
        
        # Prepare Header
        title = f"## Sheet: {sheet_name} {title_suffix}".strip()
        md_header_lines = [
            title,
            "",
            "| " + " | ".join(str(c) for c in header) + " |",
            "|" + "|".join(["---"] * len(header)) + "|"
        ]
        header_text = '\n'.join(md_header_lines)
        header_tokens = len(self.tokenizer.encode(header_text))
        
        current_lines = []
        current_tokens = header_tokens
        chunk_idx = start_index
        
        for row in data_rows:
            self._check_stop()
            # Sanitize cells (remove newlines to keep MD format)
            clean_row = [str(c).replace('\n', ' ') for c in row]
            row_md = "| " + " | ".join(clean_row) + " |"
            row_tokens = len(self.tokenizer.encode(row_md))
            
            # Check limits
            if current_tokens + row_tokens > self.chunk_token_size - 20:
                if current_lines:
                    # Flush current chunk
                    chunks.append({
                        'tokens': current_tokens,
                        'content': header_text + '\n' + '\n'.join(current_lines),
                        'chunk_order_index': chunk_idx
                    })
                    chunk_idx += 1
                    current_lines = []
                    current_tokens = header_tokens
            
            # If a single row is massive (still > chunk_size after width-check?), truncate/split it
            # This handles the rare "single cell huge text" case
            if row_tokens > self.chunk_token_size - header_tokens - 20:
                 # Truncate for now (or could split further, but let's be safe)
                 row_md = row_md[:(self.chunk_token_size - header_tokens - 50) * 4] + "..."
                 row_tokens = len(self.tokenizer.encode(row_md))
            
            current_lines.append(row_md)
            current_tokens += row_tokens
            
        # Flush last chunk
        if current_lines:
            chunks.append({
                'tokens': current_tokens,
                'content': header_text + '\n' + '\n'.join(current_lines),
                'chunk_order_index': chunk_idx
            })
            
        return chunks
    
    # ==================== CSV/TSV Chunking ====================
    
    def _chunk_csv(self, content: str) -> List[Dict[str, Any]]:
        """
        Chunk CSV/TSV format
        
        Strategy:
        1. Detect delimiter (comma or tab)
        2. First row as header
        3. Chunk by data rows, each chunk includes header
        """
        lines = content.strip().split('\n')
        if len(lines) < 2:
            logger.warning("[TableChunker] CSV has less than 2 lines, falling back to plain text")
            return self._chunk_plain_text(content)
        
        # Detect delimiter
        first_line = lines[0]
        tab_count = first_line.count('\t')
        comma_count = first_line.count(',')
        delimiter = '\t' if tab_count > comma_count else ','
        
        # Convert to Markdown table format
        markdown_lines = []
        
        # Process header
        header_cells = lines[0].split(delimiter)
        markdown_lines.append('| ' + ' | '.join(cell.strip() for cell in header_cells) + ' |')
        markdown_lines.append('|' + '|'.join(['---'] * len(header_cells)) + '|')
        
        # Process data rows
        for line in lines[1:]:
            if line.strip():
                cells = line.split(delimiter)
                # Pad column count
                while len(cells) < len(header_cells):
                    cells.append('')
                markdown_lines.append('| ' + ' | '.join(cell.strip() for cell in cells[:len(header_cells)]) + ' |')
        
        # Use Markdown table chunking logic
        markdown_content = '\n'.join(markdown_lines)
        logger.debug(f"[TableChunker] Converted CSV to Markdown table ({len(lines)} rows)")
        return self._chunk_markdown_table(markdown_content)
    
    # ==================== JSON Table Chunking ====================
    
    def _chunk_json_table(self, content: str) -> List[Dict[str, Any]]:
        """
        Chunk JSON table
        
        Strategy:
        1. Parse JSON structure
        2. Extract column names and row data
        3. Convert to Markdown table format
        4. Use Markdown table chunking logic
        """
        try:
            data = json.loads(content.strip())
            
            # Handle dictionary format (e.g., {columns: [...], rows: [...]})
            if isinstance(data, dict):
                columns = data.get('columns', [])
                rows = data.get('rows', [])
                
                if not columns and rows and isinstance(rows, list) and len(rows) > 0:
                    # Infer column names from first row
                    if isinstance(rows[0], dict):
                        columns = list(rows[0].keys())
                
                if columns and rows:
                    return self._json_dict_to_markdown_chunks(columns, rows)
            
            # Handle array format (e.g., [{col1: val1, col2: val2}, ...])
            elif isinstance(data, list) and len(data) > 0:
                if isinstance(data[0], dict):
                    columns = list(data[0].keys())
                    return self._json_dict_to_markdown_chunks(columns, data)
            
            # Unrecognized JSON format, fallback
            logger.warning("[TableChunker] Unrecognized JSON format, falling back to plain text")
            return self._chunk_plain_text(content)
            
        except Exception as e:
            logger.error(f"[TableChunker] Failed to parse JSON table: {e}")
            return self._chunk_plain_text(content)
    
    def _json_dict_to_markdown_chunks(
        self, 
        columns: List[str], 
        rows: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Convert JSON dictionary array to Markdown table and chunk"""
        markdown_lines = []
        
        # Header
        markdown_lines.append('| ' + ' | '.join(str(col) for col in columns) + ' |')
        markdown_lines.append('|' + '|'.join(['---'] * len(columns)) + '|')
        
        # Data rows
        for row in rows:
            cells = []
            for col in columns:
                value = row.get(col, '')
                # Handle complex types
                if isinstance(value, (dict, list)):
                    value = json.dumps(value, ensure_ascii=False)
                cells.append(str(value))
            markdown_lines.append('| ' + ' | '.join(cells) + ' |')
        
        # Use Markdown table chunking logic
        markdown_content = '\n'.join(markdown_lines)
        logger.debug(f"[TableChunker] Converted JSON to Markdown table ({len(rows)} rows, {len(columns)} columns)")
        return self._chunk_markdown_table(markdown_content)
    
    # ==================== Fallback: Standard Text Chunking ====================
    
    def _chunk_plain_text(self, content: str) -> List[Dict[str, Any]]:
        """
        Standard text chunking (fallback)
        
        Uses LightRAG's default token-based chunking
        """
        from lightrag.operate import chunking_by_token_size
        
        logger.debug("[TableChunker] Using LightRAG standard chunking")
        return chunking_by_token_size(
            self.tokenizer,
            content,
            split_by_character=None,
            split_by_character_only=False,
            overlap_token_size=self.chunk_overlap_token_size,
            max_token_size=self.chunk_token_size,
        )


# ==================== LightRAG Interface Function ====================

def universal_chunking_func(
    tokenizer,
    content: str,
    split_by_character: Optional[str] = None,
    split_by_character_only: bool = False,
    chunk_overlap_token_size: int = 100,
    chunk_token_size: int = 1200,
) -> List[Dict[str, Any]]:
    """
    Universal chunking function, LightRAG interface
    
    Automatically detects content type (Markdown table, CSV, JSON table, plain text) and chunks intelligently
    
    Args:
        tokenizer: LightRAG Tokenizer instance
        content: Document content
        split_by_character: Delimiter (optional, ignored for table chunking)
        split_by_character_only: Whether to split only by delimiter (ignored for table chunking)
        chunk_overlap_token_size: Overlap token count
        chunk_token_size: Maximum chunk token size
        
    Returns:
        List of chunk dictionaries with keys:
        - tokens (int): Token count
        - content (str): Chunk content
        - chunk_order_index (int): Order index
    """
    chunker = UniversalTableChunker(
        tokenizer=tokenizer,
        chunk_token_size=chunk_token_size,
        chunk_overlap_token_size=chunk_overlap_token_size,
    )
    
    chunks = chunker.chunk(content)
    
    # Validate chunks before returning using the ACTUAL tokenizer
    # This ensures chunks can be properly encoded by LightRAG
    valid_chunks = []
    for i, chunk in enumerate(chunks):
        chunk_content = chunk.get('content', '')
        
        # Skip if content is empty
        if not chunk_content or not chunk_content.strip():
            logger.warning(f"[TableChunker] Skipping chunk {i}: empty content")
            continue
        
        # Try to encode with the actual tokenizer to verify it's valid
        try:
            tokens = tokenizer.encode(chunk_content)
            
            # Check if encoding produced valid tokens
            if not tokens or len(tokens) == 0:
                logger.warning(f"[TableChunker] Skipping chunk {i}: tokenizer produced no tokens")
                continue
            
            # Update token count with actual tokenizer result
            chunk['tokens'] = len(tokens)
            valid_chunks.append(chunk)
            
        except Exception as e:
            logger.warning(f"[TableChunker] Skipping chunk {i}: tokenizer error - {e}")
            continue
    
    if len(valid_chunks) < len(chunks):
        logger.info(f"[TableChunker] Filtered {len(chunks) - len(valid_chunks)} invalid chunks, {len(valid_chunks)} valid chunks remaining")
    
    # If all chunks were filtered out, fall back to standard chunking
    if not valid_chunks:
        logger.warning("[TableChunker] All chunks were invalid, falling back to standard chunking")
        from lightrag.operate import chunking_by_token_size
        return chunking_by_token_size(
            tokenizer,
            content,
            split_by_character=split_by_character,
            split_by_character_only=split_by_character_only,
            overlap_token_size=chunk_overlap_token_size,
            max_token_size=chunk_token_size,
        )
    
    return valid_chunks
