#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tool Management Commands - Query available tools in the system.
"""

import click

from ..base.output import get_output


@click.group()
def tools():
    """
    Tool management commands.

    QUERY commands for listing and inspecting available tools.

    Tools are utilities that agents can use to perform actions,
    such as web search, file operations, or API calls.

    Examples:
      ecan tools list
      ecan tools get web-search
    """
    pass


@tools.command('list')
@click.option('--category', '-c',
              help='Filter tools by category (e.g., search, web, execution)')
@click.option('--limit', '-l', default=50, type=int,
              help='Maximum number of results (default: 50)')
@click.option('--format', '-f', type=click.Choice(['table', 'json', 'simple']),
              default='table',
              help='Output format (default: table)')
def list_tools(category, limit, format):
    """
    List all available tools.

    QUERY command - retrieves and displays available tools.

    Examples:
      ecan tools list
      ecan tools list --category search
      ecan tools list --format json
    """
    out = get_output()

    tools_data = [
        {
            'id': 'web-search',
            'name': 'Web Search',
            'category': 'search',
            'description': 'Search the web using search engines'
        },
        {
            'id': 'web-fetch',
            'name': 'Web Fetch',
            'category': 'web',
            'description': 'Fetch and parse web pages'
        },
        {
            'id': 'code-interpreter',
            'name': 'Code Interpreter',
            'category': 'execution',
            'description': 'Execute code in a sandboxed environment'
        },
    ]

    if category:
        tools_data = [t for t in tools_data if t.get('category') == category]
    tools_data = tools_data[:limit]

    if format == 'json':
        out.json({'tools': tools_data, 'count': len(tools_data)})
    elif format == 'simple':
        for tool in tools_data:
            out.print(f"{tool['name']}\t{tool['category']}")
    else:
        rows = [[t['id'], t['name'], t['category'], t['description']] for t in tools_data]
        out.table("Tools", ["ID", "Name", "Category", "Description"], rows)


@tools.command()
@click.argument('tool_id')
def get(tool_id):
    """
    Get tool details by ID.

    QUERY command - retrieves detailed information about a tool.

    Examples:
      ecan tools get web-search
      ecan tools get code-interpreter
    """
    out = get_output()

    tools_map = {
        'web-search': {
            'id': 'web-search',
            'name': 'Web Search',
            'category': 'search',
            'description': 'Search the web using search engines',
            'parameters': {
                'query': {'type': 'string', 'required': True, 'description': 'Search query'},
                'limit': {'type': 'integer', 'required': False, 'description': 'Max results'}
            }
        },
        'web-fetch': {
            'id': 'web-fetch',
            'name': 'Web Fetch',
            'category': 'web',
            'description': 'Fetch and parse web pages',
            'parameters': {
                'url': {'type': 'string', 'required': True, 'description': 'URL to fetch'},
                'extract_text': {'type': 'boolean', 'required': False, 'description': 'Extract text only'}
            }
        },
        'code-interpreter': {
            'id': 'code-interpreter',
            'name': 'Code Interpreter',
            'category': 'execution',
            'description': 'Execute code in a sandboxed environment',
            'parameters': {
                'language': {'type': 'string', 'required': True, 'description': 'Programming language'},
                'code': {'type': 'string', 'required': True, 'description': 'Code to execute'}
            }
        },
    }

    if tool_id in tools_map:
        out.json(tools_map[tool_id])
    else:
        out.error(f"Tool not found: {tool_id}")
        out.print("Run 'ecan tools list' to see available tools")
        raise SystemExit(1)
