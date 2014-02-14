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
from tests import BaseAWSHelpOutputTest
import six
import mock

from awscli.customizations import backcompat


class TestAliasCommands(BaseAWSHelpOutputTest):
    def assert_command_is_aliased(self, service, current, alias_name):
        # We verify the command is aliased by actually trying it.
        # We call help for both the current command and the alias
        # command, and verify they both work.
        # We then look at the help at the service level, and verify
        # that the alias command is hidden.
        self.driver.main([service, current, 'help'])
        self.assert_contains(current)
        self.driver.main([service, alias_name, 'help'])
        self.assert_contains(current)
        # Verify alias command is hidden
        self.driver.main([service, 'help'])
        self.assert_not_contains(alias_name)

    def test_verify_alias_commands(self):
        self.assert_command_is_aliased('elasticbeanstalk',
                                       'swap-environment-cnames',
                                       alias_name='swap-environment-cnam-es')
        self.assert_command_is_aliased(
            'storagegateway',
            'create-cached-iscsi-volume',
            alias_name='create-cachedi-scsi-volume')
        self.assert_command_is_aliased(
            'storagegateway',
            'describe-cached-iscsi-volumes',
            alias_name='describe-cachedi-scsi-volumes')
        self.assert_command_is_aliased(
            'storagegateway',
            'describe-stored-iscsi-volumes',
            alias_name='describe-storedi-scsi-volumes')

    def test_attempt_to_alias_nonexistant_command(self):
        # session supports the same interface as the event emitter
        # so we can use a session as well in the CommandAliaser.
        alias = backcompat.CommandAliaser(self.driver.session)
        alias.alias_command('cloudformation', 'command-does-not-exist',
                            alias_name='anything')
        # Now, we don't want to bring down the CLI in the case of
        # an error, we just want to log an error.
        captured_stderr = six.StringIO()
        with mock.patch('sys.stderr', captured_stderr) as f:
            self.driver.main(['cloudformation', 'help'])
        self.assertIn(
            'Attempted to alias a nonexistant command: command-does-not-exist',
            captured_stderr.getvalue())
