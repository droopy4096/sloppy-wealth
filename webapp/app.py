"""The wealth-planner PoC server (see SPEC.md): the JSON API and the web pages, deployed
together but separate (ADR-0069).

- ``api.py`` (``/api/...``): state in, state out; the only part that uses the engine
  (``state_machine/``). It keeps nothing between requests.
- ``web/`` (the pages): the Jinja builder, a client of the API; the scenario lives in
  the browser tab (sessionStorage) and comes with every request.

Run: ``.venv/bin/python app.py`` (debug server on http://127.0.0.1:5000).
"""
from flask import Flask

from api import MAX_BODY, api
import schema as _schema
FIELDS = _schema.merged()["fields"]  # noqa: F401  (tests: the Canadian forms)
from state_machine import engine  # noqa: F401  (tests)
from web.pages import web

app = Flask(__name__)
# Request bodies over 1 MB are refused (ADR-0069 decision 6).
app.config["MAX_CONTENT_LENGTH"] = MAX_BODY
app.register_blueprint(api)
app.register_blueprint(web)


if __name__ == "__main__":
    app.run(debug=True)
