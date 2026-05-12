"""Fetch skill files from GitHub URLs or local paths."""

from __future__ import annotations

import base64
import re
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import requests

from skill_warden.settings import (
    GITHUB_API_BASE,
    MAX_FILE_SIZE_BYTES,
    SCANNABLE_EXTENSIONS,
    SKILL_DIRS,
    SKILL_MD_FILENAME,
)


@dataclass
class SkillFileData:
    filename: str
    content: str
    file_type: str  # "text"


@dataclass
class SkillData:
    name: str
    description: Optional[str]
    files: list[SkillFileData]
    skill_path: str
    github_url: str
    commit_sha: str


def _make_headers(token: Optional[str]) -> dict[str, str]:
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _parse_github_url(url: str) -> dict:
    """
    Parse a GitHub URL into components: owner, repo, branch, path.
    Supports:
      - owner/repo
      - https://github.com/owner/repo
      - https://github.com/owner/repo/tree/BRANCH/path/to/dir
    """
    url = url.strip()
    if not url.startswith("http"):
        parts = url.split("/")
        return {"owner": parts[0], "repo": parts[1], "branch": None, "path": ""}

    parsed = urllib.parse.urlparse(url)
    path_parts = [p for p in parsed.path.strip("/").split("/") if p]

    if len(path_parts) < 2:
        raise ValueError(f"Cannot parse GitHub URL: {url}")

    owner, repo = path_parts[0], path_parts[1]
    branch = None
    sub_path = ""

    if len(path_parts) > 2 and path_parts[2] == "tree":
        branch = path_parts[3] if len(path_parts) > 3 else None
        sub_path = "/".join(path_parts[4:]) if len(path_parts) > 4 else ""

    return {"owner": owner, "repo": repo, "branch": branch, "path": sub_path}


def _get_default_branch(owner: str, repo: str, headers: dict) -> str:
    resp = requests.get(f"{GITHUB_API_BASE}/repos/{owner}/{repo}", headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json().get("default_branch", "main")


def _get_commit_sha(owner: str, repo: str, branch: str, headers: dict) -> str:
    resp = requests.get(
        f"{GITHUB_API_BASE}/repos/{owner}/{repo}/commits/{branch}",
        headers=headers,
        timeout=30,
    )
    if resp.status_code == 200:
        return resp.json().get("sha", "unknown")[:12]
    return "unknown"


def _fetch_contents(owner: str, repo: str, path: str, ref: str, headers: dict) -> list[dict]:
    url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/contents/{path}"
    params = {"ref": ref}
    resp = requests.get(url, headers=headers, params=params, timeout=30)
    if resp.status_code == 404:
        return []
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, list):
        return data
    return [data]


def _decode_file(item: dict) -> Optional[str]:
    if item.get("size", 0) > MAX_FILE_SIZE_BYTES:
        return None
    encoding = item.get("encoding", "")
    content = item.get("content", "")
    if encoding == "base64":
        try:
            return base64.b64decode(content).decode("utf-8", errors="replace")
        except Exception:
            return None
    return content


def _parse_frontmatter(content: str) -> dict:
    """Extract YAML frontmatter from a markdown file."""
    import yaml

    if not content.startswith("---"):
        return {}
    end = content.find("\n---", 3)
    if end == -1:
        return {}
    fm_text = content[3:end].strip()
    try:
        return yaml.safe_load(fm_text) or {}
    except Exception:
        return {}


def _is_scannable(filename: str) -> bool:
    return Path(filename).suffix.lower() in SCANNABLE_EXTENSIONS


def _fetch_skill_folder(
    owner: str,
    repo: str,
    folder_path: str,
    ref: str,
    github_url: str,
    commit_sha: str,
    headers: dict,
) -> Optional[SkillData]:
    """Fetch all files from a skill folder and return a SkillData."""
    items = _fetch_contents(owner, repo, folder_path, ref, headers)
    if not items:
        return None

    # Check if SKILL.md exists
    skill_md_item = next(
        (i for i in items if i.get("name", "").upper() == SKILL_MD_FILENAME and i.get("type") == "file"),
        None,
    )
    if skill_md_item is None:
        # Look for any .md file if no SKILL.md
        skill_md_item = next(
            (i for i in items if i.get("name", "").endswith(".md") and i.get("type") == "file"),
            None,
        )
    if skill_md_item is None:
        return None

    skill_md_content = _decode_file(skill_md_item)
    if skill_md_content is None:
        return None

    fm = _parse_frontmatter(skill_md_content)
    name = fm.get("name") or Path(folder_path).name or "unknown"
    description = fm.get("description")

    files: list[SkillFileData] = []
    for item in items:
        if item.get("type") != "file":
            continue
        fname = item.get("name", "")
        if not _is_scannable(fname):
            continue
        content = _decode_file(item)
        if content is None:
            continue
        files.append(SkillFileData(filename=fname, content=content, file_type="text"))

    if not files:
        return None

    return SkillData(
        name=name,
        description=description,
        files=files,
        skill_path=folder_path,
        github_url=github_url,
        commit_sha=commit_sha,
    )


def fetch_from_github(url: str, token: Optional[str] = None) -> list[SkillData]:
    """
    Fetch skill(s) from a GitHub URL.
    Returns a list of SkillData objects (one per skill found).
    """
    parsed = _parse_github_url(url)
    owner = parsed["owner"]
    repo = parsed["repo"]
    branch = parsed["branch"]
    sub_path = parsed["path"]

    headers = _make_headers(token)

    if branch is None:
        branch = _get_default_branch(owner, repo, headers)

    commit_sha = _get_commit_sha(owner, repo, branch, headers)
    github_url = f"https://github.com/{owner}/{repo}"

    # If a specific path was given, treat it as the skill folder directly
    if sub_path:
        skill = _fetch_skill_folder(
            owner, repo, sub_path, branch, github_url, commit_sha, headers
        )
        if skill:
            return [skill]
        # Maybe it's a skills container directory - list sub-folders
        items = _fetch_contents(owner, repo, sub_path, branch, headers)
        skills = []
        for item in items:
            if item.get("type") == "dir":
                s = _fetch_skill_folder(
                    owner, repo, item["path"], branch, github_url, commit_sha, headers
                )
                if s:
                    skills.append(s)
        return skills

    # No path given - look for skills/ or plugins/ directories
    for skill_dir in SKILL_DIRS:
        items = _fetch_contents(owner, repo, skill_dir, branch, headers)
        if items:
            skills = []
            # Check if it's a container of skill folders or a skill folder itself
            sub_dirs = [i for i in items if i.get("type") == "dir"]
            skill_md = next(
                (i for i in items if i.get("name", "").upper() == SKILL_MD_FILENAME),
                None,
            )
            if skill_md:
                # The skills/ dir itself is a single skill
                s = _fetch_skill_folder(
                    owner, repo, skill_dir, branch, github_url, commit_sha, headers
                )
                if s:
                    return [s]
            elif sub_dirs:
                for item in sub_dirs:
                    s = _fetch_skill_folder(
                        owner, repo, item["path"], branch, github_url, commit_sha, headers
                    )
                    if s:
                        skills.append(s)
                if skills:
                    return skills

    # Fall back to root
    skill = _fetch_skill_folder(owner, repo, "", branch, github_url, commit_sha, headers)
    if skill:
        return [skill]

    return []


def fetch_from_local(path: str) -> list[SkillFileData]:
    """
    Walk a local directory and return all scannable text files ≤50KB.
    """
    base = Path(path)
    if base.is_file():
        if _is_scannable(base.name):
            try:
                content = base.read_text(encoding="utf-8", errors="replace")
                return [SkillFileData(filename=base.name, content=content, file_type="text")]
            except Exception:
                return []
        return []

    files: list[SkillFileData] = []
    for fpath in sorted(base.rglob("*")):
        if not fpath.is_file():
            continue
        if not _is_scannable(fpath.name):
            continue
        if fpath.stat().st_size > MAX_FILE_SIZE_BYTES:
            continue
        try:
            content = fpath.read_text(encoding="utf-8", errors="replace")
            rel = str(fpath.relative_to(base))
            files.append(SkillFileData(filename=rel, content=content, file_type="text"))
        except Exception:
            continue
    return files
