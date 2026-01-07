"""
Code Agent for Skill Editor

A code generation agent that creates and edits flowgrams based on:
1. User requests (direct or from planner)
2. Implementation plans from PlannerAgent
3. Iterative validation and fixing

Inspired by BubbleLab's Boba/Pearl agent pattern.
"""

import json
import re
import uuid
from typing import Any, Dict, List, Optional, Callable

from utils.logger_helper import logger_helper as logger

from .schemas import (
    CodeAgentAction,
    CodeAgentOutput,
    Flowgram,
    FlowgramNode,
    FlowgramEdge,
    NodePosition,
    ValidationResult,
    ValidationError,
    ImplementationPlan,
    CanvasCommand,
    NODE_TYPES,
    get_node_types_description,
)
from .placement import place_nodes, LOOP_INTERNAL_CFG


# ============================================================
# Constants
# ============================================================

MAX_VALIDATION_RETRIES = 3
DEFAULT_NODE_SPACING_X = 250
DEFAULT_NODE_SPACING_Y = 150
START_POSITION_X = 100
START_POSITION_Y = 100


# ============================================================
# System Prompts
# ============================================================

CODE_GENERATION_PROMPT = """You are a Code Agent for the Skill Editor, specializing in generating flowgram workflows.

Your role is to translate user requests and implementation plans into concrete flowgram structures (nodes and edges).

## AVAILABLE NODE TYPES:
{node_types}

## CURRENT CANVAS STATE:
{canvas_context}

## IMPLEMENTATION PLAN (if provided):
{plan_context}

## SKILL DIRECTORY STRUCTURE:
Skills are stored in `my_skills/` under the application's data directory.
Each skill follows this structure:
  my_skills/<skill_name>_skill/
    diagram_dir/
      <skill_name>_skill.json        # Main flowgram definition
      <skill_name>_skill_bundle.json # Additional sheets/data

When you generate a flowgram, the system will automatically:
1. Create the skill directory structure
2. Save the flowgram JSON files
3. Load the skill into the canvas for editing

## FLOWGRAM GENERATION RULES:
1. Every flowgram MUST have a "start" node and an "end" node
2. All nodes must be connected - no orphan nodes
3. Node IDs must be unique (use descriptive IDs like "llm_process", "condition_check")
4. Position nodes in a logical flow (top to bottom or left to right)
5. Include proper configuration for each node type
6. For LLM nodes, include system_prompt and user_prompt in config
7. For MCP tool nodes, include tool_name and tool_input in config
8. For condition nodes, include the condition expression
9. Populate flowgram.metadata with `skillName` (snake_case), `description`, and helpful tags/owner info
10. Infer a concise snake_case skill name when the user does not provide one explicitly (e.g., "ebay000" → "ebay000")
11. ALWAYS write the `message` field as a short, human-readable summary of what you built (do not echo raw JSON)
12. Include where the skill was saved in your message (e.g., "Created 'ebay000' skill with start→end flow. Saved to my_skills/ebay000_skill/")

## CONDITION NODE STRUCTURE (IMPORTANT):
Condition nodes have multiple output branches (if/elseif/else). They require:

1. A `conditions` array in the config with branch definitions
2. Each condition has a unique `key` (e.g., "if_xxx", "elseif_xxx", "else_xxx") and a `value` object
3. Order: if branch first, then any elseif branches, then else branch last
4. By default, only if and else branches (no elseif). Add elseif branches only when needed.
5. Edges FROM condition nodes MUST use `source_handle` (or `sourcePortID`) matching the condition key
6. Note: Each elseif branch adds ~27px to the node height

Example condition node (default - no elseif):
{{
  "id": "condition_1",
  "type": "condition",
  "label": "Check Status",
  "position": {{"x": 400, "y": 200}},
  "config": {{
    "conditions": [
      {{"key": "if_branch", "value": {{}}}},
      {{"key": "else_branch", "value": {{}}}}
    ]
  }}
}}

Example condition node with elseif:
{{
  "id": "condition_2",
  "type": "condition",
  "label": "Multi-way Branch",
  "position": {{"x": 400, "y": 200}},
  "config": {{
    "conditions": [
      {{"key": "if_high", "value": {{}}}},
      {{"key": "elseif_medium", "value": {{}}}},
      {{"key": "elseif_low", "value": {{}}}},
      {{"key": "else_default", "value": {{}}}}
    ]
  }}
}}

Example edges from condition node:
{{
  "source": "condition_1",
  "target": "success_node",
  "source_handle": "if_branch"
}},
{{
  "source": "condition_1",
  "target": "failure_node",
  "source_handle": "else_branch"
}}

## LOOP NODE STRUCTURE (IMPORTANT):
Loop nodes are container nodes that hold internal nodes. They have a special structure:

1. Loop nodes MUST have a `blocks` array containing internal nodes
2. The `blocks` array MUST include:
   - A "block-start" node (type: "block-start") at the beginning
   - A "block-end" node (type: "block-end") at the end
   - Any content nodes (llm, mcp, code, etc.) between them
3. Loop nodes MUST have an `internal_edges` array connecting the blocks
4. Internal node positions are RELATIVE to the loop's internal coordinate system:
   - block-start: position around (30, 0)
   - Content nodes: y ~16, x spread between 120 and 450
   - block-end: position at the right side
5. Loop node config should include: loopMode ("loopFor", "loopWhile", "loopForEach"), loopCountExpr, loopWhileExpr

Example loop node:
{{
  "id": "loop_1",
  "type": "loop",
  "label": "Process Items",
  "position": {{"x": 400, "y": 200}},
  "config": {{"loopMode": "loopFor", "loopCountExpr": "3", "loopWhileExpr": ""}},
  "blocks": [
    {{"id": "block_start_1", "type": "block-start", "label": "Loop Start", "position": {{"x": 30, "y": 0}}, "config": {{}}}},
    {{"id": "llm_in_loop", "type": "llm", "label": "Process", "position": {{"x": 200, "y": 16}}, "config": {{}}}},
    {{"id": "block_end_1", "type": "block-end", "label": "Loop End", "position": {{"x": 450, "y": 16}}, "config": {{}}}}
  ],
  "internal_edges": [
    {{"source": "block_start_1", "target": "llm_in_loop"}},
    {{"source": "llm_in_loop", "target": "block_end_1"}}
  ]
}}

## OUTPUT FORMAT:
You MUST respond with valid JSON containing the flowgram:

{{
  "action": "generate_flowgram",
  "message": "Brief, human-readable summary of what was created (e.g. 'Created ebay order triage flow with 5 nodes')",
  "flowgram": {{
    "nodes": [
      {{
        "id": "start",
        "type": "start",
        "label": "Start",
        "position": {{"x": 100, "y": 100}},
        "config": {{}}
      }},
      {{
        "id": "llm_process",
        "type": "llm",
        "label": "Process with AI",
        "position": {{"x": 100, "y": 250}},
        "config": {{
          "model": "gpt-4o-mini",
          "system_prompt": "You are a helpful assistant.",
          "user_prompt": "Process the input: {{{{input}}}}",
          "temperature": 0.7
        }}
      }},
      {{
        "id": "end",
        "type": "end",
        "label": "End",
        "position": {{"x": 100, "y": 400}},
        "config": {{}}
      }}
    ],
    "edges": [
      {{"source": "start", "target": "llm_process"}},
      {{"source": "llm_process", "target": "end"}}
    ],
    "metadata": {{
      "name": "Workflow Name",
      "description": "What this workflow does"
    }}
  }}
}}

For simple answers without code generation:
{{
  "action": "answer",
  "message": "Your explanation or answer here (human readable)"
}}

For requests that cannot be fulfilled:
{{
  "action": "reject",
  "message": "Explanation of why this cannot be done"
}}

## IMPORTANT:
- Generate complete, valid flowgrams
- Use descriptive node labels
- Position nodes to avoid overlap
- Include all necessary configurations
- Connect all nodes properly
"""

EDIT_FLOWGRAM_PROMPT = """You are a Code Agent for the Skill Editor, specializing in editing existing flowgrams.

## CURRENT FLOWGRAM:
{current_flowgram}

## EDIT REQUEST:
{edit_request}

## AVAILABLE NODE TYPES:
{node_types}

## EDIT RULES:
1. Preserve existing node IDs when modifying nodes
2. Only change what's necessary for the edit
3. Maintain valid connections after edits
4. Update positions if adding/removing nodes to avoid overlap
5. Keep the start and end nodes

## CONDITION NODE STRUCTURE (IMPORTANT):
When adding or editing condition nodes:
1. They MUST have a `conditions` array in config with branch definitions
2. Each condition has a unique `key` (e.g., "if_xxx", "elseif_xxx", "else_xxx") and a `value` object
3. Order: if branch first, then any elseif branches, then else branch last
4. Edges FROM condition nodes MUST include `source_handle` matching the condition key

Example condition node config:
{{"conditions": [{{"key": "if_branch", "value": {{}}}}, {{"key": "else_branch", "value": {{}}}}]}}

Example edges FROM a condition node (CRITICAL - must include source_handle):
{{"source": "condition_1", "target": "success_node", "source_handle": "if_branch"}}
{{"source": "condition_1", "target": "failure_node", "source_handle": "else_branch"}}

## LOOP NODE STRUCTURE (IMPORTANT):
When adding or editing loop nodes, they MUST have:
1. A `blocks` array with block-start, content nodes, and block-end
2. An `internal_edges` array connecting the blocks
3. Internal positions relative to loop's coordinate system (block-start at x:30, content at x:120-450, block-end at right)

## EDITING NODES INSIDE A LOOP:
When the user asks to add/remove/update nodes "inside", "in", or "within" a loop:
1. Find the target loop node in the flowgram
2. Modify its `blocks` array (add/remove/update nodes)
3. Update its `internal_edges` array to maintain proper connections
4. Keep block-start as the first node and block-end as the last node in the chain
5. Position new internal nodes between x:120-450, y:16

Example requests that target loop internals:
- "add an llm node inside the loop" → Add to loop's blocks array
- "remove the mcp node from the loop" → Remove from loop's blocks array
- "connect the llm to the code node in the loop" → Update loop's internal_edges

## OUTPUT FORMAT:
Respond with the complete updated flowgram:

{{
  "action": "edit_flowgram",
  "message": "Description of changes made",
  "flowgram": {{
    "nodes": [...],
    "edges": [...],
    "metadata": {{...}}
  }}
}}
"""


# ============================================================
# Code Agent Class
# ============================================================

class CodeAgent:
    """
    Code generation agent that creates and edits flowgrams.
    
    This agent:
    1. Generates flowgrams from natural language or plans
    2. Edits existing flowgrams based on requests
    3. Validates flowgram structure
    4. Iteratively fixes validation errors
    """
    
    def __init__(self, llm=None):
        """
        Initialize the code agent.
        
        Args:
            llm: LangChain LLM instance. If None, will use default from settings.
        """
        self._llm = llm
        self._current_flowgram: Optional[Flowgram] = None
        self._generation_history: List[Dict[str, Any]] = []
        logger.info("[CodeAgent] Initialized")
    
    @property
    def llm(self):
        """Lazy load LLM from settings if not provided"""
        if self._llm is None:
            try:
                self._llm = self._load_llm_from_settings()
                logger.info("[CodeAgent] Loaded LLM from settings")
            except Exception as e:
                logger.error(f"[CodeAgent] Failed to load LLM: {e}")
                raise
        return self._llm
    
    def _load_llm_from_settings(self):
        """Load LLM instance from application settings"""
        try:
            from app_context import AppContext
            from agent.ec_skills.llm_utils.llm_utils import pick_llm
            
            mainwin = AppContext.get_main_window()
            if mainwin is None:
                raise RuntimeError("Main window not available")
            
            config_manager = getattr(mainwin, 'config_manager', None)
            if config_manager is None:
                raise RuntimeError("Config manager not available")
            
            # Get LLM providers and default LLM from config_manager
            llm_providers = config_manager.llm_manager.get_all_providers()
            default_llm = config_manager.general_settings.default_llm
            
            if not llm_providers:
                raise RuntimeError("No LLM providers configured")
            
            llm_instance = pick_llm(
                default_llm=default_llm,
                llm_providers=llm_providers,
                config_manager=config_manager,
                allow_fallback=True
            )
            
            if llm_instance is None:
                raise RuntimeError("Failed to create LLM instance")
            
            return llm_instance
            
        except Exception as e:
            logger.error(f"[CodeAgent] Error loading LLM: {e}")
            try:
                from langchain_openai import ChatOpenAI
                import os
                api_key = os.environ.get("OPENAI_API_KEY")
                if api_key:
                    logger.info("[CodeAgent] Using fallback OpenAI LLM")
                    return ChatOpenAI(model="gpt-4o-mini", api_key=api_key)
            except Exception:
                pass
            raise
    
    def _format_canvas_context(self, canvas_context: Optional[Dict]) -> str:
        """Format canvas context for prompts"""
        if not canvas_context:
            return "Empty canvas (no nodes or edges)"
        
        nodes = canvas_context.get("nodes", [])
        edges = canvas_context.get("edges", [])
        
        if not nodes:
            return "Empty canvas (no nodes or edges)"
        
        lines = [f"Nodes ({len(nodes)}):"]
        for node in nodes[:10]:
            lines.append(f"  - {node.get('id')}: {node.get('type')} ({node.get('label', 'unnamed')})")
        
        if len(nodes) > 10:
            lines.append(f"  ... and {len(nodes) - 10} more nodes")
        
        lines.append(f"\nEdges ({len(edges)}):")
        for edge in edges[:10]:
            lines.append(f"  - {edge.get('source')} → {edge.get('target')}")
        
        if len(edges) > 10:
            lines.append(f"  ... and {len(edges) - 10} more edges")
        
        return "\n".join(lines)
    
    def _format_plan_context(self, plan: Optional[ImplementationPlan]) -> str:
        """Format implementation plan for prompts"""
        if not plan:
            return "No implementation plan provided"
        
        lines = [
            f"Summary: {plan.summary}",
            f"Complexity: {plan.complexity}",
            f"Estimated nodes: {', '.join(plan.estimated_nodes)}",
            "\nSteps:"
        ]
        
        for i, step in enumerate(plan.steps, 1):
            lines.append(f"  {i}. {step.title}")
            lines.append(f"     {step.description}")
            if step.node_types:
                lines.append(f"     Node types: {', '.join(step.node_types)}")
        
        return "\n".join(lines)
    
    async def _invoke_llm_async(self, prompt: str) -> str:
        """Invoke LLM asynchronously"""
        logger.debug(f"[CodeAgent] Invoking LLM, prompt length: {len(prompt)}")
        try:
            if hasattr(self.llm, 'ainvoke'):
                response = await self.llm.ainvoke(prompt)
                result = response.content if hasattr(response, 'content') else str(response)
                logger.debug(f"[CodeAgent] LLM response length: {len(result)}")
                return result
            else:
                response = self.llm.invoke(prompt)
                result = response.content if hasattr(response, 'content') else str(response)
                logger.debug(f"[CodeAgent] LLM response length: {len(result)}")
                return result
        except Exception as e:
            logger.error(f"[CodeAgent] LLM invocation failed: {e}")
            raise
    
    async def _stream_llm_async(self, prompt: str):
        """Stream LLM response asynchronously"""
        logger.debug(f"[CodeAgent] Streaming LLM, prompt length: {len(prompt)}")
        chunk_count = 0
        try:
            if hasattr(self.llm, 'astream'):
                async for chunk in self.llm.astream(prompt):
                    content = chunk.content if hasattr(chunk, 'content') else str(chunk)
                    if content:
                        chunk_count += 1
                        yield content
                logger.debug(f"[CodeAgent] Streaming complete, {chunk_count} chunks")
            elif hasattr(self.llm, 'stream'):
                for chunk in self.llm.stream(prompt):
                    content = chunk.content if hasattr(chunk, 'content') else str(chunk)
                    if content:
                        chunk_count += 1
                        yield content
                logger.debug(f"[CodeAgent] Streaming complete, {chunk_count} chunks")
            else:
                response = await self._invoke_llm_async(prompt)
                yield response
        except Exception as e:
            logger.error(f"[CodeAgent] LLM streaming failed: {e}")
            raise
    
    def _parse_flowgram_from_response(self, response: str) -> Optional[Dict]:
        """Extract flowgram JSON from LLM response"""
        logger.debug(f"[CodeAgent] Parsing flowgram from response (length: {len(response)})")
        
        try:
            # Try to extract JSON from markdown code block
            json_match = re.search(r'```json\s*([\s\S]*?)\s*```', response)
            if json_match:
                return json.loads(json_match.group(1))
            
            # Try to find raw JSON object
            json_match = re.search(r'\{[\s\S]*"flowgram"[\s\S]*\}', response)
            if json_match:
                return json.loads(json_match.group(0))
            
            # Try to find just the flowgram object
            json_match = re.search(r'\{[\s\S]*"nodes"[\s\S]*\}', response)
            if json_match:
                data = json.loads(json_match.group(0))
                if "nodes" in data:
                    return {"action": "generate_flowgram", "flowgram": data, "message": ""}
                return data
            
            logger.warning("[CodeAgent] No JSON found in response")
            return None
            
        except json.JSONDecodeError as e:
            logger.warning(f"[CodeAgent] JSON parse error: {e}")
            return None

    def _ensure_start_end_nodes(self, flowgram: Optional[Flowgram]) -> None:
        """Ensure the flowgram has start/end nodes, minimal connectivity, and metadata defaults."""
        if not flowgram:
            return

        if flowgram.metadata is None:
            flowgram.metadata = {}

        metadata = flowgram.metadata

        if not metadata.get("skillName"):
            base_name = metadata.get("name") or "generated skill"
            slug = re.sub(r"[^a-z0-9]+", "_", base_name.lower()).strip("_")
            metadata["skillName"] = slug or "generated_skill"

        if not metadata.get("description"):
            metadata["description"] = metadata.get("summary") or "Workflow generated via Skill Editor"

        start_node = next((node for node in flowgram.nodes if node.type == "start"), None)
        if not start_node:
            start_node = FlowgramNode(
                id="start",
                type="start",
                label="Start",
                position=NodePosition(x=START_POSITION_X, y=START_POSITION_Y),
                config={}
            )
            flowgram.nodes.insert(0, start_node)

        end_node = next((node for node in flowgram.nodes if node.type == "end"), None)
        if not end_node:
            end_node = FlowgramNode(
                id="end",
                type="end",
                label="End",
                position=NodePosition(x=START_POSITION_X, y=START_POSITION_Y),  # Will be repositioned by layout
                config={}
            )
            flowgram.nodes.append(end_node)

        def edge_exists(src: str, dst: str) -> bool:
            return any(edge.source == src and edge.target == dst for edge in flowgram.edges)

        if not any(edge.source == start_node.id for edge in flowgram.edges):
            next_node = next((node for node in flowgram.nodes if node.id != start_node.id), None)
            target_id = next_node.id if next_node else end_node.id
            if not edge_exists(start_node.id, target_id):
                flowgram.edges.insert(0, FlowgramEdge(source=start_node.id, target=target_id))

        if not any(edge.target == end_node.id for edge in flowgram.edges):
            candidate = next((node for node in reversed(flowgram.nodes) if node.id not in {start_node.id, end_node.id}), None)
            source_id = candidate.id if candidate else start_node.id
            if not edge_exists(source_id, end_node.id):
                flowgram.edges.append(FlowgramEdge(source=source_id, target=end_node.id))

        flowgram.metadata = metadata
        
        # Apply automatic layout to avoid overlapping nodes
        self._apply_layout(flowgram)
    
    def _apply_layout(self, flowgram: Flowgram) -> None:
        """
        Apply automatic layout algorithm to position nodes.
        Uses Sugiyama-style layered DAG placement to avoid overlapping
        and tangled edges. Accounts for different node sizes (e.g., loop nodes are larger).
        """
        if not flowgram or not flowgram.nodes:
            return
        
        try:
            # Extract node IDs, edge tuples, and node types
            node_ids = [node.id for node in flowgram.nodes]
            edge_tuples = [(edge.source, edge.target) for edge in flowgram.edges]
            node_types = {node.id: node.type for node in flowgram.nodes}
            
            # Compute placement using the placement algorithm with node type awareness
            placement = place_nodes(node_ids, edge_tuples, node_types)
            
            # Apply placement to nodes
            for node in flowgram.nodes:
                if node.id in placement:
                    x, y = placement[node.id]
                    node.position = NodePosition(x=x, y=y)
            
            logger.debug(f"[CodeAgent] Applied layout to {len(flowgram.nodes)} nodes")
        except Exception as e:
            logger.warning(f"[CodeAgent] Layout failed, using default positions: {e}")
            # Fallback: simple vertical layout
            for i, node in enumerate(flowgram.nodes):
                if not node.position:
                    node.position = NodePosition(
                        x=START_POSITION_X,
                        y=START_POSITION_Y + i * DEFAULT_NODE_SPACING_Y
                    )

    def _summarize_flowgram(self, flowgram: Optional[Flowgram]) -> str:
        """Generate a concise human-readable summary of the flowgram."""
        if not flowgram or not flowgram.nodes:
            return "Created a starter workflow."

        metadata = flowgram.metadata or {}
        skill_name = metadata.get("skillName") or metadata.get("name")
        total_nodes = len(flowgram.nodes)
        unique_types = sorted({node.type for node in flowgram.nodes if node.type})

        ordered_nodes = sorted(
            flowgram.nodes,
            key=lambda n: (
                n.position.x if n.position else 0,
                n.position.y if n.position else 0,
            )
        )
        labels = [node.label or node.id for node in ordered_nodes]
        path_preview = " → ".join(labels[:6])
        if len(labels) > 6:
            path_preview += " → …"

        type_text = ", ".join(unique_types) if unique_types else "mixed nodes"
        prefix = f"Created '{skill_name}' workflow" if skill_name else "Created workflow"
        summary = f"{prefix} with {total_nodes} nodes ({type_text})."
        if path_preview:
            summary += f" Primary path: {path_preview}."
        return summary

    def _finalize_message(self, raw_message: Any, flowgram: Optional[Flowgram]) -> str:
        """Ensure the message returned to the user is human-friendly."""
        if isinstance(raw_message, str):
            text = raw_message.strip()
            if text:
                return text

        if isinstance(raw_message, dict):
            for key in ("summary", "description"):
                value = raw_message.get(key)
                if isinstance(value, str):
                    text = value.strip()
                    if text:
                        return text

        return self._summarize_flowgram(flowgram)

    def _apply_internal_layout(self, blocks: List[FlowgramNode]) -> None:
        """
        Apply layout to internal nodes of a loop.
        Positions block-start at left, block-end at right, and content nodes in between.
        """
        if not blocks:
            return
        
        x_start = LOOP_INTERNAL_CFG["x_start"]
        x_end = LOOP_INTERNAL_CFG["x_end"]
        y_start = LOOP_INTERNAL_CFG["y_start"]
        spacing_x = LOOP_INTERNAL_CFG["node_spacing_x"]
        spacing_y = LOOP_INTERNAL_CFG["node_spacing_y"]
        
        # Separate block markers from content nodes
        block_start = None
        block_end = None
        content_nodes = []
        
        for node in blocks:
            if node.type == "block-start":
                block_start = node
            elif node.type == "block-end":
                block_end = node
            else:
                content_nodes.append(node)
        
        # Position block-start
        if block_start:
            block_start.position = NodePosition(
                x=LOOP_INTERNAL_CFG["block_start_x"],
                y=LOOP_INTERNAL_CFG["block_start_y"]
            )
        
        # Position block-end
        if block_end:
            block_end.position = NodePosition(
                x=LOOP_INTERNAL_CFG["block_end_x"],
                y=LOOP_INTERNAL_CFG["block_end_y"]
            )
        
        # Position content nodes in the usable area with proper spacing
        if content_nodes:
            # Calculate available width for content nodes
            usable_width = x_end - x_start
            
            # Arrange content nodes horizontally with spacing
            num_nodes = len(content_nodes)
            if num_nodes == 1:
                # Single node: center it
                content_nodes[0].position = NodePosition(
                    x=x_start + usable_width // 2 - 100,  # Center (assuming ~200px node width)
                    y=y_start
                )
            else:
                # Multiple nodes: distribute with spacing
                # Calculate step based on number of nodes
                total_spacing = (num_nodes - 1) * spacing_x
                if total_spacing > usable_width:
                    # Not enough horizontal space, stack vertically
                    for i, node in enumerate(content_nodes):
                        node.position = NodePosition(
                            x=x_start,
                            y=y_start + i * spacing_y
                        )
                else:
                    # Distribute horizontally
                    for i, node in enumerate(content_nodes):
                        node.position = NodePosition(
                            x=x_start + i * spacing_x,
                            y=y_start
                        )

    def _parse_node(self, n: Dict[str, Any], index: int) -> FlowgramNode:
        """Parse a node dict into FlowgramNode, handling loop and condition nodes."""
        pos = n.get("position", {"x": 100, "y": 100})
        node_type = n.get("type", "llm")
        config = n.get("config", {})
        
        # Handle condition nodes - ensure they have conditions array
        if node_type == "condition":
            if "conditions" not in config or not config.get("conditions"):
                # Generate unique branch keys
                node_id = n.get("id", f"condition_{index}")
                config["conditions"] = [
                    {"key": f"if_{node_id[-5:]}", "value": {}},
                    {"key": f"else_{node_id[-5:]}", "value": {}},
                ]
        
        # Parse blocks for loop nodes
        blocks = None
        internal_edges = None
        
        if node_type == "loop":
            blocks_data = n.get("blocks", [])
            if blocks_data:
                blocks = [self._parse_node(b, i) for i, b in enumerate(blocks_data)]
                # Apply internal layout to ensure proper spacing
                self._apply_internal_layout(blocks)
            else:
                # Create default block-start and block-end if not provided
                block_start_id = f"block_start_{n.get('id', index)}"
                block_end_id = f"block_end_{n.get('id', index)}"
                blocks = [
                    FlowgramNode(
                        id=block_start_id,
                        type="block-start",
                        label="Loop Start",
                        position=NodePosition(
                            x=LOOP_INTERNAL_CFG["block_start_x"],
                            y=LOOP_INTERNAL_CFG["block_start_y"]
                        ),
                        config={}
                    ),
                    FlowgramNode(
                        id=block_end_id,
                        type="block-end",
                        label="Loop End",
                        position=NodePosition(
                            x=LOOP_INTERNAL_CFG["block_end_x"],
                            y=LOOP_INTERNAL_CFG["block_end_y"]
                        ),
                        config={}
                    )
                ]
                internal_edges = [
                    FlowgramEdge(source=block_start_id, target=block_end_id)
                ]
            
            # Parse internal edges
            internal_edges_data = n.get("internal_edges", [])
            if internal_edges_data:
                internal_edges = [
                    FlowgramEdge(
                        source=e.get("source", ""),
                        target=e.get("target", ""),
                        source_handle=e.get("source_handle") or e.get("sourceHandle"),
                        target_handle=e.get("target_handle") or e.get("targetHandle"),
                    )
                    for e in internal_edges_data
                ]
        
        return FlowgramNode(
            id=n.get("id", f"node_{index}"),
            type=node_type,
            label=n.get("label", n.get("id", "Node")),
            position=NodePosition(x=pos.get("x", 100), y=pos.get("y", 100)),
            config=config,
            blocks=blocks,
            internal_edges=internal_edges
        )

    def _parse_code_agent_output(self, response: str) -> CodeAgentOutput:
        """Parse LLM response into CodeAgentOutput"""
        data = self._parse_flowgram_from_response(response)
        
        if not data:
            return CodeAgentOutput(
                action=CodeAgentAction.ANSWER,
                message=response
            )
        
        # Parse action
        action_str = data.get("action", "generate_flowgram")
        try:
            action = CodeAgentAction(action_str)
        except ValueError:
            action = CodeAgentAction.GENERATE_FLOWGRAM
        
        # Parse flowgram if present
        flowgram = None
        flowgram_data = data.get("flowgram")
        if flowgram_data:
            try:
                nodes = []
                for n in flowgram_data.get("nodes", []):
                    nodes.append(self._parse_node(n, len(nodes)))
                
                edges = []
                for e in flowgram_data.get("edges", []):
                    edges.append(FlowgramEdge(
                        source=e.get("source", ""),
                        target=e.get("target", ""),
                        source_handle=e.get("source_handle") or e.get("sourceHandle"),
                        target_handle=e.get("target_handle") or e.get("targetHandle"),
                        label=e.get("label")
                    ))
                
                flowgram = Flowgram(
                    nodes=nodes,
                    edges=edges,
                    metadata=flowgram_data.get("metadata", {})
                )
                self._ensure_start_end_nodes(flowgram)
                logger.info(f"[CodeAgent] Parsed flowgram: {len(flowgram.nodes)} nodes, {len(flowgram.edges)} edges")
            except Exception as e:
                logger.warning(f"[CodeAgent] Error parsing flowgram: {e}")

        message = self._finalize_message(data.get("message"), flowgram)

        return CodeAgentOutput(
            action=action,
            message=message,
            flowgram=flowgram
        )
    
    def validate_flowgram(self, flowgram: Flowgram) -> ValidationResult:
        """Validate a flowgram structure"""
        logger.debug(f"[CodeAgent] Validating flowgram with {len(flowgram.nodes)} nodes")
        errors = []
        warnings = []
        
        node_ids = {n.id for n in flowgram.nodes}
        
        # Check for start node
        has_start = any(n.type == "start" for n in flowgram.nodes)
        if not has_start:
            errors.append(ValidationError(
                message="Flowgram must have a 'start' node",
                severity="error"
            ))
        
        # Check for end node
        has_end = any(n.type == "end" for n in flowgram.nodes)
        if not has_end:
            errors.append(ValidationError(
                message="Flowgram must have an 'end' node",
                severity="error"
            ))
        
        # Check for duplicate node IDs
        seen_ids = set()
        for node in flowgram.nodes:
            if node.id in seen_ids:
                errors.append(ValidationError(
                    node_id=node.id,
                    message=f"Duplicate node ID: {node.id}",
                    severity="error"
                ))
            seen_ids.add(node.id)
        
        # Check node types are valid
        for node in flowgram.nodes:
            if node.type not in NODE_TYPES:
                warnings.append(ValidationError(
                    node_id=node.id,
                    message=f"Unknown node type: {node.type}",
                    severity="warning"
                ))
        
        # Check edges reference valid nodes
        for edge in flowgram.edges:
            if edge.source not in node_ids:
                errors.append(ValidationError(
                    message=f"Edge source '{edge.source}' does not exist",
                    severity="error"
                ))
            if edge.target not in node_ids:
                errors.append(ValidationError(
                    message=f"Edge target '{edge.target}' does not exist",
                    severity="error"
                ))
        
        # Check for orphan nodes (not connected)
        connected_nodes = set()
        for edge in flowgram.edges:
            connected_nodes.add(edge.source)
            connected_nodes.add(edge.target)
        
        for node in flowgram.nodes:
            if node.id not in connected_nodes and node.type not in ["start", "end"]:
                warnings.append(ValidationError(
                    node_id=node.id,
                    message=f"Node '{node.id}' is not connected to any other node",
                    severity="warning"
                ))
        
        # Check LLM nodes have required config
        for node in flowgram.nodes:
            if node.type == "llm":
                if not node.config.get("system_prompt") and not node.config.get("user_prompt"):
                    warnings.append(ValidationError(
                        node_id=node.id,
                        field="config",
                        message="LLM node should have system_prompt or user_prompt",
                        severity="warning"
                    ))
        
        is_valid = len(errors) == 0
        logger.info(f"[CodeAgent] Validation result: valid={is_valid}, errors={len(errors)}, warnings={len(warnings)}")
        
        return ValidationResult(
            valid=is_valid,
            errors=errors,
            warnings=warnings
        )
    
    def _node_to_canvas_payload(self, node: FlowgramNode) -> Dict[str, Any]:
        """Convert a FlowgramNode to canvas command payload, handling loop and condition nodes."""
        payload = {
            "nodeType": node.type,
            "position": {"x": node.position.x, "y": node.position.y},
            "config": {
                "id": node.id,
                "label": node.label,
                **node.config
            }
        }
        
        # Handle condition nodes - ensure conditions array is in data for frontend
        if node.type == "condition":
            conditions = node.config.get("conditions", [])
            if not conditions:
                # Generate default conditions if not present
                conditions = [
                    {"key": f"if_{node.id[-5:]}", "value": {}},
                    {"key": f"else_{node.id[-5:]}", "value": {}},
                ]
            payload["data"] = {
                "title": node.label,
                "conditions": conditions,
            }
        
        # Handle loop nodes with blocks
        if node.type == "loop" and node.blocks:
            payload["blocks"] = [
                {
                    "id": b.id,
                    "type": b.type,
                    "meta": {"position": {"x": b.position.x, "y": b.position.y}},
                    "data": {"title": b.label, **b.config}
                }
                for b in node.blocks
            ]
            if node.internal_edges:
                payload["edges"] = [
                    {"sourceNodeID": e.source, "targetNodeID": e.target}
                    for e in node.internal_edges
                ]
        
        return payload
    
    def generate_canvas_commands(self, flowgram: Flowgram) -> List[CanvasCommand]:
        """Generate canvas commands from a flowgram"""
        logger.debug(f"[CodeAgent] Generating canvas commands for {len(flowgram.nodes)} nodes")
        commands = []
        
        # Clear existing canvas first
        commands.append(CanvasCommand(
            type="canvas.clear",
            payload={}
        ))
        
        # Add nodes
        for node in flowgram.nodes:
            commands.append(CanvasCommand(
                type="canvas.add_node",
                payload=self._node_to_canvas_payload(node)
            ))
        
        # Add edges
        for edge in flowgram.edges:
            commands.append(CanvasCommand(
                type="canvas.add_edge",
                payload={
                    "sourceNodeId": edge.source,
                    "targetNodeId": edge.target,
                    "sourceHandle": edge.source_handle,
                    "targetHandle": edge.target_handle,
                    "label": edge.label
                }
            ))
        
        logger.info(f"[CodeAgent] Generated {len(commands)} canvas commands")
        return commands
    
    async def generate(
        self,
        user_message: str,
        canvas_context: Optional[Dict] = None,
        plan: Optional[ImplementationPlan] = None,
        on_event: Optional[Callable] = None
    ) -> CodeAgentOutput:
        """
        Generate a flowgram from user request and optional plan.
        
        Args:
            user_message: User's request
            canvas_context: Current canvas state
            plan: Implementation plan from PlannerAgent
            on_event: Callback for streaming events
            
        Returns:
            CodeAgentOutput with generated flowgram
        """
        logger.info(f"[CodeAgent] Generating flowgram for: {user_message[:100]}...")
        
        try:
            # Build prompt
            prompt = CODE_GENERATION_PROMPT.format(
                node_types=get_node_types_description(),
                canvas_context=self._format_canvas_context(canvas_context),
                plan_context=self._format_plan_context(plan)
            )
            
            prompt += f"\n\n## USER REQUEST:\n{user_message}"
            
            # Invoke LLM
            logger.debug("[CodeAgent] Invoking LLM for generation")
            response = await self._invoke_llm_async(prompt)
            
            # Parse response
            output = self._parse_code_agent_output(response)
            
            # Validate if flowgram was generated
            if output.flowgram:
                validation = self.validate_flowgram(output.flowgram)
                output.validation = validation
                
                # Store current flowgram
                self._current_flowgram = output.flowgram
                
                # Retry if validation failed
                if not validation.valid and MAX_VALIDATION_RETRIES > 0:
                    logger.info("[CodeAgent] Validation failed, attempting fix...")
                    output = await self._fix_validation_errors(
                        output, validation, user_message, canvas_context, plan
                    )
                
                # Send flowgram event
                if on_event and output.flowgram:
                    on_event({
                        "type": "flowgram",
                        "data": output.flowgram.model_dump()
                    })
            
            return output
            
        except Exception as e:
            logger.error(f"[CodeAgent] Generation failed: {e}")
            return CodeAgentOutput(
                action=CodeAgentAction.REJECT,
                message=f"Failed to generate flowgram: {str(e)}"
            )
    
    async def _fix_validation_errors(
        self,
        output: CodeAgentOutput,
        validation: ValidationResult,
        user_message: str,
        canvas_context: Optional[Dict],
        plan: Optional[ImplementationPlan],
        retry_count: int = 0
    ) -> CodeAgentOutput:
        """Attempt to fix validation errors by re-generating"""
        if retry_count >= MAX_VALIDATION_RETRIES:
            logger.warning(f"[CodeAgent] Max retries ({MAX_VALIDATION_RETRIES}) reached")
            return output
        
        logger.info(f"[CodeAgent] Fix attempt {retry_count + 1}/{MAX_VALIDATION_RETRIES}")
        
        # Build fix prompt
        error_messages = [e.message for e in validation.errors]
        fix_prompt = f"""The generated flowgram has validation errors. Please fix them.

ERRORS:
{chr(10).join(f'- {e}' for e in error_messages)}

ORIGINAL REQUEST: {user_message}

Please regenerate the flowgram with these errors fixed.
"""
        
        prompt = CODE_GENERATION_PROMPT.format(
            node_types=get_node_types_description(),
            canvas_context=self._format_canvas_context(canvas_context),
            plan_context=self._format_plan_context(plan)
        )
        prompt += f"\n\n{fix_prompt}"
        
        # Re-invoke LLM
        response = await self._invoke_llm_async(prompt)
        new_output = self._parse_code_agent_output(response)
        
        if new_output.flowgram:
            new_validation = self.validate_flowgram(new_output.flowgram)
            new_output.validation = new_validation
            
            if new_validation.valid:
                logger.info("[CodeAgent] Fix successful, flowgram is now valid")
                self._current_flowgram = new_output.flowgram
                return new_output
            else:
                # Recurse
                return await self._fix_validation_errors(
                    new_output, new_validation, user_message, 
                    canvas_context, plan, retry_count + 1
                )
        
        return output
    
    async def edit(
        self,
        edit_request: str,
        current_flowgram: Optional[Flowgram] = None,
        on_event: Optional[Callable] = None
    ) -> CodeAgentOutput:
        """
        Edit an existing flowgram.
        
        Args:
            edit_request: What to change
            current_flowgram: Current flowgram to edit
            on_event: Callback for streaming events
            
        Returns:
            CodeAgentOutput with edited flowgram
        """
        flowgram = current_flowgram or self._current_flowgram
        
        if not flowgram:
            return CodeAgentOutput(
                action=CodeAgentAction.REJECT,
                message="No flowgram to edit. Please generate one first."
            )
        
        logger.info(f"[CodeAgent] Editing flowgram: {edit_request[:100]}...")
        
        try:
            # Build edit prompt
            prompt = EDIT_FLOWGRAM_PROMPT.format(
                current_flowgram=json.dumps(flowgram.model_dump(), indent=2),
                edit_request=edit_request,
                node_types=get_node_types_description()
            )
            
            # Invoke LLM
            response = await self._invoke_llm_async(prompt)
            output = self._parse_code_agent_output(response)
            
            if output.flowgram:
                output.action = CodeAgentAction.EDIT_FLOWGRAM
                
                # Re-run placement algorithm to avoid overlaps after edit
                self._apply_layout(output.flowgram)
                
                validation = self.validate_flowgram(output.flowgram)
                output.validation = validation
                self._current_flowgram = output.flowgram
                
                if on_event:
                    on_event({
                        "type": "flowgram",
                        "data": output.flowgram.model_dump()
                    })
            
            return output
            
        except Exception as e:
            logger.error(f"[CodeAgent] Edit failed: {e}")
            return CodeAgentOutput(
                action=CodeAgentAction.REJECT,
                message=f"Failed to edit flowgram: {str(e)}"
            )
    
    def generate_sync(
        self,
        user_message: str,
        canvas_context: Optional[Dict] = None,
        plan: Optional[ImplementationPlan] = None,
        on_event: Optional[Callable] = None
    ) -> CodeAgentOutput:
        """Synchronous version of generate"""
        import asyncio
        
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                from agent.ec_skills.llm_utils.llm_utils import run_async_in_sync
                return run_async_in_sync(
                    self.generate(user_message, canvas_context, plan, on_event)
                )
            else:
                return loop.run_until_complete(
                    self.generate(user_message, canvas_context, plan, on_event)
                )
        except RuntimeError:
            return asyncio.run(
                self.generate(user_message, canvas_context, plan, on_event)
            )
    
    def get_current_flowgram(self) -> Optional[Flowgram]:
        """Get the current flowgram"""
        return self._current_flowgram
    
    def set_current_flowgram(self, flowgram: Flowgram):
        """Set the current flowgram"""
        self._current_flowgram = flowgram
    
    def clear(self):
        """Clear current flowgram and history"""
        self._current_flowgram = None
        self._generation_history = []
        logger.info("[CodeAgent] Cleared")


# ============================================================
# Singleton Instance
# ============================================================

_code_agent_instance: Optional[CodeAgent] = None


def get_code_agent() -> CodeAgent:
    """Get or create the singleton code agent instance"""
    global _code_agent_instance
    if _code_agent_instance is None:
        logger.info("[CodeAgent] Creating new singleton instance")
        _code_agent_instance = CodeAgent()
    return _code_agent_instance


def reset_code_agent():
    """Reset the singleton instance"""
    global _code_agent_instance
    logger.info("[CodeAgent] Resetting singleton instance")
    if _code_agent_instance:
        _code_agent_instance.clear()
    _code_agent_instance = None
