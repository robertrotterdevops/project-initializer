#!/usr/bin/env python3
"""
Integration test / usage example for the project-initializer skill.
Actually imports and invokes the real functions rather than printing fake API calls.
"""

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

# Ensure sibling module is importable
sys.path.insert(0, str(Path(__file__).resolve().parent))

from project_analyzer import ProjectAnalyzer, analyze_project
from generate_structure import initialize_project, prepare_template_context


def test_analyze_project():
    """Test keyword detection across all project types."""
    print("=== Test: analyze_project ===\n")

    cases = [
        ("elastic-observability", "Elasticsearch cluster on OpenShift with monitoring", "elasticsearch"),
        ("k8s-platform", "Kubernetes platform with GitOps workflows", "kubernetes"),
        ("terraform-infra", "Terraform infrastructure provisioning for cloud", "terraform"),
        ("azure-network", "Azure AKS networking with Microsoft services", "azure"),
        ("gitops-repo", "FluxCD GitOps platform for multi-cluster kustomize", "gitops"),
    ]

    all_pass = True
    for name, desc, expected_cat in cases:
        result = analyze_project(name, desc)
        detected = result["primary_category"]
        ok = detected == expected_cat
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {name}: expected={expected_cat}, got={detected}")
        if not ok:
            all_pass = False

    print()
    return all_pass


def test_initialize_project():
    """Test full project scaffolding for each type."""
    print("=== Test: initialize_project ===\n")

    cases = [
        ("test-elastic", "Elasticsearch on OpenShift"),
        ("test-k8s", "Kubernetes platform deployment"),
        ("test-tf", "Terraform infrastructure modules"),
        ("test-azure", "Azure AKS cloud platform"),
        ("test-gitops", "FluxCD GitOps kustomization"),
    ]

    all_pass = True
    for name, desc in cases:
        tmpdir = tempfile.mkdtemp(prefix=f"pi-{name}-")
        try:
            result = initialize_project(name, desc, tmpdir)

            # Check README.md exists and has no Jinja2 blocks
            readme_path = os.path.join(tmpdir, "README.md")
            readme_exists = os.path.isfile(readme_path)
            has_jinja = False
            if readme_exists:
                content = Path(readme_path).read_text()
                has_jinja = "{%" in content or "| join" in content

            agents_exists = os.path.isfile(os.path.join(tmpdir, "AGENTS.md"))
            gitignore_exists = os.path.isfile(os.path.join(tmpdir, ".gitignore"))

            ok = readme_exists and agents_exists and gitignore_exists and not has_jinja
            status = "PASS" if ok else "FAIL"
            print(f"  [{status}] {name}: cat={result['primary_category']}, "
                  f"skill={result['primary_skill']}, "
                  f"files={len(result['generated_files'])}, "
                  f"jinja_free={'yes' if not has_jinja else 'NO'}")
            if not ok:
                all_pass = False
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    print()
    return all_pass


def test_json_output():
    """Test that analyze_project returns valid JSON-serialisable data."""
    print("=== Test: JSON serialisation ===\n")

    result = analyze_project("test-json", "Elasticsearch GitOps platform")
    try:
        output = json.dumps(result, indent=2)
        parsed = json.loads(output)
        ok = parsed["project_name"] == "test-json"
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] JSON round-trip successful")
    except (TypeError, json.JSONDecodeError) as exc:
        print(f"  [FAIL] JSON error: {exc}")
        ok = False

    print()
    return ok


def test_no_external_imports():
    """Verify only stdlib modules are used."""
    print("=== Test: stdlib-only imports ===\n")

    scripts_dir = Path(__file__).resolve().parent
    forbidden = {"yaml", "jinja2", "requests", "click", "typer", "pyyaml"}
    violations = []

    for py_file in scripts_dir.glob("*.py"):
        if py_file.name == "usage_example.py":
            continue
        content = py_file.read_text()
        for mod in forbidden:
            if f"import {mod}" in content:
                violations.append(f"{py_file.name}: imports {mod}")

    ok = len(violations) == 0
    status = "PASS" if ok else "FAIL"
    if ok:
        print(f"  [{status}] No forbidden imports found")
    else:
        for v in violations:
            print(f"  [FAIL] {v}")

    print()
    return ok


def main():
    print("Project Initializer -- Integration Tests\n")

    results = [
        test_analyze_project(),
        test_initialize_project(),
        test_json_output(),
        test_no_external_imports(),
    ]

    passed = sum(results)
    total = len(results)
    print(f"Results: {passed}/{total} test groups passed")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
