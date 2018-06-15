import unittest

import pytest
import trigger


class Test(unittest.TestCase):

    def test_args_1(self):
        args = trigger.parse_args('-a atok -p ptok -e foo-1=bar2 -e foo2=bar3 proj'.split())
        assert args.api_token == 'atok'
        assert args.pipeline_token == 'ptok'
        assert args.env == ['foo-1=bar2', 'foo2=bar3']
        assert args.project_id == 'proj'

    def test_args_2(self):
        with pytest.raises(SystemExit):
            trigger.parse_args('-a foo -e foo1=bar2 foo2=bar3 dangling'.split())

    def test_pargs_env(self):
        envs = trigger.parse_env(['foo-1=bar2', 'foo2=bar3'])
        assert envs == {'variables[foo-1]': 'bar2', 'variables[foo2]': 'bar3'}
