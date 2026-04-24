#!/usr/bin/env bash
# ============================================================================
# Claude Unavailable Banner
# ============================================================================
# Called by session-status-check.sh when Claude API issues are detected,
# or run manually when you hit a usage cap.
#
# Usage: bash .claude/hooks/claude-unavailable-banner.sh

BLUE='\033[0;34m'
GOLD='\033[1;33m'
GREEN='\033[0;32m'
RED='\033[0;31m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

echo ""
echo -e "${RED}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${RED}║  ${BOLD}Claude is unavailable.${NC}${RED} Gemini is ready to take over.       ║${NC}"
echo -e "${RED}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${BOLD}To continue working in this terminal:${NC}"
echo ""
echo -e "  ${CYAN}bash .claude/tools/pact-orchestrate${NC}"
echo ""
echo -e "${DIM}This launches Gemini as your orchestrator — same project, same rules,${NC}"
echo -e "${DIM}same worker models (Trinity for research, M2.5 for code).${NC}"
echo ""
echo -e "${BOLD}Quick commands:${NC}"
echo -e "  ${GREEN}pact-orchestrate${NC}               ${DIM}— Interactive Gemini session${NC}"
echo -e "  ${GREEN}pact-orchestrate \"do X\"${NC}         ${DIM}— Single task, headless${NC}"
echo -e "  ${GREEN}pact-orchestrate --status${NC}       ${DIM}— Check what's available${NC}"
echo ""
echo -e "${BOLD}Or delegate directly to workers (no orchestrator needed):${NC}"
echo -e "  ${GREEN}pact-delegate research \"...\"${NC}    ${DIM}— Trinity researches${NC}"
echo -e "  ${GREEN}pact-delegate code \"...\"${NC}        ${DIM}— M2.5 generates code${NC}"
echo ""
echo -e "${DIM}All work is governed by the same PACT hooks. Nothing changes except${NC}"
echo -e "${DIM}which model is thinking. Your rules, your project, your data.${NC}"
echo ""
