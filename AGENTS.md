# System Changes / Agent Permissions

IMPORTANT: the files you edit should only be in this local repo, NEVER anywhere else on the system.

You, the agent, should NEVER run commands on the system that would make permanent changes outside
the project's repo directory.

You are ONLY ALLOWED to run READ-ONLY cli commands if they would affect files outside the
project directory.

If you are ever confused about what you have permission to do, stop and ask.

## Temporary files / directories

An exception to the permission policies is changes to files inside known system temporary directories like `/tmp`.


# Conditional Instructions Index

1. At the start of every session, before responding to the first user prompt or doing any
   task-related work, you MUST ALWAYS load the [index
   file](https://raw.githubusercontent.com/rsyring/agent-configs/refs/heads/main/conditional-instructions.yaml)
2. You MUST NOT load any linked documents from that index UNLESS that document's `when` condition
   applies to the current task.
3. If the index file cannot be fetched, stop and report that failure before answering the user
   substantively.
4. WHEN you load a document from the index, notify the user.


# System Commands

- Use `rg` instead of `grep`


# File paths prefer dashes

Prefer dashes (`-`) in file paths and names instead of underscores.
