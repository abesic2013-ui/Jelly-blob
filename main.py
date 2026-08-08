"""
Jelly Blob 2.0 - Pydroid 3 App
"""

import math
import random
import struct
import wave
import os
import threading
import colorsys

from kivy.app import App
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.widget import Widget
from kivy.uix.button import Button
from kivy.graphics import Color, Line, Mesh, Ellipse
from kivy.core.window import Window
from kivy.core.audio import SoundLoader
from kivy.clock import Clock

try:
    from jnius import autoclass
    _PythonActivity = autoclass('org.kivy.android.PythonActivity')
    _Context = autoclass('android.content.Context')
    _VIBRATOR_OK = True
except Exception:
    _VIBRATOR_OK = False


def vibrate(ms=15):
    if not _VIBRATOR_OK:
        return
    try:
        activity = _PythonActivity.mActivity
        vibrator = activity.getSystemService(_Context.VIBRATOR_SERVICE)
        vibrator.vibrate(ms)
    except Exception:
        pass


def _catmull_point(p0, p1, p2, p3, t):
    t2, t3 = t * t, t * t * t
    x = 0.5 * ((2 * p1[0]) + (-p0[0] + p2[0]) * t +
               (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2 +
               (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3)
    y = 0.5 * ((2 * p1[1]) + (-p0[1] + p2[1]) * t +
               (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2 +
               (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3)
    return x, y


def smooth_closed_curve(points, subdivisions=6):
    n = len(points)
    result = []
    for i in range(n):
        p0 = points[(i - 1) % n]
        p1 = points[i]
        p2 = points[(i + 1) % n]
        p3 = points[(i + 2) % n]
        for s in range(subdivisions):
            result.append(_catmull_point(p0, p1, p2, p3, s / subdivisions))
    return result


def generate_boing_wav(filepath, duration=0.35, start_freq=650, end_freq=140, sample_rate=44100):
    n_samples = int(sample_rate * duration)
    samples = []
    for i in range(n_samples):
        t = i / sample_rate
        freq = start_freq + (end_freq - start_freq) * (t / duration)
        envelope = max(0.0, 1.0 - (t / duration))
        val = math.sin(2 * math.pi * freq * t) * envelope
        samples.append(int(val * 32767 * 0.6))
    with wave.open(filepath, 'w') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b''.join(struct.pack('<h', s) for s in samples))


class Node:
    __slots__ = ('ox', 'oy', 'x', 'y', 'vx', 'vy', 'held_by')

    def __init__(self, x, y):
        self.ox, self.oy = x, y
        self.x, self.y = x, y
        self.vx, self.vy = 0.0, 0.0
        self.held_by = None


class JellyBlob(Widget):
    SHAPES = [('circle', 'Krug'), ('square', 'Kvadrat'), ('star', 'Zvijezda'),
              ('heart', 'Srce'), ('blob', 'Mrlja')]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.cx = Window.width / 2
        self.cy = Window.height / 2
        self.radius = min(Window.width, Window.height) * 0.28
        self.num_nodes = 20
        self.shape_index = 0
        self.nodes = []
        self.target_area = 1.0
        self.build_shape('circle')

        self.stiffness = 0.08
        self.neighbor_pull = 0.12
        self.damping = 0.88
        self.pressure_strength = 4.0

        self.touches = {}
        self.particles = []
        self.trail = []
        self.current_color = (0.2, 1.0, 0.5, 0.85)
        self.current_stretch = 0.0

        self.last_boing_time = 0.0
        self.wav_path = os.path.join(App.get_running_app().user_data_dir, 'jelly_boing.wav')

        with self.canvas.before:
            Color(0.03, 0.03, 0.07, 1)
        Clock.schedule_interval(self.update, 1 / 60.0)

    def _polygon_area(self, pts):
        area = 0.0
        n = len(pts)
        for i in range(n):
            x1, y1 = pts[i]
            x2, y2 = pts[(i + 1) % n]
            area += x1 * y2 - x2 * y1
        return abs(area) / 2.0

    def build_shape(self, shape_key):
        n = self.num_nodes
        raw = []
        if shape_key == 'heart':
            for i in range(n):
                t = (2 * math.pi * i) / n
                hx = 16 * (math.sin(t) ** 3)
                hy = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
                scale = self.radius / 16.0
                raw.append((self.cx + hx * scale, self.cy + hy * scale))
        elif shape_key == 'blob':
            radii = [self.radius * random.uniform(0.65, 1.15) for _ in range(n)]
            for _ in range(2):
                radii = [(radii[(i - 1) % n] + radii[i] + radii[(i + 1) % n]) / 3 for i in range(n)]
            for i in range(n):
                angle = (2 * math.pi * i) / n
                r = radii[i]
                raw.append((self.cx + r * math.cos(angle), self.cy + r * math.sin(angle)))
        else:
            for i in range(n):
                angle = (2 * math.pi * i) / n
                if shape_key == 'square':
                    c, s = math.cos(angle), math.sin(angle)
                    r = self.radius / (abs(c) ** 4 + abs(s) ** 4) ** 0.25
                elif shape_key == 'star':
                    spikes = 5
                    r = self.radius * (0.55 + 0.45 * ((math.cos(spikes * angle) + 1) / 2))
                else:
                    r = self.radius
                raw.append((self.cx + r * math.cos(angle), self.cy + r * math.sin(angle)))

        self.nodes = [Node(x, y) for x, y in raw]
        self.target_area = self._polygon_area(raw)

    def next_shape(self):
        self.shape_index = (self.shape_index + 1) % len(self.SHAPES)
        key, name = self.SHAPES[self.shape_index]
        self.build_shape(key)
        return name

    def nearest_node(self, x, y):
        best_i, best_d = None, float('inf')
        for i, node in enumerate(self.nodes):
            if node.held_by is not None:
                continue
            d = (node.x - x) ** 2 + (node.y - y) ** 2
            if d < best_d:
                best_d, best_i = d, i
        if best_i is None:
            for i, node in enumerate(self.nodes):
                d = (node.x - x) ** 2 + (node.y - y) ** 2
                if d < best_d:
                    best_d, best_i = d, i
        return best_i

    def on_touch_down(self, touch):
        if getattr(touch, 'is_double_tap', False):
            self.pop_explosion(touch.x, touch.y)
            return True
        idx = self.nearest_node(touch.x, touch.y)
        self.nodes[idx].held_by = touch.id
        self.touches[touch.id] = idx
        vibrate(12)
        return True

    def on_touch_move(self, touch):
        if touch.id in self.touches:
            node = self.nodes[self.touches[touch.id]]
            node.x, node.y = touch.x, touch.y
            node.vx, node.vy = 0, 0
        return True

    def on_touch_up(self, touch):
        if touch.id in self.touches:
            node = self.nodes[self.touches[touch.id]]
            stretch = math.hypot(node.x - node.ox, node.y - node.oy)
            node.held_by = None
            del self.touches[touch.id]
            if stretch > self.radius * 0.25:
                self.play_boing()
                vibrate(20)
        return True

    def play_boing(self):
        now = Clock.get_time()
        if now - self.last_boing_time < 0.15:
            return
        self.last_boing_time = now
        threading.Thread(target=self._gen_and_play).start()

    def _gen_and_play(self):
        try:
            generate_boing_wav(self.wav_path)
            sound = SoundLoader.load(self.wav_path)
            if sound:
                sound.play()
        except Exception:
            pass

    def pop_explosion(self, x, y):
        for _ in range(35):
            angle = random.uniform(0, 2 * math.pi)
            speed = random.uniform(3, 10)
            hue = random.uniform(0.3, 0.95)
            r, g, b = colorsys.hsv_to_rgb(hue, 0.8, 1.0)
            self.particles.append({
                'x': x, 'y': y,
                'vx': math.cos(angle) * speed, 'vy': math.sin(angle) * speed,
                'life': 1.0, 'color': (r, g, b), 'size': random.uniform(4, 9)
            })
        vibrate(25)

    def update(self, dt):
        n = len(self.nodes)
        cx = sum(nd.x for nd in self.nodes) / n
        cy = sum(nd.y for nd in self.nodes) / n

        area = self._polygon_area([(nd.x, nd.y) for nd in self.nodes])
        area_ratio = (self.target_area - area) / max(self.target_area, 1)

        max_stretch = 0.0
        for i, node in enumerate(self.nodes):
            stretch = math.hypot(node.x - node.ox, node.y - node.oy)
            if stretch > max_stretch:
                max_stretch = stretch
            if node.held_by is not None:
                continue

            left = self.nodes[(i - 1) % n]
            right = self.nodes[(i + 1) % n]

            fx = (node.ox - node.x) * self.stiffness
            fy = (node.oy - node.y) * self.stiffness
            fx += ((left.x - node.x) + (right.x - node.x)) * self.neighbor_pull
            fy += ((left.y - node.y) + (right.y - node.y)) * self.neighbor_pull

            tx, ty = right.x - left.x, right.y - left.y
            nx, ny = ty, -tx
            nl = math.hypot(nx, ny) or 1
            nx, ny = nx / nl, ny / nl
            if nx * (node.x - cx) + ny * (node.y - cy) < 0:
                nx, ny = -nx, -ny
            p = area_ratio * self.pressure_strength
            fx += nx * p
            fy += ny * p

            node.vx = (node.vx + fx) * self.damping
            node.vy = (node.vy + fy) * self.damping
            node.x += node.vx
            node.y += node.vy

        self.current_stretch = max_stretch
        factor = min(1.0, max_stretch / (self.radius * 0.7))
        hue = 0.38 * (1 - factor) + 0.92 * factor
        r, g, b = colorsys.hsv_to_rgb(hue, 0.75, 1.0)
        self.current_color = (r, g, b, 0.85)

        alive = []
        for pt in self.particles:
            pt['x'] += pt['vx']
            pt['y'] += pt['vy']
            pt['vy'] -= 0.2
            pt['life'] -= 0.02
            if pt['life'] > 0:
                alive.append(pt)
        self.particles = alive

        self.draw()

    def draw(self):
        self.canvas.after.clear()
        pts = [(nd.x, nd.y) for nd in self.nodes]
        smooth = smooth_closed_curve(pts, subdivisions=6)
        flat = []
        for x, y in smooth:
            flat += [x, y]
        cx = sum(p[0] for p in smooth) / len(smooth)
        cy = sum(p[1] for p in smooth) / len(smooth)

        with self.canvas.after:
            for i, trail_pts in enumerate(self.trail):
                alpha = (i + 1) / (len(self.trail) + 1) * 0.15
                Color(*self.current_color[:3], alpha)
                tf = []
                for x, y in trail_pts:
                    tf += [x, y]
                Line(points=tf + tf[:2], width=1.5, close=True)

            glow = []
            for x, y in smooth:
                glow += [cx + (x - cx) * 1.12, cy + (y - cy) * 1.12]
            Color(*self.current_color[:3], 0.18)
            Line(points=glow + glow[:2], width=14, close=True)

            vertices = [cx, cy, 0, 0]
            indices = []
            m = len(smooth)
            for x, y in smooth:
                vertices += [x, y, 0, 0]
            for i in range(m):
                indices += [0, i + 1, ((i + 1) % m) + 1]
            Color(*self.current_color)
            Mesh(vertices=vertices, indices=indices, mode='triangles')

            Color(min(1, self.current_color[0] + 0.3), min(1, self.current_color[1] + 0.3),
                  min(1, self.current_color[2] + 0.3), 0.9)
            Line(points=flat + flat[:2], width=2.5, close=True)

            hl_x = cx - self.radius * 0.28
            hl_y = cy + self.radius * 0.28
            Color(1, 1, 1, 0.25)
            Ellipse(pos=(hl_x - self.radius * 0.22, hl_y - self.radius * 0.14),
                    size=(self.radius * 0.44, self.radius * 0.26))

            for pt in self.particles:
                Color(*pt['color'], pt['life'])
                s = pt['size']
                Ellipse(pos=(pt['x'] - s / 2, pt['y'] - s / 2), size=(s, s))

        self.trail.append(smooth)
        if len(self.trail) > 4:
            self.trail.pop(0)

    def do_pop(self):
        cx = sum(nd.x for nd in self.nodes) / len(self.nodes)
        cy = sum(nd.y for nd in self.nodes) / len(self.nodes)
        self.pop_explosion(cx, cy)


class RootLayout(FloatLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.blob = JellyBlob()
        self.add_widget(self.blob)

        self.shape_btn = Button(
            text='OBLIK: Krug',
            size_hint=(0.32, 0.07),
            pos_hint={'right': 0.98, 'top': 0.98},
            background_color=(0.15, 0.5, 0.3, 0.9)
        )
        self.shape_btn.bind(on_press=self.change_shape)
        self.add_widget(self.shape_btn)

        pop_btn = Button(
            text='POP',
            size_hint=(0.2, 0.07),
            pos_hint={'right': 0.98, 'top': 0.89},
            background_color=(0.6, 0.15, 0.4, 0.9)
        )
        pop_btn.bind(on_press=lambda x: self.blob.do_pop())
        self.add_widget(pop_btn)

        info = Button(
            text='Vuci prstom da rastegnes - dupli dodir = POP',
            size_hint=(0.75, 0.05),
            pos_hint={'x': 0.02, 'top': 0.99},
            background_color=(0, 0, 0, 0),
            color=(0.5, 0.5, 0.5, 1),
            font_size=12,
            disabled=True
        )
        self.add_widget(info)

    def change_shape(self, *args):
        name = self.blob.next_shape()
        self.shape_btn.text = f'OBLIK: {name}'


class JellyApp(App):
    def build(self):
        self.title = 'Jelly Blob 2.0'
        return RootLayout()


if __name__ == '__main__':
    JellyApp().run()
