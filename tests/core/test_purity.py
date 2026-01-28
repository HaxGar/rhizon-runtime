import os
import ast
import pytest
from pathlib import Path

CORE_DIR = Path(__file__).parent.parent.parent / "src" / "rhizon_runtime" / "core"

def get_python_files(directory: Path):
    return directory.rglob("*.py")

def get_imports(file_path: Path):
    with open(file_path, "r", encoding="utf-8") as f:
        root = ast.parse(f.read(), filename=str(file_path))
    
    imports = set()
    for node in ast.walk(root):
        if isinstance(node, ast.Import):
            for name in node.names:
                imports.add(name.name.split('.')[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module.split('.')[0])
    return imports

def test_no_framework_dependency_in_runtime_core():
    """
    DoD: Core Runtime MUST NOT import framework libraries (maf, langchain, etc).
    """
    forbidden_libs = {"maf", "langchain", "langgraph", "autogen", "crewai"}
    
    core_files = list(get_python_files(CORE_DIR))
    assert len(core_files) > 0, "Core directory should not be empty"
    
    for file_path in core_files:
        imports = get_imports(file_path)
        violations = imports.intersection(forbidden_libs)
        
        assert not violations, f"File {file_path.name} imports forbidden libraries: {violations}"
