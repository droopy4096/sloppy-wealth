"""The web module's only way to the engine: the JSON API (ADR-0069 decision 5).

``call(path, payload)`` posts JSON and returns the decoded answer; ``get(path)`` gets.
By default the API is called in-process (the same Flask app, same contract, through
its test client); with ``WEB_API_URL`` set (e.g. ``http://localhost:5001``) it is called
over HTTP. Either way the web module never imports the engine.

Answers carry money and rates as decimal strings; the numeric fields of runs, holdings,
the ledger and tax (``NUMERIC``) are turned back into ``Decimal`` for the templates; the
scenario is left as it is (``amount`` and ``rate`` are also item fields).
"""
import json
import os
import urllib.request
from decimal import Decimal

from flask import current_app

NUMERIC = {"assets", "assetsNetWorth", "cash", "debts", "investments", "netWorth",
           "realAssetsNetWorth", "realNetWorth",
           "opening", "closing", "interest", "paid", "principalPaid", "rate", "amount",
           "deductions", "incomeTax", "ownRateTax", "poolIn", "poolOut", "taxable", "total",
           "used", "net_cash", "monthly", "oneOff", "gross",
           # break-even (ADR-0073)
           "value", "sellingCosts", "balance", "penalty", "netProceeds", "netInvestment",
           "breakEven", "rentEquivalent", "closingPenalty",
           # vehicle cost of ownership (ADR-0074)
           "netValue", "paidSoFar", "costPerMonth"}


# A jurisdiction's limit columns in result rows (ADR-0071), e.g. rrspRoom.
LIMIT_COLUMN = lambda key: isinstance(key, str) and key.endswith(("Room", "Limit"))
LABELS = {"names", "items", "jurisdiction", "jurisdictions"}  # labels and items: not result fields


def decimals(value, key=None):
    """``value`` with the strings of NUMERIC fields as Decimal, recursively (not inside
    LABELS)."""
    if isinstance(value, dict):
        if key in LABELS:
            return value
        return {k: decimals(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [decimals(v, key) for v in value]
    if isinstance(value, str) and (key in NUMERIC or LIMIT_COLUMN(key)):
        return Decimal(value)
    return value


def _http(method, path, payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(os.environ["WEB_API_URL"].rstrip("/") + path, data=data,
                                     method=method,
                                     headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as e:            # 4xx answers are JSON too
        return json.loads(e.read())


def _in_process(method, path, payload=None):
    client = current_app.test_client()
    # Plain json.dumps: Flask's JSON would sort the keys, reordering the scenario's fields.
    response = client.get(path) if method == "GET" else client.post(
        path, data=json.dumps(payload), content_type="application/json")
    return response.get_json()


def _send(method, path, payload=None, convert=True):
    send = _http if os.environ.get("WEB_API_URL") else _in_process
    answer = send(method, "/api" + path, payload)
    if not isinstance(answer, dict):
        return {"ok": False, "messages": [f"the API gave no answer for {path}"]}
    # The scenario stays plain JSON (it goes back to the browser as it is).
    if not convert:
        return answer
    return {k: v if k == "scenario" else decimals(v, k) for k, v in answer.items()}


def call(path, payload):
    return _send("POST", path, payload)


def get(path, convert=True):
    """``convert`` False: no Decimal conversion (the schema has no amounts)."""
    return _send("GET", path, convert=convert)
