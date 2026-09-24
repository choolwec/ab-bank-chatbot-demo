"""The agent desk (ticket H2): a self-hosted Chatwoot with an API-channel inbox.

  chatwoot.py  a thin httpx client for the Chatwoot Application API
  links.py     which desk conversation belongs to which session (hashed keys)
  bridge.py    handoff, forwarding while paused, agent replies, resume

We keep the Meta channels ourselves (research §7.6): Chatwoot only mirrors the
conversation, and agents' replies come back through our own channel adapter,
which enforces the 24-h window. Jira stays the system of record.
"""
