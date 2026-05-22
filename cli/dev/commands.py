#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Development Commands - Build, test, lint, and development utilities.
"""

import os
import sys
import click
import subprocess

from ..base.context import get_context
from ..base.output import get_output


@click.group()
def dev():
    """
    Development commands.

    CONTROL commands for build, test, lint, and development tasks.

    Examples:
      ecan dev build run --mode prod
      ecan dev test run --coverage
      ecan dev lint run --fix
    """
    pass


@dev.group()
def build():
    """Build system commands."""
    pass


@build.command()
@click.option('--mode', '-m', type=click.Choice(['fast', 'dev', 'prod']),
              default='dev',
              help='Build mode: fast (cached), dev (debug), prod (optimized)')
@click.option('--clean', '-c', is_flag=True,
              help='Clean build artifacts before building')
@click.option('--verbose', '-v', is_flag=True,
              help='Verbose output')
def run(mode, clean, verbose):
    """
    Run the build system.

    CONTROL command - compiles and packages the application.

    Build modes:
      fast  - Fast build with caching (recommended for development)
      dev   - Development build with debug symbols
      prod  - Production build with full optimization

    Examples:
      ecan dev build run
      ecan dev build run --mode prod
      ecan dev build run --mode fast --clean
    """
    ctx = get_context()
    out = get_output()

    cmd = [sys.executable, 'build.py', '--mode', mode]
    if clean:
        cmd.append('--cleanup-only')
    if verbose:
        cmd.append('--verbose')

    out.info(f"Running build in {mode} mode...")
    result = subprocess.run(cmd, cwd=str(ctx.project_root))

    if result.returncode == 0:
        out.success("Build completed")
    else:
        out.error("Build failed")
        raise SystemExit(result.returncode)


@build.command()
def clean():
    """
    Clean build artifacts.

    CONTROL command - removes build output and caches.

    Examples:
      ecan dev build clean
    """
    out = get_output()
    ctx = get_context()

    out.info("Cleaning build artifacts...")

    try:
        from build_system.build_cleaner import BuildCleaner
        cleaner = BuildCleaner(verbose=False)
        results = cleaner.clean_all()
        out.success(f"Cleaned: {results['total_size_mb']:.1f}MB freed, "
                   f"{results['broken_symlinks']} broken symlinks removed")
    except ImportError:
        out.error("Build cleaner not found")
        raise SystemExit(1)


@dev.group()
def test():
    """Test commands."""
    pass


@test.command()
@click.argument('path', required=False, default='.')
@click.option('--pattern', '-p', default='test_*.py',
              help='Test file pattern (default: test_*.py)')
@click.option('--verbose', '-v', is_flag=True,
              help='Verbose output')
@click.option('--coverage', '-c', is_flag=True,
              help='Generate coverage report')
@click.option('--html', is_flag=True,
              help='Generate HTML coverage report')
def run(path, pattern, verbose, coverage, html):
    """
    Run tests.

    CONTROL command - executes the test suite.

    Examples:
      ecan dev test run
      ecan dev test run tests/unit
      ecan dev test run --coverage --html
    """
    out = get_output()
    ctx = get_context()

    out.info(f"Running tests in {path}...")

    cmd = [sys.executable, '-m', 'pytest', path, '-v' if verbose else '-q']

    if coverage:
        cmd.extend(['--cov=.', '--cov-report=term-missing'])
        if html:
            cmd.append('--cov-report=html')

    result = subprocess.run(cmd, cwd=str(ctx.project_root))

    if result.returncode == 0:
        out.success("All tests passed")
    else:
        out.error("Some tests failed")
        raise SystemExit(result.returncode)


@test.command()
@click.argument('path', required=False)
def watch(path):
    """
    Run tests with file watching.

    CONTROL command - runs tests automatically when files change.

    Requires pytest-watch (ptw) to be installed.

    Examples:
      ecan dev test watch
      ecan dev test watch tests/
    """
    out = get_output()
    ctx = get_context()

    path = path or '.'
    out.info(f"Watching tests in {path}...")

    cmd = [sys.executable, '-m', 'ptw', path]
    result = subprocess.run(cmd, cwd=str(ctx.project_root))
    raise SystemExit(result.returncode)


@dev.group()
def lint():
    """Linting commands."""
    pass


@lint.command()
@click.argument('path', required=False, default='.')
@click.option('--fix', '-f', is_flag=True,
              help='Auto-fix issues where possible')
@click.option('--verbose', '-v', is_flag=True,
              help='Verbose output')
def run(path, fix, verbose):
    """
    Run linters (ruff, mypy).

    CONTROL command - checks code quality and style.

    Examples:
      ecan dev lint run
      ecan dev lint run --fix
      ecan dev lint run cli/
    """
    out = get_output()
    ctx = get_context()

    path = path or '.'

    out.info("Running ruff...")
    ruff_cmd = ['ruff', 'check', path]
    if fix:
        ruff_cmd.append('--fix')
    if verbose:
        ruff_cmd.append('-v')

    result = subprocess.run(ruff_cmd, cwd=str(ctx.project_root))

    if result.returncode != 0 and not fix:
        out.warning("Ruff found issues (use --fix to auto-fix)")
        raise SystemExit(result.returncode)

    out.info("Running mypy...")
    mypy_cmd = ['mypy', path]
    result = subprocess.run(mypy_cmd, cwd=str(ctx.project_root))

    if result.returncode == 0:
        out.success("All linting passed")
    else:
        out.error("Linting failed")
        raise SystemExit(result.returncode)


@lint.command()
@click.option('--fix', '-f', is_flag=True,
              help='Apply formatting')
def format(fix):
    """
    Format code with ruff.

    CONTROL command - formats code to follow style guidelines.

    Examples:
      ecan dev lint format
      ecan dev lint format --fix
    """
    out = get_output()
    ctx = get_context()

    out.info("Formatting code...")

    cmd = ['ruff', 'format']
    if fix:
        cmd.append('--respect-gitignore')

    result = subprocess.run(cmd, cwd=str(ctx.project_root))

    if result.returncode == 0:
        out.success("Code formatted")
    else:
        out.error("Formatting failed")
        raise SystemExit(result.returncode)


@dev.command()
@click.option('--host', '-h', default='127.0.0.1',
              help='Host to bind to (default: 127.0.0.1)')
@click.option('--port', '-p', default=5000, type=int,
              help='Port to bind to (default: 5000)')
@click.option('--reload', '-r', is_flag=True,
              help='Enable auto-reload on code changes')
def serve(host, port, reload):
    """
    Start development server.

    CONTROL command - launches a local development server.

    Examples:
      ecan dev serve
      ecan dev serve -h 0.0.0.0 -p 8080
      ecan dev serve --reload
    """
    out = get_output()
    ctx = get_context()

    out.info(f"Starting dev server on {host}:{port}...")

    env = os.environ.copy()
    env['ECAN_MODE'] = 'dev'

    cmd = [sys.executable, '-m', 'uvicorn',
           'web_server:app', '--host', host, '--port', str(port)]

    if reload:
        cmd.append('--reload')

    result = subprocess.run(cmd, cwd=str(ctx.project_root), env=env)
    raise SystemExit(result.returncode)


@dev.group()
def db():
    """Database commands."""
    pass


@db.command()
@click.option('--host', '-h', default='localhost',
              help='Database host (default: localhost)')
@click.option('--port', '-p', default=5432, type=int,
              help='Database port (default: 5432)')
@click.option('--user', '-u', default='postgres',
              help='Database user (default: postgres)')
@click.option('--password', '-pw', prompt=True, hide_input=True,
              help='Database password')
@click.option('--database', '-d',
              help='Database name (default: ecan)')
def connect(host, port, user, password, database):
    """
    Connect to database using psql.

    CONTROL command - opens an interactive PostgreSQL session.

    Examples:
      ecan dev db connect -h localhost -u postgres -pw secret
      ecan dev db connect -d mydb
    """
    out = get_output()
    ctx = get_context()

    db_name = database or 'ecan'

    cmd = ['psql', '-h', host, '-p', str(port), '-U', user, '-d', db_name]

    env = os.environ.copy()
    env['PGPASSWORD'] = password

    result = subprocess.run(cmd, cwd=str(ctx.project_root), env=env)
    raise SystemExit(result.returncode)


@db.command()
def migrate():
    """
    Run database migrations.

    CONTROL command - applies pending database migrations.

    Examples:
      ecan dev db migrate
    """
    out = get_output()
    ctx = get_context()

    out.info("Running migrations...")

    cmd = [sys.executable, '-m', 'alembic', 'upgrade', 'head']
    result = subprocess.run(cmd, cwd=str(ctx.project_root))

    if result.returncode == 0:
        out.success("Migrations applied")
    else:
        out.error("Migration failed")
        raise SystemExit(result.returncode)


@db.command()
@click.option('--message', '-m', required=True,
              help='Migration message (required)')
def makemigration(message):
    """
    Create a new migration.

    CONTROL command - generates a new Alembic migration file.

    Examples:
      ecan dev db makemigration -m "add user table"
    """
    out = get_output()
    ctx = get_context()

    out.info("Creating migration...")

    cmd = [sys.executable, '-m', 'alembic', 'revision', '--autogenerate', '-m', message]
    result = subprocess.run(cmd, cwd=str(ctx.project_root))

    if result.returncode == 0:
        out.success("Migration created")
    else:
        out.error("Migration creation failed")
        raise SystemExit(result.returncode)


@dev.command()
@click.option('--python', '-p', is_flag=True,
              help='Start Python shell')
@click.option('--ipython', '-i', is_flag=True,
              help='Start IPython shell')
def shell(python, ipython):
    """
    Start interactive shell.

    CONTROL command - opens a Python REPL with the project loaded.

    Examples:
      ecan dev shell
      ecan dev shell --ipython
    """
    out = get_output()
    ctx = get_context()

    if ipython:
        cmd = ['ipython']
    elif python:
        cmd = [sys.executable]
    else:
        cmd = ['ipython'] if _which('ipython') else [sys.executable]

    result = subprocess.run(cmd, cwd=str(ctx.project_root))
    raise SystemExit(result.returncode)


def _which(cmd):
    """Check if command exists."""
    result = subprocess.run(['which', cmd], capture_output=True)
    return result.returncode == 0
