"""Thin, cached clients for the Meta Model API (api.meta.ai/v1).

Every network call goes through `cache` (so re-runs are free) and `ledger`
(so every dollar is accounted for and the hard budget stop is enforced).
"""
