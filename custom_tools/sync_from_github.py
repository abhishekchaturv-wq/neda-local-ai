import subprocess
import os
import time
from datetime import datetime
from pathlib import Path

def sync_from_github():
    repo_path = Path.home() / "local-ai"
    
    # Step 1: Verify ~/local-ai is a Git repository
    # Validation with py_compile
    import py_compile
    py_compile.compile(repo_path / "custom_tools/sync_from_github.py")
    
    try:
        subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=repo_path, check=True, capture_output=True)
    except subprocess.CalledProcessError:
        return "The directory is not a Git repository."
    
    # Step 2: Run git status --porcelain
    status_output = subprocess.run(["git", "status", "--porcelain"], cwd=repo_path, capture_output=True, text=True)
    
    # Step 3: If the working tree is dirty, refuse to update and return the list of local changes
    if status_output.stdout.strip():
        return f"Working tree is dirty:\n{status_output.stdout}"
    
    # Step 4: Record the current HEAD SHA
    head_sha_output = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo_path, capture_output=True, text=True)
    current_head_sha = head_sha_output.stdout.strip()
    
    # Step 5: Run git fetch origin main
    subprocess.run(["git", "fetch", "origin", "main"], cwd=repo_path, check=True)
    
    # Step 6: Get origin/main SHA
    origin_main_sha_output = subprocess.run(["git", "rev-parse", "origin/main"], cwd=repo_path, capture_output=True, text=True)
    origin_main_sha = origin_main_sha_output.stdout.strip()
    
    # Step 7: If local HEAD already equals origin/main, report "already up to date" and do nothing
    if current_head_sha == origin_main_sha:
        return "already up to date"
    
    # Step 8: If local history is ahead of or diverged from origin/main, refuse the update
    ahead_or_diverged_output = subprocess.run(["git", "rev-list", "--count", "--left-right", f"{current_head_sha}...origin/main"], cwd=repo_path, capture_output=True, text=True)
    ahead, diverged = map(int, ahead_or_diverged_output.stdout.strip().split())
    if ahead > 0 or diverged > 0:
        return "Local history is ahead of or diverged from origin/main. Refusing update."
    
    # Step 9: If origin/main is a fast-forward descendant of HEAD
    try:
        # Create a rollback branch named neda-before-sync-<unix timestamp> pointing to the current HEAD
        rollback_branch_name = f"neda-before-sync-{int(time.time())}"
        subprocess.run(["git", "branch", rollback_branch_name, current_head_sha], cwd=repo_path, check=True)
        
        # Run git pull --ff-only origin main
        subprocess.run(["git", "pull", "--ff-only", "origin", "main"], cwd=repo_path, check=True)
        
        # Enumerate tracked Python files with git ls-files "*.py"
        ls_files_output = subprocess.run(["git", "ls-files", "*.py"], cwd=repo_path, capture_output=True, text=True)
        tracked_python_files = ls_files_output.stdout.strip().splitlines()
        
        # Exclude venv/ and chroma_db/
        filtered_python_files = [f for f in tracked_python_files if not f.startswith(("venv/", "chroma_db/"))]
        
        # Compile every remaining Python file using ./venv/bin/python -m py_compile
        compilation_errors = []
        for file in filtered_python_files:
            try:
                subprocess.run([os.path.join(repo_path, "venv/bin/python"), "-m", "py_compile", os.path.join(repo_path, file)], check=True)
            except subprocess.CalledProcessError:
                compilation_errors.append(file)
        
        # Step 10: If any Python compilation fails
        if compilation_errors:
            # Automatically git reset --hard to the rollback branch
            subprocess.run(["git", "reset", "--hard", rollback_branch_name], cwd=repo_path, check=True)
            return f"Compilation failed for files: {', '.join(compilation_errors)}. Rollback to {rollback_branch_name} performed."
        
        # Step 11: If validation succeeds
        return f"Old SHA: {current_head_sha}, New SHA: {origin_main_sha}, Rollback Branch: {rollback_branch_name}, Validation Success. Call restart_self() to load the new version."
    except subprocess.CalledProcessError as e:
        return f"An error occurred during synchronization: {e}"