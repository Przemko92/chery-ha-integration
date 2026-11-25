"""Readable text for the tspconsole response codes Chery Europe answers with.

The backend always replies with HTTP 200 and puts the real outcome in ``code``:
the accepted ones live in ``TSP_COMMAND_SUCCESS`` and every other code is a
refusal. Only a handful of the refusals can be explained instead of just shown
as a raw code, so this map carries those texts and the rest stay verbatim.
"""

from __future__ import annotations

CODE_MEANING = {
    # The car runs one command at a time: a command that arrives while the
    # previous one is still being executed is NOT executed. Transient, so the
    # same command a few seconds later goes through.
    "A00082": "auto zajęte — wykonuje inną komendę, ponów za kilka sekund",
    "A00084": "auto nie pozwala na tę funkcję (brak uprawnień do komendy)",
    "A00089": "nieprawidłowy taskId — komenda wymaga potwierdzenia PIN-em",
    "A00546": "nieprawidłowy taskId — zły scenariusz potwierdzenia PIN-em",
    "A00567": "niekompletne dane potwierdzenia PIN-em",
    "A00000": "sesja wygasła — zaloguj się ponownie kodem OTP",
    "A07312": "auto odmawia kolejnego wybudzania — spróbuj później",
    "A07900": "auto śpi lub jest nieosiągalne (albo podpis / car_token jest zły)",
}


def describe_code(code: object) -> str | None:
    """Return the readable text for ``code``, or None when the code is unknown."""
    if code is None:
        return None
    return CODE_MEANING.get(str(code))
