"""The shipping bounded context: available delivery methods and their rates.

This first slice models flat-rate shipping only: each channel offers a small set of
named methods, each with a fixed price and an estimated delivery window. A method is
*quoted* at checkout and its price is captured onto the order (the order context owns
that capture; the shipping context only knows methods and rates). Weight/table rates
and shipping zones are later slices.

Pure Python at the domain layer -- no Django, no DRF, no ORM.
"""
