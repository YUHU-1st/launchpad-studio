from __future__ import annotations

import random
from datetime import datetime

FONT = {
    "0": ("111", "101", "101", "101", "111"), "1": ("010", "110", "010", "010", "111"),
    "2": ("111", "001", "111", "100", "111"), "3": ("111", "001", "111", "001", "111"),
    "4": ("101", "101", "111", "001", "001"), "5": ("111", "100", "111", "001", "111"),
    "6": ("111", "100", "111", "101", "111"), "7": ("111", "001", "010", "010", "010"),
    "8": ("111", "101", "111", "101", "111"), "9": ("111", "101", "111", "001", "111"),
    ":": ("0", "1", "0", "1", "0"), "-": ("000", "000", "111", "000", "000"),
    "C": ("111", "100", "100", "100", "111"), " ": ("00", "00", "00", "00", "00"),
}


def blank(output_size=(8, 8)):
    width, height = (max(1, int(value)) for value in output_size)
    frame = {(x, y): (0, 0, 0) for y in range(1, height + 1) for x in range(width)}
    frame.update({(x, 0): (0, 0, 0) for x in range(width)})
    frame.update({(width, y): (0, 0, 0) for y in range(1, height + 1)})
    return frame


def _columns(text):
    columns = []
    for char in text:
        glyph = FONT.get(char, FONT[" "])
        width = len(glyph[0])
        columns.extend([[row[x] == "1" for row in glyph] for x in range(width)])
        columns.append([False] * 5)
    return columns[:-1] if columns else []


def scrolling_text(text, phase, color=(80, 220, 255), accent=(255, 80, 190), output_size=(8, 8)):
    width, height = (max(1, int(value)) for value in output_size)
    frame = blank((width, height)); cols = _columns(text)
    if not cols:return frame
    travel = len(cols) + width
    offset = width - (phase % travel)
    start_y = max(1, (height - 5) // 2 + 1)
    for source_x, column in enumerate(cols):
        x = source_x + offset
        if 0 <= x < width:
            for py, lit in enumerate(column):
                y = start_y + py
                if lit and y <= height:frame[(x, y)] = color if py < 3 else accent
    return frame


def clock_frame(now: datetime, phase: int, color, accent, output_size=(8, 8)):
    width, _ = output_size
    frame = scrolling_text(now.strftime("%H:%M"), phase, color, accent, output_size)
    frame[(min(width - 1, now.second * width // 60), 0)] = accent
    return frame


def calendar_frame(now: datetime, phase: int, color, accent, output_size=(8, 8)):
    width, _ = output_size
    frame = scrolling_text(now.strftime("%m-%d"), phase, color, accent, output_size)
    for x in range(max(1, round((now.weekday() + 1) * width / 7))):frame[(x, 0)] = accent
    return frame


def weather_frame(code: int, temperature: float, color=(80, 220, 255), accent=(255, 190, 40), output_size=(8, 8)):
    width, height = (max(1, int(value)) for value in output_size)
    frame = blank((width, height))
    center_x, center_y = (width - 1) // 2, (height + 1) // 2
    # WMO: 0 clear, 1-3 cloud, 45/48 fog, 51-67 rain, 71-77 snow, 80-99 showers/storms.
    if code == 0:
        points=((0,0),(1,0),(0,1),(1,1),(0,-1),(1,-1),(-1,0),(2,0),(0,2),(1,2))
        for dx,dy in points:
            xy=(center_x+dx,center_y+dy)
            if 0<=xy[0]<width and 1<=xy[1]<=height:frame[xy]=accent
    elif code < 50:
        for dy,span in ((-1,4),(0,6),(1,5)):
            target_y=center_y+dy
            for x in range(center_x-span//2,center_x-span//2+span):
                if 0<=x<width and 1<=target_y<=height:frame[(x,target_y)]=color
    else:
        for dy,span in ((-2,4),(-1,6),(0,5)):
            for x in range(center_x-span//2,center_x-span//2+span):
                if 0<=x<width and 1<=center_y+dy<=height:frame[(x,center_y+dy)]=color
        drops=((-2,2),(0,2),(2,2),(-1,4),(1,4))
        for dx,dy in drops:
            x,y=center_x+dx,center_y+dy
            if 0<=x<width and 1<=y<=height:frame[(x,y)]=(170,220,255) if code < 70 else ((240,250,255) if code < 80 else accent)
    level=max(0,min(height,round((temperature+20)/70*height)))
    for i in range(level):frame[(width,height-i)]=(40+min(215,round(i*280/max(1,height))),80,max(0,255-round(i*255/max(1,height))))
    return frame


class SnakeGame:
    def __init__(self):
        self.rng=random.Random(); self.reset()

    def reset(self, width=8, height=8):
        self.width=max(3,int(width)); self.height=max(3,int(height))
        head_x=max(2,self.width//2-1); head_y=self.height//2+1
        self.snake=[(head_x-offset,head_y) for offset in range(3)]; self.direction=(1,0); self.next_direction=(1,0)
        self.food=self._food(); self.score=0; self.alive=True

    def _food(self):
        choices=[(x,y) for y in range(1,self.height+1) for x in range(self.width) if (x,y) not in self.snake]
        return self.rng.choice(choices) if choices else None

    def steer(self,direction):
        if (direction[0]+self.direction[0],direction[1]+self.direction[1]) != (0,0):
            self.next_direction=direction

    def tick(self):
        if not self.alive:return False
        self.direction=self.next_direction; hx,hy=self.snake[0]
        # The playable area is a torus: leaving one edge enters from
        # the opposite edge.  Row zero remains reserved for direction keys.
        head=((hx+self.direction[0])%self.width,((hy-1+self.direction[1])%self.height)+1)
        if head in self.snake[:-1]:
            self.alive=False; return False
        self.snake.insert(0,head)
        if head==self.food:
            self.score+=1; self.food=self._food()
        else:self.snake.pop()
        return True

    @property
    def level(self):
        return self.score//5+1

    def frame(self):
        frame=blank((self.width,self.height))
        if self.food:frame[self.food]=(255,55,95)
        for i,xy in enumerate(self.snake):frame[xy]=(110,255,120) if i else (235,255,120)
        for base in range(0,self.width,8):
            for x in range(base,min(base+4,self.width)):frame[(x,0)]=(80,130,255)
        if not self.alive:
            for x in range(self.width):
                y=1+round(x*(self.height-1)/max(1,self.width-1))
                frame[(x,y)]=(255,30,40); frame[(self.width-1-x,y)]=(255,30,40)
        return frame


class WhackAMole:
    def __init__(self):
        self.rng=random.Random(); self.reset()

    def reset(self,max_misses=8,width=8,height=8):
        self.width=max(1,int(width)); self.height=max(1,int(height))
        self.max_misses=max(1,int(max_misses))
        self.target=self._target(); self.score=0; self.misses=0; self.running=True

    def _target(self):return self.rng.randrange(self.width),self.rng.randrange(1,self.height+1)

    def hit(self,xy):
        if not self.running:return False
        if xy==self.target:
            self.score+=1; self.target=self._target(); return True
        self.misses+=1
        if self.misses>=self.max_misses:self.running=False
        return False

    def timeout(self):
        if not self.running:return
        self.misses+=1
        if self.misses>=self.max_misses:self.running=False
        else:self.target=self._target()

    @property
    def level(self):
        return self.score//8+1

    def frame(self):
        frame=blank((self.width,self.height))
        if self.running:frame[self.target]=(255,170,30)
        else:
            middle=max(1,self.height//2)
            for x in range(self.width):frame[(x,middle)]=(255,40,80); frame[(x,min(self.height,middle+1))]=(255,40,80)
        # The side column is only eight pads high, so it shows the remaining
        # chances proportionally for difficulty levels with more than 8 lives.
        remaining=max(0,self.max_misses-self.misses)
        lights=round(remaining/self.max_misses*self.height) if remaining else 0
        for i in range(lights):frame[(self.width,self.height-i)]=(70,255,120)
        return frame
