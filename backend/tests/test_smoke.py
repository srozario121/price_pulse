"""
Scaffolding smoke test — verifies the test suite can be discovered and run.

This test will be replaced by real unit/integration tests once the application
modules are implemented in Items 2–6.
"""


def test_scaffolding_is_in_place() -> None:
    """Verify the repository scaffolding is set up correctly."""
    # Arrange
    import pathlib

    repo_root = pathlib.Path(__file__).parent.parent.parent

    # Act / Assert — key scaffolding files must exist
    assert (repo_root / "pyproject.toml").exists(), "Root pyproject.toml is missing"
    assert (repo_root / "Makefile").exists(), "Makefile is missing"
    assert (repo_root / "docker-compose.yml").exists(), "docker-compose.yml is missing"
    assert (repo_root / ".env.example").exists(), ".env.example is missing"
    assert (repo_root / "README.md").exists(), "README.md is missing"
    assert (repo_root / "CONTRIBUTING.md").exists(), "CONTRIBUTING.md is missing"
    assert (repo_root / "CHANGELOG.md").exists(), "CHANGELOG.md is missing"
    assert (repo_root / "LICENSE").exists(), "LICENSE is missing"
    assert (repo_root / ".pre-commit-config.yaml").exists(), ".pre-commit-config.yaml is missing"
    assert (repo_root / ".github" / "workflows" / "ci.yml").exists(), "ci.yml is missing"
