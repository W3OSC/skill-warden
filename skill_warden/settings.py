"""Constants and path settings for skill-warden."""

from pathlib import Path

PACKAGE_DIR = Path(__file__).parent
TEMPLATES_DIR = PACKAGE_DIR / "templates"
STATIC_DIR = PACKAGE_DIR.parent / "static"

MAX_FILE_SIZE_BYTES = 50 * 1024  # 50 KB

GITHUB_API_BASE = "https://api.github.com"
GITHUB_RAW_BASE = "https://raw.githubusercontent.com"

SCANNABLE_EXTENSIONS = {".md", ".txt", ".sh", ".py", ".json", ".yaml", ".yml"}

SKILL_MD_FILENAME = "SKILL.md"
SKILL_DIRS = ["skills", "plugins"]

VERSION = "1.0.0"

SARIF_SCHEMA = (
    "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master"
    "/Documents/CommitteeSpecifications/2.1.0/sarif-schema-2.1.0.json"
)

SEVERITY_TO_SARIF_LEVEL = {
    "critical": "error",
    "high": "error",
    "medium": "warning",
    "low": "note",
    "info": "note",
}
