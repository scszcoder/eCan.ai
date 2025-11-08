import os, subprocess, shlex
from pathlib import Path

def run_git(cmd: str | list[str], repo: str | None = None, check=True, timeout=120, env=None):
    """
    Run a git command and return (stdout, stderr, returncode).
    Example: run_git('status', repo='C:/code/myrepo')
    """
    if isinstance(cmd, str):
        args = ["git"] + shlex.split(cmd)
    else:
        args = ["git"] + cmd
    cwd = str(Path(repo)) if repo else None
    # Apply Windows hidden console flags in frozen builds
    try:
        from utils.subprocess_helper import get_subprocess_kwargs
        kwargs = get_subprocess_kwargs({
            'cwd': cwd,
            'env': env,
            'check': False,
            'stdout': subprocess.PIPE,
            'stderr': subprocess.PIPE,
            'text': True,
            'timeout': timeout,
        })
    except Exception:
        kwargs = {
            'cwd': cwd,
            'env': env,
            'check': False,
            'stdout': subprocess.PIPE,
            'stderr': subprocess.PIPE,
            'text': True,
            'timeout': timeout,
        }
    proc = subprocess.run(args, **kwargs)
    if check and proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args[1:])} failed:\n{proc.stderr}")
    return proc.stdout.strip(), proc.stderr.strip(), proc.returncode

# --- Common routines ---
def git_clone(url: str, dest: str):
    return run_git(["clone", url, dest])

def git_status(repo: str):
    out, _, _ = run_git("status --porcelain=v1 -b", repo=repo)
    return out

def git_checkout(repo: str, branch: str, create=False):
    if create:
        return run_git(["checkout", "-b", branch], repo=repo)
    return run_git(["checkout", branch], repo=repo)

def git_pull(repo: str, remote="origin", branch=None):
    cmd = ["pull", remote] + ([branch] if branch else [])
    return run_git(cmd, repo=repo)

def git_fetch(repo: str, remote="origin", prune=True):
    cmd = ["fetch", remote] + (["--prune"] if prune else [])
    return run_git(cmd, repo=repo)

def git_add_all(repo: str):
    return run_git(["add", "-A"], repo=repo)

def git_commit(repo: str, message: str):
    return run_git(["commit", "-m", message], repo=repo, check=False)  # ok if nothing to commit

def git_push(repo: str, remote="origin", branch=None, set_upstream=False):
    cmd = ["push", remote] + ([branch] if branch else [])
    if set_upstream and branch:
        cmd.insert(1, "-u")
    return run_git(cmd, repo=repo)

def git_tag(repo: str, name: str, annotate_msg: str | None = None, push=False):
    if annotate_msg:
        run_git(["tag", "-a", name, "-m", annotate_msg], repo=repo)
    else:
        run_git(["tag", name], repo=repo)
    if push:
        run_git(["push", "origin", name], repo=repo)


def git_log(
        repo: str,
        max_count: int | None = 10,
        pretty: str = "oneline",  # "oneline", "short", "medium", "full", "fuller", or custom format
        author: str | None = None,
        grep: str | None = None,
):
    """
    Show git commit history.
    Example:
        git_log(repo, max_count=5)
        git_log(repo, pretty="%h %ad | %s%d [%an]", max_count=20)
    """
    cmd = ["log"]
    if max_count:
        cmd += [f"--max-count={max_count}"]
    if pretty:
        # git allows special keywords ("oneline", "short", etc.) or custom formats
        if pretty.startswith("%"):
            cmd += ["--pretty=format:" + pretty]
        else:
            cmd += [f"--pretty={pretty}"]
    if author:
        cmd += [f"--author={author}"]
    if grep:
        cmd += [f"--grep={grep}"]

    out, _, _ = run_git(cmd, repo=repo)
    return out

# --- Branch Management ---

def git_branch_list(repo: str, remote: bool = False):
    """
    List branches (local by default, remote if remote=True).
    Returns a list of branch names, with '*' marking the current one.
    """
    cmd = ["branch"]
    if remote:
        cmd.append("-r")
    out, _, _ = run_git(cmd, repo=repo)
    return out.splitlines()


def git_branch_create(repo: str, branch: str, checkout: bool = False):
    """
    Create a new branch. Optionally check it out immediately.
    """
    run_git(["branch", branch], repo=repo)
    if checkout:
        git_checkout(repo, branch)


def git_branch_delete(repo: str, branch: str, force: bool = False):
    """
    Delete a branch (local).
    """
    flag = "-D" if force else "-d"
    return run_git(["branch", flag, branch], repo=repo)


# --- Merge ---

def git_merge(repo: str, branch: str, no_ff: bool = False, message: str | None = None):
    """
    Merge another branch into the current branch.
    Example: git_merge(repo, "feature/x", no_ff=True, message="Merge feature/x")
    """
    cmd = ["merge", branch]
    if no_ff:
        cmd.append("--no-ff")
    if message:
        cmd += ["-m", message]
    return run_git(cmd, repo=repo)



#
# # --- Example flow ---
# if __name__ == "__main__":
#     repo_dir = r"C:\code\myrepo"
#     if not Path(repo_dir).exists():
#         git_clone("git@github.com:yourname/yourrepo.git", repo_dir)
#
#     print(git_status(repo_dir))
#     git_checkout(repo_dir, "feature/x", create=True)
#     # ... modify files ...
#     git_add_all(repo_dir)
#     git_commit(repo_dir, "feat: add something")
#     git_push(repo_dir, branch="feature/x", set_upstream=True)
