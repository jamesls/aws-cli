import sys
import webbrowser

from botocore.compat import json

from awscli.compat import six, urlopen
from awscli.customizations.commands import BasicCommand


def register(event_handlers):
    event_handlers.register('building-command-table.iam',
                            add_console_command)


def add_console_command(command_table, session, **kwargs):
    WebConsoleCommand.add_command(command_table, session, **kwargs)


class WebConsoleCommand(BasicCommand):
    NAME = 'web-console'

    DESCRIPTION = (
        'Open an interactive web console for an assumed role.  This only '
        'works if the profile being used has assume role credentials, '
        "that is, you've configure a 'role_arn' in your config file."
    )

    def _run_main(self, parsed_args, parsed_globals):
        sts = self._session.create_client('sts')
        creds = self._session.get_credentials()
        if creds.token is None or not creds.method.starstwith('assume-'):
            sys.stderr.write("Can only open a web-console from a profile "
                             "that assumes a role.")
            return
        json_blob = {
            'sessionId': creds.access_key,
            'sessionKey': creds.secret_key,
            'sessionToken': creds.token,
        }
        query_params = {
            'Action': 'getSigninToken',
            'Session': json.dumps(json_blob),
        }
        encoded_query = six.moves.urllib.parse.urlencode(query_params)
        url = 'https://signin.aws.amazon.com/federation?%s' % encoded_query
        response = urlopen(url).read()
        token = json.loads(response)['SigninToken']
        final_query_params = {
            'Destination': "https://console.aws.amazon.com/",
            'Action': 'login',
            'Issuer': '',
            'SigninToken': token
        }
        final_encoded = six.moves.urllib.parse.urlencode(final_query_params)
        final_url = (
            'https://signin.aws.amazon.com/federation?%s' % final_encoded)
        webbrowser.open(final_url)
