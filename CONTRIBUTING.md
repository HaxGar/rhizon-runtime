# Contributing to Rhizon Runtime

Thank you for your interest in contributing to Rhizon Runtime! This document provides guidelines and information for contributors.

## 🚀 Quick Start

### Prerequisites
- Python 3.11 or higher
- Poetry (recommended) or pip
- Docker (for integration tests)

### Development Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/rhizon/rhizon-runtime.git
   cd rhizon-runtime
   ```

2. **Set up the development environment**
   ```bash
   # Using Poetry (recommended)
   poetry install
   
   # Or using pip
   pip install -e .
   pip install -e ".[test]"
   ```

3. **Run tests**
   ```bash
   poetry run pytest
   # or
   pytest
   ```

## 📋 Development Guidelines

### Code Style
- Follow PEP 8 style guidelines
- Use type hints for all public functions and methods
- Write comprehensive docstrings
- Keep functions focused and small

### Testing
- Write unit tests for all new functionality
- Maintain test coverage above 90%
- Integration tests should use Docker containers
- All tests must pass before merging

### Commit Messages
- Use conventional commit format:
  - `feat:` for new features
  - `fix:` for bug fixes
  - `docs:` for documentation
  - `test:` for test-related changes
  - `refactor:` for code refactoring

Example: `feat: add optimistic concurrency control to runtime engine`

## 🏗️ Architecture Overview

MeshForge Runtime follows a strict separation between core and adapters:

### Core (`src/meshforge_runtime/core/`)
- **RuntimeEngine**: Main orchestration loop
- **Models**: EventEnvelope and core data structures
- **Interfaces**: Protocol definitions for adapters
- **Invariants**: Determinism, idempotency, isolation guarantees

### Adapters (`src/meshforge_runtime/adapters/`)
- **NATS JetStream**: Event bus and routing
- **SQLite**: Event store implementation
- **LockManager**: Cooperative locking system

## 🔄 Development Workflow

### 1. Create an Issue
- Describe the feature or bug fix
- Include relevant context and examples
- Tag with appropriate labels

### 2. Create a Branch
```bash
git checkout -b feature/your-feature-name
```

### 3. Implement Changes
- Write code following guidelines
- Add comprehensive tests
- Update documentation

### 4. Submit Pull Request
- Ensure all tests pass
- Update CHANGELOG.md
- Request review from maintainers

## 🧪 Testing Strategy

### Unit Tests
- Test individual components in isolation
- Mock external dependencies
- Focus on business logic

### Integration Tests
- Test component interactions
- Use real infrastructure (NATS, SQLite)
- Validate end-to-end scenarios

### Property-Based Tests
- Test invariants and guarantees
- Verify deterministic behavior
- Validate edge cases

## 📚 Documentation

### Code Documentation
- All public APIs must have docstrings
- Include examples in docstrings
- Document parameters and return types

### README Updates
- Update installation instructions
- Add new feature descriptions
- Include usage examples

### Architecture Documentation
- Update docs/ directory with design decisions
- Include invariants and guarantees
- Document trade-offs and alternatives

## 🚀 Release Process

### Version Management
- Follow semantic versioning
- Update version in pyproject.toml
- Tag releases in Git

### Release Checklist
- [ ] All tests pass
- [ ] Documentation updated
- [ ] CHANGELOG.md updated
- [ ] Version bumped
- [ ] Git tag created
- [ ] GitHub release published

## 🤝 Community Guidelines

### Code of Conduct
- Be respectful and inclusive
- Welcome newcomers and help them learn
- Focus on constructive feedback
- Maintain professional communication

### Getting Help
- Open an issue for questions
- Check documentation first
- Search existing issues
- Use GitHub Discussions for community support

## 📄 License

By contributing to Rhizon Runtime, you agree that your contributions will be licensed under the Apache License 2.0.

## 🏆 Recognition

Contributors are recognized in:
- README.md contributors section
- GitHub release notes
- Annual community highlights

Thank you for contributing to Rhizon Runtime! 🎉
