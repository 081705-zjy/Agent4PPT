# PPT Agent Skills

Skills are stable task instructions and output contracts. They are not agents by
themselves. A runtime agent is assembled from:

- one or more skill files
- an agent config
- a model route
- tool routes
- input and output artifacts
- validation and human/review gates

Keep skills free of API keys, local machine paths, transient logs, and provider
names. Provider selection belongs in `config/default_config.json`; stage and agent
binding belongs in `config/stages.json` and `config/agents.json`.

