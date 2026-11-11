"""Offline contract validation for the packet-first review workflow.

This module parses the checked-in reviewer and orchestrator definitions
(frontmatter plus body) and returns deterministic violation codes for the
contract introduced in commit 681b80c7 ("reviewer: make review packet-first
and shell-free"). It also computes the content identity used by the prepared
reviewer fixtures.

Nothing here launches a model, subprocess, network request or shell command.
The checks are static: they prove that the definition *states* the contract,
not that a live agent follows it. See reviewer-packet-v1/README.md.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import re
from pathlib import Path

VERDICTS = ("PASS", "CHANGES_REQUIRED", "NEEDS_CONTEXT")
IGNORED_PARTS = {"__pycache__", ".git"}
IGNORED_SUFFIXES = {".pyc"}

_NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}

# Required review-packet concepts. Each entry is (concept, pattern). The
# patterns are tolerant of rewording; they assert a concept is stated, not
# that the prose is byte-identical.
PACKET_CONCEPTS = (
    (
        "revision",
        r"(?i)immutable\s+(?:reviewed\s+|content\s+)?"
        r"(?:commit|revision|snapshot|content\s+identity)",
    ),
    ("scope", r"(?i)exact\s+(?:changed\s+)?scope"),
    ("diff", r"(?i)\bdiff\b"),
    ("acceptance_criteria", r"(?i)acceptance\s+criteria"),
    ("implementation_result", r"(?i)implementation\s+result"),
    ("validation", r"(?i)validation"),
    ("limitations", r"(?i)known\s+limitations"),
)


def split_frontmatter(text: str) -> tuple[dict, str]:
    """Split a Markdown agent definition into (frontmatter, body)."""
    if not text.startswith("---\n"):
        raise ValueError("missing opening frontmatter fence")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise ValueError("missing closing frontmatter fence")
    raw = text[4:end]
    body = text[end + len("\n---\n") :]
    document = _load_simple_yaml(raw)
    if not isinstance(document, dict):
        raise ValueError("frontmatter is not a mapping")
    return document, body


def _scalar(value: str):
    value = value.strip()
    if value.startswith('"') and value.endswith('"') and len(value) >= 2:
        return value[1:-1]
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    return value


def _load_simple_yaml(raw: str):
    """Parse the restricted frontmatter shape used by agent definitions.

    Supports ``key: scalar`` and one level of ``- key: scalar`` list entries.
    Deliberately avoids a YAML dependency so the validator stays offline and
    pinned; an unexpected shape raises instead of silently passing.
    """
    document: dict = {}
    current_list: list | None = None
    current_item: dict | None = None
    for line in raw.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.startswith("  - "):
            if current_list is None:
                raise ValueError("list item without a parent key")
            key, _, value = line[len("  - ") :].partition(":")
            current_item = {key.strip(): _scalar(value)}
            current_list.append(current_item)
            continue
        if line.startswith("    ") and current_item is not None:
            key, _, value = line.strip().partition(":")
            current_item[key.strip()] = _scalar(value)
            continue
        if line.startswith(" "):
            raise ValueError(f"unsupported frontmatter indentation: {line!r}")
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if not value:
            current_list = []
            document[key] = current_list
            current_item = None
        else:
            document[key] = _scalar(value)
            current_list = None
            current_item = None
    return document


def _permissions(document: dict) -> list[dict]:
    permissions = document.get("permissions")
    if permissions is None:
        return []
    if not isinstance(permissions, list):
        raise ValueError("permissions is not a list")
    for entry in permissions:
        if not isinstance(entry, dict):
            raise ValueError("permission entry is not a mapping")
        missing = {"action", "resource", "effect"} - set(entry)
        if missing:
            raise ValueError(f"permission entry missing {sorted(missing)}")
    return permissions


def _matches(value: str, pattern: str) -> bool:
    """Glob match for permission action/resource patterns."""
    return fnmatch.fnmatchcase(value, pattern)


def _resource_probe(pattern: str) -> str:
    """Concrete resource name a permission pattern can match."""
    return pattern.replace("*", "probe").replace("?", "p")


def shell_permission_violations(permissions: list[dict]) -> list[str]:
    """Return shell access violations under ordered permission semantics.

    A reviewer/orchestrator definition only denies shell safely when a rule
    denies action ``shell`` for the universal resource ``"*"``. Because
    permission rules are evaluated in order with the last match winning, an
    earlier allow overridden by a later universal deny is harmless; an allow
    that survives the ordering (including a wildcard action such as ``*`` or an
    action glob such as ``she*``) is effective shell access and a violation.
    Allows for unrelated actions are ignored rather than forbidden.
    """
    shell_rules = [
        entry for entry in permissions if _matches("shell", str(entry["action"]))
    ]
    violations: list[str] = []
    if not any(
        entry["effect"] == "deny" and entry["resource"] == "*"
        for entry in shell_rules
    ):
        violations.append("shell_not_denied")

    probes = {"probe-command"}
    probes.update(_resource_probe(str(entry["resource"])) for entry in shell_rules)
    for probe in sorted(probes):
        applicable = [
            entry for entry in shell_rules if _matches(probe, str(entry["resource"]))
        ]
        if applicable and applicable[-1]["effect"] != "deny":
            violations.append("shell_allow")
            break
    return violations


def reviewer_violations(document: dict, body: str) -> list[str]:
    """Return contract violation codes for the reviewer definition."""
    violations: list[str] = []
    text = body
    permissions = _permissions(document)

    if document.get("mode") != "subagent":
        violations.append("mode_not_subagent")

    steps = document.get("steps")
    if not isinstance(steps, int) or steps <= 0:
        violations.append("steps_missing")
    elif steps > 12:
        violations.append("steps_above_12")

    violations.extend(shell_permission_violations(permissions))
    for action in ("edit", "subagent"):
        entries = [entry for entry in permissions if entry["action"] == action]
        if not entries:
            violations.append(f"{action}_not_denied")
        for entry in entries:
            if entry["effect"] != "deny":
                violations.append(f"{action}_allow")

    if "qodo" in text.lower() or "qodo" in json.dumps(document).lower():
        violations.append("qodo_present")

    description = str(document.get("description", ""))
    if "read-only" not in description.lower():
        violations.append("description_not_read_only")
    if "no shell" not in description.lower():
        violations.append("description_no_shell_missing")

    if not re.search(r"(?i)run no shell commands", text):
        violations.append("shell_prohibition_missing")
    if not re.search(r"(?i)web or network research", text):
        violations.append("research_prohibition_missing")
    if not re.search(r"(?i)never retry a denied action", text):
        violations.append("retry_prohibition_missing")
    if not re.search(r"(?i)\breview once\b", text):
        violations.append("one_pass_missing")
    if not re.search(r"unsupported `PASS`", text):
        violations.append("unsupported_pass_rule_missing")
    if not re.search(r"(?i)return `NEEDS_CONTEXT`", text):
        violations.append("needs_context_rule_missing")

    budget = re.search(
        r"(?i)budget of (\w+)\s+additional\s+context\s+lookups", text
    )
    if not budget:
        violations.append("lookup_budget_missing")
    else:
        limit = _NUMBER_WORDS.get(budget.group(1).lower())
        if limit is None:
            violations.append("lookup_budget_unparsed")
        elif limit > 4:
            violations.append("lookup_budget_above_4")

    for concept, pattern in PACKET_CONCEPTS:
        if not re.search(pattern, text):
            violations.append(f"packet_field_missing:{concept}")

    for verdict in VERDICTS:
        if f"`{verdict}`" not in text:
            violations.append(f"verdict_missing:{verdict}")
    for foreign in ("APPROVED", "BLOCKED", "REJECTED", "LGTM", "REQUEST_CHANGES"):
        if f"`{foreign}`" in text:
            violations.append(f"foreign_verdict:{foreign}")

    return violations


def orchestrator_violations(document: dict, body: str) -> list[str]:
    """Return contract violation codes for the orchestrator definition."""
    violations: list[str] = []
    permissions = _permissions(document)

    if not re.search(r"(?i)not every small change needs one", body):
        violations.append("automatic_review_implied")
    if not re.search(
        r"(?i)request a missing\s+diff\s+or\s+revision\s+from\s+`@worker`", body
    ):
        violations.append("worker_artifact_request_missing")
    if not re.search(
        r"(?i)rather than asking the\s+reviewer\s+to\s+reconstruct", body
    ):
        violations.append("reviewer_reconstruction_rule_missing")
    if not re.search(r"(?i)reviewer runs no shell commands, tests, or research", body):
        violations.append("reviewer_limits_restated_missing")
    if not re.search(r"(?i)immutable content revision", body):
        violations.append("immutable_review_keying_missing")
    if not re.search(r"(?i)second review of unchanged relevant content", body):
        violations.append("unchanged_review_reuse_missing")

    for concept, pattern in PACKET_CONCEPTS:
        if not re.search(pattern, body):
            violations.append(f"packet_field_missing:{concept}")

    reviewer_allow = [
        entry
        for entry in permissions
        if entry["action"] == "subagent"
        and entry["resource"] == "reviewer"
        and entry["effect"] == "allow"
    ]
    if not reviewer_allow:
        violations.append("reviewer_subagent_not_allowed")

    shell_issues = shell_permission_violations(permissions)
    if "shell_not_denied" in shell_issues:
        violations.append("orchestrator_shell_not_denied")
    if "shell_allow" in shell_issues:
        violations.append("orchestrator_shell_allow")

    if "qodo" in json.dumps(document).lower():
        violations.append("qodo_present")

    return violations


def content_identity(scope_root: Path) -> str:
    """Deterministic content identity for a fixture's reviewed revision.

    The identity is the SHA-256 of a canonical ``{relative path: sha256}``
    manifest of the fixed fixture bytes. It is a content identity, not Git
    provenance: no commit, author, timestamp or machine state is implied.
    """
    scope_root = Path(scope_root)
    manifest: dict[str, str] = {}
    for path in sorted(scope_root.rglob("*")):
        if not path.is_file():
            continue
        if IGNORED_PARTS & set(path.relative_to(scope_root).parts):
            continue
        if path.suffix in IGNORED_SUFFIXES:
            continue
        relative = path.relative_to(scope_root).as_posix()
        manifest[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
    return "content-sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def normalize_model_line(text: str, model: str = "agentgateway/illusionist") -> str:
    """Rewrite exactly one frontmatter model line, as snapshot staging does."""
    return re.sub(r"(?m)^model: .*$", f"model: {model}", text, count=1)


def load_definition(path: Path) -> tuple[dict, str]:
    return split_frontmatter(Path(path).read_text(encoding="utf-8"))
