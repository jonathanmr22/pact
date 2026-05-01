#!/usr/bin/env bash
# =============================================================================
# Source-file extension classifiers — shared across all PACT hooks
# =============================================================================
# Diagnoses the recurring "hook silently skips because the file isn't .dart"
# class of bug. Tonight (2026-04-28) the post-edit-preflight hook silently
# skipped every Python edit in scripts/lib/scraping_toolkit/, which is why
# none of the cognitive checks fired during the broken-harvest investigation.
#
# Usage in hooks:
#   source "$(dirname "${BASH_SOURCE[0]}")/lib/source-file-extensions.sh"
#   if is_source_file "$FILE_PATH"; then ... fi
#   if is_dart_file "$FILE_PATH" && ! is_generated_dart "$FILE_PATH"; then ...
#   if is_python_file "$FILE_PATH"; then ... fi
#
# All classifiers are case-insensitive on the extension and accept either
# Unix or Windows slashes in the path.
# =============================================================================

# Canonical list of source-code extensions Claude is likely to author or edit.
# This is the universe over which "did a hook fire?" should be true by default.
# Extend as the project grows. Keep ordered alphabetically for diff-friendliness.
__SOURCE_FILE_EXTS_REGEX='\.(c|cc|cpp|cs|css|dart|go|h|hpp|html|java|js|json|jsx|kt|kts|less|md|mjs|php|pl|ps1|py|rb|rs|sass|scala|scss|sh|sql|svelte|swift|toml|ts|tsx|vue|xml|yaml|yml|zsh)$'

# True for any file Claude is likely to edit as source.
is_source_file() {
  local p="${1,,}"  # lowercase
  [[ "$p" =~ $__SOURCE_FILE_EXTS_REGEX ]]
}

# Per-language classifiers — narrow the scope of language-specific checks.
is_dart_file()       { local p="${1,,}"; [[ "$p" =~ \.dart$ ]]; }
is_python_file()     { local p="${1,,}"; [[ "$p" =~ \.py$ ]]; }
is_typescript_file() { local p="${1,,}"; [[ "$p" =~ \.(ts|tsx)$ ]]; }
is_javascript_file() { local p="${1,,}"; [[ "$p" =~ \.(js|jsx|mjs)$ ]]; }
is_shell_file()      { local p="${1,,}"; [[ "$p" =~ \.(sh|bash|zsh)$ ]]; }
is_powershell_file() { local p="${1,,}"; [[ "$p" =~ \.ps1$ ]]; }
is_sql_file()        { local p="${1,,}"; [[ "$p" =~ \.sql$ ]]; }
is_yaml_file()       { local p="${1,,}"; [[ "$p" =~ \.(yaml|yml)$ ]]; }
is_markdown_file()   { local p="${1,,}"; [[ "$p" =~ \.md$ ]]; }

# Generated/derived files we never lint.
is_generated_dart() {
  local p="${1,,}"
  [[ "$p" =~ \.g\.dart$ ]] || [[ "$p" =~ \.freezed\.dart$ ]] \
    || [[ "$p" =~ \.gr\.dart$ ]] || [[ "$p" =~ \.config\.dart$ ]]
}

# True if the file lives under a test directory (any common convention).
is_test_file() {
  local p="${1,,}"
  [[ "$p" =~ /(test|tests|spec|specs|__tests__)/ ]] \
    || [[ "$p" =~ \.test\.(py|ts|tsx|js|jsx|dart)$ ]] \
    || [[ "$p" =~ _test\.(py|go|dart)$ ]]
}

# True if the file is in a vendored/generated/build path. Skip these.
# Match works whether the path starts with / or with the dir name itself.
is_vendored_file() {
  local p="${1,,}"
  [[ "$p" =~ (^|/)(node_modules|vendor|build|dist|target|\.dart_tool|\.next|\.nuxt|__pycache__)/ ]]
}

# Composite: should we run a UNIVERSAL check on this file?
# Skips test, generated, and vendored paths.
should_check_universal() {
  local p="$1"
  is_source_file "$p" || return 1
  is_test_file "$p" && return 1
  is_vendored_file "$p" && return 1
  is_generated_dart "$p" && return 1
  return 0
}

# Composite: should we run a DART-SPECIFIC check on this file?
should_check_dart() {
  local p="$1"
  is_dart_file "$p" || return 1
  is_test_file "$p" && return 1
  is_generated_dart "$p" && return 1
  return 0
}

# Composite: should we run a PYTHON-SPECIFIC check on this file?
should_check_python() {
  local p="$1"
  is_python_file "$p" || return 1
  is_test_file "$p" && return 1
  is_vendored_file "$p" && return 1
  return 0
}
