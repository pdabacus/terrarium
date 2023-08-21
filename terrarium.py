#!/usr/bin/env python3
import logging
import re
import time
import math
import json

VERSION = "1.0.0"
LOG_FILE = "/home/pavan/terrarium/log.txt"
CONFIG_FILE = "/home/pavan/terrarium/config.json"

logger = logging.getLogger("terrarium")
logger.setLevel(logging.DEBUG)
tfmt = "%Y-%m-%d %H:%M:%S"
fmt = logging.Formatter("%(asctime)s: %(name)s %(levelname)s: %(message)s",tfmt)
logfile_handler = logging.FileHandler(LOG_FILE, mode="a", encoding="utf-8")
logfile_handler.setFormatter(fmt)
stdout_handler = logging.StreamHandler()
stdout_handler.setFormatter(fmt)
logger.addHandler(logfile_handler)
logger.addHandler(stdout_handler)
logger.debug("starting log")


class Value():
    def __init__(self, name):
        self.name = name
    def getx(self):
        return 0
    def setx(self, newx):
        return 0

class VariableValue(Value):
    def __init__(self, name, x):
        super().__init__(name)
        self._x = x
    def getx(self):
        return self._x
    def setx(self, newx):
        logger.info("values.%s updated %s -> %s" % (self.name, self._x, newx))
        self._x = newx
        return self._x

class IndicatorValue(Value):
    def __init__(self, name, period, getval):
        super().__init__(name)
        self.period = period
        self._getter = getval
    def getx(self):
        return self._getter()
    def setx(self, newx):
        logger.error("cant set value for indicator %s" % self.name)
        return self._getter()

class TimeIndicatorValue(IndicatorValue):
    def __init__(self, name, period, trigger):
        self.timeformat = trigger["timeformat"]
        self.parse_values = {
            "H": 3600,
            "M": 60,
            "S": 1
        }
        class TimeRange:
            def __init__(slf, a, b):
                slf._str = "[%s, %s)" % (a, b)
                slf.a = self._parse_time(a)
                slf.b = self._parse_time(b)
                slf.fmt = fmt
            def __repr__(self):
                return self._str
            def contains(slf, other):
                if type(other) == str:
                    other = self._parse_time(other)
                return (slf.a <= other < slf.b)
        self.ranges = list()
        for r in trigger["ranges"]:
            self.ranges.append((TimeRange(r["a"], r["b"]), r["value"]))
        def getval():
            t = time.localtime()
            now = 0
            now += t.tm_hour * self.parse_values["H"]
            now += t.tm_min * self.parse_values["M"]
            now += t.tm_sec * self.parse_values["S"]
            logger.info(
                "values.%s: %s:%s:%s" % (name, t.tm_hour, t.tm_min, t.tm_sec)
            )
            for rrange, val in self.ranges:
                if rrange.contains(now):
                    return val
            logger.error(
                "couldn't find time %s in ranges for values.%s" % (now, name)
            )
        super().__init__(name, period, getval)
    def _parse_time(self, time):
        parsefmt = self.timeformat
        encountered_times = dict((x,0) for x in self.parse_values)
        for timefmt in self.parse_values:
            named_group_re = "(?P<%s>\\\\d{2})" % timefmt
            pfmt = re.sub("%"+timefmt, named_group_re, parsefmt, 1)
            if pfmt != parsefmt:
                encountered_times[timefmt] = 1
                parsefmt = pfmt
        matches = re.search(parsefmt, time)
        converted_time = 0
        for timefmt, value in self.parse_values.items():
            if encountered_times[timefmt]:
                converted_time += int(matches.group(timefmt)) * value
        return converted_time

class GPIOIndicatorValue(IndicatorValue):
    def __init__(self, name, period, trigger):
        self.pin = trigger["pin"]
        self.samples = trigger["samples"]
        self.sample_dt = trigger["sample_dt"]
        class VoltageRange:
            def __init__(slf, a, b):
                slf._str = "[%s, %s)" % (a, b)
                slf.a = a
                slf.b = b
            def __repr__(self):
                return self._str
            def contains(slf, other):
                return (slf.a <= other < slf.b)
        self.ranges = list()
        for r in trigger["ranges"]:
            self.ranges.append((VoltageRange(r["a"], r["b"]), r["value"]))
        def getval():
            import random
            measurements = list()
            for n in range(self.samples):
                #TODO read value from self.pin
                measured = 0.4 + (random.random()-0.5)/20
                measurements.append(measured)
                time.sleep(self.sample_dt)
            mean = sum(x for x in measurements) / self.samples
            var = sum(x*x for x in measurements) / self.samples - mean*mean
            std = math.sqrt(var)
            xs = [float("%f" % x) for x in measurements]
            logger.info(
                "values.%s: samples %s, mean %f, std %f" % (name, xs, mean, std)
            )
            for rrange, val in self.ranges:
                if rrange.contains(mean):
                    return val
            logger.error(
                "couldn't find value %s in ranges for values.%s" % (mean, name)
            )
        super().__init__(name, period, getval)

class Values():
    def __new__(cls, value_list):
        cls.instance = super(Values, cls).__new__(cls)
        cls.instance.state = dict()
        for value in value_list:
            cls.instance.state[value.name] = value
            def v_get(self, n=value.name):
                return self.state[n].getx()
            def v_set(self, newx, n=value.name):
                return self.state[n].setx(newx)
            prop = property(v_get, v_set)
            setattr(Values, value.name, prop)
        return cls.instance

class Control():
    def __init__(self, name, setup=None, conditions=None):
        self.name = name
        self.setup = lambda: None
        if setup:
            self.setup = lambda: setup["type"]
        self.conditions = []
        if conditions:
            self.conditions = [(x,y) for x,y in conditions.items() ]
            self.run = lambda: print(self.conditions)
    def setup(self):
        return self.setup()
    def __call__(self):
        return self.run()

class Controls():
    instance = None
    def __new__(cls, control_list):
        cls.instance = super(Controls, cls).__new__(cls)
        cls.instance.state = dict()
        for control in control_list:
            cls.instance.state[control.name] = control
            setattr(Controls, control.name, control)
        return cls.instance

def parse_config(config_path):
    with open(config_path, "r") as file:
        config = json.load(file)
    variables = list()
    indicators = list()
    for value in config["values"]:
        value_type = value["type"].lower().strip()
        if "var" in value_type:
            var_name = value["name"]
            var_default = value["default"]
            logger.info("values.%s default %s" % (var_name, var_default))
            variables.append(VariableValue(var_name, var_default))
        elif "ind" in value_type:
            ind_name = value["name"]
            ind_period = value["period"]
            ind_trigger = value["trigger"]
            trigger_type = ind_trigger["type"].lower().strip()
            if "tim" in trigger_type:
                ind = TimeIndicatorValue(ind_name, ind_period, ind_trigger)
                logger.info(
                    "values.%s (%ss): %s" % (ind_name, ind_period, ind.ranges)
                )
                indicators.append(ind)
            elif "gpio" in trigger_type:
                pin = ind_trigger["pin"]
                logger.info(
                    "values.%s (%ss): gpio pin %s" % (ind_name, ind_period, pin)
                )
                indicators.append(
                    GPIOIndicatorValue(ind_name, ind_period, ind_trigger)
                )
            else:
                logger.error("invalid config trigger type %s" % trigger_type)
        else:
            logger.error("invalid config value type %s unknown" % value["type"])
    values = Values(variables + indicators)
    control_list = list()
    for control in config["controls"]:
        ctl_name = control["name"]
        ctl_setup = None
        if "setup" in control:
            ctl_setup = control["setup"]
        if "conditions" in control:
            ctl = Control(ctl_name, ctl_setup, control["conditions"])
            logger.info("controls.%s initialized" % ctl_name)
            control_list.append(ctl)
    controls = Controls(control_list)
    return values, controls

def main():
    values, controls = parse_config(CONFIG_FILE)
    logger.debug("initialized values state and controls config")

    print("light_on:")
    print(values.light_on)
    values.light_on = 0
    print(values.light_on)

    print("light_time:")
    print(values.light_time)

    print("soil_sensor:")
    print(values.state["soil_sensor"].period)
    print(values.soil_sensor)

    #for vname,val in values.state.items():
    #    print(vname)
    #    print(type(val))
    #    print(isinstance(val, IndicatorValue))

    print("ctl")
    print(controls.state)
    print(controls.light_switch())


if __name__ == "__main__":
    main()
