"""Data access. Every database query lives here; services decide what to do with the rows.

Layering (enforced by tests/test_architecture.py):  api/routers  ->  services  ->  repositories  ->  models/core.
A repository function takes a Session, returns model objects or plain values, and never commits.
"""
