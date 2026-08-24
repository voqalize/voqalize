"""The ADK adapter does not speak wire v3 yet, so its suite is not collected.

`voqalize.google_adk` is unported: turns, the RTVI plane and heard-truth
write-back all still assume the previous contract. Delete this file once the
adapter is rewritten.
"""

collect_ignore_glob = ["test_*.py"]
