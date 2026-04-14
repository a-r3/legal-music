# Contributing

Thank you for your interest in contributing to **legal-music**!

## Reporting issues

If you find a bug or have a feature request:

1. Check [existing issues](https://github.com/your-org/legal-music/issues) first
2. If not reported, [open a new issue](https://github.com/your-org/legal-music/issues/new) with:
   - Clear description of the problem
   - Steps to reproduce (for bugs)
   - Expected vs. actual behavior
   - Your OS and Python version

## Making changes

### Setup

```bash
# Clone the repository
git clone https://github.com/your-org/legal-music.git
cd legal-music

# Install in editable mode with dev dependencies
pip install -e ".[dev]"
```

### Code quality

Before submitting:

```bash
# Format your code
ruff format .

# Check for linting issues
ruff check .

# Run tests
pytest

# Full check (recommended)
make check
```

### Submitting a PR

1. Fork the repository
2. Create a feature branch: `git checkout -b fix/my-fix` or `git checkout -b feature/my-feature`
3. Make your changes
4. Run `make check` to ensure code quality
5. Commit with clear message: `git commit -m "Fix: description"` or `git commit -m "Feature: description"`
6. Push to your fork
7. Open a pull request with:
   - Clear title and description
   - Reference to any related issues
   - Confirmation that tests pass

## Legal boundary

**This project is strictly legal-only.** Please ensure any contributions:

- ✅ Support only **legal, permitted, openly downloadable sources**
- ❌ Do NOT add piracy support
- ❌ Do NOT add DRM bypass capabilities
- ❌ Do NOT add unauthorized stream ripping (Spotify, Apple Music, YouTube Music, etc.)
- ❌ Do NOT add credential harvesting or account spoofing

If you're unsure whether a source is legal, please open an issue for discussion before implementing.

## Code style

- Use Python 3.10+ features
- Follow PEP 8
- Ruff will format and check automatically
- Keep functions focused and testable
- Add docstrings for public functions

## Documentation

- Update README.md if adding features or changing behavior
- Update CHANGELOG.md with notable changes
- Keep comments minimal (code should be self-documenting)
- Add test docstrings explaining what's being tested

## Questions?

Feel free to open an issue with the label `question` if you need clarification.

---

Thank you for helping make legal-music better! 🎵
