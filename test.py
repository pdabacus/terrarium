#!/usr/bin/env python3
import pytest
import unittest
from terrarium import Value
from terrarium import ConstantValue
from terrarium import VariableValue
from terrarium import IndicatorValue
from terrarium import TimeIndicatorValue
from terrarium import GPIOIndicatorValue
from terrarium import Values

class TestValues(unittest.TestCase):
    def test_const(self):
        v = ConstantValue("pi", "3.14")
        values = Values([v])
        assert values.pi == "3.14"
        assert values.pi != 3.14
        with pytest.raises(ValueError, match=r'can.?t.+cons'):
            values.pi = 3
        assert values.pi == "3.14"
    def test_var(self):
        p = ConstantValue("pi", 3.14)
        e = VariableValue("e", "2")
        values = Values([p, e])
        assert values.pi == 3.14
        assert values.e == "2"
        values.e = (1+1/2)**2
        assert values.e == 2.25


if __name__ == "__main__":
    pytest.main([__file__])
