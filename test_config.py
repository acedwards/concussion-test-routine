import sys, math
from PyQt5.QtWidgets import QApplication
import pygame
from pygame.locals import *

app = QApplication(sys.argv)
screen = app.screens()[0]
DPI = screen.physicalDotsPerInch()
app.quit()

WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
RED = (255,0,0)
DIS_FROM_SCREEN = 55 #cm
DEG_STIM_OFFSET = 9 #degrees
DEG_STIM_SIZE = 0.5 #degrees
SACCADE_REPS = 40
SACCADE_BLOCKS = 2
MESSAGE_DELAY = 5000 # how long a message stays up
STIM_DELAY = 1000 # how long stim stays up

screen = pygame.display.set_mode((0,0), FULLSCREEN)
width, height = screen.get_width(), screen.get_height() #in px
centre_x, centre_y = width//2, height//2

# stim location setup
stim_offset = int(DIS_FROM_SCREEN*math.tan(math.radians(DEG_STIM_OFFSET))*DPI/2.54) # 2.54 cm in an inch
left_stim_coords = [centre_x - stim_offset, centre_y]
right_stim_coords = [centre_x + stim_offset, centre_y]
stim_size = int(DIS_FROM_SCREEN*math.tan(math.radians(DEG_STIM_SIZE))*DPI/2.54) # 2.54 cm in an inch
stim_radius = int(stim_size/2)  