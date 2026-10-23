"""Static Git-workflow contract tests for agent and skill instructions.

Task B1 of the Git-workflow evaluation plan
(.config/dotfiles/docs/plans/2026-10-22-git-workflow-mlflow-evaluation.md)
requires focused delegation and safety rules in the orchestrator, worker, and
planner agent instructions plus the init-change and publish-change skills.

These tests check concrete examples, phrases, and permission boundaries only.
They do not assert whole-document prose, and passing them does not prove
runtime adherence; measured behavioral validation belongs to Task B3.
Permission assertions interpret frontmatter entry order with last-match-wins
precedence and prove that interpretation against synthetic reorder fixtures,
so they enforce ordering rather than only the presence of effect values.
"""

from __future__ import annotations

import fnmatch
import re

import pytest

from conftest import ROOT

AGENTS_DIR = ROOT / ".config" / "opencode" / "agents"
SKILLS_DIR = ROOT / ".config" / "opencode" / "skills"

ORCHESTRATOR = (AGENTS_DIR / "orchestrator.md").read_text()
WORKER = (AGENTS_DIR / "worker.md").read_text()
PLANNER = (AGENTS_DIR / "planner.md").read_text()
INIT_CHANGE = (SKILLS_DIR / "init-change" / "SKILL.md").read_text()
PUBLISH_CHANGE = (SKILLS_DIR / "publish-change" / "SKILL.md").read_text()

# A raw Git command prescription such as `git status` or `git rebase ...`.
# The lookbehind keeps documented `sandbox-git ...` wrapper usage out.
RAW_GIT_COMMAND = re.compile(
    r"(?<![A-Za-z-])git\s+"
    r"(?:status|fetch|rebase|push|pull|merge|add|commit|switch|checkout|"
    r"branch|reset|clean|restore|clone|init)\b"
)
# An embedded directory change such as `cd /path` inside an example.
EMBEDDED_CD = re.compile(r"(?<![A-Za-z-])cd\s+[A-Za-z0-~/._(-]")
# Explicit prohibition wording governing a raw Git command or embedded `cd`.
# Deliberately narrow: incidental negation anywhere on the line (a bare
# "not", "cannot determine", "does not approve") does not exempt a
# prescribing example, and the wording must share the command's clause.
PROHIBITION_MARKER = re.compile(
    r"\b(?:never|avoid)\b"
    r"|\b(?:forbid|prohibit)\w*\b"
    r"|\b(?:do|must|should)\s+not\b"
    r"|\bdon't\b",
    re.IGNORECASE,
)


def norm(text: str) -> str:
    """Collapse wrapped-line whitespace so phrase checks survive reflowing."""
    return re.sub(r"\s+", " ", text)


def strip_frontmatter(text: str) -> str:
    parts = text.split("---", 2)
    return parts[2] if len(parts) == 3 else text


def clause_around(line: str, start: int, end: int) -> str:
    """Return the sentence clause containing the ``[start, end)`` match.

    Splits at sentence and list-item boundaries (``.``, ``;``, ``:``) on both
    sides, so prohibition wording must appear in the same clause as the raw
    Git command or embedded `cd` it governs. Wording in a neighboring clause
    (for example "cannot determine; run `git rebase ...`") does not govern
    the command.
    """
    left = line[:start]
    right = line[end:]
    for boundary in (".", ";", ":"):
        left = left.rsplit(boundary, 1)[-1]
        right = right.split(boundary, 1)[0]
    return f"{left}{line[start:end]}{right}"


def markdown_section(text: str, heading: str) -> str:
    lines = text.splitlines()
    start = next(
        (index for index, line in enumerate(lines) if line.strip() == f"## {heading}"),
        None,
    )
    assert start is not None, f"section '## {heading}' not found"
    collected = [lines[start]]
    for line in lines[start + 1 :]:
        if line.startswith("## "):
            break
        collected.append(line)
    return "\n".join(collected)


def frontmatter_permissions(text: str) -> dict[tuple[str, str], str]:
    frontmatter = text.split("---", 2)[1]
    permissions: dict[tuple[str, str], str] = {}
    action: str | None = None
    resource: str | None = None
    for line in frontmatter.splitlines():
        stripped = line.strip()
        if stripped.startswith("- action:"):
            action = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("resource:"):
            resource = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("effect:") and action and resource:
            permissions[(action, resource)] = stripped.split(":", 1)[1].strip()
    return permissions


def frontmatter_permission_rules(text: str) -> list[tuple[str, str, str]]:
    """Return ``[(action, resource, effect), ...]`` in frontmatter order.

    OpenCode applies permission entries top to bottom, so a later entry for
    the same action/resource pair overrides an earlier one (last match wins)
    and a later broad pattern can shadow or re-widen an earlier narrow one.
    """
    frontmatter = text.split("---", 2)[1]
    rules: list[tuple[str, str, str]] = []
    action: str | None = None
    resource: str | None = None
    for line in frontmatter.splitlines():
        stripped = line.strip()
        if stripped.startswith("- action:"):
            action = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("resource:"):
            resource = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("effect:") and action and resource:
            rules.append((action, resource, stripped.split(":", 1)[1].strip()))
    return rules


def resolve_permission(
    rules: list[tuple[str, str, str]], command: str
) -> str | None:
    """Resolve the effect for a shell command under last-match-wins order.

    A rule matches when its resource pattern equals the command or is a
    glob that matches its whole prefix, mirroring OpenCode's resource
    matching. Later matching rules override earlier ones; entry order, not
    specificity, decides precedence.
    """
    effect: str | None = None
    for action, resource, rule_effect in rules:
        if action != "shell":
            continue
        pattern = resource.strip('"')
        if pattern == command or (
            pattern.endswith("*")
            and fnmatch.fnmatchcase(command, pattern)
        ):
            effect = rule_effect
    return effect


def permission_rule_matches(
    rules: list[tuple[str, str, str]], command: str
) -> list[tuple[int, tuple[str, str, str]]]:
    """Return ``[(index, rule), ...]`` of shell rules matching ``command``."""
    matches: list[tuple[int, tuple[str, str, str]]] = []
    for index, (action, resource, _effect) in enumerate(rules):
        if action != "shell":
            continue
        pattern = resource.strip('"')
        if pattern == command or (
            pattern.endswith("*") and fnmatch.fnmatchcase(command, pattern)
        ):
            matches.append((index, (action, resource, _effect)))
    assert matches, f"no rules match {command!r}"
    return matches


def rule_index(
    rules: list[tuple[str, str, str]],
    resource: str,
    action: str = "shell",
) -> int:
    """Return the index of the single rule with ``action`` and ``resource``."""
    found = [
        index
        for index, rule in enumerate(rules)
        if rule[0] == action and rule[1] == resource
    ]
    assert len(found) == 1, (action, resource, found)
    return found[0]


def move_rule_to_end(
    rules: list[tuple[str, str, str]], index: int
) -> list[tuple[str, str, str]]:
    """Move the rule at ``index`` to the end, simulating a hazardous reorder."""
    reordered = list(rules)
    rule = reordered.pop(index)
    reordered.append(rule)
    return reordered


def move_rule_to_front(
    rules: list[tuple[str, str, str]], index: int
) -> list[tuple[str, str, str]]:
    """Move the rule at ``index`` to the front, simulating a hazardous reorder."""
    reordered = list(rules)
    rule = reordered.pop(index)
    reordered.insert(0, rule)
    return reordered


def prescribed_violations(text: str) -> list[str]:
    """Return example lines prescribing raw Git or embedded `cd`.

    A line is exempt only when the clause governing the raw Git command or
    embedded ``cd`` carries explicit prohibition wording such as ``Never use
    `cd DIR && CMD```, ``Do not run `git status```, or ``avoid `git ...``.
    Incidental negation elsewhere on the line (``cannot determine the root;
    run `git rebase ...``, ``it is not a catalog tool``) no longer exempts a
    prescribing line, and wording in a neighboring clause does not govern.
    Only prescriptive example content is flagged.
    """
    violations: list[str] = []
    for line in strip_frontmatter(text).splitlines():
        match = RAW_GIT_COMMAND.search(line) or EMBEDDED_CD.search(line)
        if not match:
            continue
        clause = clause_around(line, match.start(), match.end())
        if PROHIBITION_MARKER.search(clause):
            continue
        violations.append(line.strip())
    return violations


# --- Orchestrator: explicit, separated Git delegation scope -----------------


def test_orchestrator_git_delegation_lists_scope_elements_separately() -> None:
    section = norm(markdown_section(ORCHESTRATOR, "Delegation execution contract"))
    for phrase in (
        "target repository",
        "base remote",
        "push destination",
        "review target",
        "approval/publication scope",
    ):
        assert phrase in section, phrase


def test_orchestrator_git_delegation_example_uses_wrapper_and_workdir() -> None:
    section = norm(markdown_section(ORCHESTRATOR, "Delegation execution contract"))
    assert "Execution root:" in section
    assert "sandbox-git" in section
    assert "shell.workdir" in section


def test_orchestrator_example_marks_no_cleanup_and_no_publication() -> None:
    section = norm(markdown_section(ORCHESTRATOR, "Delegation execution contract"))
    assert "no cleanup" in section
    assert "Publication: none" in section


def test_orchestrator_forbids_cleanup_in_return_to_base_assignments() -> None:
    section = norm(markdown_section(ORCHESTRATOR, "Delegation execution contract"))
    assert "return-to-base" in section
    assert "Do not add cleanup" in section


def test_orchestrator_keeps_forbidden_child_command_rule() -> None:
    assert (
        "Never instruct a child to use commands that its execution contract "
        "forbids" in norm(ORCHESTRATOR)
    )


def test_orchestrator_prescribes_no_raw_git_or_embedded_cd() -> None:
    assert prescribed_violations(ORCHESTRATOR) == []


# --- Worker: wrapper recognition and execution-layer honesty ----------------


def test_worker_names_sandbox_git_as_shell_executable_not_catalog_tool() -> None:
    section = norm(markdown_section(WORKER, "Git execution discipline"))
    assert "shell executable" in section
    assert "not a Code Mode catalog tool" in section


def test_worker_corrects_denied_raw_git_through_allowed_wrapper() -> None:
    section = norm(markdown_section(WORKER, "Git execution discipline"))
    assert "raw `git ...` call is denied" in section
    assert "redo the same operation" in section
    assert "allowed `sandbox-git` wrapper" in section
    assert "do not bypass" in section


def test_worker_reports_nonzero_exit_despite_tool_success() -> None:
    section = norm(markdown_section(WORKER, "Git execution discipline"))
    assert "Tool success is not command success" in section
    assert "nonzero subprocess" in section


def test_worker_stops_on_destructive_escalation_without_approval() -> None:
    section = norm(markdown_section(WORKER, "Git execution discipline"))
    assert "Never escalate a refusal into a destructive variant on your own" in section
    assert "carries specific approval" in section
    assert "configured approval prompt is honored" in section


def test_worker_adds_no_unsolicited_cleanup() -> None:
    section = norm(markdown_section(WORKER, "Git execution discipline"))
    assert "cleanup" in section
    assert "assignment did not request" in section


def test_worker_keeps_one_operation_per_call_rule() -> None:
    section = norm(markdown_section(WORKER, "Shell discipline"))
    assert "one logical operation" in section
    assert "one `sandbox-git` command" in section


def test_worker_prescribes_no_raw_git_or_embedded_cd() -> None:
    assert prescribed_violations(WORKER) == []


# --- Planner: outcome-oriented delegation with separated Git permissions ----


def test_planner_delegates_outcomes_and_verification_not_commands() -> None:
    section = norm(markdown_section(PLANNER, "Plan shape"))
    assert "outcomes and verification" in section
    assert "raw Git" in section
    assert "command sequences" in section


def test_planner_distinguishes_git_permission_scopes() -> None:
    section = norm(markdown_section(PLANNER, "Plan shape"))
    for phrase in (
        "no Git change",
        "local synchronization",
        "branch rewrite",
        "push",
        "review creation",
    ):
        assert phrase in section, phrase
    assert "blanket grant" in section


def test_planner_prescribes_no_raw_git_or_embedded_cd() -> None:
    assert prescribed_violations(PLANNER) == []


# --- Skills: feature setup vs maintenance, evidence vs authorization --------


def test_init_change_separates_feature_setup_from_maintenance() -> None:
    text = norm(INIT_CHANGE)
    assert "feature-change setup helpers" in text
    assert "returning to the base branch" in text
    assert "analysis-only" in text


def test_init_change_treats_ancestry_as_evidence_not_authorization() -> None:
    text = norm(INIT_CHANGE)
    assert "evidence for this guard, not authorization" in text
    assert "Preserve dirty and untracked work" in text


def test_publish_change_keeps_push_and_review_targets_independent() -> None:
    assert (
        "Treat the push destination and PR/MR target independently"
        in norm(PUBLISH_CHANGE)
    )


def test_publish_change_preserves_destructive_approval_prompts() -> None:
    text = norm(PUBLISH_CHANGE)
    assert "force push or branch deletion" in text
    assert "explicit human approval" in text
    assert "Never bypass the permission prompt" in text


def test_publish_change_treats_review_state_as_evidence_not_authorization() -> None:
    assert "evidence for the guard, not authorization" in norm(PUBLISH_CHANGE)


# --- Permission boundary regression (no widening) ---------------------------


def test_worker_permission_frontmatter_still_denies_raw_git_and_sweeps() -> None:
    permissions = frontmatter_permissions(WORKER)
    for resource in ('"git *"', '"find*"', '"rm -rf*"', '"sudo*"', '"kubectl*"'):
        assert permissions.get(("shell", resource)) == "deny", resource


def test_worker_permission_frontmatter_keeps_destructive_git_gated() -> None:
    permissions = frontmatter_permissions(WORKER)
    for resource in (
        '"sandbox-git branch -d*"',
        '"sandbox-git branch -D*"',
        '"sandbox-git clean*"',
        '"sandbox-git reset*"',
        '"sandbox-git restore*"',
        '"sandbox-git push --force*"',
        '"sandbox-git push -f*"',
        '"sandbox-git push --delete*"',
        '"sandbox-git commit --amend*"',
    ):
        assert permissions.get(("shell", resource)) == "ask", resource


def test_worker_permission_frontmatter_keeps_wrapper_reads_allowed() -> None:
    permissions = frontmatter_permissions(WORKER)
    assert permissions.get(("shell", '"sandbox-git status*"')) == "allow"
    assert permissions.get(("shell", '"sandbox-git push"')) == "allow"


def test_orchestrator_permission_frontmatter_keeps_boundary() -> None:
    permissions = frontmatter_permissions(ORCHESTRATOR)
    for action in ("shell", "edit", "skill", "subagent"):
        assert permissions.get((action, '"*"')) == "deny", action
    for specialist in ("architect", "planner", "reviewer", "worker", "zweistein"):
        assert permissions.get(("subagent", f'"{specialist}"')) == "allow", specialist


# --- Permission ordering: last-match-wins with ordered interpretation -------


# Concrete destructive commands and the specific frontmatter carve-out entry
# that must be their final matching rule under last-match-wins resolution.
WORKER_DESTRUCTIVE_CARVE_OUTS = {
    "sandbox-git branch -d topic": '"sandbox-git branch -d*"',
    "sandbox-git branch -D topic": '"sandbox-git branch -D*"',
    "sandbox-git clean -fd": '"sandbox-git clean*"',
    "sandbox-git reset --hard HEAD~1": '"sandbox-git reset*"',
    "sandbox-git restore .": '"sandbox-git restore*"',
    "sandbox-git push --force origin main": '"sandbox-git push --force*"',
    "sandbox-git push -f origin main": '"sandbox-git push -f*"',
    "sandbox-git push --delete origin topic": '"sandbox-git push --delete*"',
    "sandbox-git commit --amend": '"sandbox-git commit --amend*"',
}
# Destructive commands that also match an earlier broad `allow` pattern; the
# ask carve-out must win against exactly this shadowing.
WORKER_SHADOWED_BY_ALLOW = (
    "sandbox-git branch -d topic",
    "sandbox-git branch -D topic",
    "sandbox-git commit --amend",
)


def assert_worker_decision_table(rules: list[tuple[str, str, str]]) -> None:
    """Production assertion: ordered decisions for representative commands."""
    for command, expected in (
        ("git status", "deny"),
        ("sandbox-git status", "allow"),
        ("sandbox-git branch feature", "allow"),
        ("sandbox-git push", "allow"),
        ("sandbox-git push origin main", "ask"),
        ("sandbox-git checkout feature", "allow"),
        ("sandbox-git commit -m msg", "allow"),
        *WORKER_DESTRUCTIVE_CARVE_OUTS.items(),
    ):
        # The dict expansion pairs each destructive command with "ask".
        expected_effect = (
            "ask" if command in WORKER_DESTRUCTIVE_CARVE_OUTS else expected
        )
        assert resolve_permission(rules, command) == expected_effect, command


def assert_destructive_asks_are_last_match(
    rules: list[tuple[str, str, str]]
) -> None:
    """Production assertion: each destructive command's final matching rule
    must be its specific ``ask`` carve-out entry (not the catch-all ask), and
    for commands with an earlier broad ``allow`` pattern, that allow must be
    shadowed by the later carve-out."""
    for command, carve_out in WORKER_DESTRUCTIVE_CARVE_OUTS.items():
        matches = permission_rule_matches(rules, command)
        last_index, last_rule = matches[-1]
        assert last_rule[1] == carve_out, (command, last_index, last_rule)
        assert last_rule[2] == "ask", (command, last_index, last_rule)
        if command in WORKER_SHADOWED_BY_ALLOW:
            earlier_allows = [
                index
                for index, (_action, _resource, effect) in matches[:-1]
                if effect == "allow"
            ]
            assert earlier_allows, (command, matches)


def test_worker_permission_rules_are_last_match_wins_ordered() -> None:
    """Ordered interpretation: resolve commands under last-match-wins.

    Covers the concrete destructive carve-outs (branch -d/-D, push force,
    push delete, reset, clean) plus representative broad allows and the raw
    ``git`` denial, so the decision table is asserted, not just presence of
    effect values.
    """
    assert_worker_decision_table(frontmatter_permission_rules(WORKER))


def test_worker_destructive_ask_rules_come_after_broader_allows() -> None:
    """Destructive `ask` entries must be the final match for their commands.

    The frontmatter opens with a catch-all ``shell: "*" -> ask``, allows
    broad ``sandbox-git <subcommand>*`` patterns, and later carves
    destructive variants out as ``ask``. Because OpenCode resolves entries
    top to bottom (last match wins), each destructive ``ask`` entry must be
    the last matching rule for every concrete destructive command.
    """
    assert_destructive_asks_are_last_match(frontmatter_permission_rules(WORKER))


def test_reordered_broader_allow_would_be_detected_as_widening() -> None:
    """Synthetic reorder fixture: moving the broad ``sandbox-git branch*``
    allow after the destructive ``ask`` entries re-widens ``branch -D`` from
    ``ask`` to ``allow`` under the same ordered interpretation. The
    production assertions must reject that state, proving the tests are
    order-sensitive rather than only checking current effect values.
    """
    rules = frontmatter_permission_rules(WORKER)
    branch_allow = rule_index(rules, '"sandbox-git branch*"')
    assert rules[branch_allow][2] == "allow", rules[branch_allow]

    reordered = move_rule_to_end(rules, branch_allow)

    # Decision would flip to allow under the same interpretation...
    assert resolve_permission(reordered, "sandbox-git branch -D topic") == "allow"
    assert resolve_permission(reordered, "sandbox-git branch -d topic") == "allow"
    # ...so both production assertions would fail against this reorder.
    with pytest.raises(AssertionError):
        assert_worker_decision_table(reordered)
    with pytest.raises(AssertionError):
        assert_destructive_asks_are_last_match(reordered)


def test_hoisted_destructive_ask_would_be_detected_as_shadowed() -> None:
    """Synthetic reorder fixture in the other direction: hoisting the
    ``sandbox-git branch -D*`` ask entry to the very front lets the broad
    ``sandbox-git branch*`` allow shadow it, resolving ``branch -D`` to
    ``allow``. The production assertions must reject that state too, proving
    they detect precedence changes in both directions.
    """
    rules = frontmatter_permission_rules(WORKER)
    branch_d_ask = rule_index(rules, '"sandbox-git branch -D*"')
    assert rules[branch_d_ask][2] == "ask", rules[branch_d_ask]

    reordered = move_rule_to_front(rules, branch_d_ask)

    # The hoisted ask is shadowed by the later broad branch allow...
    assert resolve_permission(reordered, "sandbox-git branch -D topic") == "allow"
    # ...while the un-hoisted branch -d carve-out still wins.
    assert resolve_permission(reordered, "sandbox-git branch -d topic") == "ask"
    # Both production assertions would fail against this reorder.
    with pytest.raises(AssertionError):
        assert_worker_decision_table(reordered)
    with pytest.raises(AssertionError):
        assert_destructive_asks_are_last_match(reordered)


def test_trailing_catch_all_ask_would_shadow_raw_git_deny() -> None:
    """Synthetic reorder fixture for the raw-git denial: moving the leading
    catch-all ``shell: "*" -> ask`` to the end would shadow the ``git *``
    deny and flip raw ``git`` commands from ``deny`` to ``ask``. The
    decision table must catch that reorder as well.
    """
    rules = frontmatter_permission_rules(WORKER)
    shell_catch_all = rule_index(rules, '"*"')
    assert rules[shell_catch_all] == ("shell", '"*"', "ask"), rules[shell_catch_all]

    reordered = move_rule_to_end(rules, shell_catch_all)

    assert resolve_permission(reordered, "git status") == "ask"
    with pytest.raises(AssertionError):
        assert_worker_decision_table(reordered)


def test_permission_ordering_is_not_brittle_for_irrelevant_moves() -> None:
    """Ordering assertions track matching rules, not raw list position.

    Swapping two unrelated read-only allow entries between the catch-all ask
    and the destructive carve-outs must not change any checked decision: no
    moved rule matches any checked command. This guards against
    order-over-sensitive assertions while the synthetic reorder tests above
    guard against order-blind ones.
    """
    rules = frontmatter_permission_rules(WORKER)
    status_allow = rule_index(rules, '"sandbox-git status*"')
    log_allow = rule_index(rules, '"sandbox-git log*"')
    assert status_allow < log_allow
    reordered = list(rules)
    reordered[status_allow], reordered[log_allow] = (
        reordered[log_allow],
        reordered[status_allow],
    )
    assert reordered != rules
    assert_worker_decision_table(reordered)
    assert_destructive_asks_are_last_match(reordered)


# --- Prohibition detection regression (narrow explicit wording) --------------


def test_prohibition_detection_flags_prescribing_lines_with_incidental_not() -> None:
    """Positive regression for the exact false-exemption the loose marker had.

    A prescribing line whose earlier clause merely contains "cannot" or
    "not" must still be flagged; under the old ``not `` substring marker
    these lines were wrongly exempted.
    """
    prescribing = (
        "If the project root cannot be determined, run `git status` first.",
        "The orchestrator cannot inspect the repo; run `cd /repo && git log`.",
        "This wrapper is not a catalog tool; run `git fetch origin` now.",
    )
    for line in prescribing:
        assert prescribed_violations(f"---\n---\n{line}\n") == [line], line


def test_prohibition_detection_honors_explicit_prohibitions() -> None:
    """Negative regression: explicit prohibition wording in the governing
    clause still exempts the line.
    """
    exempt = (
        "Never use `cd DIR && CMD`; set the working directory instead.",
        "Do not run raw `git status`; use the wrapper instead.",
        "Agents must not invoke `git rebase` directly.",
        "Avoid embedding `cd /repo` in examples.",
        "The contract forbids raw `git push`; use the wrapper.",
    )
    for line in exempt:
        assert prescribed_violations(f"---\n---\n{line}\n") == [], line


def test_prohibition_detection_is_clause_local() -> None:
    """Prohibition wording separated by a sentence boundary does not exempt
    a prescribing clause; wording in a different clause is not governing.
    """
    text = "---\n---\nDo not do this. Instead run `git fetch origin` now.\n"
    flagged = prescribed_violations(text)
    # Violations are whole lines; the prescribing line is still flagged even
    # though a neighboring clause on the same line carries prohibition words.
    assert flagged == ["Do not do this. Instead run `git fetch origin` now."]


def test_prohibition_marker_matches_explicit_wording_only() -> None:
    """Direct positive/negative examples for the marker itself."""
    for wording in (
        "Never use it",
        "do not use it",
        "must not run it",
        "avoid it",
        "forbidden here",
        "forbids it",
        "prohibited here",
        "don't use it",
    ):
        assert PROHIBITION_MARKER.search(wording), wording
    for wording in (
        "You cannot determine the root, so",
        "It is not a catalog tool, so",
        "Note that this does not approve anything; then",
        "cannot determine",
        "is not evidence",
    ):
        assert not PROHIBITION_MARKER.search(wording), wording


def test_prohibition_detection_still_flags_real_document_violations() -> None:
    """The five B1 documents contain no prescribed raw Git or embedded `cd`.

    The only pattern line in them is worker's ``Never use `cd DIR && CMD``,
    which the explicit marker still exempts; this pins the behavior the
    reviewer flagged without asserting whole-document prose.
    """
    assert prescribed_violations(ORCHESTRATOR) == []
    assert prescribed_violations(WORKER) == []
    assert prescribed_violations(PLANNER) == []
    assert prescribed_violations(INIT_CHANGE) == []
    assert prescribed_violations(PUBLISH_CHANGE) == []
