import os
import asyncio
from pathlib import Path

# Add project root directory to Python path
import sys
from typing import Any, Dict, List, Optional

# Handle __file__ not defined in PyInstaller frozen environment
if '__file__' not in dir():
    if getattr(sys, 'frozen', False):
        __file__ = os.path.join(sys._MEIPASS, 'knowledge', 'lightrag_direct.py')
    else:
        __file__ = os.path.abspath(sys.argv[0])

sys.path.append(str(Path(__file__).parent.parent))

from lightrag.llm.openai import openai_complete_if_cache, openai_embed
from lightrag.utils import EmbeddingFunc, logger, set_verbose_debug
from raganything import RAGAnything, RAGAnythingConfig

from utils.logger_helper import logger_helper as logger
from utils.logger_helper import get_traceback

def list_files_in_directory(directory_path):
    """
    Lists all files (and directories) within a specified directory.

    Args:
        directory_path (str): The path to the directory to list.

    Returns:
        list: A list containing the names of all entries (files and directories)
              in the specified directory.
    """
    try:
        entries = os.listdir(directory_path)
        # Filter to include only files if desired
        files_only = [entry for entry in entries if os.path.isfile(os.path.join(directory_path, entry))]
        return files_only
    except FileNotFoundError:
        print(f"Error: Directory '{directory_path}' not found.")
        return []
    except Exception as e:
        print(f"An error occurred: {e}")
        return []

# this file bypasses client-server model, just use lightrag lib directly.
class LightRAG:
    """Backend adapter to proxy LightRAG WebGUI API calls from frontend IPC.

    NOTE: This is a skeleton. Fill in implementations to call the real LightRAG
    endpoints and translate responses as needed.
    """

    def __init__(self, working_dir:str="", parser="mineru", parse_method:str="auto", base_url: Optional[str] = None, api_key: Optional[str] = None, token: Optional[str] = None):
        self.config = RAGAnythingConfig(
            working_dir=working_dir or "./lightrag_data/inputs",
            parser=parser,  # Parser selection: mineru or docling
            parse_method="auto",  # Parse method: auto, ocr, or txt
            enable_image_processing=True,
            enable_table_processing=True,
            enable_equation_processing=True,
        )

        print("LightRAG Direct:", list_files_in_directory("./lightrag_data/inputs"))

        # Define embedding function
        self.embedding_func = EmbeddingFunc(
            embedding_dim=3072,
            max_token_size=8192,
            func=lambda texts: openai_embed(
                texts,
                model="text-embedding-3-large",
                api_key=api_key,
                base_url=base_url,
            ),
        )

        self.rag = RAGAnything(
            config=self.config,
            llm_model_func=self.llm_model_func,
            vision_model_func=self.vision_model_func,
            embedding_func=self.embedding_func,
        )

    def get_config(self):
        return self.config

    # Define LLM model function
    def llm_model_func(self, prompt, system_prompt=None, history_messages=[], **kwargs):
        return openai_complete_if_cache(
            "gpt-4o-mini",
            prompt,
            system_prompt=system_prompt,
            history_messages=history_messages,
            # api_key=api_key,
            # base_url=base_url,
            **kwargs,
        )

    # Define vision model function for image processing
    def vision_model_func(self,
            prompt,
            system_prompt=None,
            history_messages=[],
            image_data=None,
            messages=None,
            **kwargs,
    ):
        # If messages format is provided (for multimodal VLM enhanced query), use it directly
        if messages:
            return openai_complete_if_cache(
                "gpt-5-mini",
                "",
                system_prompt=None,
                history_messages=[],
                messages=messages,
                # api_key=api_key,
                # base_url=base_url,
                **kwargs,
            )
        # Traditional single image format
        elif image_data:
            return openai_complete_if_cache(
                "gpt-5-mini",
                "",
                system_prompt=None,
                history_messages=[],
                messages=[
                    {"role": "system", "content": system_prompt}
                    if system_prompt
                    else None,
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{image_data}"
                                },
                            },
                        ],
                    }
                    if image_data
                    else {"role": "user", "content": prompt},
                ],
                # api_key=api_key,
                # base_url=base_url,
                **kwargs,
            )
        # Pure text format
        else:
            return self.llm_model_func(prompt, system_prompt, history_messages, **kwargs)

    # ---- Documents ingestion ----
    async def ingest_docs(self,
        file_path: str,
        output_dir: str,
        api_key: str,
        base_url: str = None,
        working_dir: str = None,
        parser: str = None) -> Dict[str, Any]:
        """
        Process document with RAGAnything

        Args:
            file_path: Path to the document
            output_dir: Output directory for RAG results
            api_key: OpenAI API key
            base_url: Optional base URL for API
            working_dir: Working directory for RAG storage
        """
        try:
            # Process document
            await self.rag.process_document_complete(
                file_path=file_path, output_dir=output_dir, parse_method="auto"
            )


        except Exception as e:
            err = get_traceback(e, "LightragClient.ingest_files")
            logger.error(err)
            return {"status": "error", "message": str(e)}



    async def retrieve_knowledge(self,
            question: str,
            mm_content: list,
            mode: str="hybrid"
        ):
        try:
            # Some examples:
            # 1. Pure text queries using aquery()
            # text_queries = [
            #     "What is the main content of the document?",
            #     "What are the key topics discussed?",
            # ]
            #
            # for query in text_queries:
            #     logger.info(f"\n[Text Query]: {query}")
            #     result = await self.rag.aquery(query, mode="hybrid")
            #     logger.info(f"Answer: {result}")

            # 2. Multimodal query with specific multimodal content using aquery_with_multimodal()
            # logger.info(
            #     "\n[Multimodal Query]: Analyzing performance data in context of document"
            # )
            # multimodal_result = await self.rag.aquery_with_multimodal(
            #     "Compare this performance data with any similar results mentioned in the document",
            #     multimodal_content=[
            #         {
            #             "type": "table",
            #             "table_data": """Method,Accuracy,Processing_Time
            #                         RAGAnything,95.2%,120ms
            #                         Traditional_RAG,87.3%,180ms
            #                         Baseline,82.1%,200ms""",
            #             "table_caption": "Performance comparison results",
            #         }
            #     ],
            #     mode="hybrid",
            # )
            # logger.info(f"Answer: {multimodal_result}")

            # 3. Another multimodal query with equation content
            # Mathematical formula analysis
            # query = "Explain this formula and relate it to any mathematical concepts in the document"
            # multimodal_content=[
            #                     {
            #                         "type": "equation",
            #                         "latex": "F1 = 2 \\cdot \\frac{precision \\cdot recall}{precision + recall}",
            #                         "equation_caption": "F1-score calculation formula",
            #                     }
            #                 ],

            if not mm_content:
                result = await self.rag.aquery(question, mode="hybrid")
            else:
                result = await self.rag.aquery_with_multimodal(question, multimodal_content=mm_content, mode=mode)
            logger.info(f"Answer: {result}")
            return result

        except Exception as e:
            err_msg = get_traceback(e, "ErrorLightRAGRetrieveKnowledge")
            logger.error(err_msg)
            return err_msg