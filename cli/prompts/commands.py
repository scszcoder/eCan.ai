#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Prompt Management Commands - Manage reusable prompts and templates.
"""

import os
import click
from pathlib import Path

from ..base.context import get_context
from ..base.output import get_output


@click.group()
def prompts():
    """
    Prompt management commands.

    OPERATION commands for creating, editing, and deleting prompts.
    QUERY commands for listing and retrieving prompts.

    Prompts are reusable text templates that can include placeholders
    for dynamic values.

    Examples:
      ecan prompts list
      ecan prompts get myprompt
      ecan prompts add -n myprompt -c "Hello {0}!"
    """
    pass


@prompts.command('list')
@click.option('--name', '-n',
              help='Filter prompts by name (case-insensitive partial match)')
@click.option('--format', '-f', type=click.Choice(['table', 'json', 'simple']),
              default='table',
              help='Output format (default: table)')
def list_prompts(name, format):
    """
    List all prompts.

    QUERY command - retrieves and displays prompts from the prompts directory.

    Examples:
      ecan prompts list
      ecan prompts list --name "greeting"
      ecan prompts list --format json
    """
    ctx = get_context()
    out = get_output()

    prompts_dir = ctx.project_root / "prompts"
    prompts_data = []

    if prompts_dir.exists():
        for ext in ['*.txt', '*.md']:
            for f in prompts_dir.glob(ext):
                if not name or name.lower() in f.stem.lower():
                    prompts_data.append({
                        'name': f.stem,
                        'path': str(f),
                        'size': f.stat().st_size
                    })

    if not prompts_data:
        out.warning("No prompts found")
        out.info("Use 'ecan prompts add' to create one")
        return

    if format == 'json':
        out.json({'prompts': prompts_data, 'count': len(prompts_data)})
    elif format == 'simple':
        for p in prompts_data:
            out.print(p['name'])
    else:
        rows = [[p['name'], p['path'], f"{p['size']} bytes"] for p in prompts_data]
        out.table("Prompts", ["Name", "Path", "Size"], rows)


@prompts.command()
@click.argument('name')
def get(name):
    """
    Get prompt content.

    QUERY command - displays the content of a prompt.

    Examples:
      ecan prompts get myprompt
      ecan prompts get greeting
    """
    ctx = get_context()
    out = get_output()

    prompts_dir = ctx.project_root / "prompts"

    for ext in ['.txt', '.md', '']:
        prompt_file = prompts_dir / f"{name}{ext}"
        if prompt_file.exists():
            content = prompt_file.read_text()
            out.title(f"Prompt: {name}")
            out.print(content)
            return

    out.error(f"Prompt not found: {name}")
    out.print("Run 'ecan prompts list' to see available prompts")
    raise SystemExit(1)


@prompts.command()
@click.option('--name', '-n', required=True,
              help='Prompt name (required)')
@click.option('--content', '-c',
              help='Prompt content (use \\n for newlines)')
@click.option('--file', '-f', 'file_path', type=click.Path(exists=True),
              help='Read content from file')
@click.option('--overwrite', is_flag=True,
              help='Replace the prompt if it already exists')
def add(name, content, file_path, overwrite):
    """
    Create (or overwrite) a prompt.

    OPERATION command - creates a new prompt file, or replaces an existing one
    when --overwrite is given.

    Examples:
      ecan prompts add -n myprompt -c "Hello {0}, welcome!"
      ecan prompts add -n greeting -f ./templates/greeting.txt
      ecan prompts add -n myprompt -c "Updated text" --overwrite
    """
    ctx = get_context()
    out = get_output()

    prompts_dir = ctx.project_root / "prompts"
    prompts_dir.mkdir(exist_ok=True)

    if file_path:
        content = Path(file_path).read_text()

    if not content:
        out.error("Provide content via --content or --file")
        return

    prompt_file = prompts_dir / f"{name}.txt"
    existed = prompt_file.exists()
    if existed and not overwrite:
        out.error(f"Prompt already exists: {name}")
        out.info("Use --overwrite to replace it, or 'ecan prompts edit'")
        raise SystemExit(1)

    prompt_file.write_text(content)
    out.success(f"Prompt '{name}' {'updated' if existed else 'created'}!")


@prompts.command()
@click.argument('name')
@click.option('--force', '-f', is_flag=True,
              help='Skip confirmation prompt')
def remove(name, force):
    """
    Delete a prompt.

    OPERATION command - permanently removes a prompt file.

    Examples:
      ecan prompts remove myprompt      # With confirmation
      ecan prompts remove myprompt -f   # Skip confirmation
    """
    ctx = get_context()
    out = get_output()

    prompts_dir = ctx.project_root / "prompts"

    for ext in ['.txt', '.md', '']:
        prompt_file = prompts_dir / f"{name}{ext}"
        if prompt_file.exists():
            if not force and not out.confirm(f"Delete prompt '{name}'?"):
                return
            prompt_file.unlink()
            out.success(f"Prompt '{name}' deleted!")
            return

    out.error(f"Prompt not found: {name}")
    raise SystemExit(1)


@prompts.command()
@click.argument('name')
@click.option('--editor', '-e', is_flag=True,
              help='Edit with default editor ($EDITOR)')
def edit(name, editor):
    """
    Edit a prompt.

    OPERATION command - opens a prompt in the editor.

    Examples:
      ecan prompts edit myprompt -e
    """
    ctx = get_context()
    out = get_output()

    prompts_dir = ctx.project_root / "prompts"
    prompt_file = prompts_dir / f"{name}.txt"

    for ext in ['.txt', '.md', '']:
        test_file = prompts_dir / f"{name}{ext}"
        if test_file.exists():
            prompt_file = test_file
            break

    if editor:
        editor_cmd = os.environ.get('EDITOR', 'vim')
        import subprocess
        subprocess.run([editor_cmd, str(prompt_file)])
    else:
        out.info(f"Use 'ecan prompts edit -e' to edit in your editor")
        out.print(f"Prompt file: {prompt_file}")


@prompts.command()
@click.argument('name')
@click.argument('args', nargs=-1)
def run(name, args):
    """
    Run a prompt with arguments.

    QUERY command - displays prompt content with placeholders replaced.

    Placeholders: {0}, {1}, ... or {arg0}, {arg1}, ...

    Examples:
      ecan prompts run greeting John
      ecan prompts run template "Hello" "World"
    """
    ctx = get_context()
    out = get_output()

    prompts_dir = ctx.project_root / "prompts"

    for ext in ['.txt', '.md', '']:
        prompt_file = prompts_dir / f"{name}{ext}"
        if prompt_file.exists():
            content = prompt_file.read_text()

            for i, arg in enumerate(args):
                content = content.replace(f"{{{i}}}", arg)
                content = content.replace(f"{{arg{i}}}", arg)

            out.title(f"Prompt: {name}")
            out.print(content)
            return

    out.error(f"Prompt not found: {name}")
    raise SystemExit(1)
