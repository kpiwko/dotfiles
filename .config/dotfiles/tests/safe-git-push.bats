#!/usr/bin/env bats

setup() {
  TEST_DIR="$(mktemp -d)"
  REMOTE_DIR="$TEST_DIR/remote.git"
  REPO_DIR="$TEST_DIR/work"
  SCRIPT="$BATS_TEST_DIRNAME/../../../.local/bin/safe-git-push"

  # Initialize bare remote repo
  git init --bare "$REMOTE_DIR" >/dev/null 2>&1
  git -C "$REMOTE_DIR" symbolic-ref HEAD refs/heads/main

  # Clone or initialize work repo
  git init "$REPO_DIR" >/dev/null 2>&1
  git -C "$REPO_DIR" config user.name "Test User"
  git -C "$REPO_DIR" config user.email "test@example.com"
  git -C "$REPO_DIR" remote add origin "$REMOTE_DIR"

  # Initial commit on main and push to remote
  (
    cd "$REPO_DIR"
    git checkout -b main >/dev/null 2>&1
    touch initial.txt
    git add initial.txt
    git commit -m "initial commit" >/dev/null 2>&1
    git push -u origin main >/dev/null 2>&1
  )
}

teardown() {
  rm -rf "$TEST_DIR"
}

@test "refuses to push when not inside a git repository" {
  NON_GIT_DIR="$TEST_DIR/nongit"
  mkdir -p "$NON_GIT_DIR"
  cd "$NON_GIT_DIR"
  run "$SCRIPT"
  [ "$status" -eq 1 ]
  [[ "$output" == *"not inside a Git repository"* ]]
}

@test "refuses to push when remote origin does not exist" {
  cd "$REPO_DIR"
  git remote remove origin
  run "$SCRIPT"
  [ "$status" -eq 1 ]
  [[ "$output" == *"remote 'origin' does not exist"* ]]
}

@test "refuses to push in detached HEAD state" {
  cd "$REPO_DIR"
  commit_hash="$(git rev-parse HEAD)"
  git checkout "$commit_hash" >/dev/null 2>&1
  run "$SCRIPT"
  [ "$status" -eq 1 ]
  [[ "$output" == *"detached HEAD; refusing to push"* ]]
}

@test "refuses to push the default branch (main)" {
  cd "$REPO_DIR"
  git checkout main >/dev/null 2>&1
  run "$SCRIPT"
  [ "$status" -eq 1 ]
  [[ "$output" == *"refusing to push protected/significant branch 'main'"* ]]
}

@test "refuses to push significant branches like develop or prod" {
  cd "$REPO_DIR"
  git checkout -b develop >/dev/null 2>&1
  run "$SCRIPT"
  [ "$status" -eq 1 ]
  [[ "$output" == *"refusing to push protected/significant branch 'develop'"* ]]

  git checkout -b prod >/dev/null 2>&1
  run "$SCRIPT"
  [ "$status" -eq 1 ]
  [[ "$output" == *"refusing to push protected/significant branch 'prod'"* ]]
}

@test "refuses to push release or hotfix branches" {
  cd "$REPO_DIR"
  git checkout -b release/1.0 >/dev/null 2>&1
  run "$SCRIPT"
  [ "$status" -eq 1 ]
  [[ "$output" == *"refusing to push release/hotfix branch 'release/1.0'"* ]]

  git checkout -b hotfix/bugfix >/dev/null 2>&1
  run "$SCRIPT"
  [ "$status" -eq 1 ]
  [[ "$output" == *"refusing to push release/hotfix branch 'hotfix/bugfix'"* ]]
}

@test "refuses to push if branch tracks another remote" {
  cd "$REPO_DIR"
  git checkout -b feat/my-feature >/dev/null 2>&1
  git config "branch.feat/my-feature.remote" "upstream"
  run "$SCRIPT"
  [ "$status" -eq 1 ]
  [[ "$output" == *"tracks 'upstream', not 'origin'"* ]]
}

@test "refuses to push if upstream branch has mismatched name" {
  cd "$REPO_DIR"
  git checkout -b feat/local-branch >/dev/null 2>&1
  touch feat.txt
  git add feat.txt
  git commit -m "add feat" >/dev/null 2>&1
  git push origin feat/local-branch:feat/remote-branch >/dev/null 2>&1
  git branch -u origin/feat/remote-branch feat/local-branch >/dev/null 2>&1

  run "$SCRIPT"
  [ "$status" -eq 1 ]
  [[ "$output" == *"differs from current branch"* ]]
}

@test "successfully pushes feature branch without prior upstream" {
  cd "$REPO_DIR"
  git checkout -b feat/new-feature >/dev/null 2>&1
  touch feature.txt
  git add feature.txt
  git commit -m "add feature" >/dev/null 2>&1

  run "$SCRIPT"
  [ "$status" -eq 0 ]
  [[ "$output" == *"safe-git-push: pushing 'feat/new-feature' -> 'origin/feat/new-feature'"* ]]
  # Verify remote received branch
  git -C "$REMOTE_DIR" rev-parse --verify refs/heads/feat/new-feature
}

@test "successfully pushes feature branch with existing upstream" {
  cd "$REPO_DIR"
  git checkout -b feat/existing-feature >/dev/null 2>&1
  touch file1.txt
  git add file1.txt
  git commit -m "file 1" >/dev/null 2>&1
  git push -u origin feat/existing-feature >/dev/null 2>&1

  touch file2.txt
  git add file2.txt
  git commit -m "file 2" >/dev/null 2>&1

  run "$SCRIPT"
  [ "$status" -eq 0 ]
  [[ "$output" == *"safe-git-push: pushing 'feat/existing-feature' -> 'origin/feat/existing-feature'"* ]]
}
