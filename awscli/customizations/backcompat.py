# Copyright 2014 Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"). You
# may not use this file except in compliance with the License. A copy of
# the License is located at
#
#     http://aws.amazon.com/apache2.0/
#
# or in the "license" file accompanying this file. This file is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF
# ANY KIND, either express or implied. See the License for the specific
# language governing permissions and limitations under the License.
"""
Backwards Compatibility Fixes
-----------------------------

This module contains customizations to make various features
backwards compatible for users.

"""
import copy
import logging
from functools import partial

LOG = logging.getLogger(__name__)


def register_backcompat(event_handler):
    alias = CommandAliaser(event_handler)
    # This is needed because we had a bug in our case inflection code where we
    # were translating names like SwapEnvironmentCNAMEs to
    # swap-environment-cnam-es.
    # We fixed the bug but we need to support the previously
    # mispelled name.
    alias.alias_command(
        service='elasticbeanstalk',
        current='swap-environment-cnames',
        alias_name='swap-environment-cnam-es')
    alias.alias_command(
        service='storagegateway',
        current='create-cached-iscsi-volume',
        alias_name='create-cachedi-scsi-volume')
    alias.alias_command(
        service='storagegateway',
        current='describe-cached-iscsi-volumes',
        alias_name='describe-cachedi-scsi-volumes')
    alias.alias_command(
        service='storagegateway',
        current='describe-stored-iscsi-volumes',
        alias_name='describe-storedi-scsi-volumes')


class CommandAliaser(object):
    def __init__(self, event_handler):
        self._event_handler = event_handler
        # Mapping of service_name, current_operation -> alias
        self._alias = {}

    def alias_command(self, service, current, alias_name):
        if service not in self._alias:
            self._event_handler.register(
                'building-command-table.%s' % service,
                self._alias_command)
        self._alias.setdefault(service, {})[current] = alias_name

    def _alias_command(self, command_table, name, **kwargs):
        for original, alias in self._alias[name].items():
            try:
                copied = copy.copy(command_table[original])
            except KeyError:
                # We don't want to bring down the CLI,
                # so we log an error message and continue.
                LOG.error("Attempted to alias a nonexistant "
                          "command: %s", original)
                continue
            # Setting this flag will prevent it from
            # showing up in the man page/html docs.
            copied._UNDOCUMENTED = True
            command_table[alias] = copied
