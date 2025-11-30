"""Utility to convert prompt JSON to tagged Markdown format (XML tags wrapping Markdown content)."""

from typing import Any, Dict, List


def prompt_json_to_tagged_markdown(prompt_data: Dict[str, Any]) -> str:
    """
    Convert a prompt JSON object to tagged Markdown format.
    
    This format uses XML-style tags to wrap Markdown content, similar to:
    <section_name>
    - Item 1
    - Item 2
    </section_name>
    
    Args:
        prompt_data: Dictionary containing prompt data with sections and userSections
        
    Returns:
        Tagged Markdown-formatted string representation of the prompt
    """
    lines: List[str] = []
    
    # Add title if present
    title = prompt_data.get("title", "").strip()
    if title:
        lines.append(f"# {title}")
        lines.append("")
    
    def _render_sections_tagged(sections: List[Dict[str, Any]]) -> None:
        """Helper to render sections in tagged Markdown format."""
        for section in sections:
            if not isinstance(section, dict):
                continue
                
            items = section.get("items", [])
            if not items:
                continue
                
            # Use customLabel if available, otherwise use type
            label = section.get("customLabel") or section.get("type", "section")
            # Convert label to valid XML tag name (lowercase, replace non-alphanumeric with underscore)
            tag_name = "".join(c if c.isalnum() or c == "_" else "_" for c in label.lower())
            
            lines.append(f"<{tag_name}>")
            
            for item in items:
                item_text = str(item).strip()
                if item_text:
                    lines.append(f"- {item_text}")
                    
            lines.append(f"</{tag_name}>")
            lines.append("")  # blank line between sections
    
    # Render system prompt sections
    system_sections = prompt_data.get("sections", [])
    if system_sections:
        lines.append("<system_prompt>")
        _render_sections_tagged(system_sections)
        lines.append("</system_prompt>")
        lines.append("")
    
    # Render user prompt sections
    user_sections = prompt_data.get("userSections", [])
    if user_sections:
        lines.append("<user_prompt>")
        _render_sections_tagged(user_sections)
        lines.append("</user_prompt>")
    
    return "\n".join(lines)


def sections_to_tagged_markdown(sections: List[Dict[str, Any]]) -> str:
    """
    Convert a list of prompt sections to tagged Markdown format.
    
    Args:
        sections: List of section dictionaries with type, items, and optional customLabel
        
    Returns:
        Tagged Markdown-formatted string
    """
    lines: List[str] = []
    
    for section in sections:
        if not isinstance(section, dict):
            continue
            
        items = section.get("items", [])
        if not items:
            continue
            
        # Use customLabel if available, otherwise use type
        label = section.get("customLabel") or section.get("type", "section")
        # Convert label to valid XML tag name (lowercase, replace non-alphanumeric with underscore)
        tag_name = "".join(c if c.isalnum() or c == "_" else "_" for c in label.lower())
        
        lines.append(f"<{tag_name}>")
        
        for item in items:
            item_text = str(item).strip()
            if item_text:
                lines.append(f"- {item_text}")
                
        lines.append(f"</{tag_name}>")
        lines.append("")  # blank line between sections
    
    return "\n".join(lines)
