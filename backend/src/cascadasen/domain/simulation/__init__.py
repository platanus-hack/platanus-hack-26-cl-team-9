"""Physical engine: reduced trunk network, DC power flow, cascade, island frequency, consequence.

Pure domain code (numpy + networkx). Every numeric parameter is loaded from `params/*.yaml` and
carries a source or `is_assumption: true` (docs/datasets.md section 6).
"""
