"""Library extraction scripts.

Scripts here build/maintain data/resources_library/ contents (rule + logic).
These are tools used to populate the library, not runtime business code.

Modules:
- narrative_extract.py — legacy 6-skill extractor (kept for reference, superseded
  by logic_extract.py which uses 2-skill carrier-strict design)
- logic_extract.py     — new 2-skill driver (deck_level + section_level)
- rule_stats.py        — statistical rule extractor (Python-only, no Claude)
"""

