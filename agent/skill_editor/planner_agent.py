"""
Planner Agent for Skill Editor

A planning agent that runs BEFORE code generation to:
1. Ask clarification questions when requirements are ambiguous
2. Gather context from available tools/nodes
3. Generate an implementation plan for the workflow

Inspired by BubbleLab's Coffee agent pattern.
"""

import json
import re
from typing import Any, Dict, List, Optional, Callable

from utils.logger_helper import logger_helper as logger

from .schemas import (
    PlannerAction,
    PlannerOutput,
    ClarificationQuestion,
    ClarificationChoice,
    ImplementationPlan,
    PlanStep,
    IntentType,
    NODE_TYPES,
    get_node_types_description,
)
from .prompt_store import prompt_store


# ============================================================
# Constants
# ============================================================

MAX_CLARIFICATION_QUESTIONS = 4
MAX_PLANNING_ITERATIONS = 3


# ============================================================
# System Prompts
# ============================================================

PLANNER_SYSTEM_PROMPT = """You are an e-Commerce Planning Agent for the Skill Editor, helping users design efficient and robust e-commerce workflow automations.

Your role is to understand the user's workflow requirements, ask clarifying questions when needed, and generate an implementation plan BEFORE code/flowgram generation begins.

## E-COMMERCE Q&A HANDLING PATTERN (CRITICAL):
When workflow involves product/service Q&A (on-site messaging or email), ALWAYS follow this order:
1. **FIRST**: Query internal knowledge base using RAG query MCP tools (rag_query)
2. **IF RAG unavailable/no answer**: Defer to human assistance with 24-hour limit
   - Use pend_event node to wait for human response
   - Set timeout to 24 hours (86400 seconds)
3. **IF human fails to respond within 24 hours**: Auto-respond with best knowledge
   - Search web for same product/service info, OR
   - Search pre-specified local directory for product/service files

This pattern ensures: RAG first → Human fallback (24h) → Auto-respond as last resort

## SUB-AGENT ERROR HANDLING PATTERN (CRITICAL):
When designing workflows with sub-agents (LLM+MCP tools or browser_automation), ALWAYS include this behavior:
1. **DON'T GET STUCK**: When uncertain or encountering an error, sub-agents should NOT block or retry indefinitely
2. **COLLECT & STORE**: Gather all information needed for human intervention (error details, context, what was attempted)
3. **MOVE ON**: Continue to the next action item in the task list
4. **BATCH HUMAN REQUESTS**: Accumulate all items requiring human intervention throughout execution
5. **REPORT AT END**: Send a consolidated summary of all human-intervention-needed items at the very end

This maximizes work completion and minimizes human interruptions during execution.

## YOUR RESPONSIBILITIES:
1. Analyze the user's natural language request
2. Identify any ambiguities or missing information
3. Ask 1-{max_questions} targeted clarification questions with multiple-choice options
4. Generate a clear implementation plan once you have enough information
5. Default working language: **English**, But do make sure always respond in the same language as the user request

## CLARIFICATION POLICY:
- require_clarification flag: {require_clarification}
- If require_clarification is true and the user has NOT explicitly opted out (e.g., "skip clarifications", "no questions", "直接生成", "不用问"), you MUST return action=ask_clarification with 2-3 targeted questions BEFORE generating a plan, even if the request seems clear.
- Only skip clarifications when the user explicitly opts out OR require_clarification is false and you are confident the request is fully specified.


## AVAILABLE NODE TYPES:
{node_types}

## CURRENT CANVAS STATE:
{canvas_context}

## CLARIFICATION QUESTIONS GUIDELINES:
- Ask questions ONLY when there's genuine ambiguity
- Each question should have 4-6 clear choices
- Questions should be actionable and help determine the implementation
- Set "allow_multiple": true when the user can reasonably select multiple options
- Always include a "None of the above" or "Other" or "Something else" option, and if this option is selected, always make a otherwise invisible text input box visible to let user input their answer.
- Always include a "Doesn't apply" option to let the user mark this question as not applicable.
- Set "allow_multiple": false when only one option should be selected
- On the Q&A form, always includes a "Cancel" button to let the user cancel the Q&A process.
- Focus on:
  - Data sources (where does the data come from?)
  - Output destinations (where should results go?)
  - Specific tools/integrations to use
  - Processing logic (filtering, transforming, etc.)
  - Trigger type (manual, scheduled, webhook)

## WORK DECOMPOSITION STRATEGY (CRITICAL):
1. **BREAK DOWN COMPLEXITY**: Always decompose complex requests into manageable components
2. **MULTI-PHASE APPROACH**: Divide long work into multiple phases with clear milestones
3. **IDENTIFY BLOCKERS EARLY**: Do thorough feasibility analysis, identify gating items and show-stoppers upfront
4. **RESOLVE BLOCKERS FIRST**: Get blockers resolved with requester before proceeding with implementation

## QUALITY ASSURANCE:
1. **VERIFY AGAINST REQUIREMENTS**: Always check results against original user requirements
2. **TEST BEFORE DELIVERY**: Validate workflow logic and node configurations before presenting
3. **DOCUMENT FOR REFERENCE**: Include clear descriptions in plan steps for future reference
4. **SEEK FEEDBACK**: Ask clarifying questions whenever uncertain; iterate based on user feedback

## BROWSER_AUTOMATION NODE - CRITICAL UNDERSTANDING:
The `browser_automation` node is a **SUB-AGENT with its own internal LLM**, can execute multiple steps consecutively based on the input prompt and tools available to it, NOT a simple action node!

**Capabilities:**
- Has its own LLM that can read/understand page DOM, extract data, and make decisions
- Can execute up to **100 consecutive interaction steps** (click, type, scroll, navigate, etc.)
- With clear specifications in the prompt, can return structured JSON output including status flags and extracted data
- Handles complex multi-step web interactions autonomously

**CORRECT Pattern - Batch Browser Work:**
Instead of creating multiple browser_automation + llm node pairs, batch related browser work:
1. Write a **detailed prompt** describing all browser tasks (e.g., "Process up to 3 orders: login, navigate to orders, for each order check messages for cancellation, if not cancelled generate shipping label, select cheapest option")
2. Configure the browser_automation node to return JSON with an `all_done` boolean flag
3. Wrap with a **loop node (while type)** that continues until `all_done` is true

**WRONG Pattern (avoid this):**
- browser_automation → llm (to understand page) → browser_automation → llm → ...
- Creating separate nodes for "extract data" then "analyze with LLM" for browser content

**RIGHT Pattern:**
- Single browser_automation node with comprehensive prompt → loop wrapper
- The browser_automation sub-agent handles DOM reading, data extraction and collection, web page interaction, AND decision-making internally

**When to use separate LLM nodes:**
- Non-browser reasoning/data processing (e.g., comparing prices from an API response, prepare and process data from API, files, spreadsheets, ppt, database etc.)
- Aggregating results from multiple sources
- Complex business logic that doesn't involve browser interaction

## LLM NODE and MCP TOOL NODE - CRITICAL UNDERSTANDING:
-The `llm` node is also agentic, meaning it has its own internal LLM, and context manager, given the right prompt it can pick the right tool to act on its own result, NOT a simple action node!
-The "mcp_tool" node can be set to call any of the pre-made tools, but it also has an llm auto-select mode, 
-Forming an sub-agent: an llm node followed by a mcp tool node, and then wrapped under a loop node, this combination is essentially an sub-agent just like the browser_automation node, except it's for other non-browser related repetitive tasks, for example: reformat a list of shipping label files and then send them to printer!

## PLAN GENERATION GUIDELINES:
When generating a plan, include:
- A brief summary of what the workflow will do
- Step-by-step breakdown with clear descriptions
- Which node types will be used in each step
- List of all estimated nodes needed
- **TIME ESTIMATES**: Provide estimated execution time for each step
- **TOTAL TIME**: Aggregate total estimated work time
- **PHASES**: For complex workflows, group steps into phases with phase-level estimates

Example time estimates:
- Simple LLM call: ~5-10 seconds
- MCP tool execution: ~2-30 seconds (depends on tool)
- Browser automation batch (up to 100 steps): ~30 seconds to 5 minutes depending on complexity
- RAG query: ~2-5 seconds
- Loop iteration: multiply single iteration time by expected count

## OUTPUT FORMAT (JSON):
You MUST respond in valid JSON with one of these structures:

When you need clarification:
{{
  "action": "ask_clarification",
  "questions": [
    {{
      "id": "unique_id",
      "question": "Clear question text?",
      "choices": [
        {{ "id": "choice_1", "label": "Option A", "description": "What this option means" }},
        {{ "id": "choice_2", "label": "Option B", "description": "What this option means" }}
      ],
      "context": "Why this question is important (optional)",
      "allow_multiple": false
    }}
  ],
  "a2ui": {{
    "version": "v0.10",
    "surfaceId": "clarification_<timestamp>",
    "messages": [
      {{
        "createSurface": {{
          "surfaceId": "clarification_<timestamp>",
          "catalogId": "https://a2ui.org/specification/v0_10/standard_catalog.json",
          "theme": {{ "primaryColor": "#3b82f6" }},
          "sendDataModel": true
        }}
      }},
      {{
        "updateComponents": {{
          "surfaceId": "clarification_<timestamp>",
          "components": [
            {{ "id": "root", "component": "Column", "children": ["header", "divider", "q1-container", "buttons-row"] }},
            {{ "id": "header", "component": "Text", "text": "🤔 I have a few questions:", "variant": "h4" }},
            {{ "id": "divider", "component": "Divider" }},
            {{ "id": "q1-container", "component": "Column", "children": ["q1-text", "q1-picker"] }},
            {{ "id": "q1-text", "component": "Text", "text": "1. Question text here?", "variant": "body" }},
            {{ "id": "q1-picker", "component": "ChoicePicker", "label": "", "variant": "mutuallyExclusive", "options": [
              {{ "label": "Option A", "value": "choice_1" }},
              {{ "label": "Option B", "value": "choice_2" }}
            ], "value": {{ "path": "/answers/q1" }} }},
            {{ "id": "buttons-row", "component": "Row", "justify": "end", "children": ["cancel-btn", "submit-btn"] }},
            {{ "id": "cancel-btn", "component": "Button", "child": "cancel-text", "action": {{ "name": "cancel" }} }},
            {{ "id": "cancel-text", "component": "Text", "text": "Cancel" }},
            {{ "id": "submit-btn", "component": "Button", "variant": "primary", "child": "submit-text", "action": {{ "name": "submit" }} }},
            {{ "id": "submit-text", "component": "Text", "text": "Submit" }}
          ]
        }}
      }},
      {{
        "updateDataModel": {{
          "surfaceId": "clarification_<timestamp>",
          "path": "/answers",
          "value": {{ "q1": [] }}
        }}
      }}
    ]
  }},
  "message": "I have a few questions to better understand your requirements."
}}

**A2UI COMPONENT GUIDELINES:**
- Use "ChoicePicker" for all question options (variant: "mutuallyExclusive" for single-select, "multipleSelection" for multi-select)
- Bind each ChoicePicker value to "/answers/<question_id>" path
- Include a Cancel button with action {{ "name": "cancel" }}
- Include a Submit button (variant: "primary") with action {{ "name": "submit" }}
- The ChoicePicker "options" array must use "label" and "value" keys
- Generate unique surfaceId using format: clarification_<timestamp_ms>
- All components must be arranged in a Column with proper children references

When you have enough information to generate a plan:
{{
  "action": "generate_plan",
  "plan": {{
    "summary": "Brief overview of what the workflow will accomplish",
    "steps": [
      {{
        "title": "Step title (must be meaningful workflow logic)",
        "description": "Detailed description of what this step does",
        "node_types": ["node_type_1", "node_type_2"],
        "time_estimate": "~5-10 seconds"
      }}
    ],
    "estimated_nodes": ["start", "browser-automation", "llm", "condition", "loop", "mcp", "end"],
    "complexity": "simple" | "medium" | "complex",
    "total_time_estimate": "~2-5 minutes",
    "blockers": []
  }},
  "message": "Here's my implementation plan for your workflow."
}}

## PLAN STEPS REQUIREMENTS (CRITICAL):
**NEVER generate plans with only trivial steps like "start" and "end"!**

1. **Minimum 3 meaningful steps** for any workflow
2. **Each step = one functional unit**: e.g., "Fetch orders", "Process messages", "Send notifications"
3. **Steps must map to actual nodes**: browser-automation, llm, condition, loop, mcp, code, etc.
4. **DO NOT include start/end as steps** - they are automatically added

**BAD PLAN:**
- Step 1: "Scheduled trigger" (start) ❌
- Step 2: "End" ❌

**GOOD PLAN for eBay after-sales:**
- Step 1: "Fetch unshipped orders from Seller Hub" - browser-automation
- Step 2: "Check each order for cancellation messages" - loop + browser-automation
- Step 3: "Generate shipping labels for valid orders" - browser-automation
- Step 4: "Handle buyer Q&A with RAG→human→auto pattern" - rag + condition + pend_event
- Step 5: "Process return requests" - browser-automation + condition
- Step 6: "Send consolidated summary email" - http or mcp

When the request is clear and simple enough to proceed directly:
{{
  "action": "proceed_to_code",
  "message": "Your request is clear. I'll generate the workflow now."
}}

## DECISION PROCESS:
1. Read the user's request carefully
2. Check if clarification answers are provided (from previous round)
3. If this is the first interaction AND there's ambiguity → Ask clarification questions
4. If clarification answers are provided OR request is clear → Generate the plan
5. ALWAYS prefer generating a plan over asking more questions when possible
6. For very simple requests (e.g., "create a simple LLM node" or "create a blank skill named xyz"), proceed directly to code

Remember: Your goal is to understand the user's intent and requirements well enough to create a solid implementation plan. Don't over-question - if the request is reasonably clear, proceed with plan generation.
"""


# ============================================================
# Planner Agent Class
# ============================================================

class PlannerAgent:
    """
    Planning agent that gathers requirements and creates implementation plans.
    
    This agent:
    1. Analyzes user requests for ambiguity
    2. Asks targeted clarification questions
    3. Generates structured implementation plans
    4. Decides when to proceed to code generation
    """
    
    def __init__(self, llm=None):
        """
        Initialize the planner agent.
        
        Args:
            llm: LangChain LLM instance. If None, will use default from settings.
        """
        self._llm = llm
        self._clarification_history: List[Dict[str, Any]] = []
        self._current_plan: Optional[ImplementationPlan] = None
        logger.info("[PlannerAgent] Initialized")
    
    @property
    def llm(self):
        """Lazy load LLM from settings if not provided"""
        if self._llm is None:
            try:
                self._llm = self._load_llm_from_settings()
                logger.info("[PlannerAgent] Loaded LLM from settings")
            except Exception as e:
                logger.error(f"[PlannerAgent] Failed to load LLM: {e}")
                raise
        return self._llm
    
    def _load_llm_from_settings(self):
        """Load LLM instance from application settings"""
        try:
            from app_context import AppContext
            from agent.ec_skills.llm_utils.llm_utils import pick_llm
            
            mainwin = AppContext.get_main_window()
            if not mainwin or not hasattr(mainwin, 'config_manager'):
                raise RuntimeError("[PlannerAgent] Cannot access Settings to get default LLM")
            
            # Use unified method to get default LLM config
            llm_config = mainwin.config_manager.llm_manager.get_default_llm_config()
            llm_providers = mainwin.config_manager.llm_manager.get_all_providers()
            
            llm_instance = pick_llm(
                default_llm=llm_config['provider_id'],
                llm_providers=llm_providers,
                config_manager=mainwin.config_manager,
                allow_fallback=False
            )
            
            if not llm_instance:
                raise RuntimeError(f"[PlannerAgent] Failed to create LLM instance for provider '{llm_config['provider_id']}'")
            
            logger.info(f"[PlannerAgent] Loaded LLM from Settings: {llm_config['provider_id']}, model: {llm_config['model_name']}")
            return llm_instance
            
        except Exception as e:
            logger.error(f"[PlannerAgent] Failed to load LLM from Settings: {e}")
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
    
    def _build_conversation_context(
        self,
        user_message: str,
        clarification_responses: Optional[Dict[str, List[str]]] = None
    ) -> str:
        """Build conversation context including clarification history"""
        context_parts = [f"User's workflow request: \"{user_message}\""]
        
        # Add clarification history
        if self._clarification_history:
            context_parts.append("\n=== PREVIOUS CLARIFICATION Q&A ===")
            for item in self._clarification_history:
                q = item.get("question", {})
                answers = item.get("answers", [])
                context_parts.append(f"Q: {q.get('question', 'Unknown question')}")
                if answers:
                    answer_labels = []
                    for ans_id in answers:
                        for choice in q.get("choices", []):
                            if choice.get("id") == ans_id:
                                answer_labels.append(choice.get("label", ans_id))
                                break
                    context_parts.append(f"A: {', '.join(answer_labels)}")
        
        # Add current clarification responses if provided
        if clarification_responses:
            context_parts.append("\n=== USER'S ANSWERS TO CLARIFICATION ===")
            for q_id, answer_ids in clarification_responses.items():
                context_parts.append(f"Question {q_id}: {', '.join(answer_ids)}")
        
        return "\n".join(context_parts)
    
    async def _invoke_llm_async(self, prompt: str) -> str:
        """Invoke LLM asynchronously"""
        logger.debug(f"[PlannerAgent] Invoking LLM, prompt length: {len(prompt)}")
        try:
            if hasattr(self.llm, 'ainvoke'):
                response = await self.llm.ainvoke(prompt)
                result = response.content if hasattr(response, 'content') else str(response)
                logger.debug(f"[PlannerAgent] LLM response length: {len(result)}")
                return result
            else:
                response = self.llm.invoke(prompt)
                result = response.content if hasattr(response, 'content') else str(response)
                logger.debug(f"[PlannerAgent] LLM response length: {len(result)}")
                return result
        except Exception as e:
            logger.error(f"[PlannerAgent] LLM invocation failed: {e}")
            raise
    
    def _parse_planner_output(self, response: str) -> PlannerOutput:
        """Parse LLM response into structured PlannerOutput"""
        logger.debug(f"[PlannerAgent] Parsing response (length: {len(response)})")
        
        try:
            # Try to extract JSON from response
            json_match = re.search(r'```json\s*([\s\S]*?)\s*```', response)
            if json_match:
                json_str = json_match.group(1)
            else:
                # Try to find raw JSON
                json_match = re.search(r'\{[\s\S]*\}', response)
                if json_match:
                    json_str = json_match.group(0)
                else:
                    raise ValueError("No JSON found in response")
            
            data = json.loads(json_str)
            
            # Parse action
            action_str = data.get("action", "proceed_to_code")
            try:
                action = PlannerAction(action_str)
            except ValueError:
                action = PlannerAction.PROCEED_TO_CODE
            
            # Parse questions if present
            questions = None
            if data.get("questions"):
                questions = []
                for q_data in data["questions"][:MAX_CLARIFICATION_QUESTIONS]:
                    choices = [
                        ClarificationChoice(
                            id=c.get("id", f"choice_{i}"),
                            label=c.get("label", "Option"),
                            description=c.get("description")
                        )
                        for i, c in enumerate(q_data.get("choices", []))
                    ]
                    questions.append(ClarificationQuestion(
                        id=q_data.get("id", f"q_{len(questions)}"),
                        question=q_data.get("question", ""),
                        choices=choices,
                        context=q_data.get("context"),
                        allow_multiple=q_data.get("allow_multiple", False)
                    ))
            
            # Parse plan if present
            plan = None
            if data.get("plan"):
                plan_data = data["plan"]
                logger.debug(f"[PlannerAgent] Plan data keys: {list(plan_data.keys())}")
                
                # Check for steps in different locations (direct steps or inside phases)
                raw_steps = plan_data.get("steps", [])
                
                # If steps is empty, try to extract from phases
                if not raw_steps and plan_data.get("phases"):
                    logger.debug(f"[PlannerAgent] No direct steps, extracting from phases")
                    for phase in plan_data.get("phases", []):
                        phase_steps = phase.get("steps", [])
                        raw_steps.extend(phase_steps)
                
                logger.debug(f"[PlannerAgent] Found {len(raw_steps)} raw steps")
                
                steps = [
                    PlanStep(
                        title=s.get("title", "Step"),
                        description=s.get("description", ""),
                        node_types=s.get("node_types", [])
                    )
                    for s in raw_steps
                ]
                plan = ImplementationPlan(
                    summary=plan_data.get("summary", ""),
                    steps=steps,
                    estimated_nodes=plan_data.get("estimated_nodes", []),
                    complexity=plan_data.get("complexity", "medium")
                )
            
            return PlannerOutput(
                action=action,
                questions=questions,
                plan=plan,
                message=data.get("message")
            )
            
        except json.JSONDecodeError as e:
            logger.warning(f"[PlannerAgent] JSON parse error: {e}")
            # Return a default proceed action
            return PlannerOutput(
                action=PlannerAction.PROCEED_TO_CODE,
                message="I'll proceed with generating the workflow based on your request."
            )
        except Exception as e:
            logger.error(f"[PlannerAgent] Parse error: {e}")
            return PlannerOutput(
                action=PlannerAction.PROCEED_TO_CODE,
                message="I'll proceed with generating the workflow based on your request."
            )
    
    async def plan(
        self,
        user_message: str,
        canvas_context: Optional[Dict] = None,
        clarification_responses: Optional[Dict[str, List[str]]] = None,
        on_event: Optional[Callable] = None,
        require_clarification: bool = False,
    ) -> PlannerOutput:
        """
        Run the planning process.
        
        Args:
            user_message: User's workflow request
            canvas_context: Current canvas state
            clarification_responses: Answers to previous clarification questions
            on_event: Callback for streaming events
            
        Returns:
            PlannerOutput with action and relevant data
        """
        logger.info(f"[PlannerAgent] Planning for: {user_message[:100]}...")
        
        try:
            # Build system prompt
            system_prompt = prompt_store.get("planner", default=PLANNER_SYSTEM_PROMPT).format(
                max_questions=MAX_CLARIFICATION_QUESTIONS,
                node_types=get_node_types_description(),
                canvas_context=self._format_canvas_context(canvas_context),
                require_clarification=str(require_clarification).lower()
            )
            
            # Build conversation context
            conversation = self._build_conversation_context(
                user_message,
                clarification_responses
            )
            
            # Combine into full prompt
            full_prompt = f"{system_prompt}\n\n{conversation}"
            
            # Invoke LLM
            logger.debug("[PlannerAgent] Invoking LLM for planning")
            response = await self._invoke_llm_async(full_prompt)
            
            # Parse response
            output = self._parse_planner_output(response)
            logger.info(f"[PlannerAgent] Planning result: action={output.action.value}")

            # Enforce clarification when required and no answers yet
            if require_clarification and not clarification_responses:
                if output.action != PlannerAction.ASK_CLARIFICATION or not output.questions:
                    fallback_questions = [
                        ClarificationQuestion(
                            id="wf_trigger",
                            question="What triggers this workflow?",
                            choices=[
                                ClarificationChoice(id="manual", label="Manual / ad-hoc", description=None),
                                ClarificationChoice(id="schedule", label="Scheduled / cron", description=None),
                                ClarificationChoice(id="webhook", label="Webhook / event-based", description=None),
                                ClarificationChoice(id="other", label="Other / specify", description=None),
                                ClarificationChoice(id="none", label="Doesn't apply", description=None),
                            ],
                            allow_multiple=False,
                        ),
                        ClarificationQuestion(
                            id="wf_outputs",
                            question="Where should outputs/notifications go?",
                            choices=[
                                ClarificationChoice(id="chat", label="Chat canvas summary only", description=None),
                                ClarificationChoice(id="http", label="HTTP/Webhook push", description=None),
                                ClarificationChoice(id="file", label="Save to file/storage", description=None),
                                ClarificationChoice(id="none", label="Doesn't apply", description=None),
                                ClarificationChoice(id="other", label="Other / specify", description=None),
                            ],
                            allow_multiple=True,
                        ),
                    ]
                    output = PlannerOutput(
                        action=PlannerAction.ASK_CLARIFICATION,
                        questions=fallback_questions,
                        message="I have a few questions to tailor the workflow before generating the plan.",
                    )
            
            # Store clarification history if questions were asked
            if output.action == PlannerAction.ASK_CLARIFICATION and output.questions:
                # Store questions for later reference
                for q in output.questions:
                    self._clarification_history.append({
                        "question": q.model_dump(),
                        "answers": []
                    })
            
            # Update answers if provided
            if clarification_responses:
                for q_id, answers in clarification_responses.items():
                    for item in self._clarification_history:
                        if item["question"].get("id") == q_id:
                            item["answers"] = answers
            
            # Store plan if generated
            if output.plan:
                self._current_plan = output.plan
                logger.info(f"[PlannerAgent] Generated plan with {len(output.plan.steps)} steps")
            
            # Send event if callback provided
            if on_event:
                import asyncio
                if output.action == PlannerAction.ASK_CLARIFICATION:
                    result = on_event({
                        "type": "clarification",
                        "data": {"questions": [q.model_dump() for q in output.questions]}
                    })
                    # Handle both sync and async callbacks
                    if asyncio.iscoroutine(result):
                        await result
                elif output.action == PlannerAction.GENERATE_PLAN:
                    result = on_event({
                        "type": "plan",
                        "data": output.plan.model_dump()
                    })
                    # Handle both sync and async callbacks
                    if asyncio.iscoroutine(result):
                        await result
            
            return output
            
        except Exception as e:
            logger.error(f"[PlannerAgent] Planning failed: {e}")
            return PlannerOutput(
                action=PlannerAction.PROCEED_TO_CODE,
                message=f"I encountered an issue during planning, but I'll try to generate the workflow: {str(e)}"
            )
    
    def plan_sync(
        self,
        user_message: str,
        canvas_context: Optional[Dict] = None,
        clarification_responses: Optional[Dict[str, List[str]]] = None,
        on_event: Optional[Callable] = None,
        require_clarification: bool = False,
    ) -> PlannerOutput:
        """Synchronous version of plan"""
        import asyncio
        
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                from agent.ec_skills.llm_utils.llm_utils import run_async_in_sync
                return run_async_in_sync(
                    self.plan(
                        user_message,
                        canvas_context,
                        clarification_responses,
                        on_event,
                        require_clarification=require_clarification,
                    )
                )
            else:
                return loop.run_until_complete(
                    self.plan(
                        user_message,
                        canvas_context,
                        clarification_responses,
                        on_event,
                        require_clarification=require_clarification,
                    )
                )
        except RuntimeError:
            return asyncio.run(
                self.plan(
                    user_message,
                    canvas_context,
                    clarification_responses,
                    on_event,
                    require_clarification=require_clarification,
                )
            )
    
    def get_current_plan(self) -> Optional[ImplementationPlan]:
        """Get the current implementation plan"""
        return self._current_plan
    
    def clear_history(self):
        """Clear clarification history and current plan"""
        self._clarification_history = []
        self._current_plan = None
        logger.info("[PlannerAgent] History cleared")


# ============================================================
# Singleton Instance
# ============================================================

_planner_instance: Optional[PlannerAgent] = None


def get_planner_agent() -> PlannerAgent:
    """Get or create the singleton planner agent instance"""
    global _planner_instance
    if _planner_instance is None:
        logger.info("[PlannerAgent] Creating new singleton instance")
        _planner_instance = PlannerAgent()
    return _planner_instance


def reset_planner_agent():
    """Reset the singleton instance"""
    global _planner_instance
    logger.info("[PlannerAgent] Resetting singleton instance")
    if _planner_instance:
        _planner_instance.clear_history()
    _planner_instance = None
