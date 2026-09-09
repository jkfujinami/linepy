# Manual scripts

Not tests. These need a real LINE account and either the network or a person
at the keyboard, so pytest cannot run them: it collects nothing here
(`pytest.ini` sets `norecursedirs`), and the filenames deliberately do not
start with `test_`.

They lived in `tests/` as `test_login.py`, `test_timeline.py` and
`test_storage.py`, where they failed on every single run -- three of them by
blocking on `input()` under captured stdin, one by making a real HTTP call.
Seven red results that meant nothing drowned out any that would have.

Run one directly:

```sh
python tests/manual/login.py     # QR / email / token login, prompts for input
python tests/manual/storage.py   # token persistence + auto-login round trip
python tests/manual/timeline.py  # VOOM / Square Note posting, hits the network
```

`login.py` and `storage.py` write to `.linepy_test.json` in the repo root
(gitignored). Delete it to start from a clean session.
