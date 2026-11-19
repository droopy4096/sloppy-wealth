# Tutorials

Short, hands-on walk-throughs. Each one takes you from a fresh checkout to one working,
tested change. Read the [developer intro](../README.md) first for the big picture; look
details up in the [reference](../reference/).

All commands run from `webapp/`. Every tutorial ends with the same three gates:

```
.venv/bin/python -m unittest -q test_engine test_keep_payment test_ui_emitters test_api test_docs
.venv/bin/python -m unittest discover -s state_machine/tests -t .
.venv/bin/python state_machine/tools/update_golden.py --check
```

In a sensible order:

1. [Add an item type](add-item-type.md): a one-off `gift`; emitter, event,
   `household.move`, validation, builder form, spec and test.
2. [Add a value to the output](change-output.md): a new column in the result rows, through
   the JSON API to the Run page; why golden hashes change and how to review them.
3. [Extend a jurisdiction](extend-jurisdiction.md): Canada's FHSA as a new account type;
   tax treatment flags, the conformance test, updating the sample and its golden set.
4. [Add a new jurisdiction](new-jurisdiction.md): a minimal United Kingdom package with
   two account types, a sample, a golden set and its tests.
5. [Add a rule](add-rule.md): a US early-withdrawal tax as a calculator called from a
   jurisdiction hook; when to use a scenario-level emitter instead.

Each tutorial was run as written against a copy of the code. Do them in a branch; they
are examples, not features agreed for the product.
