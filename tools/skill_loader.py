"""
Skill loader — loads agent skill files at runtime.
Skills define HOW each agent does its job.
Loaded before every analysis run to ensure consistency.
"""

from pathlib import Path
import logging

logger = logging.getLogger(__name__)

SKILLS_DIR = Path(__file__).parent.parent / "skills"

REQUIRED_SKILLS = [
    "world_intelligence",
    "causal_reasoning",
    "sentiment",
    "narrative_cycle",
    "screener",
    "market_analysis",
    "news_analysis",
    "fundamentals_analysis",
    "geo_analysis",
    "ranking",
]


def load_skill(skill_name: str) -> str:
    """
    Load a skill file by name.
    Returns full content as string.
    Raises FileNotFoundError if skill does not exist.

    Usage:
        skill = load_skill("causal_reasoning")
        prompt = f"{skill}\n\nNOW APPLY TO:\n{data}"
    """
    skill_path = SKILLS_DIR / f"{skill_name}.md"

    if not skill_path.exists():
        raise FileNotFoundError(
            f"Skill file not found: {skill_path}\n"
            f"Available skills: {list_skills()}"
        )

    content = skill_path.read_text(encoding="utf-8")
    logger.debug(f"Loaded skill: {skill_name} ({len(content)} chars)")
    return content


def list_skills() -> list[str]:
    """List all available skill names."""
    if not SKILLS_DIR.exists():
        return []
    return [f.stem for f in SKILLS_DIR.glob("*.md")]


def validate_skill_exists(skill_name: str) -> bool:
    """Check if a skill file exists."""
    return (SKILLS_DIR / f"{skill_name}.md").exists()


def load_all_skills() -> dict[str, str]:
    """Load all skill files. Returns dict of name -> content."""
    return {skill: load_skill(skill) for skill in list_skills()}


def validate_all_skills() -> None:
    """Raise RuntimeError if any required skill file is missing."""
    missing = [s for s in REQUIRED_SKILLS if not validate_skill_exists(s)]
    if missing:
        raise RuntimeError(
            f"Missing skill files: {missing}\n"
            f"Create them in skills/ folder before running."
        )
    print(f"✓ All {len(REQUIRED_SKILLS)} skill files loaded")
