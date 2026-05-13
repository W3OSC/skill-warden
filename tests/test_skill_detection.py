"""Unit tests for skill detection logic (fetcher + local scanner)."""

import base64
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from skill_warden.fetcher import _fetch_skill_folder, _parse_frontmatter, _is_scannable
from skill_warden.scanner import (
    _detect_skill_dirs,
    _find_nested_skill_dirs,
    _has_skill_md,
    _validate_local_skill_md,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _b64(text: str) -> str:
    return base64.b64encode(text.encode()).decode() + "\n"


def _make_item(name: str, content: str, item_type: str = "file") -> dict:
    return {
        "name": name,
        "type": item_type,
        "encoding": "base64",
        "content": _b64(content),
        "size": len(content),
    }


VALID_SKILL_MD = "---\nname: my-skill\ndescription: Does useful things.\n---\n\n# My Skill\n"


def _call_fetch(items: list[dict], folder_path: str = "skills/my-skill") -> object:
    """Call _fetch_skill_folder with mocked _fetch_contents."""
    with patch("skill_warden.fetcher._fetch_contents", return_value=items):
        return _fetch_skill_folder(
            owner="org",
            repo="repo",
            folder_path=folder_path,
            ref="main",
            github_url="https://github.com/org/repo",
            commit_sha="abc123",
            headers={},
        )


# ---------------------------------------------------------------------------
# _parse_frontmatter
# ---------------------------------------------------------------------------

class TestParseFrontmatter:
    def test_valid(self):
        fm = _parse_frontmatter("---\nname: foo\ndescription: bar\n---\n# body")
        assert fm["name"] == "foo"
        assert fm["description"] == "bar"

    def test_no_frontmatter(self):
        assert _parse_frontmatter("# Just a heading") == {}

    def test_missing_closing_fence(self):
        assert _parse_frontmatter("---\nname: foo\n") == {}

    def test_empty_frontmatter(self):
        fm = _parse_frontmatter("---\n---\n# body")
        assert fm == {}


# ---------------------------------------------------------------------------
# _is_scannable
# ---------------------------------------------------------------------------

class TestIsScannable:
    @pytest.mark.parametrize("fname", ["SKILL.md", "program.md", "helper.txt", "script.sh", "config.yaml", "config.yml", "data.json", "code.py"])
    def test_accepted_extensions(self, fname):
        assert _is_scannable(fname) is True

    @pytest.mark.parametrize("fname", ["image.png", "binary.exe", "archive.zip", "code.sol", "README"])
    def test_rejected_extensions(self, fname):
        assert _is_scannable(fname) is False


# ---------------------------------------------------------------------------
# _fetch_skill_folder - GitHub detection
# ---------------------------------------------------------------------------

class TestFetchSkillFolderGitHub:
    def test_valid_skill_md(self):
        items = [_make_item("SKILL.md", VALID_SKILL_MD)]
        result = _call_fetch(items)
        assert result is not None
        assert result.name == "my-skill"
        assert result.description == "Does useful things."

    def test_case_sensitive_skill_md_rejected(self):
        """skill.md / Skill.MD must not match."""
        for wrong_case in ("skill.md", "Skill.MD", "SKILL.MD"):
            items = [_make_item(wrong_case, VALID_SKILL_MD)]
            assert _call_fetch(items) is None, f"{wrong_case} should be rejected"

    def test_fallback_program_md(self):
        """program.md is accepted when no SKILL.md present."""
        content = "---\nname: my-skill\ndescription: Uses program.md.\n---\n\n# Skill\n"
        items = [_make_item("program.md", content)]
        result = _call_fetch(items)
        assert result is not None
        assert result.name == "my-skill"

    def test_arbitrary_md_not_accepted_as_fallback(self):
        """README.md or other .md files must not trigger skill detection."""
        items = [_make_item("README.md", VALID_SKILL_MD)]
        assert _call_fetch(items) is None

    def test_missing_name_in_frontmatter_rejected(self):
        content = "---\ndescription: No name field.\n---\n\n# Skill\n"
        items = [_make_item("SKILL.md", content)]
        assert _call_fetch(items) is None

    def test_missing_description_in_frontmatter_rejected(self):
        content = "---\nname: my-skill\n---\n\n# Skill\n"
        items = [_make_item("SKILL.md", content)]
        assert _call_fetch(items) is None

    def test_no_frontmatter_rejected(self):
        items = [_make_item("SKILL.md", "# Just a heading, no frontmatter\n")]
        assert _call_fetch(items) is None

    def test_name_mismatch_dir_rejected(self):
        """YAML name must match directory name."""
        content = "---\nname: different-name\ndescription: Mismatch.\n---\n\n# Skill\n"
        items = [_make_item("SKILL.md", content)]
        assert _call_fetch(items, folder_path="skills/my-skill") is None

    def test_name_matches_dir_accepted(self):
        result = _call_fetch([_make_item("SKILL.md", VALID_SKILL_MD)], folder_path="skills/my-skill")
        assert result is not None

    def test_empty_folder_rejected(self):
        assert _call_fetch([]) is None

    def test_no_md_file_rejected(self):
        items = [_make_item("script.sh", "#!/bin/bash\necho hi\n")]
        assert _call_fetch(items) is None

    def test_skill_md_at_root_no_dir_name_check(self):
        """Scanning root (folder_path='') skips dir-name match check."""
        content = "---\nname: anything\ndescription: Root skill.\n---\n\n# Skill\n"
        items = [_make_item("SKILL.md", content)]
        result = _call_fetch(items, folder_path="")
        assert result is not None

    def test_non_scannable_files_excluded(self):
        items = [
            _make_item("SKILL.md", VALID_SKILL_MD),
            _make_item("image.png", "binarydata"),
            _make_item("notes.py", "# code"),
        ]
        result = _call_fetch(items)
        assert result is not None
        fnames = [f.filename for f in result.files]
        assert "skills/my-skill/image.png" not in fnames
        assert "skills/my-skill/notes.py" in fnames

    def test_filenames_are_repo_relative(self):
        """SkillFileData filenames must include the folder path for correct SARIF artifact URIs."""
        items = [_make_item("SKILL.md", VALID_SKILL_MD)]
        result = _call_fetch(items, folder_path="skills/my-skill")
        assert result is not None
        assert result.files[0].filename == "skills/my-skill/SKILL.md"

    def test_filenames_root_folder_no_prefix(self):
        """When scanning the repo root (folder_path=''), filename is just the bare name."""
        content = "---\nname: anything\ndescription: Root skill.\n---\n\n# Skill\n"
        items = [_make_item("SKILL.md", content)]
        result = _call_fetch(items, folder_path="")
        assert result is not None
        assert result.files[0].filename == "SKILL.md"

    def test_subdirs_ignored(self):
        items = [
            _make_item("SKILL.md", VALID_SKILL_MD),
            {"name": "subdir", "type": "dir"},
        ]
        result = _call_fetch(items)
        assert result is not None


# ---------------------------------------------------------------------------
# Local detection helpers
# ---------------------------------------------------------------------------

class TestLocalSkillDetection:
    def _make_skill_dir(self, tmp: Path, dir_name: str, skill_md_content: str) -> Path:
        d = tmp / dir_name
        d.mkdir()
        (d / "SKILL.md").write_text(skill_md_content)
        return d

    def test_has_skill_md_true(self, tmp_path):
        d = tmp_path / "my-skill"
        d.mkdir()
        (d / "SKILL.md").write_text(VALID_SKILL_MD)
        assert _has_skill_md(d) is True

    def test_has_skill_md_false_wrong_case(self, tmp_path):
        d = tmp_path / "my-skill"
        d.mkdir()
        (d / "skill.md").write_text(VALID_SKILL_MD)
        assert _has_skill_md(d) is False

    def test_has_skill_md_false_no_file(self, tmp_path):
        d = tmp_path / "my-skill"
        d.mkdir()
        assert _has_skill_md(d) is False

    def test_validate_valid_skill(self, tmp_path):
        d = self._make_skill_dir(tmp_path, "my-skill", VALID_SKILL_MD)
        assert _validate_local_skill_md(d) == "my-skill"

    def test_validate_missing_description(self, tmp_path):
        content = "---\nname: my-skill\n---\n\n# Skill\n"
        d = self._make_skill_dir(tmp_path, "my-skill", content)
        assert _validate_local_skill_md(d) is None

    def test_validate_missing_name(self, tmp_path):
        content = "---\ndescription: Some skill.\n---\n\n# Skill\n"
        d = self._make_skill_dir(tmp_path, "my-skill", content)
        assert _validate_local_skill_md(d) is None

    def test_validate_name_mismatch(self, tmp_path):
        content = "---\nname: wrong-name\ndescription: Some skill.\n---\n\n# Skill\n"
        d = self._make_skill_dir(tmp_path, "my-skill", content)
        assert _validate_local_skill_md(d) is None

    def test_validate_no_skill_md(self, tmp_path):
        d = tmp_path / "my-skill"
        d.mkdir()
        assert _validate_local_skill_md(d) is None

    def test_detect_base_has_skill_md(self, tmp_path):
        d = tmp_path / "my-skill"
        d.mkdir()
        (d / "SKILL.md").write_text(VALID_SKILL_MD)
        assert _detect_skill_dirs(d) == [d]

    def test_detect_subdirs_with_skill_md(self, tmp_path):
        s1 = self._make_skill_dir(tmp_path, "skill-a", "---\nname: skill-a\ndescription: A.\n---\n")
        s2 = self._make_skill_dir(tmp_path, "skill-b", "---\nname: skill-b\ndescription: B.\n---\n")
        result = _detect_skill_dirs(tmp_path)
        assert set(result) == {s1, s2}

    def test_detect_fallback_no_skill_md_anywhere(self, tmp_path):
        """No SKILL.md anywhere → fall back to base dir."""
        assert _detect_skill_dirs(tmp_path) == [tmp_path]

    def test_detect_single_file_path(self, tmp_path):
        f = tmp_path / "SKILL.md"
        f.write_text(VALID_SKILL_MD)
        assert _detect_skill_dirs(f) == [f]


# ---------------------------------------------------------------------------
# _find_nested_skills - */skills/ pattern
# ---------------------------------------------------------------------------

class TestFindNestedSkillsGitHub:
    """Tests for the */skills/ discovery (e.g. .claude/skills/, src/skills/)."""

    def _make_dir_item(self, name: str, path: str) -> dict:
        return {"name": name, "path": path, "type": "dir"}

    def _make_file_item(self, name: str, content: str) -> dict:
        return {
            "name": name,
            "path": name,
            "type": "file",
            "encoding": "base64",
            "content": base64.b64encode(content.encode()).decode() + "\n",
            "size": len(content),
        }

    def test_finds_skills_in_nested_dir(self):
        """Repo with .claude/skills/my-skill/SKILL.md should be found."""
        from skill_warden.fetcher import _find_nested_skills

        skill_content = "---\nname: my-skill\ndescription: Does things.\n---\n\n# My Skill\n"

        def mock_fetch_contents(owner, repo, path, ref, headers):
            if path == "":
                return [self._make_dir_item(".claude", ".claude")]
            if path == ".claude/skills":
                return [self._make_dir_item("my-skill", ".claude/skills/my-skill")]
            if path == ".claude/skills/my-skill":
                return [self._make_file_item("SKILL.md", skill_content)]
            return []

        with patch("skill_warden.fetcher._fetch_contents", side_effect=mock_fetch_contents):
            skills = _find_nested_skills("org", "repo", "main", "https://github.com/org/repo", "abc", {})

        assert len(skills) == 1
        assert skills[0].name == "my-skill"
        assert skills[0].skill_path == ".claude/skills/my-skill"

    def test_multiple_nested_skills(self):
        """Multiple skill folders under a nested skills/ directory all returned."""
        from skill_warden.fetcher import _find_nested_skills

        def _skill_md(name: str) -> str:
            return f"---\nname: {name}\ndescription: Does things.\n---\n\n# {name}\n"

        def mock_fetch_contents(owner, repo, path, ref, headers):
            if path == "":
                return [self._make_dir_item("custom", "custom")]
            if path == "custom/skills":
                return [
                    self._make_dir_item("skill-a", "custom/skills/skill-a"),
                    self._make_dir_item("skill-b", "custom/skills/skill-b"),
                ]
            if path == "custom/skills/skill-a":
                return [self._make_file_item("SKILL.md", _skill_md("skill-a"))]
            if path == "custom/skills/skill-b":
                return [self._make_file_item("SKILL.md", _skill_md("skill-b"))]
            return []

        with patch("skill_warden.fetcher._fetch_contents", side_effect=mock_fetch_contents):
            skills = _find_nested_skills("org", "repo", "main", "https://github.com/org/repo", "abc", {})

        assert {s.name for s in skills} == {"skill-a", "skill-b"}

    def test_no_nested_skills_dir_returns_empty(self):
        """Root dirs without a skills/ subdir yield nothing."""
        from skill_warden.fetcher import _find_nested_skills

        def mock_fetch_contents(owner, repo, path, ref, headers):
            if path == "":
                return [self._make_dir_item("src", "src")]
            return []

        with patch("skill_warden.fetcher._fetch_contents", side_effect=mock_fetch_contents):
            skills = _find_nested_skills("org", "repo", "main", "https://github.com/org/repo", "abc", {})

        assert skills == []


# ---------------------------------------------------------------------------
# program.md fallback - local scanner
# ---------------------------------------------------------------------------

class TestProgramMdFallback:
    def test_has_skill_md_true_for_program_md(self, tmp_path):
        d = tmp_path / "my-skill"
        d.mkdir()
        (d / "program.md").write_text("---\nname: my-skill\ndescription: Does things.\n---\n")
        assert _has_skill_md(d) is True

    def test_validate_accepts_program_md(self, tmp_path):
        d = tmp_path / "my-skill"
        d.mkdir()
        (d / "program.md").write_text("---\nname: my-skill\ndescription: Does things.\n---\n")
        assert _validate_local_skill_md(d) == "my-skill"

    def test_skill_md_preferred_over_program_md(self, tmp_path):
        d = tmp_path / "my-skill"
        d.mkdir()
        (d / "SKILL.md").write_text("---\nname: my-skill\ndescription: From SKILL.md.\n---\n")
        (d / "program.md").write_text("---\nname: wrong\ndescription: Should be ignored.\n---\n")
        assert _validate_local_skill_md(d) == "my-skill"


# ---------------------------------------------------------------------------
# */skills/ nested discovery - local scanner
# ---------------------------------------------------------------------------

class TestLocalNestedSkillDirs:
    def test_finds_nested_skills_dir(self, tmp_path):
        d = tmp_path / ".claude" / "skills" / "my-skill"
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text("---\nname: my-skill\ndescription: Does things.\n---\n")
        result = _find_nested_skill_dirs(tmp_path)
        assert result == [d]

    def test_multiple_nested_skills(self, tmp_path):
        for name in ("skill-a", "skill-b"):
            d = tmp_path / "src" / "skills" / name
            d.mkdir(parents=True)
            (d / "SKILL.md").write_text(f"---\nname: {name}\ndescription: Does things.\n---\n")
        result = _find_nested_skill_dirs(tmp_path)
        assert {p.name for p in result} == {"skill-a", "skill-b"}

    def test_no_nested_returns_empty(self, tmp_path):
        (tmp_path / "src").mkdir()
        assert _find_nested_skill_dirs(tmp_path) == []

    def test_detect_skill_dirs_falls_through_to_nested(self, tmp_path):
        d = tmp_path / ".claude" / "skills" / "my-skill"
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text("---\nname: my-skill\ndescription: Does things.\n---\n")
        assert _detect_skill_dirs(tmp_path) == [d]


# ---------------------------------------------------------------------------
# Fetcher - case-sensitive SKILL.md check in skills/ container
# ---------------------------------------------------------------------------

class TestFetcherSkillDirCaseSensitive:
    def test_skill_md_in_skills_dir_detected(self):
        """skills/ dir containing SKILL.md should be treated as a single skill, not a container."""
        from skill_warden.fetcher import fetch_from_github

        skill_content = "---\nname: skills\ndescription: A skill.\n---\n\n# Skill\n"

        def mock_fetch_contents(owner, repo, path, ref, headers):
            if path == "skills":
                return [{"name": "SKILL.md", "type": "file", "encoding": "base64",
                          "content": base64.b64encode(skill_content.encode()).decode() + "\n",
                          "size": len(skill_content)}]
            return []

        with patch("skill_warden.fetcher._fetch_contents", side_effect=mock_fetch_contents), \
             patch("skill_warden.fetcher._get_default_branch", return_value="main"), \
             patch("skill_warden.fetcher._get_commit_sha", return_value="abc123"):
            results = fetch_from_github("org/repo")

        assert len(results) == 1
        assert results[0].name == "skills"
