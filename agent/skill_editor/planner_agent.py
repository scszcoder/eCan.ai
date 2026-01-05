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


# ============================================================
# Constants
# ============================================================

MAX_CLARIFICATION_QUESTIONS = 4
MAX_PLANNING_ITERATIONS = 3


# ============================================================
# System Prompts
# ============================================================

PLANNER_SYSTEM_PROMPT = """You are a Planning Agent for the Skill Editor, helping users design workflow automations.

Your role is to understand the user's workflow requirements, ask clarifying questions when needed, and generate an implementation plan BEFORE code/flowgram generation begins.

## YOUR RESPONSIBILITIES:
1. Analyze the user's natural language request
2. Identify any ambiguities or missing information
3. Ask 1-{max_questions} targeted clarification questions with multiple-choice options
4. Generate a clear implementation plan once you have enough information

## AVAILABLE NODE TYPES:
{node_types}

## CURRENT CANVAS STATE:
{canvas_context}

## CLARIFICATION QUESTIONS GUIDELINES:
- Ask questions ONLY when there's genuine ambiguity
- Each question should have 2-4 clear choices
- Questions should be actionable and help determine the implementation
- Set "allow_multiple": true when the user can reasonably select multiple options
- Set "allow_multiple": false when only one option should be selected
- Focus on:
  - Data sources (where does the data come from?)
  - Output destinations (where should results go?)
  - Specific tools/integrations to use
  - Processing logic (filtering, transforming, etc.)
  - Trigger type (manual, scheduled, webhook)

## PLAN GENERATION GUIDELINES:
When generating a plan, include:
- A brief summary of what the workflow will do
- Step-by-step breakdown with clear descriptions
- Which node types will be used in each step
- List of all estimated nodes needed

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
  "message": "I have a few questions to better understand your requirements."
}}

When you have enough information to generate a plan:
{{
  "action": "generate_plan",
  "plan": {{
    "summary": "Brief overview of what the workflow will accomplish",
    "steps": [
      {{
        "title": "Step title",
        "description": "Detailed description of what this step does",
        "node_types": ["node_type_1", "node_type_2"]
      }}
    ],
    "estimated_nodes": ["start", "llm", "mcp_tool", "end"],
    "complexity": "simple" | "medium" | "complex"
  }},
  "message": "Here's my implementation plan for your workflow."
}}

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
6. For very simple requests (e.g., "create a simple LLM node"), proceed directly to code

Remember: Your goal is to understand the user's intent well enough to create a solid implementation plan. Don't over-question - if the request is reasonably clear, proceed with plan generation.
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
            from agent.ec_skills.llm_utils.llm_utils import select_or_create_llm
            
            mainwin = AppContext.get_main_window()
            if mainwin is None:
                raise RuntimeError("Main window not available")
            
            llm_providers = getattr(mainwin, 'llm_providers', [])
            default_llm = getattr(mainwin, 'default_llm', None)
            config_manager = getattr(mainwin, 'config_manager', None)
            
            if not llm_providers:
                raise RuntimeError("No LLM providers configured")
            
            llm_instance = select_or_create_llm(
                default_llm=default_llm,
                llm_providers=llm_providers,
                config_manager=config_manager,
                allow_fallback=True
            )
            
            if llm_instance is None:
                raise RuntimeError("Failed to create LLM instance")
            
            return llm_instance
            
        except Exception as e:
            logger.error(f"[PlannerAgent] Error loading LLM: {e}")
            try:
                from langchain_openai import ChatOpenAI
                import os
                api_key = os.environ.get("OPENAI_API_KEY")
                if api_key:
                    logger.info("[PlannerAgent] Using fallback OpenAI LLM")
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
                steps = [
                    PlanStep(
                        title=s.get("title", "Step"),
                        description=s.get("description", ""),
                        node_types=s.get("node_types", [])
                    )
                    for s in plan_data.get("steps", [])
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
        on_event: Optional[Callable] = None
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
            system_prompt = PLANNER_SYSTEM_PROMPT.format(
                max_questions=MAX_CLARIFICATION_QUESTIONS,
                node_types=get_node_types_description(),
                canvas_context=self._format_canvas_context(canvas_context)
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
                if output.action == PlannerAction.ASK_CLARIFICATION:
                    on_event({
                        "type": "clarification",
                        "data": {"questions": [q.model_dump() for q in output.questions]}
                    })
                elif output.action == PlannerAction.GENERATE_PLAN:
                    on_event({
                        "type": "plan",
                        "data": output.plan.model_dump()
                    })
            
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
        on_event: Optional[Callable] = None
    ) -> PlannerOutput:
        """Synchronous version of plan"""
        import asyncio
        
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                from agent.ec_skills.llm_utils.llm_utils import run_async_in_sync
                return run_async_in_sync(
                    self.plan(user_message, canvas_context, clarification_responses, on_event)
                )
            else:
                return loop.run_until_complete(
                    self.plan(user_message, canvas_context, clarification_responses, on_event)
                )
        except RuntimeError:
            return asyncio.run(
                self.plan(user_message, canvas_context, clarification_responses, on_event)
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
