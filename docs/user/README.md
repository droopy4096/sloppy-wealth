# Getting started

Sloppy Wealth is a ballpark calculator for a household's big financial questions: buy or
lease, rent or buy, when a house breaks even, when you can retire. You describe your
household as a set of items (incomes, expenses, accounts, properties, mortgages, vehicles,
pensions) and the app plays them forward month by month over the years you choose.

## Run it
You need Python 3. From a copy of the repository:

```
cd webapp
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt   # once
.venv/bin/python app.py
```

Then open http://127.0.0.1:5000 in your browser.

## Your data stays with you
The scenario you build lives in your browser tab while you work. **Save** (in the top
menu) downloads it as a JSON file, which you can **Load** again later, compare with
another, or share. The app keeps nothing: there are no accounts and no database. The
tab's copy is gone once the tab is closed, so save before you close it; the app warns you
about unsaved changes.

## The menu
| Item | What it does |
|---|---|
| Canada / United States | The scenario's jurisdiction: tax rules, account types and limits. Click it to change it in the scenario's settings. |
| **New** | Start an empty scenario, choosing its jurisdiction. |
| **Builder** | Your scenario as cards, grouped by person and by category. |
| **Builder (flat)** | The same items as one list, with all the "add" forms grouped by category. |
| **Timeline** | When each item starts and ends, and what is tied to what. |
| **Run** | The month-by-month results: cash, investments, property and vehicles, debts and net worth, also in today's dollars. |
| **Save** / **Load** | Download the scenario as a file; open a saved one. |
| **Compare** | Run two saved scenarios side by side. |
| **Help** | This guide. |

## Building a scenario
- **Settings.** Open the **Scenario** card (under **Household**) to set the name, the
  horizon (first and last month), the opening cash, tax rates and inflation, and whose
  dollars the "today's dollars" figures are in.
- **Adding.** Each category and card has **+ Add** buttons for the items that belong
  there: a vehicle's insurance is added on the vehicle's card, so it is tied to it.
- **Icons on a card.** **+** shows what can be added to it, the green pencil edits it, the
  red bin deletes it (with everything tied to it, after asking).
- **Switching on and off.** The checkmark at the left of a card or row switches the item
  off, and everything tied to it follows. Switched-off items stay in the scenario, so you
  can compare setups by switching them back on: no need to delete anything.
- **Estimates.** Cards show a greyed figure per month, a quick estimate from the item's
  own amounts. **Run** gives the exact figures.

## Calculators
The purple chart icon opens a calculator for that item:

- **Property: break-even and rent equivalent.** Each month, what a sale would bring
  (after selling costs, the mortgage and its early-closure penalty) against everything
  paid for the property, and the rent that would have cost the same.
- **Vehicle: cost of ownership.** Each month, everything paid for the vehicle so far, less
  its value, per month owned.

## Tutorials
Step by step, with screenshots and an example scenario to load:

- [Lease or buy a vehicle](vehicle-lease-or-own.md): would it be cheaper to lease a vehicle
  than to keep and maintain one for 20 years?
- [When a house breaks even](house-break-even.md): when can I sell the house without losing
  the money I put into buying and maintaining it?

More are coming, one for each question in the project's README.

## Good to know
- It is a ballpark: as good as the figures you enter. Amounts are rounded to cents and
  the model is simple on purpose.
- It understands Canadian and US accounts and taxes (RRSP, TFSA, RESP; 401(k), IRA, HSA).
  Other countries may lack features they need.
