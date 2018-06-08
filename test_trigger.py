import unittest

import pytest
import trigger


class Test(unittest.TestCase):

    def test_args_1(self):
        args = trigger.parse_args('-a foo -e foo1=bar2 -e foo2=bar3 proj'.split())
        assert args.api_token == 'foo'
        assert args.env == ['foo1=bar2', 'foo2=bar3']
        assert args.project_id == 'proj'

    def test_args_2(self):
        with pytest.raises(SystemExit):
            trigger.parse_args('-a foo -e foo1=bar2 foo2=bar3 dangling'.split())

    def test_pargs_envs(self):
        envs = trigger.parse_envs(['foo1=bar2', 'foo2=bar3'])
        assert envs == [dict(key='foo1', value='bar2'), dict(key='foo2', value='bar3')]
