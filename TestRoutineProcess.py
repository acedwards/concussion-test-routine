from TestRoutine.test_routine import Menu, TestSession
from BaseProcess import BaseProcess

# class TestRoutine(BaseProcess):
class TestRoutine:
    def __init__(self, queues):
        self.id = 0
        self.name = 'Test Routine'
        self.queues = queues
        self.process_names = {
            'Test Routine': 0,
            'Concussion Model': 1,
            'Pupil Tracking': 2,
            'Saccade Detector': 3
        }

    def run(self):
        self.menu = Menu(self.queues, self.process_names)
        self.test_session = TestSession(self.queues, self.process_names, num_blocks=1)
        self.menu.run()
        self.test_session.run()
