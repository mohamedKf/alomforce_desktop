# AlomForce Desktop

Office application for the AlomForce aluminium profile business: catalog,
stock, orders, clients, invoices and delivery notes.

Built with PySide6 (Qt). It has no database of its own — it is a client of the
AlomForce Django backend.

## Setup

    python3 -m venv .venv
    .venv/bin/pip install -r requirements.txt

## Run

The backend must be running first (in the `alomforce` project):

    .venv/bin/python manage.py runserver

Then:

    .venv/bin/python main.py

Point it at a different backend with:

    ALOMFORCE_API=https://api.example.com/api/ .venv/bin/python main.py

## Layout

    main.py            entry point, window, login/shell routing
    app/api.py         REST client — every call runs off the UI thread
    app/session.py     tokens and signed-in user, persisted between runs
    app/i18n.py        English source strings + Hebrew/Arabic, RTL handling
    app/theme.py       Qt style sheet
    app/views/         login, shell (sidebar), catalog

## Languages

English, Hebrew and Arabic. Hebrew and Arabic mirror the entire window to RTL.
