"""The movement ledger (ADR-0053): every balance change is one entry, in firing order.

Results (WP8) read ``household.ledger.entries``: a list of dicts with keys, in this
order, ``month`` (label 'YYYY-MM'), ``kind``, ``from``, ``to``, ``amount`` (Decimal,
rounded, never 0), ``source``. ``from``/``to`` are holding ids or None (outside).
"""


class Ledger:
    def __init__(self):
        self.entries = []

    def record(self, month_label, kind, src, dst, amount, source):
        self.entries.append({"month": month_label, "kind": kind, "from": src,
                             "to": dst, "amount": amount, "source": source})

    def __iter__(self):
        return iter(self.entries)

    def __len__(self):
        return len(self.entries)
