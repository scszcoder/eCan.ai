#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Knowledge Base Management Commands - Query and manage knowledge bases.
"""

import click

from ..base.context import get_context
from ..base.output import get_output
from ..base.decorators import requires_auth


@click.group()
def knowledge():
    """
    Knowledge base management commands.

    QUERY commands for searching and retrieving from knowledge bases.
    OPERATION commands for adding and managing knowledge bases.

    Knowledge bases store documents and data that can be used by agents
    for RAG (Retrieval Augmented Generation) queries.

    Examples:
      ecan knowledge list
      ecan knowledge search "shipping policy"
      ecan knowledge add -n "Product FAQ"
    """
    pass


@knowledge.command('list')
@click.option('--name', '-n',
              help='Filter knowledge bases by name')
@click.option('--limit', '-l', default=50, type=int,
              help='Maximum number of results (default: 50)')
@click.option('--format', '-f', type=click.Choice(['table', 'json', 'simple']),
              default='table',
              help='Output format (default: table)')
def list_knowledge(name, limit, format):
    """
    List all knowledge bases.

    QUERY command - retrieves and displays knowledge bases.

    Examples:
      ecan knowledge list
      ecan knowledge list --name "Product"
      ecan knowledge list --format json
    """
    out = get_output()

    knowledge_data = []

    if not knowledge_data:
        out.warning("No knowledge bases found (knowledge bases are not yet implemented)")
        return

    knowledge_data = knowledge_data[:limit]

    if format == 'json':
        out.json({'knowledge_bases': knowledge_data, 'count': len(knowledge_data)})
    elif format == 'simple':
        for kb in knowledge_data:
            out.print(f"{kb.get('name', '')}\t{kb.get('type', '')}")
    else:
        rows = [[kb.get('id', '')[:12], kb.get('name', ''), kb.get('type', '')] for kb in knowledge_data]
        out.table("Knowledge Bases", ["ID", "Name", "Type"], rows)


@knowledge.command()
@click.argument('knowledge_id')
def get(knowledge_id):
    """
    Get knowledge base details by ID.

    QUERY command - retrieves detailed information about a knowledge base.

    Examples:
      ecan knowledge get abc123
    """
    out = get_output()
    out.warning("Knowledge base details not yet implemented")
    raise SystemExit(1)


@knowledge.command()
@requires_auth
@click.option('--name', '-n', required=True,
              help='Knowledge base name (required)')
@click.option('--type', '-t',
              help='Knowledge base type (e.g., document, qa, faq)')
@click.option('--source', '-s', type=click.Path(exists=True),
              help='Source file or directory to import')
def add(name, type, source):
    """
    Add a new knowledge base.

    OPERATION command - creates a new knowledge base.

    Requires authentication. Use 'ecan auth login' first.

    Examples:
      ecan knowledge add -n "Product Manual" -t document -s ./docs/
      ecan knowledge add -n "FAQ" -t faq
    """
    out = get_output()
    out.warning("Knowledge base creation not yet implemented")
    raise SystemExit(1)


@knowledge.command()
@click.argument('query')
@click.option('--kb', '-k',
              help='Knowledge base ID to search in (default: all)')
@click.option('--limit', '-l', default=10, type=int,
              help='Maximum number of results (default: 10)')
def search(query, kb, limit):
    """
    Search knowledge base for relevant documents.

    QUERY command - performs semantic search across knowledge bases.

    Examples:
      ecan knowledge search "what is your return policy"
      ecan knowledge search "shipping options" --limit 20
      ecan knowledge search "pricing" -k abc123
    """
    out = get_output()
    out.info(f"Searching for: {query}")
    out.warning("Knowledge search not yet implemented")
    raise SystemExit(1)


# ---- product files an agent fetched for review (knowledge/ks/pending_imports.py) ----

def _pending_store():
    """The signed-in user's staged imports (same folder the app uses)."""
    import os
    from utils.user_path_helper import get_user_data_dir
    from knowledge.ks.pending_imports import PendingImports
    ctx = get_context()
    return PendingImports(os.path.join(get_user_data_dir(user_email=ctx.username), "knowledge_service"))


@knowledge.group()
def pending():
    """
    Product files waiting for review.

    An agent (e.g. the product-export skill) downloads the store's product list and leaves
    it here; review and import it in the app (Product Knowledge > Import).

    Examples:
      ecan knowledge pending list
      ecan knowledge pending dismiss 3f2a9c81b0d4
    """
    pass


@pending.command('list')
@requires_auth
@click.option('--format', '-f', type=click.Choice(['table', 'json']), default='table',
              help='Output format (default: table)')
def list_pending(format):
    """List the product files waiting for review."""
    import time
    out = get_output()
    items = _pending_store().list()
    if format == 'json':
        out.json({'items': items, 'count': len(items)})
        return
    if not items:
        out.info("Nothing waiting for review")
        return
    rows = [[e.get('id', ''), e.get('file_name', ''), str(e.get('rows', '')), e.get('source', ''),
             e.get('store_id', ''), time.strftime('%Y-%m-%d %H:%M', time.localtime(e.get('created_at') or 0))]
            for e in items]
    out.table("Waiting for review", ["ID", "File", "Rows", "From", "Store", "Fetched"], rows)


@pending.command('dismiss')
@requires_auth
@click.argument('pending_id')
def dismiss_pending(pending_id):
    """Drop a waiting product file without importing it."""
    out = get_output()
    if not _pending_store().remove(pending_id):
        out.error(f"No waiting file with id {pending_id}")
        raise SystemExit(1)
    out.success("Dismissed")
