#!/usr/bin/env python3
"""
PACT Feedback Report Generator

Generates an anonymous session report from PACT event data.
Called by Claude when the user agrees to generate a feedback report.

Usage:
  python pact-feedback-report.py generate [--project-root /path]
  python pact-feedback-report.py mark-done day2|week2

The report is written to ~/.claude/pact-feedback-report.yaml
The user reviews it, then decides whether to share.
"""

import json
import os
import sys
from collections import Counter
from datetime import datetime


PACT_DIR = os.path.join(os.path.expanduser('~'), '.claude')
CONFIG_PATH = os.path.join(PACT_DIR, 'pact-config.json')
REPORT_PATH = os.path.join(PACT_DIR, 'pact-feedback-report.yaml')


def load_events():
    """Load events from central JSONL."""
    events = []
    for path in [
        os.path.join(PACT_DIR, 'pact-events.jsonl'),
    ]:
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            events.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
    return events


def load_feedback(project_root=None):
    """Load task ratings from feedback file."""
    ratings = []
    paths = [os.path.join(PACT_DIR, 'pact-ratings.jsonl')]
    if project_root:
        paths.insert(0, os.path.join(project_root, '.claude', 'bugs', '_FEEDBACK.jsonl'))

    for path in paths:
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            ratings.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
            break
    return ratings


def generate(project_root=None):
    """Generate the anonymous feedback report."""
    events = load_events()
    ratings = load_feedback(project_root)

    # Load config
    config = {}
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, 'r') as f:
            config = json.load(f)

    first_used = config.get('first_used', 'unknown')
    pact_version = '0.7.0'
    days_used = 0
    if first_used != 'unknown':
        try:
            days_used = (datetime.now() - datetime.strptime(first_used, '%Y-%m-%d')).days
        except ValueError:
            pass

    # Count event types
    type_counts = Counter(e.get('type', 'unknown') for e in events)

    # Count unique sessions
    sessions = set(e.get('sid', '') for e in events if e.get('sid'))

    # Count unique projects
    projects = set(e.get('project', '') for e in events if e.get('project'))

    # Rating stats
    scores = [r.get('score', 0) for r in ratings if r.get('score')]
    avg_score = sum(scores) / len(scores) if scores else 0
    tag_counts = Counter()
    for r in ratings:
        for t in r.get('tags', []):
            if t != 'Nothing':
                tag_counts[t] += 1

    # Subsystems detected
    subsystems = {
        'hooks': type_counts.get('hook_block', 0) + type_counts.get('hook_warn', 0) > 0,
        'preflight': type_counts.get('preflight', 0) > 0,
        'dashboard': type_counts.get('edit', 0) > 0,  # if events exist, dashboard was running
        'vector_memory': os.path.exists(os.path.join(PACT_DIR, 'pact-memory.db')),
        'task_rating': len(ratings) > 0,
        'prompt_capture': type_counts.get('prompt', 0) > 0,
    }

    # Build report — NO project-specific content, NO file paths, NO personal data
    lines = [
        '# PACT Anonymous Feedback Report',
        f'# Generated: {datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")}',
        '#',
        '# PRIVACY: This report is designed to be fully anonymous.',
        '#   - NO project names, company names, or repo identifiers',
        '#   - NO file paths, directory structures, or code snippets',
        '#   - NO usernames, emails, API keys, or personal identifiers',
        '#   - NO git history, branch names, or commit messages',
        '#   - ONLY aggregate counts and PACT-specific subsystem usage',
        '#',
        '# Individual tools/frameworks (e.g. "Flutter", "PostgreSQL") are OK to',
        '# mention — they help PACT improve for that ecosystem. What makes a stack',
        '# identifying is the COMBINATION of all its parts. Mention one or two',
        '# if relevant to the feedback. Don\'t list your full stack.',
        '#',
        '# Review every line before sharing. If anything below could identify',
        '# you or your project — edit or delete it.',
        '',
        f'pact_version: "{pact_version}"',
        f'days_used: {days_used}',
        f'total_sessions: {len(sessions)}',
        f'total_projects: {len(projects)}',
        f'total_events: {len(events)}',
        '',
        '# Event breakdown',
        'events:',
    ]
    for etype, count in sorted(type_counts.items(), key=lambda x: -x[1]):
        lines.append(f'  {etype}: {count}')

    lines.extend([
        '',
        '# Subsystems used',
        'subsystems:',
    ])
    for sub, used in sorted(subsystems.items()):
        lines.append(f'  {sub}: {str(used).lower()}')

    lines.extend([
        '',
        '# Task ratings (if any)',
        f'tasks_rated: {len(ratings)}',
        f'avg_score: {avg_score:.1f}',
    ])
    if tag_counts:
        lines.append('common_issues:')
        for tag, count in tag_counts.most_common(5):
            lines.append(f'  - "{tag}": {count}')

    lines.extend([
        '',
        '# ── User + Claude feedback (filled in conversationally) ──',
        '#',
        '# Claude: ask the user about each section. Also reflect honestly',
        '# on your OWN experience — what PACT rules helped your reasoning,',
        '# what felt like noise, and what workarounds you had to invent.',
        '#',
        '# IMPORTANT: Keep responses generic enough to not identify the project.',
        '# Mentioning a framework is fine if relevant ("preflight checks helped',
        '# catch a missing migration in our ORM"). Describing the full stack or',
        '# project purpose is not ("our Flutter/Supabase social app for...").',
        '',
        'what_helped: []',
        '  # - "what PACT feature was most useful (keep generic, no tech stack details)"',
        'what_caused_friction: []',
        '  # - "what was annoying or got in the way (describe the PACT behavior, not the project context)"',
        'workarounds_invented: []',
        '  # - "solutions Claude had to create because PACT did not cover the case"',
        '  # These are the most valuable signal — they show exactly where PACT has gaps.',
        '  # Describe the PATTERN, not the project. "Had to manually check cascading',
        '  # deletes" not "had to check User → Order → Payment cascade in our e-commerce app."',
        'missing_features: []',
        '  # - "what you wished PACT had (describe the capability, not the use case)"',
        'hooks_that_blocked_legitimate_work: []',
        '  # - "which hook, what it blocked, why it was a false positive"',
        'would_recommend: null  # yes / no / maybe',
    ])

    report = '\n'.join(lines) + '\n'
    with open(REPORT_PATH, 'w', encoding='utf-8') as f:
        f.write(report)

    print(f'Report generated: {REPORT_PATH}')
    print(f'  {len(events)} events, {len(sessions)} sessions, {len(ratings)} ratings')
    print(f'  Review the file, then tell Claude what helped and what caused friction.')
    return REPORT_PATH


def mark_done(milestone):
    """Mark a feedback milestone as complete."""
    if not os.path.exists(CONFIG_PATH):
        return
    with open(CONFIG_PATH, 'r') as f:
        config = json.load(f)
    config[f'feedback_{milestone}_done'] = True
    with open(CONFIG_PATH, 'w') as f:
        json.dump(config, f, indent=2)
    print(f'Marked {milestone} feedback as done.')


def main():
    if len(sys.argv) < 2:
        print('Usage:')
        print('  python pact-feedback-report.py generate [--project-root /path]')
        print('  python pact-feedback-report.py mark-done day2|week2')
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == 'generate':
        project_root = None
        if '--project-root' in sys.argv:
            idx = sys.argv.index('--project-root')
            if idx + 1 < len(sys.argv):
                project_root = sys.argv[idx + 1]
        generate(project_root)

    elif cmd == 'mark-done':
        if len(sys.argv) < 3:
            print('Specify milestone: day2 or week2')
            sys.exit(1)
        mark_done(sys.argv[2])

    else:
        print(f'Unknown command: {cmd}')
        sys.exit(1)


if __name__ == '__main__':
    main()
