from __future__ import annotations

import random
from datetime import datetime

from .launchpad import ALL_PADS


FONT = {
    "0": ("111", "101", "101", "101", "111"), "1": ("010", "110", "010", "010", "111"),
    "2": ("111", "001", "111", "100", "111"), "3": ("111", "001", "111", "001", "111"),
    "4": ("101", "101", "111", "001", "001"), "5": ("111", "100", "111", "001", "111"),
    "6": ("111", "100", "111", "101", "111"), "7": ("111", "001", "010", "010", "010"),
    "8": ("111", "101", "111", "101", "111"), "9": ("111", "101", "111", "001", "111"),
    ":": ("0", "1", "0", "1", "0"), "-": ("000", "000", "111", "000", "000"),
    "C": ("111", "100", "100", "100", "111"), " ": ("00", "00", "00", "00", "00"),
}


def blank():
    return {xy: (0, 0, 0) for xy in ALL_PADS}


def _columns(text):
    columns = []
    for char in text:
        glyph = FONT.get(char, FONT[" "])
        width = len(glyph[0])
        columns.extend([[row[x] == "1" for row in glyph] for x in range(width)])
        columns.append([False] * 5)
    return columns[:-1] if columns else []


def scrolling_text(text, phase, color=(80, 220, 255), accent=(255, 80, 190)):
    frame = blank(); cols = _columns(text)
    if not cols:return frame
    travel = len(cols) + 8
    offset = 8 - (phase % travel)
    for source_x, column in enumerate(cols):
        x = source_x + offset
        if 0 <= x < 8:
            for py, lit in enumerate(column):
                if lit:frame[(x, py + 2)] = color if py < 3 else accent
    return frame


def clock_frame(now: datetime, phase: int, color, accent):
    frame = scrolling_text(now.strftime("%H:%M"), phase, color, accent)
    frame[(now.second % 8, 0)] = accent
    return frame


def calendar_frame(now: datetime, phase: int, color, accent):
    frame = scrolling_text(now.strftime("%m-%d"), phase, color, accent)
    for x in range(min(7, now.weekday() + 1)):frame[(x, 0)] = accent
    return frame


def weather_frame(code: int, temperature: float, color=(80, 220, 255), accent=(255, 190, 40)):
    frame = blank()
    # WMO: 0 clear, 1-3 cloud, 45/48 fog, 51-67 rain, 71-77 snow, 80-99 showers/storms.
    if code == 0:
        for xy in ((3,3),(4,3),(3,4),(4,4),(3,2),(4,2),(2,3),(5,3),(3,5),(4,5)):
            frame[xy]=accent
    elif code < 50:
        for y,width in ((3,4),(4,6),(5,5)):
            for x in range((8-width)//2,(8-width)//2+width):frame[(x,y)]=color
    else:
        for y,width in ((2,4),(3,6),(4,5)):
            for x in range((8-width)//2,(8-width)//2+width):frame[(x,y)]=color
        drops=((2,6),(4,6),(6,6),(3,8),(5,8))
        for x,y in drops:
            frame[(x,y)]=(170,220,255) if code < 70 else ((240,250,255) if code < 80 else accent)
    level=max(0,min(8,round((temperature+20)/70*8)))
    for i in range(level):frame[(8,8-i)]=(40+min(215,i*35),80,max(0,255-i*32))
    return frame


class SnakeGame:
    def __init__(self):
        self.rng=random.Random(); self.reset()

    def reset(self):
        self.snake=[(3,5),(2,5),(1,5)]; self.direction=(1,0); self.next_direction=(1,0)
        self.food=self._food(); self.score=0; self.alive=True

    def _food(self):
        choices=[(x,y) for y in range(1,9) for x in range(8) if (x,y) not in self.snake]
        return self.rng.choice(choices) if choices else None

    def steer(self,direction):
        if (direction[0]+self.direction[0],direction[1]+self.direction[1]) != (0,0):
            self.next_direction=direction

    def tick(self):
        if not self.alive:return False
        self.direction=self.next_direction; hx,hy=self.snake[0]
        head=(hx+self.direction[0],hy+self.direction[1])
        if not (0<=head[0]<8 and 1<=head[1]<=8) or head in self.snake[:-1]:
            self.alive=False; return False
        self.snake.insert(0,head)
        if head==self.food:
            self.score+=1; self.food=self._food()
        else:self.snake.pop()
        return True

    def frame(self):
        frame=blank()
        if self.food:frame[self.food]=(255,55,95)
        for i,xy in enumerate(self.snake):frame[xy]=(110,255,120) if i else (235,255,120)
        for x,c in enumerate(((80,130,255),(80,130,255),(80,130,255),(80,130,255))):frame[(x,0)]=c
        if not self.alive:
            for i in range(8):frame[(i,i+1)]=(255,30,40); frame[(7-i,i+1)]=(255,30,40)
        return frame


class WhackAMole:
    def __init__(self):
        self.rng=random.Random(); self.reset()

    def reset(self):
        self.target=self._target(); self.score=0; self.misses=0; self.running=True

    def _target(self):return self.rng.randrange(8),self.rng.randrange(1,9)

    def hit(self,xy):
        if not self.running:return False
        if xy==self.target:
            self.score+=1; self.target=self._target(); return True
        self.misses+=1
        if self.misses>=5:self.running=False
        return False

    def timeout(self):
        if not self.running:return
        self.misses+=1
        if self.misses>=5:self.running=False
        else:self.target=self._target()

    def frame(self):
        frame=blank()
        if self.running:frame[self.target]=(255,170,30)
        else:
            for x in range(8):frame[(x,4)]=(255,40,80); frame[(x,5)]=(255,40,80)
        for i in range(max(0,5-self.misses)):frame[(8,8-i)]=(70,255,120)
        return frame
