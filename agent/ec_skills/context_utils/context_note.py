# context utility functions
import json
from rich.console import Console
from rich.panel import Panel

console = Console()

def format_message_content(message):
    """Convert message content to displayable string"""
    if isinstance(message.content, str):
        return message.content
    elif isinstance(message.content, list):
        # Handle complex content like tool calls
        parts = []
        for item in message.content:
            if item.get('type') == 'text':
                parts.append(item['text'])
            elif item.get('type') == 'tool_use':
                parts.append(f"\n🔧 Tool Call: {item['name']}")
                parts.append(f"   Args: {json.dumps(item['input'], indent=2)}")
        return "\n".join(parts)
    else:
        return str(message.content)


def format_messages(messages):
    """Format and display a list of messages with Rich formatting"""
    for m in messages:
        msg_type = m.__class__.__name__.replace('Message', '')
        content = format_message_content(m)

        if msg_type == 'Human':
            console.print(Panel(content, title="🧑 Human", border_style="blue"))
        elif msg_type == 'Ai':
            console.print(Panel(content, title="🤖 Assistant", border_style="green"))
        elif msg_type == 'Tool':
            console.print(Panel(content, title="🔧 Tool Output", border_style="yellow"))
        else:
            console.print(Panel(content, title=f"📝 {msg_type}", border_style="white"))


def format_message(messages):
    """Alias for format_messages for backward compatibility"""
    return format_messages(messages)


# ===============================================================
# Selecting Context in LangGraph\n",
# Selecting context means pulling it into the context window to help an agent
# perform a task.
## Scratchpad\n",
# The mechanism for selecting context from a scratchpad depends upon how the
# scratchpad is implemented.
# If it’s a [tool](https://www.anthropic.com/engineering/claude-think-tool),
# then an agent can simply read it by making a tool call. If it’s part of the
# agent’s runtime state, then the developer can choose what parts of state to
# expose to an agent each step. This provides a fine-grained level of control
# for exposing context to an agent.",
### Scratchpad selecting in LangGraph",
# In `1_write_context.ipynb`, we saw how to write to the LangGraph state object.
# Now, we'll see how to select context from state and present it to an LLM call
# in a downstream node. This ability to select from state gives us control over
# what context we present to LLM calls. "


from typing import TypedDict
from rich.console import Console
from rich.pretty import pprint
# Initialize console for rich formatting
console = Console()
class State(TypedDict):
    """State schema for the context selection workflow.
    Attributes:
        topic: The topic for joke generation
        joke: The generated joke content
    """
    topic: str
    joke: str


import getpass
import os
from IPython.display import Image, display
from langchain.chat_models import init_chat_model
from langgraph.graph import END, START, StateGraph
def _set_env(var: str) -> None:
    """Set environment variable if not already set."""
    if not os.environ.get(var):
        os.environ[var] = getpass.getpass(f"{var}: ")
        # Set up environment and initialize model
        _set_env("ANTHROPIC_API_KEY")
        llm = init_chat_model("anthropic:claude-sonnet-4-20250514", temperature=0)

def generate_joke(state: State) -> dict[str, str]:
    """Generate an initial joke about the topic.
    Args:
        state: Current state containing the topic
    Returns:
        Dictionary with the generated joke
    """
    msg = llm.invoke(f"Write a short joke about {state['topic']}")
    return {"joke": msg.content}

def improve_joke(state: State) -> dict[str, str]:
    """Improve an existing joke by adding wordplay.
    This demonstrates selecting context from state - we read the existing
    joke from state and use it to generate an improved version.
    Args:
        state: Current state containing the original joke
    Returns:
        Dictionary with the improved joke
    """
    print(f"Initial joke: {state['joke']}")
    # Select the joke from state to present it to the LLM
    msg = llm.invoke(f"Make this joke funnier by adding wordplay: {state['joke']}")
    return {"improved_joke": msg.content}
    # Build the workflow with two sequential nodes
    workflow = StateGraph(State)
    # Add both joke generation nodes
    workflow.add_node("generate_joke", generate_joke)
    workflow.add_node("improve_joke", improve_joke)
    # Connect nodes in sequence
    workflow.add_edge(START, "generate_joke")
    workflow.add_edge("generate_joke", "improve_joke")
    workflow.add_edge("improve_joke", END)
    # Compile the workflow
    chain = workflow.compile()
    # Display the workflow visualization
    display(Image(chain.get_graph().draw_mermaid_png()))

# Execute the workflow to see context selection in action
joke_generator_state = chain.invoke({"topic": "cats"})

# Display the final state with rich formatting
console.print("\\n[bold blue]Final Workflow State:[/bold blue]")
pprint(joke_generator_state)

## Memory",
# If agents have the ability to save memories, they also need the ability to
# select memories relevant to the task they are performing. This can be useful
# for a few reasons. Agents might select few-shot examples
# ([episodic](https://langchain-ai.github.io/langgraph/concepts/memory/#memory-types)
# [memories](https://arxiv.org/pdf/2309.02427)) for examples of desired behavior,
# instructions
# ([procedural](https://langchain-ai.github.io/langgraph/concepts/memory/#memory-types)
# [memories](https://arxiv.org/pdf/2309.02427)) to steer behavior,
# or facts ([semantic](https://langchain-ai.github.io/langgraph/concepts/memory/#memory-types)
# [memories](https://arxiv.org/pdf/2309.02427)) give the agent task-relevant context.",
# One challenge is ensure that relevant memories are selected. Some popular agents simply use a narrow set of files to
# store memories. For example, many code agent use “rules” files to save instructions (”procedural” memories) or,
# in some cases, examples (”episodic” memories). Claude Code uses [`CLAUDE.md`](http://CLAUDE.md).
# [Cursor](https://docs.cursor.com/context/rules) and [Windsurf](https://windsurf.com/editor/directory) use rules files.
# These are always pulled into context.",
# But, if an agent is storing a larger [collection](https://langchain-ai.github.io/langgraph/concepts/memory/#collection)
# of facts and / or relationships ([semantic](https://langchain-ai.github.io/langgraph/concepts/memory/#memory-types)
# memories), selection is harder. [ChatGPT](https://help.openai.com/en/articles/8590148-memory-faq) is a good example
# of this. At the AIEngineer World’s Fair, [Simon Willison shared](https://simonwillison.net/2025/Jun/6/six-months-in-llms/)
# a good example of memory selection gone wrong: ChatGPT fetched his location and injected it into an image that he requested.
# This type of erroneous memory retrieval can make users feel like the context winder “*no longer belongs to them*”!
# Use of embeddings and/or [knowledge](https://arxiv.org/html/2501.13956v1#:~:text=In%20Zep%2C%20memory%20is%20powered,subgraph%2C%20and%20a%20community%20subgraph)
# [graphs](https://neo4j.com/blog/developer/graphiti-knowledge-graph-memory/#:~:text=changes%20since%20updates%20can%20trigger,and%20holistic%20memory%20for%20agentic)
# for indexing of memories have been used to assist with selection.\n",
### Memory selecting in LangGraph\n",
# In `1_write_context.ipynb`, we saw how to write to `InMemoryStore` in graph nodes. Now let's select state from it.
# We can use the [get](https://langchain-ai.github.io/langgraph/concepts/memory/#memory-storage) method to
# select context from state."

from langgraph.store.memory import InMemoryStore
# Initialize the memory store
store = InMemoryStore()
# Define namespace for organizing memories
namespace = ("rlm", "joke_generator")

# Store the generated joke in memory
store.put(
    namespace,    # namespace for organization
 "last_joke",   # key identifier"
{"joke": joke_generator_state["joke"]} # value to store
)

# Select (retrieve) the joke from memory
retrieved_joke = store.get(namespace, "last_joke").value

# Display the retrieved context
console.print("\\n[bold green]Retrieved Context from Memory:[/bold green]")
pprint(retrieved_joke)


from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.base import BaseStore
from langgraph.store.memory import InMemoryStore

# Initialize storage components
checkpointer = InMemorySaver()
memory_store = InMemoryStore()

def generate_joke(state: State, store: BaseStore) -> dict[str, str]:
    """Generate a joke with memory-aware context selection.
    This function demonstrates selecting context from memory before
    generating new content, ensuring consistency and avoiding duplication.
    Args:
        state: Current state containing the topic
        store: Memory store for persistent context
    Returns:
        Dictionary with the generated joke
    """

    # Select prior joke from memory if it exists
    prior_joke = store.get(namespace, "last_joke")
    if prior_joke:
        prior_joke_text = prior_joke.value["joke"]
        print(f"Prior joke: {prior_joke_text}")
    else:
        print("Prior joke: None!")

    # Generate a new joke that differs from the prior one
    prompt = (
        f"Write a short joke about {state['topic']}, "
        f"but make it different from any prior joke you've written: {prior_joke_text if prior_joke else 'None'}"
    )
    msg = llm.invoke(prompt)
    # Store the new joke in memory for future context selection
    store.put(namespace, "last_joke", {"joke": msg.content})
    return {"joke": msg.content}

    # Build the memory-aware workflow
    workflow = StateGraph(State)
    workflow.add_node("generate_joke", generate_joke)

    # Connect the workflow
    workflow.add_edge(START, "generate_joke")
    workflow.add_edge("generate_joke", END)

    # Compile with both checkpointing and memory store
    chain = workflow.compile(checkpointer=checkpointer, store=memory_store)

# Execute the workflow with the first thread
config = {"configurable": {"thread_id": "1"}}
joke_generator_state = chain.invoke({"topic": "cats"}, config)

# Latest Graph State:
# Extracted Notebook Content
# Extracted from: lc1.md Total cells found: 37
## Code Cell 1 (Execution Count: N/A)
# --------------------------------------------------
# ```python
from typing import TypedDict

from rich.console import Console
from rich.pretty import pprint

# Initialize console for rich formatting
console = Console()


class State(TypedDict):
    """State schema for the context selection workflow.

    Attributes:
        topic: The topic for joke generation
        joke: The generated joke content
    """
    topic: str
    joke: str


# ```

## Code Cell 2 (Execution Count: N/A)
# --------------------------------------------------
# ```python
import getpass
import os

from IPython.display import Image, display
from langchain.chat_models import init_chat_model
from langgraph.graph import END, START, StateGraph


def _set_env(var: str) -> None:
    """Set environment variable if not already set."""
    if not os.environ.get(var):
        os.environ[var] = getpass.getpass(f"{var}: ")


# Set up environment and initialize model
_set_env("ANTHROPIC_API_KEY")
llm = init_chat_model("anthropic:claude-sonnet-4-20250514", temperature=0)


def generate_joke(state: State) -> dict[str, str]:
    """Generate an initial joke about the topic.

    Args:
        state: Current state containing the topic

    Returns:
        Dictionary with the generated joke
    """
    msg = llm.invoke(f"Write a short joke about {state['topic']}")
    return {"joke": msg.content}


def improve_joke(state: State) -> dict[str, str]:
    """Improve an existing joke by adding wordplay.

    This demonstrates selecting context from state - we read the existing
    joke from state and use it to generate an improved version.

    Args:
        state: Current state containing the original joke

    Returns:
        Dictionary with the improved joke
    """
    print(f"Initial joke: {state['joke']}")

    # Select the joke from state to present it to the LLM
    msg = llm.invoke(f"Make this joke funnier by adding wordplay: {state['joke']}")
    return {"improved_joke": msg.content}


# Build the workflow with two sequential nodes
workflow = StateGraph(State)

# Add both joke generation nodes
workflow.add_node("generate_joke", generate_joke)
workflow.add_node("improve_joke", improve_joke)

# Connect nodes in sequence
workflow.add_edge(START, "generate_joke")
workflow.add_edge("generate_joke", "improve_joke")
workflow.add_edge("improve_joke", END)

# Compile the workflow
chain = workflow.compile()

# Display the workflow visualization
display(Image(chain.get_graph().draw_mermaid_png()))
# ```

## Code Cell 3 (Execution Count: N/A)
# --------------------------------------------------
# ```python
# Execute the workflow to see context selection in action
joke_generator_state = chain.invoke({"topic": "cats"})

# Display the final state with rich formatting
console.print("\n[bold blue]Final Workflow State:[/bold blue]")
pprint(joke_generator_state)
# ```

## Code Cell 4 (Execution Count: N/A)
# --------------------------------------------------
# ```python
from langgraph.store.memory import InMemoryStore

# Initialize the memory store
store = InMemoryStore()

# Define namespace for organizing memories
namespace = ("rlm", "joke_generator")

# Store the generated joke in memory
store.put(
    namespace,  # namespace for organization
    "last_joke",  # key identifier
    {"joke": joke_generator_state["joke"]}  # value to store
)

# Select (retrieve) the joke from memory
retrieved_joke = store.get(namespace, "last_joke").value

# Display the retrieved context
console.print("\n[bold green]Retrieved Context from Memory:[/bold green]")
pprint(retrieved_joke)
# ```

## Code Cell 5 (Execution Count: N/A)
# --------------------------------------------------
# ```python
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.base import BaseStore
from langgraph.store.memory import InMemoryStore

# Initialize storage components
checkpointer = InMemorySaver()
memory_store = InMemoryStore()


def generate_joke(state: State, store: BaseStore) -> dict[str, str]:
    """Generate a joke with memory-aware context selection.

    This function demonstrates selecting context from memory before
    generating new content, ensuring consistency and avoiding duplication.

    Args:
        state: Current state containing the topic
        store: Memory store for persistent context

    Returns:
        Dictionary with the generated joke
    """
    # Select prior joke from memory if it exists
    prior_joke = store.get(namespace, "last_joke")
    if prior_joke:
        prior_joke_text = prior_joke.value["joke"]
        print(f"Prior joke: {prior_joke_text}")
    else:
        print("Prior joke: None!")

    # Generate a new joke that differs from the prior one
    prompt = (
        f"Write a short joke about {state['topic']}, "
        f"but make it different from any prior joke you've written: {prior_joke_text if prior_joke else 'None'}"
    )
    msg = llm.invoke(prompt)

    # Store the new joke in memory for future context selection
    store.put(namespace, "last_joke", {"joke": msg.content})

    return {"joke": msg.content}


# Build the memory-aware workflow
workflow = StateGraph(State)
workflow.add_node("generate_joke", generate_joke)

# Connect the workflow
workflow.add_edge(START, "generate_joke")
workflow.add_edge("generate_joke", END)

# Compile with both checkpointing and memory store
chain = workflow.compile(checkpointer=checkpointer, store=memory_store)
# ```

## Code Cell 6 (Execution Count: N/A)
# --------------------------------------------------
# ```python
# Execute the workflow with the first thread
config = {"configurable": {"thread_id": "1"}}
joke_generator_state = chain.invoke({"topic": "cats"}, config)
# ```

## Code Cell 7 (Execution Count: 12)
# --------------------------------------------------
# ```python
# Get the latest state of the graph

latest_state = chain.get_state(config)

console.print("\
[bold magenta]Latest Graph State:[/bold magenta]")

pprint(latest_state)
# ```

## Markdown Cell 8
# ----------------------------------------
# We fetch the prior joke from memory and pass it to an LLM to improve it!


## Code Cell 9 (Execution Count: N/A)
# --------------------------------------------------
# ```python
# Execute the workflow with a second thread to demonstrate memory persistence
config = {"configurable": {"thread_id": "2"}}
joke_generator_state = chain.invoke({"topic": "cats"}, config)
# ```

## Markdown Cell 10
# ----------------------------------------
## Tools


# Agents use tools, but can become overloaded if they are provided
# with too many.This is often because the tool descriptions can overlap,
# causing model confusion about which tool to use.One approach is to apply
# RAG to tool descriptions in order to fetch the most relevant tools for a
# task based upon semantic similarity, an idea that Drew Breunig
# calls “[tool loadout](https://www.dbreunig.com/2025/06/26/how-to-fix-your-context.html).”
#     Some[recent papers](https://arxiv.org/abs/2505.03275) have shown that this
#     improve tool selection accuracy by 3 - fold.

### Tool selecting in LangGraph


# For tool selection,
# the[LangGraph Bigtool](https://github.com/langchain-ai/langgraph-bigtool)
# library is a great way to apply semantic similarity search over tool
# descriptions for selection of the most relevant tools for a task.It leverages
# LangGraph's long-term memory store to allow an agent to search for and
# retrieve relevant tools for a given problem.
# Lets demonstrate `langgraph-bigtool` by equipping an agent with all
# functions from Python's built- in math library.


## Code Cell 11 (Execution Count: 14)
# --------------------------------------------------
# ```python
import math

import types

import uuid

from langchain.embeddings import init_embeddings

from langgraph.store.memory import InMemoryStore

from langgraph_bigtool import create_agent

from langgraph_bigtool.utils import (convert_positional_only_function_to_tool)

_set_env("OPENAI_API_KEY")

# Collect functions from `math` built-in

all_tools = []

for function_name in dir(math):
    function = getattr(math, function_name)

    if not isinstance(function, types.BuiltinFunctionType):
        continue

    # This is an idiosyncrasy of the `math` library

    if tool := convert_positional_only_function_to_tool(function):
        all_tools.append(tool)

# Create registry of tools. This is a dict mapping

# identifiers to tool instances.

tool_registry = {
    str(uuid.uuid4()): tool
    for tool in all_tools
}

# Index tool names and descriptions in the LangGraph

# Store. Here we use a simple in-memory store.

embeddings = init_embeddings("openai:text-embedding-3-small")

store = InMemoryStore(
    index={
        "embed": embeddings,
        "dims": 1536,
        "fields": ["description"],
    }
)

for tool_id, tool in tool_registry.items():
    store.put(
        ("tools",), tool_id,
        {"description": f"{tool.name}: {tool.description}", },)

# Initialize agent

builder = create_agent(llm, tool_registry)

agent = builder.compile(store=store)

# agent
# ```

## Code Cell 12 (Execution Count: 9)
# --------------------------------------------------
# ```python
from utils import format_messages

query = "Use available tools to calculate arc cosine of 0.5."

result = agent.invoke({"messages": query})

format_messages(result['messages'])
# ```

## Markdown Cell 13
# ----------------------------------------
### Learn more


# * ** Toolshed: Scale Tool - Equipped Agents with Advanced RAG-Tool Fusion
# ** - Lumer, E., Subbiah, V.K., Burke, J.A., Basavaraju, P.H.& Huber, A.(2024).
# arXiv:2410.14594.
#
# The paper introduces Toolshed Knowledge Bases and Advanced RAG - Tool Fusion to
# address challenges in scaling tool - equipped AI agents.The Toolshed Knowledge
# Base is a vector database designed to store enhanced tool representations and
# optimize tool selection for large - scale tool - equipped agents.The Advanced
# RAG-Tool Fusion technique applies retrieval-augmented generation across three
# phases: pre-retrieval(tool document enhancement),
# intra-retrieval(query planning and transformation), and
# post-retrieval(document refinement and self-reflection).The researchers
# demonstrated significant performance improvements, achieving 46 %, 56 %, and
# 47 % absolute improvements on different benchmark datasets(Recall @ 5),
# all without requiring model fine - tuning.

# * ** Graph RAG - Tool Fusion ** - Lumer, E., Basavaraju, P.H., Mason, M., Burke, J.A. & Subbiah, V.K.(2025).arXiv: 2502.07223.

# This paper addresses limitations in current RAG approaches
# for tool selection by introducing Graph RAG-Tool Fusion, which
# combines vector-based retrieval with graph traversal to capture tool
# dependencies. Traditional RAG methods fail to capture structured
# dependencies between tools (e.g., a "get stock price" API requiring a
# "stock ticker" parameter from another API).The authors present ToolLinkOS,
# a benchmark dataset with 573 fictional tools across 15 industries,
# each averaging 6.3 tool dependencies.G and 22.1 %over naïve RAG on
# ToolLinkOS and ToolSandbox benchmarks, respectively, by understanding
# and navigating interconnected tool relationships within a predefined
# knowledge graph.
#
# * ** LLM - Tool - Survey ** - https://github.com/quchangle1/LLM-Tool-Survey

# This comprehensive survey repository explores Tool Learning with Large
# Language Models, presenting a systematic examination of how AI models can
# effectively use external tools to enhance their capabilities.The repository
# covers key aspects including benefits of tools (knowledge acquisition,
# expertise enhancement, interaction improvement) and technical workflows.
# It provides an extensive collection of research papers categorized by tool
# types, reasoning methods, and technological approaches, ranging from
# mathematical tools and programming interpreters to multi-modal and
# domain-specific applications.The repository serves as a valuable
# collaborative resource for researchers and practitioners interested in the
# evolving landscape of AI tool integration.

# * ** Retrieval Models Aren't Tool-Savvy: Benchmarking Tool Retrieval** - Shi, Z., Wang, Y., Yan, L., Ren, P., Wang, S., Yin, D. & Ren, Z. arXiv:2503.01763.

# The paper introduces ToolRet, a benchmark for evaluating tool retrieval
# capabilities of information retrieval (IR) models in LLM contexts.Unlike
# existing benchmarks that manually pre-annotate small sets of relevant tools,
# ToolRet comprises 7.6k diverse retrieval tasks and a corpus of 43k tools from
# existing datasets.The research found that even IR models with strong
# performance in conventional benchmarks exhibit poor performance on ToolRet,
# directly impacting task success rates of tool-using LLMs.As a solution, the
# researchers contributed a large-scale training dataset with over 200k
# instances that substantially optimizes tool retrieval ability, bridging
# the gap between existing approaches and real-world tool-learning scenarios.



## Knowledge

# [RAG](https://github.com/langchain-ai/rag-from-scratch) (retrieval
# augmented generation) is an  extremely rich topic. Code agents are some of the
# best examples of agentic RAG in large - scale production.[In practice, RAG is
# can be a central context engineering challenge]
# (https://x.com/_mohansolo/status/1899630246862966837).
# Varun from Windsurf captures some of these challenges well:
#
# > Indexing code ≠ context retrieval … [We are doing indexing & embedding
# search … [with] AST parsing code and chunking along semantically meaningful
# boundaries … embedding search becomes unreliable as a retrieval heuristic as
# the size of the codebase grows … we must rely on a combination of techniques
# like grep / file search, knowledge graph based retrieval, and … a re-ranking
# step where[context] is ranked in order of relevance.

### RAG in LangGraph

# There are several[tutorials and videos]
# (https://langchain-ai.github.io/langgraph/tutorials/rag/langgraph_agentic_rag/) that
# show how to use RAG with LangGraph.When combining RAG with agents in LangGraph,
# it's common to build a retrieval tool. Note that this tool could incorporate
# any combination of RAG techniques, as mentioned above.



# Fetch documents to use in our RAG system.We will use three of the most
# recent pages from Lilian Weng's excellent blog. We'll start by fetching
# the content of the pages using WebBaseLoader utility.

## Code Cell 14 (Execution Count: 15)
# --------------------------------------------------
# ```python
from langchain_community.document_loaders import WebBaseLoader

urls =[
"https://lilianweng.github.io/posts/2025-05-01-thinking/",
"https://lilianweng.github.io/posts/2024-11-28-reward-hacking/",
"https://lilianweng.github.io/posts/2024-07-07-hallucination/",
"https://lilianweng.github.io/posts/2024-04-12-diffusion-video/"
]


docs =[WebBaseLoader(url).load() for url in urls]
# ```


## Markdown Cell 15
# ----------------------------------------
# Split the fetched documents into smaller chunks for indexing into our
# vectorstore.

## Code Cell 16 (Execution Count: 16)
# --------------------------------------------------
# ```python
from langchain_text_splitters import RecursiveCharacterTextSplitter



docs_list =[item for sublist in docs for item in sublist]

text_splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
    chunk_size=2000, chunk_overlap=50
)

doc_splits = text_splitter.split_documents(docs_list)
# ```


## Markdown Cell 17
----------------------------------------
# Now that we have our split documents, we can index them into a vector store
# that we'll use for semantic search.

## Code Cell 18 (Execution Count: 17)
# --------------------------------------------------
# ```python
from langchain_core.vectorstores import InMemoryVectorStore

vectorstore = InMemoryVectorStore.from_documents(documents=doc_splits, embedding=embeddings)

retriever = vectorstore.as_retriever()
# ```


## Markdown Cell 19
# ----------------------------------------
# Create a retriever tool that we can use in our agent.

## Code Cell 20 (Execution Count: 18)
# --------------------------------------------------
# ```python
from langchain.tools.retriever import create_retriever_tool

retriever_tool = create_retriever_tool(retriever, "retrieve_blog_posts", "Search and return information about Lilian Weng blog posts.",)

retriever_tool.invoke({"query": "types of reward hacking"})
# ```
## Markdown Cell 21
# ----------------------------------------
# Now, implement an agent that can select context from the tool.

## Code Cell 22 (Execution Count: 19)
# --------------------------------------------------
# ```python
from langgraph.graph import MessagesState

from langchain_core.messages import SystemMessage, ToolMessage

from typing_extensions import Literal



rag_prompt = """You are a helpful assistant tasked with retrieving information from a series of technical blog posts by Lilian Weng.

Clarify the scope of research with the user before using your retrieval tool to gather context. Reflect on any context you fetch, and

proceed until you have sufficient context to answer the user's research request."""

# Nodes


def llm_call(state: MessagesState):
    """LLM decides whether to call a tool or not"""

    return {
        "messages": [
            llm_with_tools.invoke(
                [
                    SystemMessage(content=rag_prompt)
                ]
                + state["messages"]
            )
        ]
    }


def tool_node(state: dict):
    """Performs the tool call"""

    result = []

    for tool_call in state["messages"][-1].tool_calls:
        tool = tools_by_name[tool_call["name"]]

        observation = tool.invoke(tool_call["args"])

        result.append(ToolMessage(content=observation, tool_call_id=tool_call["id"]))

    return {"messages": result}


# Conditional edge function to route to the tool node or end based upon whether the LLM made a tool call

def should_continue(state: MessagesState) -> Literal["environment", END]:
    """Decide if we should continue the loop or stop based upon whether the LLM made a tool call"""

    messages = state["messages"]

    last_message = messages[-1]

    # If the LLM makes a tool call, then perform an action

    if last_message.tool_calls:
        return "Action"

    # Otherwise, we stop (reply to the user)

    return END


# Build workflow

agent_builder = StateGraph(MessagesState)

# Add nodes

agent_builder.add_node("llm_call", llm_call)

agent_builder.add_node("environment", tool_node)

# Add edges to connect nodes

agent_builder.add_edge(START, "llm_call")

agent_builder.add_conditional_edges(
    "llm_call",
    should_continue,{
        # Name returned by should_continue : Name of next node to visit
        "Action": "environment",
        END: END,
    },

)

agent_builder.add_edge("environment", "llm_call")

# Compile the agent

agent = agent_builder.compile()

# Show the agent

display(Image(agent.get_graph(xray=True).draw_mermaid_png()))
# ```

## Code Cell 23 (Execution Count: N/A)
# --------------------------------------------------
# ```python
from utils import format_messages

query = "What are the types of reward hacking discussed in the blogs?"

result = agent.invoke({"messages": query})

format_messages(result['messages'])
# ```

## Code Cell 24 (Execution Count: N/A)
# --------------------------------------------------
# ```python
from langchain.tools.retriever import create_retriever_tool
from langchain_community.document_loaders import WebBaseLoader
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain.embeddings import init_embeddings

# Define URLs for document loading
urls = [
    "https://lilianweng.github.io/posts/2025-05-01-thinking/",
    "https://lilianweng.github.io/posts/2024-11-28-reward-hacking/",
    "https://lilianweng.github.io/posts/2024-07-07-hallucination/",
    "https://lilianweng.github.io/posts/2024-04-12-diffusion-video/",
]

# Load documents from the specified URLs
docs = [WebBaseLoader(url).load() for url in urls]
docs_list = [item for sublist in docs for item in sublist]

# Split documents into manageable chunks
text_splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
    chunk_size=2000,
    chunk_overlap=50
)
doc_splits = text_splitter.split_documents(docs_list)

# Create embeddings and vectorstore
embeddings = init_embeddings("openai:text-embedding-3-small")
vectorstore = InMemoryVectorStore.from_documents(
    documents=doc_splits,
    embedding=embeddings
)
retriever = vectorstore.as_retriever()

# Create retriever tool for the agent
retriever_tool = create_retriever_tool(
    retriever,
    "retrieve_blog_posts",
    "Search and return information about Lilian Weng blog posts.",
)

# Test the retriever tool
test_result = retriever_tool.invoke({"query": "types of reward hacking"})
# ```/

## Code Cell 25 (Execution Count: N/A)
# --------------------------------------------------
# ```python
from langchain.chat_models import init_chat_model

# Initialize the language model
llm = init_chat_model("anthropic:claude-sonnet-4-20250514", temperature=0)

# Set up tools and bind them to the LLM
tools = [retriever_tool]
tools_by_name = {tool.name: tool for tool in tools}

# Bind tools to LLM for agent functionality
llm_with_tools = llm.bind_tools(tools)
# ```

## Code Cell 26 (Execution Count: N/A)
# --------------------------------------------------
# ```python
from typing_extensions import Literal

from IPython.display import Image, display
from langchain_core.messages import SystemMessage, ToolMessage
from langgraph.graph import END, START, MessagesState, StateGraph


# Define extended state with summary field
class State(MessagesState):
    """Extended state that includes a summary field for context compression."""
    summary: str


# Define the RAG agent system prompt
rag_prompt = """You are a helpful assistant tasked with retrieving information from a series of technical blog posts by Lilian Weng. 
Clarify the scope of research with the user before using your retrieval tool to gather context. Reflect on any context you fetch, and
proceed until you have sufficient context to answer the user's research request."""

# Define the summarization prompt
summarization_prompt = """Summarize the full chat history and all tool feedback to 
give an overview of what the user asked about and what the agent did."""


def llm_call(state: MessagesState) -> dict:
    """Execute LLM call with system prompt and message history.

    Args:
        state: Current conversation state

    Returns:
        Dictionary with new messages
    """
    messages = [SystemMessage(content=rag_prompt)] + state["messages"]
    response = llm_with_tools.invoke(messages)
    return {"messages": [response]}


def tool_node(state: MessagesState) -> dict:
    """Execute tool calls and return results.

    Args:
        state: Current conversation state with tool calls

    Returns:
        Dictionary with tool results
    """
    result = []
    for tool_call in state["messages"][-1].tool_calls:
        tool = tools_by_name[tool_call["name"]]
        observation = tool.invoke(tool_call["args"])
        result.append(ToolMessage(content=observation, tool_call_id=tool_call["id"]))
    return {"messages": result}


def summary_node(state: MessagesState) -> dict:
    """Generate a summary of the conversation and tool interactions.

    Args:
        state: Current conversation state

    Returns:
        Dictionary with conversation summary
    """
    messages = [SystemMessage(content=summarization_prompt)] + state["messages"]
    result = llm.invoke(messages)
    return {"summary": result.content}


def should_continue(state: MessagesState) -> Literal["Action", "summary_node"]:
    """Determine next step based on whether LLM made tool calls.

    Args:
        state: Current conversation state

    Returns:
        Next node to execute
    """
    messages = state["messages"]
    last_message = messages[-1]

    # If LLM made tool calls, execute them
    if last_message.tool_calls:
        return "Action"
    # Otherwise, proceed to summarization
    return "summary_node"


# Build the RAG agent workflow
agent_builder = StateGraph(State)

# Add nodes to the workflow
agent_builder.add_node("llm_call", llm_call)
agent_builder.add_node("environment", tool_node)
agent_builder.add_node("summary_node", summary_node)

# Define the workflow edges
agent_builder.add_edge(START, "llm_call")
agent_builder.add_conditional_edges(
    "llm_call",
    should_continue,
    {
        "Action": "environment",
        "summary_node": "summary_node",
    },
)
agent_builder.add_edge("environment", "llm_call")
agent_builder.add_edge("summary_node", END)

# Compile the agent
agent = agent_builder.compile()

# Display the agent workflow
display(Image(agent.get_graph(xray=True).draw_mermaid_png()))
# ```

## Code Cell 27 (Execution Count: 4)
# --------------------------------------------------
# ```python
from utils import format_messages, format_message

# ```

## Code Cell 28 (Execution Count: N/A)
# --------------------------------------------------
# ```python
query = "Why does RL improve LLM reasoning according to the blogs?"

result = agent.invoke({"messages": query})

format_message(result['messages'])

# ```
## Code Cell 29 (Execution Count: 6)
# --------------------------------------------------
# ```python
from rich.markdown import Markdown

Markdown(result["summary"])
# ```

## Markdown Cell 30
# ----------------------------------------
tool_summarization_prompt = """You will be provided a doc from a RAG system.
Summarize the docs, ensuring to retain all relevant / essential information.
Your goal is simply to reduce the size of the doc (tokens) to a more manageable size."""


# Conditional edge function to route to the tool node or end based upon whether the LLM made a tool call

def should_continue(state: MessagesState) -> Literal["environment", END]:
    """Decide if we should continue the loop or stop based upon whether the LLM made a tool call"""

    messages = state["messages"]

    last_message = messages[-1]

    # If the LLM makes a tool call, then perform an action

    if last_message.tool_calls:
        return "Action"

    # Otherwise, we stop (reply to the user)

    return END


def tool_node_with_summarization(state: dict):
    """Performs the tool call"""

    result = []

    for tool_call in state["messages"][-1].tool_calls:
        tool = tools_by_name[tool_call["name"]]

        observation = tool.invoke(tool_call["args"])

        # Summarize the doc

        summary = llm.invoke([{"role": "system",
                               "content": tool_summarization_prompt},
                              {"role": "user",
                               "content": observation}])

        result.append(ToolMessage(content=summary.content, tool_call_id=tool_call["id"]))

    return {"messages": result}


# Build workflow

agent_builder = StateGraph(State)

# Add nodes

agent_builder.add_node("llm_call", llm_call)

agent_builder.add_node("environment_with_summarization", tool_node_with_summarization)

# Add edges to connect nodes

agent_builder.add_edge(START, "llm_call")

agent_builder.add_conditional_edges(
    "llm_call",
    should_continue,
    {
        # Name returned by should_continue : Name of next node to visit
        "Action": "environment_with_summarization",
        END: END,
    },
)

agent_builder.add_edge("environment_with_summarization", "llm_call")

# Compile the agent

agent = agent_builder.compile()

# Show the agent

display(Image(agent.get_graph(xray=True).draw_mermaid_png()))

## Code Cell 31 (Execution Count: N/A)
# --------------------------------------------------
# ```python
from utils import format_messages

query = "Why does RL improve LLM reasoning according to the blogs?"

result = agent.invoke({"messages": query})

format_messages(result['messages'])
# ```

## Markdown Cell 32
# ----------------------------------------
from utils import format_messages

format_messages(result['messages'])

## Markdown Cell 33
----------------------------------------
### Learn more


# * ** LangGraph Swarm ** - https://github.com/langchain-ai/langgraph-swarm-py

# LangGraph Swarm is a Python library
# for creating multi - agent AI systems with dynamic collaboration capabilities.
# Key features include agents that can dynamically hand off control based on
# specialization while maintaining conversation context between transitions.
# The library supports customizable handoff tools between agents, streaming,
# short-term and long-term memory, and human- in -the-loop interactions.
# Built on the LangGraph framework, it enables creating flexible, context-aware
# multi-agent systems where different AI agents can collaborate and seamlessly
# transfer conversation control based on their unique capabilities.Installation is
# simple with `pip install langgraph-swarm`.
#
# *[See](https://www.youtube.com/watch?v=4nZl32FwU-o)
# [these](https://www.youtube.com/watch?v=JeyDrn1dSUQ)
# [videos](https://www.youtube.com/watch?v=B_0TNuYi56w)
# for more detail on on multi-agent systems.


## Markdown Cell 34
# ----------------------------------------
## Sandboxed Environment


# HuggingFace’s[deepresearcher](https://huggingface.co/blog/open-deep-research#:~:text=From%20building%20,it%20can%20still%20use%20it) shows another
# interesting example of context isolation.

# Most agents use [tool calling APIs]
# (https://docs.anthropic.com/en/docs/agents-and-tools/tool-use/overview),
# which return JSON objects (tool arguments) that can be passed to
# tools (e.g., a search API) to get tool feedback (e.g., search results).
# HuggingFace uses a [CodeAgent](https://huggingface.co/papers/2402.01030),
# which outputs code to invoke tools. The code then runs in a
# [sandbox](https://e2b.dev/). Selected context (e.g., return values)
# from code execution is then passed back to the LLM.

# This allows context to be isolated in the environment, outside of the
# LLM context window.Hugging Face noted that this is a great way to isolate
# token-heavy objects from the LLM:

# >[Code Agents allow for] a better handling of state … Need to store this
# image / audio / other for later use? No problem, just assign it as a variable
# in your state and you[use it later].

### Sandboxed Environment in LangGraph

# It's pretty easy to use Sandboxes with LangGraph agents.
# [LangChain Sandbox](https://github.com/langchain-ai/langchain-sandbox) provides
# a secure environment for executing untrusted Python code. It leverages
# Pyodide (Python compiled to WebAssembly) to run Python code in a sandboxed
# environment. This can simply be used as a tool in a LangGraph agent.
# NOTE: Install Deno (required): https://docs.deno.com/runtime/getting_started/installation/

## Code Cell 35 (Execution Count: 4)
# --------------------------------------------------
# ```python
from langchain_sandbox import PyodideSandboxTool

tool = PyodideSandboxTool()

result = await tool.ainvoke("print('Hello, world!')")
# ```


## Code Cell 36 (Execution Count: N/A)
# --------------------------------------------------
# ```python
from langchain_sandbox import PyodideSandboxTool
from langgraph.prebuilt import create_react_agent

# Create sandbox tool with network access for package installation
tool = PyodideSandboxTool(
    # Allow Pyodide to install Python packages that might be required
    allow_net=True
)

# Create a React agent with the sandbox tool
agent = create_react_agent(
    "anthropic:claude-3-7-sonnet-latest",
    tools=[tool],
)

# Execute a mathematical query using the sandbox
result = await agent.ainvoke(
    {"messages": [{"role": "user", "content": "what's 5 + 7?"}]},
)

# Format and display the results
format_messages(result['messages'])
# ```


## Markdown Cell 37
# ----------------------------------------
### State

# An agent’s runtime state object can also be a great way to isolate context.
# This can serve the same purpose as sandboxing. A state object can be designed
# with a schema (e.g., a Pydantic model) that has various fields that context
# can be written to.One field of the schema (e.g., messages) can be exposed to
# the LLM at each turn of the agent, but the schema can isolate information in
# other fields for more selective use.

### State Isolation in LangGraph

# LangGraph is designed around a
# [state](https://langchain-ai.github.io/langgraph/concepts/low_level/#state) object,
# allowing you to design a state schema and access different fields of that schema
# across trajectory of your agent. For example, you can easily store context from
# tool calls in certain fields of your state object, isolating from the LLM until
# that context is required. In these notebooks, you've seen numerous example of this.


