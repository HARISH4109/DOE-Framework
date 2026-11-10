# Directive: Review Execution Code

## Goal
The goal of this directive is to employ a "Reviewer Sub-Agent" to analyze execution scripts (Python) created by other agents. The reviewer looks for effectiveness, code quality, potential bugs, and human-level logic optimizations.

## When to use
- After creating a new execution script.
- When an existing script is failing or performing poorly.
- Before "shipping" a critical script.

## Inputs
- `file_path`: Absolute path to the execution script to be reviewed.

## Execution Tool
- `python execution/reviewer_agent.py --file <file_path>`

## Process
1. **Identify Script**: Locate the script you want to review.
2. **Run Reviewer**: Execute the command above.
3. **Analyze Output**: Read the output from the reviewer agent.
    - **Pass**: If the reviewer says "LGTM" (Looks Good To Me) or only minor nits.
    - **Refactor**: If the reviewer finds "Critical Issues" or "Inefficiencies", you MUST plan a refactor or update of the script based on the guidance.
4. **Iterate**: If changes are made, run the reviewer again.

## Output Structure
The reviewer will provide:
- **Summary**: Brief overview of the script's purpose.
- **Efficiency Check**: Is this done in the most effective manner?
- **Code Quality**: Design patterns, error handling, strict typing.
- **Recommendations**: Specific instructions for the top-level agent to improve the build.
