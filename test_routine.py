from enum import Enum
import time
from random import triangular, randint
import pygame
import cv2
import numpy
from pygame.locals import *
import pygame_gui
from queue import Empty as QueueEmpty

from multiprocessing import Queue
from BaseProcess import BaseProcess

import TestRoutine.test_config as test_config
from TestRoutine.TestMessages import PatientDataMessage, TestStartMessage, TestEndMessage, TestCalibrationMessage, StimLogMessage, ShutdownMessage

class BlockType(Enum):
    PRO = 0
    ANTI = 1

class Location(Enum):
    LEFT = 0
    RIGHT = 1
    CENTRE = 2

class StimLog:
    def __init__(self, id):
        self.id = id
        self.location = None
        self.start_time = None # time stim appears
        self.end_time = None # time stim disappears

class SaccadeBlock:
    def __init__(self, total_reps=test_config.SACCADE_REPS, starting_type=BlockType.PRO, num=1):
        self.total_reps = total_reps
        self.reps_complete = 0
        self.block_complete = False
        self.areas_to_update = []
        self.type = starting_type
        self.target_drawn = False
        self.set_in_prog = False
        self.set_start_time = None
        self.current_stim_rect = None
        self.current_stim_log = None
        self.current_delay = None
        self.num = num
    
    def reset_for_next_block(self):
        self.reps_complete = 0
        self.block_complete = False
        self.target_drawn = False
        self.areas_to_update = []
        self.num += 1

    def update_reps(self):
        if not self.block_complete:
            self.reps_complete += 1
            if self.reps_complete == self.total_reps:
                self.block_complete = True

    def start_set(self):
        # a set being centre target being displayed for random amount of time, followed by stim being displayed for STIM_DELAY
        # reset for new set
        self.current_stim_log = StimLog(self.reps_complete)
        self.current_stim_rect = None
        self.current_delay = self.get_target_delay()
        self.set_start_time = None

        if not self.target_drawn:
            self.draw_centre_target()
        else:
            # target is already drawn so time won't be updated when frame is drawn
            self.update_set_start_time()
        self.set_in_prog = True
        

    def draw_centre_target(self):
        self.areas_to_update.append(pygame.draw.circle(test_config.screen, test_config.BLACK, [test_config.centre_x, test_config.centre_y], test_config.stim_radius))
        self.target_drawn = True


    def draw_stimulus(self, stimulus_delay_event):
        if randint(0, 1) == 0:
            self.areas_to_update.append(pygame.draw.circle(test_config.screen, test_config.BLACK, test_config.left_stim_coords, test_config.stim_radius))
            self.current_stim_log.location = Location.LEFT
        else:
            self.areas_to_update.append(pygame.draw.circle(test_config.screen, test_config.BLACK, test_config.right_stim_coords, test_config.stim_radius))
            self.current_stim_log.location = Location.RIGHT
        self.current_stim_rect = self.areas_to_update[-1]
        pygame.time.set_timer(stimulus_delay_event, test_config.STIM_DELAY)


    def get_target_delay(self):
        # delay between centre target appearing and stimulus appearing should be between 1000 - 3500 ms
        # with an average of 1500 ms - I tried my best! :/
        # https://docs.python.org/2/library/random.html#random.triangular
        delay = int(triangular(1000, 3500, 1200))
        return delay
    
    def update_set_start_time(self):
        self.set_start_time = pygame.time.get_ticks()

class TestSession:
    test_intro = ["In order to calibrate our device, please look at the centre target.", "When you are focussed on it, press the spacebar."]
    antisaccade_instructions = ["Look at the centre target.", "As soon as a new dot appears look in the opposite direction as fast as you can.", "", "You will probably sometimes make some mistakes,", "and this is perfectly normal."]
    prosaccade_instructions = ["Please focus on the centre target. When a dot appears to the left or right, look directly at it."]
    test_outro = ["Thank you for completing the concussion indicator test.", "Your results will appear shortly."]

    instruction_display_time = 8000 # 8 sec

    message_delay_event = USEREVENT + 1
    stimulus_delay_event = USEREVENT + 2
    centre_target_delay_event = USEREVENT + 3

    message_params = [pygame.font.match_font('timesnewroman'), 22, test_config.BLACK]
    
    def __init__(self, queues, process_names, num_blocks=test_config.SACCADE_BLOCKS):
        self.test_started = False
        self.test_ended = False
        self.received_results = False
        self.block_started = False
        self.current_block = SaccadeBlock(starting_type=BlockType.ANTI)
        self.running = True
        self.waiting_for_delay = False
        self.waiting_for_input = True
        self.stim_log = []
        self.num_blocks = num_blocks
        # multiprocessing
        self.queues = queues
        self.process_names = process_names
    
    def start_test(self):
        if not self.test_started:
            self.display_message(*self.message_params, self.test_intro, 0)
            self.current_block.draw_centre_target()
            self.test_started = True
            self.waiting_for_input = True
            
            # send start time to pupil tracking and saccade detection
            msg = TestStartMessage(time.time())
            self.queues[self.process_names['Pupil Tracking']].put(msg)
            self.queues[self.process_names['Saccade Detector']].put(msg)
        else:
            print('Test already started!')
    
    def end_test(self):
        self.display_message(*self.message_params, self.test_outro, 0)
        self.test_ended = True
        # send end message to saccade detection and pupil tracking
        msg = TestEndMessage(time.time())
        self.queues[self.process_names['Pupil Tracking']].put(msg)
        self.queues[self.process_names['Saccade Detector']].put(msg)

        # send stim log to saccade detection
        print("[TestRoutine][DEBUG] Sending stim log")
        msg = StimLogMessage(self.stim_log)
        self.queues[self.process_names['Saccade Detector']].put(msg)
    
    def start_block(self):
        if self.current_block.type == BlockType.ANTI:
            self.display_instructions(self.antisaccade_instructions)
        else:
            self.display_instructions(self.prosaccade_instructions)
        self.block_started = True
    
    def show_results(self, results):
        self.reset_screen()

        font_object = pygame.font.Font(pygame.font.match_font('timesnewroman'), 22)
        
        we_predict = font_object.render("We have predicted a concussion likelihood of", True, (test_config.BLACK))
        we_predict_rect = we_predict.get_rect(center=(test_config.centre_x, test_config.centre_y - 125))
        test_config.screen.blit(we_predict, we_predict_rect)

        confirm = font_object.render("Please confirm this data with a medical professional.", True, (test_config.BLACK))
        confirm_rect = confirm.get_rect(center=(test_config.centre_x, test_config.centre_y + 30))
        test_config.screen.blit(confirm, confirm_rect)

        font_object = pygame.font.Font(pygame.font.match_font('timesnewroman'), 50)
        results_text = font_object.render(str(results.probability)+"%", True, (test_config.BLACK))
        results_text_rect = results_text.get_rect(center=(test_config.centre_x, test_config.centre_y - 80))
        test_config.screen.blit(results_text, results_text_rect)

        font_object = pygame.font.Font(pygame.font.match_font('timesnewroman'), 14)
        exit_text = font_object.render("Press ESC at any time to exit the test", True, (test_config.BLACK))
        exit_text_rect = exit_text.get_rect(center=(test_config.centre_x, test_config.centre_y + 200))
        test_config.screen.blit(exit_text, exit_text_rect)

        pygame.display.update()

    def display_instructions(self, instructions):
        self.display_message(*self.message_params, instructions, self.instruction_display_time)

    def display_message(self, font, size, colour, messages, display_time):
        self.reset_screen()
        font_object = pygame.font.Font(font, size)
        offset = 40
        for message in messages:
            if message:
                rendered_text = font_object.render(message, True, (colour))
                rendered_text_rect = rendered_text.get_rect(center=(test_config.centre_x, offset))
                test_config.screen.blit(rendered_text, rendered_text_rect)
            offset += 30
        pygame.display.update()
        if display_time != 0:
            pygame.time.set_timer(self.message_delay_event, display_time)
            self.waiting_for_delay = True
    
    def process_events(self):
        for event in pygame.event.get():
            if event.type == QUIT:
                self.running = False
            elif event.type == KEYDOWN:
                if event.key == K_SPACE:
                    if self.test_started and self.waiting_for_input:
                        #send calibration flag to saccade detector
                        msg = TestCalibrationMessage(time.time())
                        self.queues[self.process_names['Saccade Detector']].put(msg)
                        self.reset_screen()
                        self.waiting_for_input = False
                        self.current_block.target_drawn = False
                if event.key == K_ESCAPE:
                    self.running = False
            elif event.type == self.message_delay_event:
                self.reset_screen()
                pygame.time.set_timer(self.message_delay_event, 0)
                self.waiting_for_delay = False
            elif event.type == self.stimulus_delay_event:
                # stim has been displayed for STIM_DELAY time
                # time to get rid of it
                test_config.screen.blit(test_config.screen, self.current_block.current_stim_rect)
                self.current_block.areas_to_update.append(self.current_block.current_stim_rect)
                
                # reset stim timer, update rep and complete set
                pygame.time.set_timer(self.stimulus_delay_event, 0)
                self.current_block.update_reps()
                self.current_block.set_in_prog = False
                self.waiting_for_delay = False
                self.draw_frame()
            # menu_manager.process_events(event)
    
    def draw_frame(self):
        if (len(self.current_block.areas_to_update) > 0):
            if not self.waiting_for_input: # if not calibrating
                if self.current_block.set_in_prog:
                    if not self.current_block.current_stim_rect: #drawing centre target
                        self.current_block.update_set_start_time()

                    elif not self.current_block.current_stim_log.start_time: #drawing stim
                        # setting start time when stim is actually drawn for better accuracy
                        self.current_block.current_stim_log.start_time = time.time()
                elif self.current_block.current_stim_log.start_time: #removing stim
                    self.current_block.current_stim_log.end_time = time.time()
                    self.stim_log.append(self.current_block.current_stim_log)
            pygame.display.update(self.current_block.areas_to_update) 
            self.current_block.areas_to_update = []
    
    def run(self):
        test_config.screen.fill(test_config.WHITE)
        pygame.display.flip()
        while self.running:
            self.process_events()
            if not self.test_started:
                self.start_test()
            elif self.test_ended and not self.received_results:
                # results = 0
                try:
                    results = self.queues[self.process_names['Test Routine']].get_nowait()

                    if results.id == "ConcussionProbability":
                        print("[TestRoutine][INFO] Received concussion probability")
                        self.received_results = True
                        self.show_results(results)
                        self.waiting_for_input = True
                except QueueEmpty:
                    pass
                
            else:
                if self.waiting_for_input or self.waiting_for_delay:
                    # do nothing
                    continue
                if not self.block_started:
                    # Block hasn't started, display instructions and buckle your seatbelts
                    self.start_block()
                elif self.current_block.block_complete:
                    # Block is complete.
                    if self.current_block.num < self.num_blocks:
                        # If there's still another block to go, switch type and start over
                        self.current_block.reset_for_next_block()
                        self.current_block.type = BlockType.ANTI if self.current_block.type == BlockType.PRO else BlockType.PRO
                        self.block_started = False
                    else:
                        # All blocks are complete. Display test outro.
                        self.end_test()
                else:
                    # Block is in progress
                    if not self.current_block.set_in_prog:
                        self.current_block.start_set()
                    elif (pygame.time.get_ticks() - self.current_block.set_start_time) >= self.current_block.current_delay:
                        # target has been by itself long enough, draw stim
                        self.waiting_for_delay = True
                        self.current_block.draw_stimulus(self.stimulus_delay_event)

            self.draw_frame()
        print('quitting...')
        msg = ShutdownMessage(time.time())
        self.queues[self.process_names['Concussion Model']].put(msg)
        self.queues[self.process_names['Pupil Tracking']].put(msg)
        self.queues[self.process_names['Saccade Detector']].put(msg)
        print('[TestRoutine][INFO] exited at {}'.format(msg.time))
        pygame.display.quit()
        pygame.quit()
    
    def reset_screen(self):
        test_config.screen.fill(test_config.WHITE)
        pygame.display.flip()

class Menu:
    # gui setup
    pygame.init()

    menu_manager = pygame_gui.UIManager((test_config.width, test_config.height))
    BUTTON_WIDTH = 150
    BUTTON_HEIGHT = 50
    BUTTON_SIZE = (BUTTON_WIDTH, BUTTON_HEIGHT)
    loading_event = USEREVENT + 4

    def __init__(self, queues, process_names, video_device=0):
        self.queues = queues
        self.process_names = process_names
        self.sex_selection = None
        self.data_entry_elements = []
        self.clock = pygame.time.Clock()
        self.cam = cv2.VideoCapture(video_device) #640x480 by default
        self.cam.set(3,640)
        self.cam.set(4,480)
        self.show_cam = False
        self.cont_button_2 = None

    def create_data_entry_elements(self):
        self.sex_dropdown = pygame_gui.elements.UIDropDownMenu(['Male', 'Female'], 
                                                        starting_option='Unselected',
                                                        manager=self.menu_manager,
                                                        relative_rect=pygame.Rect((test_config.centre_x, test_config.centre_y - 3*self.BUTTON_HEIGHT+25), self.BUTTON_SIZE)) 
        self.data_entry_elements.append(self.sex_dropdown)
        self.dropdown_label = pygame_gui.elements.UILabel(relative_rect=pygame.Rect(test_config.centre_x - 3*self.BUTTON_WIDTH/2, test_config.centre_y - 3*self.BUTTON_HEIGHT+25, 200, 50),
                                                        text='Patient Sex:',
                                                        manager=self.menu_manager)
        self.data_entry_elements.append(self.dropdown_label)
        self.cont_button = pygame_gui.elements.UIButton(relative_rect=pygame.Rect((test_config.centre_x - 3*self.BUTTON_WIDTH/2, test_config.centre_y + 200), self.BUTTON_SIZE),
                                                text='Continue',
                                                manager=self.menu_manager)
        self.data_entry_elements.append(self.cont_button)
        self.age_entry = pygame_gui.elements.UITextEntryLine(relative_rect=pygame.Rect((test_config.centre_x, test_config.centre_y - 15*self.BUTTON_HEIGHT/4), self.BUTTON_SIZE),
                                                            manager=self.menu_manager)
        self.age_entry.set_allowed_characters('numbers')
        self.data_entry_elements.append(self.age_entry)
        self.age_entry_label = pygame_gui.elements.UILabel(relative_rect=pygame.Rect(test_config.centre_x - 3*self.BUTTON_WIDTH/2, test_config.centre_y - 4*self.BUTTON_HEIGHT, 200, 50),
                                                        text='Patient Age:',
                                                        manager=self.menu_manager)
        self.data_entry_elements.append(self.age_entry_label)
        self.data_entry_instructions = pygame_gui.elements.UILabel(relative_rect=pygame.Rect(test_config.centre_x - 225, 100, 450, 50),
                                                                text='Please enter the following information to continue',
                                                                manager=self.menu_manager)
        self.data_entry_elements.append(self.data_entry_instructions)

    def data_is_valid(self):
        if not self.age_entry.get_text() or not self.sex_selection:
            # age hasn't been entered or sex not selected
            return False
        else:
            return True

    def reset_screen(self):
        test_config.screen.fill(test_config.WHITE)
        pygame.display.flip()

    def run(self):
        test_config.screen.fill(test_config.WHITE)
        # wait for pupil tracking to be ready
        loading_message_frames = [".", "..", "..."]
        loading = True
        i = 0
        message = "Initializing Concussion Detector"
        font_object = pygame.font.Font(pygame.font.match_font('timesnewroman'), 18)
        rendered_text = font_object.render(message, True, test_config.BLACK)
        rendered_text_rect = rendered_text.get_rect(center=(test_config.centre_x, test_config.centre_y))
        test_config.screen.blit(rendered_text, rendered_text_rect)
        pygame.time.set_timer(self.loading_event, 500)
        while(loading):
            if i > 2:
                i = 0
            try:
                msg = self.queues[self.process_names["Test Routine"]].get_nowait()

                if msg.id == "PupilTrackerReady":
                    print("[TestRoutine][INFO] Received ready message from Pupil Tracker")
                    pygame.time.set_timer(self.loading_event, 0)
                    loading = False
            except QueueEmpty:
                pass

            for event in pygame.event.get():
                if event.type == self.loading_event:
                    message = "Initializing Concussion Detector" + loading_message_frames[i]
                    i += 1
                    self.reset_screen()
                    rendered_text = font_object.render(message, True, test_config.BLACK)
                    rendered_text_rect = rendered_text.get_rect(center=(test_config.centre_x, test_config.centre_y))
                    test_config.screen.blit(rendered_text, rendered_text_rect)
                elif event.type == KEYDOWN:
                    if event.key == K_ESCAPE:
                        self.shutdown()

            pygame.display.update()

        self.quit_button = pygame_gui.elements.UIButton(relative_rect=pygame.Rect((test_config.centre_x + self.BUTTON_WIDTH/2, test_config.centre_y + 200), self.BUTTON_SIZE),
                                                text='Quit',
                                                manager=self.menu_manager)
        self.start_button = pygame_gui.elements.UIButton(relative_rect=pygame.Rect((test_config.centre_x - 3*self.BUTTON_WIDTH/2, test_config.centre_y + 200), self.BUTTON_SIZE),
                                                text='Start Test',
                                                manager=self.menu_manager)
        self.welcome_text = pygame_gui.elements.UITextBox(html_text="<font size=5>Welcome to <b>ProSpecs</b> Concussion Detection</font>",
                                                relative_rect=pygame.Rect((test_config.centre_x - 230, 100), (460, 50)),
                                                manager=self.menu_manager,
                                                wrap_to_height=True)
        running = True
        data_entry_elements_created = False
        
        while running:
            time_delta = self.clock.tick(60)/1000.0
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    quit()
                
                if event.type == pygame.USEREVENT:
                    if event.user_type == pygame_gui.UI_BUTTON_PRESSED:
                        if event.ui_element == self.quit_button:
                            if self.show_cam:
                                self.cam.release()
                            self.shutdown()
                        
                        if event.ui_element == self.start_button:
                            self.start_button.kill()
                            self.welcome_text.kill()
                            self.create_data_entry_elements()

                        if event.ui_element == self.cont_button:
                            if self.data_is_valid():
                                #send data to concussion model
                                self.sex_selection = 0 if self.sex_selection=='Male' else 1
                                self.queues[self.process_names['Concussion Model']].put(PatientDataMessage(self.sex_selection, self.age_entry.get_text()))
                                for element in self.data_entry_elements:
                                    element.kill()
                                self.cont_button_2 = pygame_gui.elements.UIButton(relative_rect=pygame.Rect((test_config.centre_x - 3*self.BUTTON_WIDTH/2, test_config.centre_y + 200), self.BUTTON_SIZE),
                                                                                text='Continue',
                                                                                manager=self.menu_manager)
                                self.camera_label = pygame_gui.elements.UILabel(relative_rect=pygame.Rect(test_config.centre_x - 750/2.0, test_config.centre_y + 100, 750, 50),
                                                                                text="Please make sure the patient's pupil is within the red square and in focus before proceeding.",
                                                                                manager=self.menu_manager)
                                self.show_cam = True
                        if event.ui_element == self.cont_button_2:
                            self.cam.release()
                            self.show_cam = False
                            running = False
                    
                    if event.user_type == pygame_gui.UI_DROP_DOWN_MENU_CHANGED:
                        if event.ui_element == self.sex_dropdown:
                            self.sex_selection = event.text

                self.menu_manager.process_events(event)
            self.menu_manager.update(time_delta)

            test_config.screen.fill(test_config.WHITE)
            self.menu_manager.draw_ui(test_config.screen)

            if self.show_cam:
                image = self.getCamFrame()
                box_height = 300
                box_width = 350
                pygame.draw.rect(image, test_config.RED, pygame.Rect(image.get_width()/2.0 - box_width/2.0,image.get_height()/2.0 - box_height/2.0, box_width, box_height), 2)
                test_config.screen.blit(image, (test_config.centre_x - image.get_width()/2.0,0))

            pygame.display.update()
    
    def getCamFrame(self):
        ret,frame = self.cam.read()
        frame = numpy.rot90(frame)
        frame = pygame.surfarray.make_surface(frame)
        return frame
    
    def shutdown(self):
        msg = ShutdownMessage(time.time())
        self.queues[self.process_names['Concussion Model']].put(msg)
        self.queues[self.process_names['Pupil Tracking']].put(msg)
        self.queues[self.process_names['Saccade Detector']].put(msg)
        pygame.quit()
        quit()

if __name__ == "__main__":
    pygame.init()
    process_names = {
            'Test Routine': 0,
            'Concussion Model': 1,
            'Pupil Tracking': 2,
            'Saccade Detector': 3,
        }
    menu = Menu([Queue(),Queue(), Queue(), Queue()], process_names)
    test = TestSession([Queue(),Queue(), Queue(), Queue()], process_names, num_blocks=1)
    menu.run()
    test.run()
