"""The ``person`` item type (ADR-0061): compiles to nothing; the Household reads the
person items when it is built (``household.persons``, see ``persons.py``)."""
from ..compiler import item_type


@item_type("person")
def compile_person(item, ctx):
    return []
