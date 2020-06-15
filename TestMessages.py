from BaseMessage import BaseMessage

class PatientDataMessage(BaseMessage):
    def __init__(self, sex, age):
        self.sex = sex
        self.age = age

        BaseMessage.__init__(self, "PatientData")

class StimLogMessage(BaseMessage):
    def __init__(self, log):
        self.log = log

        BaseMessage.__init__(self, "StimLog")

class TestStartMessage(BaseMessage):
    def __init__(self, start_time):
        self.start_time = start_time

        BaseMessage.__init__(self, "TestStart")

class TestEndMessage(BaseMessage):
    def __init__(self, end_time):
        self.end_time = end_time

        BaseMessage.__init__(self, "TestEnd")

class TestCalibrationMessage(BaseMessage):
    def __init__(self, calibration_time):
        self.calibration_time = calibration_time

        BaseMessage.__init__(self, "TestCalibration")

class ShutdownMessage(BaseMessage):
    def __init__(self, time):
        self.time = time

        BaseMessage.__init__(self, "Shutdown")