"""Where the publish-viz skill lives, and how `viz install-skill` copies it to
the folder Claude Code reads personal skills from."""
import shutil
from pathlib import Path

SKILL_NAME = "publish-viz"

# An installed wheel carries the skill at viz/_skills/publish-viz (see
# pyproject.toml); a source checkout has it at skills/publish-viz.
_CANDIDATE_DIRS = (
    Path(__file__).resolve().parents[1] / "_skills" / SKILL_NAME,
    Path(__file__).resolve().parents[2] / "skills" / SKILL_NAME,
)


class SkillExists(FileExistsError):
    pass


class UnsafeTarget(ValueError):
    pass


def skill_source() -> Path:
    for directory in _CANDIDATE_DIRS:
        if (directory / "SKILL.md").is_file():
            return directory
    raise FileNotFoundError("the publish-viz skill files are not packaged with this install")


def default_destination() -> Path:
    return Path.home() / ".claude" / "skills"


def install_skill(dest_root: Path, force: bool = False) -> Path:
    source = skill_source()
    target = Path(dest_root) / SKILL_NAME

    if target.exists() and (target.is_symlink() or not target.is_dir()):
        raise UnsafeTarget(f"{target} exists and is not a plain directory; refusing to touch it")

    resolved_source = source.resolve()
    resolved_target = target.resolve()
    if (
        resolved_source == resolved_target
        or resolved_source.is_relative_to(resolved_target)
        or resolved_target.is_relative_to(resolved_source)
    ):
        raise UnsafeTarget(f"{target} is the skill source itself; refusing to install onto it")

    if target.exists():
        if not force:
            raise SkillExists(f"{target} already exists; ask the user before passing --force to replace it")
        shutil.rmtree(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target)
    return target
