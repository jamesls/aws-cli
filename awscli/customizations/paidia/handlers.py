"""The paidia extensions.

This is a collection extensions to the CLI that are experimental
and not intended for general use.  This is a proving ground for
feature that could end up back in the original AWS CLI.

"""
from awscli.customizations.paidia import configure
from awscli.customizations.paidia import login


def awscli_initialize(event_handlers):
    configure.register(event_handlers)
    login.register(event_handlers)
