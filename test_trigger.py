import unittest

import pytest
import trigger


class Test(unittest.TestCase):

    def test_args_1(self):
        args = trigger.parse_args('-p ptok -t ref -e foo-1=bar2 -e foo2=bar3 proj'.split())
        assert args.pipeline_token == 'ptok'
        assert args.target_ref == 'ref'
        assert args.env == ['foo-1=bar2', 'foo2=bar3']
        assert args.project_id == 'proj'

    def test_args_2(self):
        with pytest.raises(SystemExit):
            trigger.parse_args('-a foo -e foo1=bar2 foo2=bar3 dangling'.split())

    def test_parse_args_retry(self):
        args = trigger.parse_args('-a foo -p bar -t ref proj'.split())
        assert args.retry is False
        assert args.pid is None
        args = trigger.parse_args('-a foo -p bar -t ref --pid 123 proj'.split())
        assert args.retry is False
        assert args.pid == 123
        args = trigger.parse_args('-a foo -p bar -t ref -r --pid 123 proj'.split())
        assert args.retry is True
        assert args.pid == 123

    def test_parse_env(self):
        envs = trigger.parse_env(['foo-1=bar2', 'foo2=bar3='])
        assert envs == {'variables[foo-1]': 'bar2', 'variables[foo2]': 'bar3='}
