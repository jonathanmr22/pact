#!/usr/bin/env bash
# =============================================================================
# PACT PostToolUse Hook — Silent linter (only surfaces errors)
#
# Runs your project's static analyzer after every edit. Silent when clean.
# Over a 100-edit session, suppressing "No issues found!" saves hundreds
# of lines of wasted context.
#
# CUSTOMIZE: Replace the analyzer command with your project's tool.
# =============================================================================

# ---- CUSTOMIZE: Your analyzer command ----
# Dart/Flutter:   dart analyze lib
# TypeScript:     npx tsc --noEmit
# Python:         ruff check .
# Rust:           cargo check 2>&1
# Go:             go vet ./...

OUTPUT=$(dart analyze lib 2>&1)

# ---- CUSTOMIZE: Your error/warning patterns ----
# Dart:       'error •\|warning •'
# TypeScript: 'error TS'
# Python:     'error\|warning'
# Rust:       'error\[E'

if echo "$OUTPUT" | grep -q 'error •\|warning •'; then
  echo "$OUTPUT" | grep 'error •\|warning •' >&2
fi
exit 0
