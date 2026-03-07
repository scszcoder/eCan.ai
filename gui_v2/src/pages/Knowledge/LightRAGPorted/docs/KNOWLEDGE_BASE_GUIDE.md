# Knowledge Base User Guide

## Overview

The Knowledge Base feature powered by LightRAG allows you to build a searchable knowledge repository from your documents. It uses advanced RAG (Retrieval-Augmented Generation) technology to index documents and answer questions based on their content.

## Getting Started

### Step 1: Create a Workspace

A workspace is an isolated environment for your knowledge base. Each workspace has its own documents, indexes, and configuration.

**Creating a Workspace:**
1. Navigate to the **Knowledge** tab → **Settings**
2. In the **Workspace Configuration** section, you'll see the current workspace name
3. To create a new workspace:
   - Click the workspace selector dropdown
   - Select "Create New Workspace"
   - Enter a unique name (e.g., "project_docs", "research_papers")
   - Click "Create"

**Default Workspace:**
- If you don't create a workspace, the system uses "default"
- You can switch between workspaces anytime without losing data

**Important Notes:**
- Each workspace maintains its own vector database and knowledge graph
- Switching workspaces requires restarting the LightRAG service
- Workspace data is stored in `rag_storage/<workspace_name>/`

---

### Step 2: Configure LLM, Embedding, and Reranker Models

Before uploading documents, configure the AI models that power your knowledge base.

#### 2.1 LLM Provider Configuration

The LLM (Large Language Model) generates natural language answers based on retrieved context.

**Supported Providers:**
- **OpenAI**: GPT-4, GPT-3.5-turbo
- **Azure OpenAI**: Enterprise-grade OpenAI models
- **Anthropic**: Claude 3.5 Sonnet, Claude 3 Opus
- **Google Gemini**: Gemini 1.5 Pro/Flash
- **DeepSeek**: DeepSeek Chat, DeepSeek Reasoner
- **Qwen**: Qwen Max, Qwen Plus, Qwen Turbo
- **Ollama**: Local models (Llama, Qwen, DeepSeek)

**Configuration Steps:**
1. Go to **Settings** → **LLM Provider**
2. Select your provider from the dropdown
3. Configure provider-specific settings:
   - **API Key**: Your provider's API key (required for cloud providers)
   - **API Host**: Provider endpoint (auto-filled for most providers)
   - **Model**: Select from available models
   - **Max Tokens**: Maximum response length (default: 4096)

**Recommended Models:**
- **For Quality**: GPT-4, Claude 3.5 Sonnet, Qwen Max
- **For Speed**: GPT-3.5-turbo, Gemini 1.5 Flash, Qwen Turbo
- **For Privacy**: Ollama (runs locally)

#### 2.2 Embedding Provider Configuration

Embeddings convert text into numerical vectors for semantic search.

**Supported Providers:**
- **OpenAI**: text-embedding-3-large (1536/3072 dims), text-embedding-3-small (512/1536 dims)
- **Azure OpenAI**: Same as OpenAI
- **Ollama**: Local embedding models
- **Jina AI**: jina-embeddings-v3 (1024 dims)
- **Voyage AI**: voyage-3, voyage-3-lite
- **Cohere**: embed-english-v3.0, embed-multilingual-v3.0

**Configuration Steps:**
1. Go to **Settings** → **Embedding Provider**
2. Select your provider
3. Configure settings:
   - **API Key**: Provider API key
   - **Model**: Embedding model
   - **Dimensions**: Vector dimensions (critical - must match your data!)
   - **Token Limit**: Max input tokens per request

**Important - Embedding Dimensions:**
- **Cannot change** after uploading documents without clearing the database
- Common dimensions: 1024 (Jina, Qwen), 1536 (OpenAI default), 3072 (OpenAI large)
- If you change dimensions, you must:
  1. Create a new workspace, OR
  2. Clear existing data (Documents tab → Clear All)

**Recommended Embeddings:**
- **Best Quality**: text-embedding-3-large (3072 dims)
- **Balanced**: text-embedding-3-large (1536 dims), jina-embeddings-v3
- **Fast & Local**: Ollama with qwen2.5-embedding

#### 2.3 Reranker Configuration (Optional)

Rerankers improve search accuracy by re-scoring retrieved results.

**Supported Providers:**
- **Cohere**: rerank-english-v3.0, rerank-multilingual-v3.0
- **Jina AI**: jina-reranker-v2-base-multilingual
- **Voyage AI**: rerank-2, rerank-2-lite
- **null**: Disable reranking

**Configuration Steps:**
1. Go to **Settings** → **Reranking Provider**
2. Select provider or "null" to disable
3. Configure API key and model
4. Enable "Rerank by Default" checkbox

**When to Use Reranking:**
- ✅ Large document collections (>1000 documents)
- ✅ Need high precision in results
- ✅ Multi-language content
- ❌ Small datasets (<100 documents) - may not see improvement
- ❌ Speed is critical - adds latency

---

### Step 3: Configure Advanced Parameters

Fine-tune the knowledge base behavior with these parameters.

#### 3.1 Storage Configuration

**Vector Storage:**
- **FAISS** (default): Fast, in-memory vector search
- **Milvus**: Scalable, production-grade vector database
- **Qdrant**: High-performance vector search engine
- **PostgreSQL (PGVector)**: SQL-based vector storage

**Graph Storage:**
- **NetworkX** (default): In-memory graph for small datasets
- **Neo4j**: Production graph database for large knowledge graphs
- **Memgraph**: High-performance graph database

**Document Status Storage:**
- **JsonKVStorage** (default): Simple JSON file storage
- **PostgreSQL**: SQL-based storage for production

**Recommendation:** Use defaults (FAISS + NetworkX + JsonKVStorage) unless you have >10,000 documents.

#### 3.2 Chunking Parameters

Controls how documents are split for indexing.

| Parameter | Default | Description | Recommended Range |
|-----------|---------|-------------|-------------------|
| **Chunk Token Size** | 1200 | Tokens per chunk | 800-2000 |
| **Chunk Overlap** | 100 | Overlap between chunks | 50-200 |
| **Max Async** | 4 | Parallel processing tasks | 2-8 |
| **Max Embed Tokens** | 8192 | Max tokens for embedding | Model-dependent |

**Tuning Tips:**
- **Larger chunks** (1500-2000): Better context, slower processing
- **Smaller chunks** (800-1000): Faster, more granular search
- **More overlap** (150-200): Better continuity, more storage
- **Less overlap** (50-100): Faster processing, less redundancy

#### 3.3 Entity Extraction Parameters

Controls knowledge graph construction.

| Parameter | Default | Description |
|-----------|---------|-------------|
| **Entity Types** | organization, person, geo, event | Types to extract |
| **Max Gleaning** | 1 | Refinement iterations |
| **Entity Summary to Max Tokens** | 500 | Summary length |

**When to Adjust:**
- **Domain-specific**: Add custom entity types (e.g., "product", "chemical")
- **High precision**: Increase max_gleaning to 2-3 (slower)
- **Speed priority**: Set max_gleaning to 0

#### 3.4 Query Parameters

Default settings for queries (can be overridden per query).

| Parameter | Default | Description |
|-----------|---------|-------------|
| **Top K** | 60 | Entities/relations to retrieve |
| **Max Token for Text Unit** | 4000 | Context window |
| **Max Token for Local Context** | 4000 | Local mode context |
| **Max Token for Global Context** | 4000 | Global mode context |

#### 3.5 Log Configuration

- **Verbose Logging**: Enable detailed logs for debugging
- **Log Level**: INFO (default), DEBUG, WARNING, ERROR

---

### Step 4: Upload Documents and Process

#### 4.1 Supported File Formats

- **Documents**: PDF, DOC, DOCX, TXT, MD
- **Data**: CSV, JSON, XML
- **Code**: PY, JS, TS, JAVA, CPP, etc.
- **Web**: HTML, HTM

#### 4.2 Upload Process

1. Navigate to **Documents** tab
2. Click **Upload Files** button
3. Select one or more files
4. Click **Upload**
5. Monitor processing status:
   - **Pending**: Queued for processing
   - **Processing**: Currently being indexed
   - **Preprocessed**: Text extracted, ready for embedding
   - **Processed**: Successfully indexed
   - **Failed**: Error occurred (check logs)

#### 4.3 Processing Pipeline

```
Upload → Text Extraction → Chunking → Embedding → Entity Extraction → Knowledge Graph Construction → Indexing
```

**Processing Time:**
- Small files (<1MB): 10-30 seconds
- Medium files (1-10MB): 1-5 minutes
- Large files (>10MB): 5-30 minutes

**Tips:**
- Upload multiple files at once for batch processing
- Check "Track Status" to monitor progress
- Failed documents can be re-uploaded after fixing issues

#### 4.4 Document Management

- **View Documents**: See all uploaded documents with status
- **Delete Documents**: Remove documents from knowledge base
- **Re-process**: Delete and re-upload to update content
- **Clear All**: Remove all documents (requires confirmation)

---

### Step 5: Query the Knowledge Base

#### 5.1 Query Modes

The knowledge base supports multiple query modes:

| Mode | Description | Best For |
|------|-------------|----------|
| **local** | Entity-focused search | Specific facts, definitions |
| **global** | Relationship pattern analysis | Trends, connections, summaries |
| **hybrid** | Combines local + global | Comprehensive answers |
| **naive** | Pure vector search | Simple keyword matching |
| **mix** | Knowledge graph + vector | **Recommended default** |
| **bypass** | Direct LLM (no retrieval) | General questions |

#### 5.2 Using the Retrieval Tab

1. Navigate to **Retrieval** tab
2. Enter your question in the input box
3. (Optional) Adjust query settings:
   - **Mode**: Select query mode
   - **Top K**: Number of results to retrieve
   - **Custom Prompt**: Guide response format
   - **Enable Rerank**: Toggle reranking
4. Click **Send** or press Enter
5. View the response with references

**Query Examples:**
- "What are the main features of product X?"
- "Summarize the key findings in the research papers"
- "How does component A interact with component B?"
- "List all mentioned companies and their roles"

#### 5.3 Advanced Query Options

**Custom Prompt:**
```
Please provide a detailed technical explanation with code examples.
```

**Response Type:**
- "Multiple Paragraphs"
- "Single Paragraph"
- "Bullet Points"
- "Table Format"

**Context Control:**
- **only_need_context**: Get raw context without LLM generation
- **only_need_prompt**: See the prompt sent to LLM
- **include_chunk_content**: View actual text chunks in references

---

### Step 6: Explore the Knowledge Graph

#### 6.1 Graph Visualization

1. Navigate to **Graph** tab
2. View the knowledge graph visualization
3. Interact with the graph:
   - **Zoom**: Mouse wheel or pinch
   - **Pan**: Click and drag
   - **Select Node**: Click on entity
   - **View Details**: Check properties panel

#### 6.2 Graph Features

- **Nodes**: Entities (people, organizations, locations, events)
- **Edges**: Relationships between entities
- **Colors**: Different entity types
- **Size**: Importance/frequency

#### 6.3 Graph Operations

- **Search**: Find specific entities
- **Filter**: Show/hide entity types
- **Layout**: Adjust graph layout algorithm
- **Export**: Save graph data
- **Full Screen**: Expand graph view

---

## MCP API Integration

The Knowledge Base can be accessed programmatically via MCP (Model Context Protocol) tools in the Skill Editor.

### Available MCP Tools

#### 1. `ragify` - Upload Documents

Ingest documents or text into the knowledge base.

**Parameters:**
```json
{
  "input": {
    "file_paths": ["path/to/file1.pdf", "path/to/file2.txt"],
    "text": "Optional direct text content",
    "file_source": "Optional source identifier"
  }
}
```

**Returns:**
- Track ID for monitoring processing status
- Success/error message

**Example Use Case:**
- Automatically upload documents from a folder
- Insert scraped web content
- Batch process research papers

#### 2. `rag_query` - Query Knowledge Base

Search and retrieve information from the knowledge base.

**Parameters:**
```json
{
  "input": {
    "query": "What are the main features?",
    "mode": "mix",
    "top_k": 60,
    "enable_rerank": true,
    "include_references": true,
    "user_prompt": "Provide a technical summary",
    "response_type": "Bullet Points"
  }
}
```

**Returns:**
- Generated answer
- References with source documents
- Metadata (tokens used, processing time)

**Query Modes:**
- `local`: Entity-focused retrieval
- `global`: Relationship analysis
- `hybrid`: Combined approach
- `naive`: Vector search only
- `mix`: Knowledge graph + vector (recommended)
- `bypass`: Direct LLM without retrieval

**Example Use Case:**
- Build a Q&A chatbot
- Automated research assistant
- Document analysis pipeline

#### 3. `ragify_async` - Async Upload with Notification

Upload documents with background processing and completion notification.

**Parameters:**
```json
{
  "input": {
    "file_paths": ["large_file.pdf"],
    "on_complete": true,
    "notify_task_id": "task_123",
    "timeout_seconds": 600,
    "poll_interval_seconds": 15,
    "notification_message": "Processing complete!"
  }
}
```

**Returns:**
- Immediate response with track ID
- Background monitoring sends notification when done

**Example Use Case:**
- Long-running document processing
- Batch uploads without blocking
- Automated workflows

#### 4. `wait_for_rag_completion` - Wait for Processing

Block until document processing completes.

**Parameters:**
```json
{
  "input": {
    "track_id": "abc123",
    "timeout_seconds": 600,
    "poll_interval_seconds": 15,
    "max_retries": 3
  }
}
```

**Returns:**
- Completion status (success/failed/partial)
- Processed/failed document counts
- Document details

**Example Use Case:**
- Synchronous workflows
- Ensure documents are ready before querying
- Error handling and retry logic

#### 5. `in_browser_upload_file` - Upload via Browser

Upload files through browser automation (for web-based upload forms).

**Parameters:**
```json
{
  "input": {
    "driver_type": "cdp",
    "browser_type": "chrome",
    "href": "https://example.com/upload",
    "upload_file_path": "/path/to/file.pdf"
  }
}
```

**Example Use Case:**
- Automated form submissions
- Web scraping with file uploads
- Testing upload functionality

### MCP Integration Examples

#### Example 1: Auto-Upload and Query

```python
# In Skill Editor - MCP Node
# Step 1: Upload document
{
  "tool": "ragify",
  "input": {
    "file_paths": ["{{file_path}}"]
  }
}

# Step 2: Wait for completion
{
  "tool": "wait_for_rag_completion",
  "input": {
    "track_id": "{{previous_step.track_id}}",
    "timeout_seconds": 300
  }
}

# Step 3: Query the document
{
  "tool": "rag_query",
  "input": {
    "query": "Summarize the main points",
    "mode": "mix",
    "top_k": 30
  }
}
```

#### Example 2: Async Workflow

```python
# Upload with async notification
{
  "tool": "ragify_async",
  "input": {
    "file_paths": ["large_dataset.csv"],
    "on_complete": true,
    "notify_task_id": "{{current_task_id}}",
    "notification_message": "Dataset processing complete"
  }
}

# Continue with other tasks...
# Notification will arrive when processing is done
```

---

## Troubleshooting

### Common Issues

**1. Dimension Mismatch Error**
```
Error: FAISS dimension mismatch
```
**Solution:** 
- Create a new workspace with correct dimensions, OR
- Clear all documents and re-configure embedding dimensions

**2. API Key Errors**
```
Error: Invalid API key
```
**Solution:**
- Verify API key in Settings
- Check provider account status
- Restart application after updating keys

**3. Processing Stuck**
```
Document status: Processing (30+ minutes)
```
**Solution:**
- Check LightRAG server logs (Settings → View Logs)
- Restart LightRAG service (Settings → Restart Service)
- Verify file is not corrupted

**4. Empty Responses**
```
Query returns no results
```
**Solution:**
- Ensure documents are fully processed (status: Processed)
- Try different query modes (mix, hybrid, naive)
- Increase top_k parameter
- Check if query matches document content

**5. Slow Queries**
```
Queries take >30 seconds
```
**Solution:**
- Enable reranking only for important queries
- Reduce top_k value
- Use faster embedding models
- Consider upgrading storage backend (FAISS → Milvus)

### Getting Help

- **Logs**: Settings → View Logs
- **Documentation**: This guide
- **GitHub Issues**: Report bugs and feature requests
- **Community**: Join discussions

---

## Best Practices

### 1. Workspace Organization
- Create separate workspaces for different projects
- Use descriptive names: "legal_docs", "tech_specs", "research_2024"
- Don't mix unrelated content in one workspace

### 2. Document Preparation
- Clean up documents before upload (remove headers/footers)
- Use consistent formatting
- Split very large files (>50MB) into smaller parts
- Include metadata in filenames

### 3. Model Selection
- **Development**: Use fast, cheap models (GPT-3.5, Qwen Turbo)
- **Production**: Use high-quality models (GPT-4, Claude 3.5)
- **Privacy-sensitive**: Use local models (Ollama)

### 4. Query Optimization
- Start with "mix" mode, adjust based on results
- Use specific questions, not vague queries
- Leverage custom prompts for formatting
- Enable reranking for critical queries

### 5. Performance Tuning
- Monitor processing times and adjust chunk sizes
- Use appropriate storage backends for scale
- Enable verbose logging only for debugging
- Regularly clean up unused documents

---

## Appendix

### A. Configuration File Locations

- **Settings**: `<workspace>/resource/data/lightrag.env`
- **Documents**: `<workspace>/rag_storage/<workspace_name>/`
- **Logs**: Check application logs directory

### B. API Endpoints

LightRAG server runs on `http://localhost:20443` by default.

- `POST /documents/upload` - Upload files
- `POST /documents/text` - Insert text
- `POST /query` - Query knowledge base
- `GET /documents/track/{track_id}` - Check processing status
- `GET /graph/entities` - Get entities
- `GET /graph/relationships` - Get relationships

### C. Glossary

- **RAG**: Retrieval-Augmented Generation
- **Embedding**: Vector representation of text
- **Entity**: Named object (person, place, thing)
- **Relationship**: Connection between entities
- **Knowledge Graph**: Network of entities and relationships
- **Chunk**: Text segment for processing
- **Reranking**: Re-scoring search results for accuracy
- **Vector Database**: Storage for embeddings
- **Track ID**: Unique identifier for processing job

---

**Version**: 1.0  
**Last Updated**: 2025-03-07  
**For**: eCan.ai Knowledge Base Feature
