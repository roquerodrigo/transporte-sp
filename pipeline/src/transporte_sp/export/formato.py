"""Numbers and dates as they are written in Brazil.

Comma for the decimal, dot for the thousands, ``dd/mm/aaaa`` for dates. Done here rather
than with ``locale`` because that would make the generated pages depend on which locales
happen to be installed on the machine running the pipeline.
"""

from __future__ import annotations

from datetime import date

# Line lengths are published to one decimal. The sources place the same station up to a few
# hundred metres apart, so a length written to the metre would claim a precision the data
# does not have. The full value stays in network.json.
CASAS_EXTENSAO = 1


def numero(valor: float, casas: int = 0) -> str:
    """``1234.5`` → ``1.234,5``."""
    texto = f"{valor:,.{casas}f}"
    return texto.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def quilometros(valor: float) -> str:
    """``12.765`` → ``12,8 km``."""
    return f"{numero(valor, CASAS_EXTENSAO)} km"


def data(valor: date | str) -> str:
    """``1974-09-14`` → ``14/09/1974``."""
    if isinstance(valor, str):
        try:
            valor = date.fromisoformat(valor[:10])
        except ValueError:
            return valor
    return valor.strftime("%d/%m/%Y")
