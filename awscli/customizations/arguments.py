from awscli.arguments import CustomArgument


class OverrideRequiredArgsArgument(CustomArgument):
    """An argument that if specified makes all other arguments not required

    By not required, it refers to not having an error thrown when the
    parser parses the arguments. To obtain this argument's property of
    ignoring required arguments, subclass from this class and fill out
    the ``ARG_DATA`` parameter as described below.
    """

    # ``ARG_DATA`` follows the same format as a member of ``ARG_TABLE`` in
    # ``BasicCommand`` class as specified in
    # ``awscli/customizations/commands.py``.
    #
    # For example, an ``ARG_DATA`` variable would be filled out as:
    #
    # ARG_DATA =
    # {'name': 'my-argument',
    #  'help_text': 'This is argument ensures the argument is specified'
    #               'no other arguments are required'}
    ARG_DATA = {}

    def __init__(self, session):
        self._session = session
        self._register_argument_action()
        super(OverrideRequiredArgsArgument, self).__init__(**self.ARG_DATA)

    def _register_argument_action(self):
        self._session.register('building-argument-table-parser',
                               self.override_required_args)

    def override_required_args(self, argument_table, args, **kwargs):
        name_in_cmdline = '--' + self.name
        if name_in_cmdline in args:
            for arg_name in argument_table.keys():
                argument_table[arg_name].required = False
