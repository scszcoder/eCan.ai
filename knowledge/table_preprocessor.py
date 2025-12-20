"""
Table Preprocessor for LightRAG

Provides semantic enhancement and data cleaning for table data using Pandas.
Optimizes Excel/CSV files before sending to LightRAG for better query accuracy.
"""

import io
import pandas as pd
from typing import Optional, Dict, Any
from utils.logger_helper import logger_helper as logger


class TablePreprocessor:
    """Semantic table preprocessor using Pandas"""
    
    def __init__(self, enable_statistics: bool = True, enable_description: bool = True):
        """
        Initialize preprocessor
        
        Args:
            enable_statistics: Add statistical summary to output
            enable_description: Add descriptive metadata to output
        """
        self.enable_statistics = enable_statistics
        self.enable_description = enable_description
    
    def preprocess_excel(self, file_bytes: bytes, filename: str, sheet_name: Optional[str] = None) -> str:
        """
        Preprocess Excel file with Pandas for semantic enhancement
        
        Args:
            file_bytes: Raw Excel file bytes
            filename: Original filename
            sheet_name: Specific sheet to process (None for all sheets)
            
        Returns:
            Enhanced Markdown format with metadata and cleaned data
        """
        try:
            logger.info(f"[TablePreprocessor] Processing Excel file: {filename}")
            
            # Read Excel file
            excel_file = io.BytesIO(file_bytes)
            
            if sheet_name:
                # Process single sheet
                df = pd.read_excel(excel_file, sheet_name=sheet_name)
                return self._process_dataframe(df, f"{filename} - {sheet_name}")
            else:
                # Process all sheets
                sheets_dict = pd.read_excel(excel_file, sheet_name=None)
                
                if not sheets_dict:
                    logger.warning(f"[TablePreprocessor] No sheets found in {filename}")
                    return f"[No data found in {filename}]"
                
                markdown_blocks = []
                for sheet_name, df in sheets_dict.items():
                    if df.empty:
                        logger.debug(f"[TablePreprocessor] Sheet '{sheet_name}' is empty, skipping")
                        continue
                    
                    sheet_markdown = self._process_dataframe(df, f"{filename} - {sheet_name}")
                    markdown_blocks.append(sheet_markdown)
                
                result = "\n\n---\n\n".join(markdown_blocks)
                logger.info(f"[TablePreprocessor] ✅ Processed {len(markdown_blocks)} sheets from {filename}")
                return result
                
        except Exception as e:
            logger.error(f"[TablePreprocessor] ❌ Failed to preprocess Excel {filename}: {e}")
            return None
    
    def preprocess_csv(self, file_bytes: bytes, filename: str, delimiter: str = None) -> str:
        """
        Preprocess CSV file with Pandas for semantic enhancement
        
        Args:
            file_bytes: Raw CSV file bytes
            filename: Original filename
            delimiter: CSV delimiter (auto-detect if None)
            
        Returns:
            Enhanced Markdown format with metadata and cleaned data
        """
        try:
            logger.info(f"[TablePreprocessor] Processing CSV file: {filename}")
            
            # Read CSV
            csv_file = io.BytesIO(file_bytes)
            
            if delimiter:
                df = pd.read_csv(csv_file, delimiter=delimiter)
            else:
                # Auto-detect delimiter
                df = pd.read_csv(csv_file, sep=None, engine='python')
            
            return self._process_dataframe(df, filename)
            
        except Exception as e:
            logger.error(f"[TablePreprocessor] ❌ Failed to preprocess CSV {filename}: {e}")
            return None
    
    def _process_dataframe(self, df: pd.DataFrame, table_name: str) -> str:
        """
        Process a single DataFrame with cleaning and semantic enhancement
        
        Args:
            df: Pandas DataFrame
            table_name: Name for the table
            
        Returns:
            Enhanced Markdown format
        """
        # 1. Data Cleaning
        df = self._clean_dataframe(df)
        
        if df.empty:
            logger.warning(f"[TablePreprocessor] DataFrame '{table_name}' is empty after cleaning")
            return f"# {table_name}\n\n[No data after cleaning]"
        
        # 2. Column name standardization
        df = self._standardize_columns(df)
        
        # 3. Data type inference
        df = self._infer_types(df)
        
        # 4. Generate enhanced Markdown
        markdown = self._generate_enhanced_markdown(df, table_name)
        
        logger.debug(f"[TablePreprocessor] Processed '{table_name}': {len(df)} rows, {len(df.columns)} columns")
        return markdown
    
    def _clean_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """Clean DataFrame by removing empty rows/columns and duplicates"""
        original_shape = df.shape
        
        # Remove completely empty rows
        df = df.dropna(how='all')
        
        # Remove completely empty columns
        df = df.dropna(axis=1, how='all')
        
        # Remove duplicate rows
        df = df.drop_duplicates()
        
        # Reset index
        df = df.reset_index(drop=True)
        
        cleaned_shape = df.shape
        if original_shape != cleaned_shape:
            logger.debug(f"[TablePreprocessor] Cleaned: {original_shape} → {cleaned_shape}")
        
        return df
    
    def _standardize_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """Standardize column names"""
        # Convert to string and clean
        new_columns = []
        for col in df.columns:
            # Convert to string
            col_str = str(col).strip()
            
            # Replace newlines and multiple spaces
            col_str = col_str.replace('\n', ' ').replace('\r', ' ')
            col_str = ' '.join(col_str.split())
            
            # Handle unnamed columns
            if col_str.lower().startswith('unnamed:'):
                col_str = f"Column_{len(new_columns)}"
            
            new_columns.append(col_str)
        
        # Handle duplicate column names
        seen = {}
        final_columns = []
        for col in new_columns:
            if col in seen:
                seen[col] += 1
                final_columns.append(f"{col}_{seen[col]}")
            else:
                seen[col] = 0
                final_columns.append(col)
        
        df.columns = final_columns
        return df
    
    def _infer_types(self, df: pd.DataFrame) -> pd.DataFrame:
        """Infer and convert data types"""
        # Auto-infer object types
        df = df.infer_objects()
        
        # Try to convert to numeric where possible
        for col in df.columns:
            if df[col].dtype == 'object':
                # Try numeric conversion
                try:
                    df[col] = pd.to_numeric(df[col], errors='ignore')
                except:
                    pass
        
        return df
    
    def _generate_enhanced_markdown(self, df: pd.DataFrame, table_name: str) -> str:
        """Generate enhanced Markdown with metadata and statistics"""
        lines = []
        
        # Title
        lines.append(f"# Table: {table_name}")
        lines.append("")
        
        # Metadata section
        if self.enable_description:
            lines.append("**Metadata**:")
            lines.append(f"- Rows: {len(df)}")
            lines.append(f"- Columns: {len(df.columns)}")
            lines.append(f"- Column Names: {', '.join(df.columns)}")
            
            # Data types
            type_summary = {}
            for col, dtype in df.dtypes.items():
                dtype_str = str(dtype)
                if dtype_str not in type_summary:
                    type_summary[dtype_str] = []
                type_summary[dtype_str].append(col)
            
            lines.append(f"- Data Types:")
            for dtype, cols in type_summary.items():
                lines.append(f"  - {dtype}: {len(cols)} columns")
            
            lines.append("")
        
        # Statistics section (for numeric columns)
        if self.enable_statistics:
            numeric_cols = df.select_dtypes(include=['number']).columns
            if len(numeric_cols) > 0:
                lines.append("**Statistics**:")
                
                for col in numeric_cols[:5]:  # Limit to first 5 numeric columns
                    series = df[col].dropna()
                    if len(series) > 0:
                        lines.append(f"- {col}:")
                        lines.append(f"  - Count: {len(series)}")
                        lines.append(f"  - Mean: {series.mean():.2f}")
                        lines.append(f"  - Min: {series.min():.2f}")
                        lines.append(f"  - Max: {series.max():.2f}")
                
                if len(numeric_cols) > 5:
                    lines.append(f"- ... and {len(numeric_cols) - 5} more numeric columns")
                
                lines.append("")
        
        # Data table
        lines.append("**Data**:")
        lines.append("")
        
        # Convert to Markdown table (custom implementation to avoid tabulate dependency)
        # Handle NaN values
        df_display = df.fillna('[Empty]')
        
        # Limit very long cell content
        for col in df_display.columns:
            df_display[col] = df_display[col].apply(
                lambda x: str(x)[:100] + '...' if len(str(x)) > 100 else str(x)
            )
        
        # Generate Markdown table manually
        markdown_table = self._dataframe_to_markdown(df_display)
        lines.append(markdown_table)
        
        return "\n".join(lines)
    
    def _dataframe_to_markdown(self, df: pd.DataFrame) -> str:
        """Convert DataFrame to Markdown table without tabulate dependency"""
        lines = []
        
        # Header row
        header = "| " + " | ".join(str(col) for col in df.columns) + " |"
        lines.append(header)
        
        # Separator row
        separator = "|" + "|".join(["---"] * len(df.columns)) + "|"
        lines.append(separator)
        
        # Data rows
        for _, row in df.iterrows():
            row_str = "| " + " | ".join(str(val) for val in row) + " |"
            lines.append(row_str)
        
        return "\n".join(lines)
    
    def get_dataframe_summary(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Get summary statistics for a DataFrame"""
        return {
            'rows': len(df),
            'columns': len(df.columns),
            'column_names': list(df.columns),
            'dtypes': {col: str(dtype) for col, dtype in df.dtypes.items()},
            'missing_values': df.isnull().sum().to_dict(),
            'memory_usage': df.memory_usage(deep=True).sum()
        }


def preprocess_excel_with_pandas(file_bytes: bytes, filename: str) -> Optional[str]:
    """
    Convenience function for Excel preprocessing
    
    Args:
        file_bytes: Raw Excel file bytes
        filename: Original filename
        
    Returns:
        Enhanced Markdown format or None if failed
    """
    preprocessor = TablePreprocessor(enable_statistics=True, enable_description=True)
    return preprocessor.preprocess_excel(file_bytes, filename)


def preprocess_csv_with_pandas(file_bytes: bytes, filename: str) -> Optional[str]:
    """
    Convenience function for CSV preprocessing
    
    Args:
        file_bytes: Raw CSV file bytes
        filename: Original filename
        
    Returns:
        Enhanced Markdown format or None if failed
    """
    preprocessor = TablePreprocessor(enable_statistics=True, enable_description=True)
    return preprocessor.preprocess_csv(file_bytes, filename)
