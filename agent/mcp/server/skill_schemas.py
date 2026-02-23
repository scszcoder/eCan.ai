"""
Skill Schemas - Anthropic Agent Skills specification-compatible schema definitions.

Compatible with https://agentskills.io/specification

The Anthropic Agent Skills spec defines a skill as a SKILL.md with:
  Required frontmatter:
    - name: 1-64 chars, lowercase alphanumeric + hyphens
    - description: 1-1024 chars, what the skill does and when to use it
  Optional frontmatter:
    - license: license name or reference to bundled license file
    - compatibility: 1-500 chars, environment requirements
    - metadata: arbitrary key-value string map
    - allowed-tools: space-delimited list of pre-approved tools
  Directory structure:
    skill-name/
    ├── SKILL.md          (required)
    ├── scripts/          (optional - executable code)
    ├── references/       (optional - documentation loaded into context)
    └── assets/           (optional - files used in output)
  Progressive disclosure:
    1. Metadata (~100 tokens): name + description loaded at startup
    2. Instructions (<5000 tokens): SKILL.md body loaded on activation
    3. Resources (as needed): scripts/, references/, assets/ loaded on demand

This module bridges eCan's EC_Skill model to the Anthropic schema and provides
a registry of all available skills in a standardized format.
"""

import os
import re
import time
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from utils.logger_helper import logger_helper as logger


# ==================== Anthropic-Compatible Skill Schema ====================

class AgentSkillMetadata(BaseModel):
    """Arbitrary key-value metadata map (string keys → string values)."""
    author: Optional[str] = None
    version: Optional[str] = None
    category: Optional[str] = None
    sub_category: Optional[str] = None
    # Allow extra fields
    extra: Dict[str, str] = Field(default_factory=dict)


class AgentSkillSchema(BaseModel):
    """
    Anthropic Agent Skills specification-compatible schema.

    See https://agentskills.io/specification for the full spec.
    """

    # --- Required frontmatter ---
    name: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Unique identifier: lowercase alphanumeric + hyphens, 1-64 chars.",
    )
    description: str = Field(
        ...,
        min_length=1,
        max_length=1024,
        description="What the skill does and when to use it. 1-1024 chars.",
    )

    # --- Optional frontmatter ---
    license: Optional[str] = Field(
        default=None,
        description="License name or reference to a bundled license file.",
    )
    compatibility: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Environment requirements. 1-500 chars if provided.",
    )
    metadata: Optional[AgentSkillMetadata] = Field(
        default=None,
        description="Arbitrary key-value mapping for additional metadata.",
    )
    allowed_tools: Optional[str] = Field(
        default=None,
        description="Space-delimited list of pre-approved tools (experimental).",
    )

    # --- eCan extensions (not part of Anthropic spec, but useful) ---
    id: Optional[str] = Field(
        default=None,
        description="eCan internal skill ID.",
    )
    source: Optional[str] = Field(
        default=None,
        description="Skill source: 'code', 'ui', 'example'.",
    )
    version: Optional[str] = Field(
        default=None,
        description="Skill version string.",
    )
    level: Optional[str] = Field(
        default=None,
        description="Skill level: 'entry', 'intermediate', 'advanced'.",
    )
    tags: Optional[List[str]] = Field(
        default=None,
        description="Tags for categorization.",
    )
    examples: Optional[List[str]] = Field(
        default=None,
        description="Example usage strings.",
    )
    input_modes: Optional[List[str]] = Field(
        default=None,
        description="Supported input modes.",
    )
    output_modes: Optional[List[str]] = Field(
        default=None,
        description="Supported output modes.",
    )
    run_in_cloud: bool = Field(
        default=False,
        description="Whether this skill can run in the cloud.",
    )
    path: Optional[str] = Field(
        default=None,
        description="File path to the skill definition.",
    )

    # --- Body content (loaded on activation, not at startup) ---
    instructions: Optional[str] = Field(
        default=None,
        description="Markdown instructions body (SKILL.md content below frontmatter). "
                    "Loaded only when skill is activated.",
    )

    # --- Resource directories ---
    scripts: Optional[List[str]] = Field(
        default=None,
        description="List of script file paths in the skill's scripts/ directory.",
    )
    references: Optional[List[str]] = Field(
        default=None,
        description="List of reference file paths in the skill's references/ directory.",
    )
    assets: Optional[List[str]] = Field(
        default=None,
        description="List of asset file paths in the skill's assets/ directory.",
    )

    @field_validator("name", mode="before")
    @classmethod
    def _normalize_name(cls, v):
        """Normalize skill name to Anthropic spec: lowercase, hyphens for spaces."""
        if not v:
            return v
        # Lowercase, replace spaces/underscores with hyphens
        normalized = re.sub(r"[\s_]+", "-", str(v).lower().strip())
        # Remove non-alphanumeric except hyphens
        normalized = re.sub(r"[^a-z0-9\-]", "", normalized)
        # Remove leading/trailing hyphens
        normalized = normalized.strip("-")
        # Collapse consecutive hyphens
        normalized = re.sub(r"-{2,}", "-", normalized)
        # Truncate to 64 chars
        return normalized[:64] if normalized else "unnamed-skill"


# ==================== Conversion from EC_Skill ====================

def convert_ec_skill_to_schema(skill) -> AgentSkillSchema:
    """
    Convert an EC_Skill object to an Anthropic-compatible AgentSkillSchema.

    Args:
        skill: EC_Skill instance (or any object with name/description/id fields)

    Returns:
        AgentSkillSchema instance
    """
    name = getattr(skill, "name", "") or "unnamed-skill"
    description = getattr(skill, "description", "") or "No description"
    skill_id = getattr(skill, "id", None)
    source = getattr(skill, "source", None)
    version = getattr(skill, "version", None)
    level = getattr(skill, "level", None)
    tags = getattr(skill, "tags", None)
    examples = getattr(skill, "examples", None)
    input_modes = getattr(skill, "inputModes", None)
    output_modes = getattr(skill, "outputModes", None)
    run_in_cloud = getattr(skill, "run_in_cloud", False)
    path = getattr(skill, "path", None)

    # Build metadata
    meta_fields = {}
    if source:
        meta_fields["source"] = source
    if getattr(skill, "owner", None):
        meta_fields["author"] = skill.owner
    if version:
        meta_fields["version"] = version
    if level:
        meta_fields["level"] = level

    # Determine category from tags or ui_info
    category = None
    sub_category = None
    ui_info = getattr(skill, "ui_info", {}) or {}
    if isinstance(ui_info, dict):
        category = ui_info.get("category")
        sub_category = ui_info.get("sub_category")

    metadata = AgentSkillMetadata(
        author=meta_fields.get("author"),
        version=version,
        category=category,
        sub_category=sub_category,
        extra={k: str(v) for k, v in meta_fields.items() if k not in ("author", "version")},
    ) if meta_fields or category else None

    # Build compatibility string
    compatibility = None
    if run_in_cloud:
        compatibility = "Supports cloud execution"
    hybrid = getattr(skill, "hybrid_cloud_mode", False)
    if hybrid:
        compatibility = "Hybrid cloud mode (local + cloud)"

    # Build allowed-tools from skill config if available
    allowed_tools = None
    config = getattr(skill, "config", {}) or {}
    if isinstance(config, dict) and config.get("allowed_tools"):
        tools_list = config["allowed_tools"]
        if isinstance(tools_list, list):
            allowed_tools = " ".join(str(t) for t in tools_list)

    # Scan for resource directories if path is available
    scripts = _scan_skill_dir(path, "scripts") if path else None
    references = _scan_skill_dir(path, "references") if path else None
    assets = _scan_skill_dir(path, "assets") if path else None

    return AgentSkillSchema(
        name=name,
        description=description[:1024],
        license=None,
        compatibility=compatibility,
        metadata=metadata,
        allowed_tools=allowed_tools,
        id=skill_id,
        source=source,
        version=version,
        level=level,
        tags=tags,
        examples=examples,
        input_modes=input_modes,
        output_modes=output_modes,
        run_in_cloud=run_in_cloud,
        path=path,
        instructions=None,  # Loaded on demand, not at startup
        scripts=scripts,
        references=references,
        assets=assets,
    )


def _scan_skill_dir(skill_path: str, subdir: str) -> Optional[List[str]]:
    """Scan a skill's subdirectory for resource files."""
    if not skill_path:
        return None
    try:
        base = os.path.dirname(skill_path) if os.path.isfile(skill_path) else skill_path
        target = os.path.join(base, subdir)
        if os.path.isdir(target):
            files = []
            for f in os.listdir(target):
                full = os.path.join(target, f)
                if os.path.isfile(full):
                    files.append(os.path.join(subdir, f))
            return files if files else None
    except Exception:
        pass
    return None


# ==================== Schema Registry ====================

def get_skill_schemas(mainwin=None) -> List[Dict[str, Any]]:
    """
    Get all available skill schemas from the running agent(s).

    Returns a list of Anthropic-compatible skill schema dicts.
    Each dict contains at minimum: name, description.
    Full schema includes all optional fields.

    This is the skill-level equivalent of tool_schemas.py's get_tool_schemas().
    """
    schemas = []

    agents = []
    if mainwin and hasattr(mainwin, "agents"):
        agents = mainwin.agents or []

    for agent in agents:
        skills = getattr(agent, "skills", []) or []
        agent_id = getattr(getattr(agent, "card", None), "id", "")
        agent_name = getattr(getattr(agent, "card", None), "name", "")

        for skill in skills:
            try:
                schema = convert_ec_skill_to_schema(skill)
                schema_dict = schema.model_dump(exclude_none=True)
                # Tag with agent info for multi-agent setups
                schema_dict["_agent_id"] = agent_id
                schema_dict["_agent_name"] = agent_name
                schemas.append(schema_dict)
            except Exception as e:
                logger.warning(
                    f"[skill_schemas] Failed to convert skill "
                    f"'{getattr(skill, 'name', '?')}': {e}"
                )

    logger.info(f"[skill_schemas] Generated {len(schemas)} skill schemas")
    return schemas


def get_skill_schemas_summary(mainwin=None) -> List[Dict[str, str]]:
    """
    Get lightweight skill summaries (name + description only).

    This corresponds to Anthropic's "progressive disclosure" level 1:
    ~100 tokens per skill, loaded at startup for all skills.
    """
    summaries = []

    agents = []
    if mainwin and hasattr(mainwin, "agents"):
        agents = mainwin.agents or []

    for agent in agents:
        skills = getattr(agent, "skills", []) or []
        for skill in skills:
            name = getattr(skill, "name", "") or "unnamed"
            desc = getattr(skill, "description", "") or ""
            skill_id = getattr(skill, "id", "")
            summaries.append({
                "name": re.sub(r"[\s_]+", "-", name.lower().strip()),
                "description": desc[:1024],
                "id": skill_id,
            })

    return summaries


# ==================== SKILL.md Generation ====================

def generate_skill_md(schema: AgentSkillSchema) -> str:
    """
    Generate a SKILL.md file content from an AgentSkillSchema.

    Produces Anthropic-compatible SKILL.md with YAML frontmatter.
    """
    lines = ["---"]
    lines.append(f"name: {schema.name}")
    lines.append(f"description: {schema.description}")

    if schema.license:
        lines.append(f"license: {schema.license}")
    if schema.compatibility:
        lines.append(f"compatibility: {schema.compatibility}")
    if schema.metadata:
        lines.append("metadata:")
        if schema.metadata.author:
            lines.append(f"  author: {schema.metadata.author}")
        if schema.metadata.version:
            lines.append(f'  version: "{schema.metadata.version}"')
        if schema.metadata.category:
            lines.append(f"  category: {schema.metadata.category}")
        if schema.metadata.sub_category:
            lines.append(f"  sub-category: {schema.metadata.sub_category}")
        for k, v in (schema.metadata.extra or {}).items():
            lines.append(f"  {k}: {v}")
    if schema.allowed_tools:
        lines.append(f"allowed-tools: {schema.allowed_tools}")

    lines.append("---")
    lines.append("")

    # Body content
    if schema.instructions:
        lines.append(schema.instructions)
    else:
        # Generate a default body from available info
        lines.append(f"# {schema.name}")
        lines.append("")
        lines.append(schema.description)
        lines.append("")

        if schema.examples:
            lines.append("## Examples")
            for ex in schema.examples:
                lines.append(f"- {ex}")
            lines.append("")

        if schema.tags:
            lines.append(f"**Tags:** {', '.join(schema.tags)}")
            lines.append("")

    return "\n".join(lines)


def parse_skill_md(content: str) -> AgentSkillSchema:
    """
    Parse a SKILL.md file content into an AgentSkillSchema.

    Handles YAML frontmatter delimited by --- and markdown body.
    """
    import yaml

    # Split frontmatter and body
    parts = content.split("---", 2)
    if len(parts) < 3:
        # No valid frontmatter
        return AgentSkillSchema(
            name="unnamed-skill",
            description=content[:1024].strip() or "No description",
            instructions=content,
        )

    frontmatter_str = parts[1].strip()
    body = parts[2].strip()

    try:
        fm = yaml.safe_load(frontmatter_str) or {}
    except Exception:
        fm = {}

    name = fm.get("name", "unnamed-skill")
    description = fm.get("description", "No description")

    # Parse metadata
    metadata = None
    if "metadata" in fm and isinstance(fm["metadata"], dict):
        meta_raw = fm["metadata"]
        metadata = AgentSkillMetadata(
            author=meta_raw.get("author"),
            version=str(meta_raw.get("version", "")) or None,
            category=meta_raw.get("category"),
            sub_category=meta_raw.get("sub-category") or meta_raw.get("sub_category"),
            extra={k: str(v) for k, v in meta_raw.items()
                   if k not in ("author", "version", "category", "sub-category", "sub_category")},
        )

    return AgentSkillSchema(
        name=name,
        description=str(description)[:1024],
        license=fm.get("license"),
        compatibility=fm.get("compatibility"),
        metadata=metadata,
        allowed_tools=fm.get("allowed-tools") or fm.get("allowed_tools"),
        instructions=body if body else None,
    )
