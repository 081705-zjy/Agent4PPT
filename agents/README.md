# PPT Agent Runtime Agents

Agent config files bind skills to execution context. A config answers:

- which stage owns the agent
- which skill files should be loaded
- which model route and tool routes are allowed
- which artifacts are expected as inputs and outputs
- whether human or review gates apply

The Python runtime loads these configs; the Markdown skill files remain stable
task instructions.

