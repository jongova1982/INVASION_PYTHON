"""INVASIO — homenaje independiente en Python a Invasión de los Xhar'Kor.

Requisitos: Python 3.10+ y pygame-ce (python -m pip install pygame-ce).
Ejecutar desde la raíz del proyecto: python Invasio.py
Las imágenes originales se cargan desde ./data y son opcionales.
Controles: flechas/WASD vuelo · W ráfaga · E misil · Q láser · P pausa.
"""
from __future__ import annotations

import math
import random
import sys
from dataclasses import dataclass
from pathlib import Path

try:
    import pygame
except ImportError as exc:
    raise SystemExit("Falta pygame-ce. Instálalo con: python -m pip install pygame-ce") from exc

W, H = 1280, 800
GALAXIES = ["GALAXIA TERRA", "NEBULOSA THARION", "CINTURÓN ZHAK", "SECTOR KOR", "NÚCLEO VHAR'ZUL"]
SCENES = [
    ((20, 88, 148), (16, 154, 210), "ÓRBITA TERRESTRE"),
    ((100, 42, 139), (224, 85, 173), "NIEBLA DE THARION"),
    ((153, 83, 34), (241, 163, 63), "CAMPO DE ASTEROIDES"),
    ((35, 111, 113), (72, 226, 182), "FRONTERA DEL SECTOR KOR"),
    ((143, 35, 54), (255, 96, 72), "TRONO DEL EMPERADOR"),
]
CYAN, GOLD, RED, MUTED = (72, 225, 255), (255, 191, 92), (255, 83, 96), (132, 174, 198)
ASSETS = Path(__file__).resolve().parent / "data"


def clamp(v, a, b):
    return max(a, min(b, v))


@dataclass
class Shot:
    x: float
    y: float
    kind: str
    vy: float
    side: int = 0


@dataclass
class Enemy:
    x: float
    y: float
    hp: int
    max_hp: int
    kind: str = "ovni"
    phase: float = 0
    cooldown: float = 2.0
    active: bool = True


@dataclass
class Escort:
    side: int
    x: float
    y: float
    vx: float = 0
    vy: float = 0
    lives: int = 10
    cooldown: float = 0
    invulnerable: float = 0
    active: bool = True


class Invasio:
    def __init__(self):
        pygame.init()
        self.sounds = {}
        self.sound_volume = .62
        self.sound_enabled = True
        self.audio_clock = 0.0
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            pygame.mixer.set_num_channels(24)
            for key, filename in {
                "burst": "sonido_metralleta.wav", "missile": "sonido_misil.wav",
                "laser": "dipsparocaza_laser.wav", "enemy": "disparovni.wav",
                "mothership": "disparo_nodriza.wav", "explosion": "explosion.wav",
                "engine": "sonidocaza.wav", "intro": "sonido_intro.wav",
                "ovni": "sonidovni.wav", "carrier": "sonidonodriza.wav",
                "victory": "victoria_1.mp3", "defeat": "grito_caida.mp3",
            }.items():
                try:
                    self.sounds[key] = pygame.mixer.Sound(ASSETS / filename)
                except (pygame.error, OSError):
                    pass
        except pygame.error:
            # Audio deshabilitado por el sistema: el juego continúa con efectos visuales.
            self.sounds = {}
        pygame.display.set_caption("INVASIO — La última defensa")
        self.screen = pygame.display.set_mode((W, H), pygame.RESIZABLE | pygame.DOUBLEBUF)
        self.canvas = pygame.Surface((W, H))
        self.clock = pygame.time.Clock()
        self.fonts = {n: pygame.font.SysFont("bahnschrift", n, bold=True) for n in (12, 13, 14, 15, 16, 18, 22, 24, 30, 44, 68)}
        self.images = {}
        for name in ("cazaf2_centro.png", "cazaf2_izq.png", "cazaf2_der.png", "ovnirojo.png", "nodriza.png", "crucero_Emperdor.png", "fondo_intro.png", "fondo_nivel1.png", "fondo_nivel2.png", "fondo_nivel3.png", "fondo_nivel4.png", "fondo_nivel5.png", "nebulosa_1.png", "nebulosa_2_nueva.png", "nebulosa_2.png", "salto1_2.png", "salto2_3.png", "salto3_4.png", "salto4_5.png"):
            try:
                im = pygame.image.load(ASSETS / name).convert_alpha()
                self.images[name] = im
            except (pygame.error, OSError):
                pass
        self.stars = [(random.random(), random.random(), random.uniform(.3, 1.0), random.uniform(0, 1)) for _ in range(190)]
        self.state = "title"
        self.reset()
        self.sound("intro", loops=-1, volume=.22)

    def sound(self, name, loops=0, volume=None):
        """Reproduce un efecto ya cargado; los recursos de audio son opcionales."""
        if not self.sound_enabled:
            return
        clip = self.sounds.get(name)
        if clip:
            clip.set_volume(self.sound_volume if volume is None else volume)
            clip.play(loops=loops)

    def stop_audio(self):
        if pygame.mixer.get_init():
            pygame.mixer.stop()

    def reset(self):
        self.level, self.score, self.lives = 1, 0, 10
        self.player_x, self.player_y = W / 2, H * .78
        self.shots, self.hostile, self.enemies, self.effects = [], [], [], []
        self.elapsed, self.fire_clock, self.missile_clock, self.laser_clock = 0, 0, 0, 0
        self.invulnerable, self.paused, self.boss_intro = 0, False, 0
        self.transition_timer = 0
        self.transition_from_level, self.transition_to_level = 1, 1
        self.transition_bonus = 0
        self.ui_buttons = {}
        self.escorts = []
        self.spawn_level()

    def spawn_level(self):
        self.shots.clear(); self.hostile.clear(); self.enemies.clear()
        self.escorts = [Escort(side, self.player_x+side*95, self.player_y+36) for side in (-1, 1)]
        count = (10, 15, 20, 23, 24)[self.level - 1]
        for i in range(count):
            boss_stage = self.level == 5
            if boss_stage and i == count - 1:
                kind, hp = "boss", 45
            elif (self.level >= 2 and i % 5 == 4) or (boss_stage and i >= count - 3):
                kind, hp = "nodriza", 10 + max(0, self.level - 5) * 2
            else:
                kind, hp = "ovni", 2 + min(2, self.level - 1)
            x = 100 + (i % 8) * 155 + random.randrange(-24, 25)
            y = 100 + (i // 8) * 100 + random.randrange(-18, 19)
            self.enemies.append(Enemy(x, y, hp, hp, kind, random.random() * 6.28, random.uniform(1, 3)))
        self.elapsed = 0

    def image(self, name, size):
        im = self.images.get(name)
        return pygame.transform.smoothscale(im, (int(size[0]), int(size[1]))) if im else None

    def text(self, text, x, y, size=18, color=(230, 245, 255), center=False):
        surface = self.fonts[size].render(text, True, color)
        rect = surface.get_rect(center=(int(x), int(y))) if center else surface.get_rect(topleft=(int(x), int(y)))
        self.canvas.blit(surface, rect)

    def panel(self, rect, fill=(7, 19, 35, 215), edge=(48, 111, 146)):
        rect = tuple(int(round(value)) for value in rect)
        layer = pygame.Surface((rect[2], rect[3]), pygame.SRCALPHA)
        pygame.draw.rect(layer, fill, layer.get_rect(), border_radius=10)
        self.canvas.blit(layer, rect[:2])
        pygame.draw.rect(self.canvas, edge, rect, 1, border_radius=10)

    def backdrop(self, dt):
        c = self.canvas
        c.fill((4, 9, 23))
        bg = self.images.get(f"fondo_nivel{self.level}.png") if self.state == "game" else self.images.get("fondo_intro.png")
        if bg:
            image = pygame.transform.smoothscale(bg, (W, H))
            image.set_alpha(168 if self.state == "game" else 125)
            c.blit(image, (0, 0))
        # Cada galaxia recibe su propio color atmosférico y horizonte planetario.
        scene_color, planet_color, _ = SCENES[self.level - 1]
        haze = pygame.Surface((W, H), pygame.SRCALPHA)
        pulse = .5 + .5 * math.sin(self.elapsed * .22)
        pygame.draw.ellipse(haze, (*scene_color, 38), (W*.12, H*.08, W*.76, H*.52))
        pygame.draw.ellipse(haze, (*planet_color, int(25 + pulse*17)), (W*.29, H*.19, W*.42, H*.35))
        c.blit(haze, (0, 0))
        for i, (sx, sy, depth, phase) in enumerate(self.stars):
            y = (sy * H + (self.elapsed * (30 + 145 * depth))) % H
            x = (sx * W + math.sin(self.elapsed * .12 + phase * 8) * depth * 24) % W
            r = max(1, int(depth * 2.4))
            color = (int(min(255, 76+depth*120+scene_color[0]*.15)), int(min(255, 105+depth*115+scene_color[1]*.16)), 255)
            pygame.draw.circle(c, color, (int(x), int(y)), r)
            if depth > .84:
                pygame.draw.line(c, (color[0], color[1], color[2], 80), (int(x), int(y-7)), (int(x), int(y+7)), 1)
        # Flight deck grid converges at the horizon.
        horizon = int(H * .25)
        grid_color = tuple(int(ch*.45) for ch in scene_color)
        for n in range(-9, 10):
            x = W/2 + n*34
            pygame.draw.line(c, grid_color, (W/2 + (x-W/2)*.09, horizon), (int(x + (x-W/2)*.8), H), 1)
        for j in range(1, 9):
            p = ((j / 8 + self.elapsed * .18) % 1)
            y = horizon + int((p ** 1.9) * (H-horizon))
            pygame.draw.line(c, tuple(int(ch*.32) for ch in scene_color), (0, y), (W, y), 1)
        pygame.draw.rect(c, (3, 12, 24), (0, H-18, W, 18))

    def draw_ship(self, x, y, scale=1, color=CYAN):
        # Malla triangular de caza con iluminación de borde.
        points = [(x, y-56*scale), (x-15*scale, y-13*scale), (x-56*scale, y+35*scale),
                  (x-24*scale, y+25*scale), (x, y+50*scale), (x+24*scale, y+25*scale),
                  (x+56*scale, y+35*scale), (x+15*scale, y-13*scale)]
        pygame.draw.polygon(self.canvas, (13, 50, 76), points)
        pygame.draw.polygon(self.canvas, color, points, max(1, int(2*scale)))
        pygame.draw.polygon(self.canvas, (92, 221, 255), [(x,y-43*scale),(x-11*scale,y+19*scale),(x,y+32*scale),(x+11*scale,y+19*scale)])
        pygame.draw.polygon(self.canvas, (145,245,255), [(x,y-31*scale),(x-5*scale,y+11*scale),(x+5*scale,y+11*scale)])
        for side in (-1, 1):
            pygame.draw.circle(self.canvas, (255, 126, 52), (int(x+side*31*scale), int(y+27*scale)), max(2, int(5*scale)))

    def draw_enemy(self, e):
        scale = 1 if e.kind == "ovni" else 1.38 if e.kind == "nodriza" else 2.4
        name = "ovnirojo.png" if e.kind == "ovni" else "nodriza.png" if e.kind == "nodriza" else "crucero_Emperdor.png"
        size = (70*scale, 60*scale) if e.kind == "ovni" else (130*scale, 75*scale) if e.kind == "nodriza" else (300, 150)
        im = self.image(name, size)
        if im:
            self.canvas.blit(im, im.get_rect(center=(int(e.x), int(e.y))))
        else:
            color = RED if e.kind == "ovni" else GOLD
            points = [(e.x, e.y-25*scale),(e.x-48*scale,e.y),(e.x-24*scale,e.y+20*scale),(e.x+24*scale,e.y+20*scale),(e.x+48*scale,e.y)]
            pygame.draw.polygon(self.canvas, (42, 23, 45), points)
            pygame.draw.polygon(self.canvas, color, points, 3)
            pygame.draw.ellipse(self.canvas, (44, 131, 170), (e.x-19*scale,e.y-5*scale,38*scale,15*scale))
        if e.kind != "ovni":
            width = 110 if e.kind == "boss" else 76
            pygame.draw.rect(self.canvas, (22,30,46),(e.x-width/2,e.y-size[1]*.60,width,5),border_radius=3)
            pygame.draw.rect(self.canvas, RED,(e.x-width/2,e.y-size[1]*.60,width*e.hp/e.max_hp,5),border_radius=3)

    def shoot(self, kind):
        if kind == "burst" and self.fire_clock <= 0:
            self.shots.extend((Shot(self.player_x-17,self.player_y-37,kind,-13), Shot(self.player_x+17,self.player_y-37,kind,-13)))
            self.fire_clock = .16
            self.sound("burst", volume=.36)
        elif kind == "missile" and self.missile_clock <= 0:
            self.shots.append(Shot(self.player_x,self.player_y-40,kind,-11)); self.missile_clock=.65
            self.sound("missile", volume=.72)
        elif kind == "laser" and self.laser_clock <= 0:
            self.shots.append(Shot(self.player_x,self.player_y-50,kind,-19)); self.laser_clock=.42
            self.sound("laser", volume=.58)

    def hit_player(self):
        if self.invulnerable <= 0:
            self.lives -= 1; self.invulnerable=1.15
            self.effects.append([self.player_x,self.player_y,0,RED])
            self.sound("explosion", volume=.82)
            if self.lives <= 0:
                self.state="defeat"
                self.sound("defeat", volume=.8)

    def update(self, dt, keys):
        self.elapsed += dt
        if self.transition_timer > 0:
            self.transition_timer = max(0, self.transition_timer-dt)
            return
        self.audio_clock = max(0, self.audio_clock-dt)
        self.fire_clock-=dt; self.missile_clock-=dt; self.laser_clock-=dt; self.invulnerable-=dt
        speed=510*dt
        dx=(keys[pygame.K_RIGHT] or keys[pygame.K_d])-(keys[pygame.K_LEFT] or keys[pygame.K_a])
        dy=(keys[pygame.K_DOWN] or keys[pygame.K_s])-(keys[pygame.K_UP] or keys[pygame.K_w])
        self.player_x=clamp(self.player_x+dx*speed,60,W-60)
        self.player_y=clamp(self.player_y+dy*speed,H*.53,H*.86)
        if keys[pygame.K_w] or keys[pygame.K_SPACE]: self.shoot("burst")
        if keys[pygame.K_e]: self.shoot("missile")
        if keys[pygame.K_q]: self.shoot("laser")
        for escort in self.escorts:
            if not escort.active:
                continue
            escort.invulnerable=max(0,escort.invulnerable-dt)
            escort.cooldown=max(0,escort.cooldown-dt)
            target=min((e for e in self.enemies if e.active), key=lambda e:(e.x-escort.x)**2+(e.y-escort.y)**2, default=None)
            if target:
                target_x=target.x+escort.side*48
                target_y=clamp(target.y+145, H*.46, H*.70)
            else:
                target_x=self.player_x+escort.side*94
                target_y=self.player_y+34
            escort.vx=(escort.vx+(target_x-escort.x)*.9*dt)*.88
            escort.vy=(escort.vy+(target_y-escort.y)*.9*dt)*.88
            escort.x=clamp(escort.x+clamp(escort.vx,-440*dt,440*dt),45,W-45)
            escort.y=clamp(escort.y+clamp(escort.vy,-400*dt,400*dt),H*.40,H*.78)
            if target and escort.cooldown<=0 and len(self.shots)<120:
                self.shots.append(Shot(escort.x,escort.y-27,"escort",-16))
                escort.cooldown=random.uniform(.64,.98)
        for e in self.enemies:
            if not e.active: continue
            e.phase += dt
            e.x += math.sin(e.phase*1.1)*dt*(60 if e.kind == "ovni" else 37)
            e.y += math.sin(e.phase*.62)*dt*(12 if e.kind == "ovni" else 6)
            e.cooldown -= dt
            if e.cooldown <= 0 and e.y < H*.65:
                e.cooldown=random.uniform(1.8,3.5)/(1+(self.level-1)*.12)
                self.hostile.append(Shot(e.x,e.y+23,"enemy",270+25*self.level))
                self.sound("mothership" if e.kind in ("nodriza", "boss") else "enemy", volume=.34 if e.kind == "ovni" else .52)
        for s in self.shots[:]:
            s.y += s.vy*60*dt
            if s.y < -40: self.shots.remove(s); continue
            for e in self.enemies:
                if e.active and (s.x-e.x)**2+(s.y-e.y)**2 < (62 if e.kind=="boss" else 47 if e.kind=="nodriza" else 34)**2:
                    damage=1 if s.kind=="burst" else 3 if s.kind=="laser" else (4 if e.kind=="boss" else 2)
                    if e.kind=="nodriza" and s.kind=="burst": damage=0
                    e.hp-=damage
                    if s in self.shots: self.shots.remove(s)
                    if e.hp<=0:
                        e.active=False; self.score+=500 if e.kind=="boss" else 180 if e.kind=="nodriza" else 100
                        self.effects.append([e.x,e.y,0,GOLD])
                        self.sound("explosion", volume=.85 if e.kind=="boss" else .62)
                        if e.kind == "nodriza": self.sound("carrier", volume=.38)
                    break
        for s in self.hostile[:]:
            s.y += s.vy*dt
            if (s.y>H+20): self.hostile.remove(s)
            elif (s.x-self.player_x)**2+(s.y-self.player_y)**2<40**2:
                self.hostile.remove(s); self.hit_player()
            else:
                target=next((escort for escort in self.escorts if escort.active and escort.invulnerable<=0 and (s.x-escort.x)**2+(s.y-escort.y)**2<34**2),None)
                if target:
                    self.hostile.remove(s)
                    target.lives-=1
                    target.invulnerable=.75
                    self.effects.append([target.x,target.y,0,CYAN])
                    self.sound("explosion",volume=.35)
                    if target.lives<=0:
                        target.active=False
                        self.effects.append([target.x,target.y,0,GOLD])
                        self.sound("explosion",volume=.65)
        for enemy in self.enemies:
            if not enemy.active: continue
            for escort in self.escorts:
                if escort.active and escort.invulnerable<=0 and (enemy.x-escort.x)**2+(enemy.y-escort.y)**2 < (180 if enemy.kind=="boss" else 58)**2:
                    escort.lives-=1
                    escort.invulnerable=.75
                    self.effects.append([escort.x,escort.y,0,CYAN])
                    if escort.lives<=0: escort.active=False
        for fx in self.effects: fx[2]+=dt
        self.effects=[fx for fx in self.effects if fx[2]<.55]
        if not any(e.active for e in self.enemies):
            if self.level < 5:
                self.transition_from_level=self.level
                self.transition_bonus=250*self.transition_from_level+max(0,self.lives)*50
                self.score+=self.transition_bonus
                self.level+=1
                self.lives=10
                self.player_x,self.player_y=W/2,H*.78
                self.spawn_level()
                self.transition_to_level=self.level
                self.transition_timer=5.0
                self.sound("ovni", volume=.42)
            else:
                self.state="victory"
                self.sound("victory", volume=.85)

    def draw_hud(self):
        # Barra superior simétrica: sector, puntuación y contactos comparten eje central.
        bar_x, bar_y, bar_w = W/2-440, 20, 880
        self.panel((bar_x,bar_y,bar_w,86),fill=(5,16,31,222))
        self.text("SECTOR",bar_x+28,bar_y+15,12,MUTED)
        self.text(f"{self.level:02d} / 05",bar_x+28,bar_y+39,22,CYAN)
        self.text(GALAXIES[self.level-1],bar_x+115,bar_y+17,15,(230,244,255))
        self.text(SCENES[self.level-1][2],bar_x+115,bar_y+46,12,MUTED)
        pygame.draw.line(self.canvas,(45,82,105),(W/2-45,bar_y+14),(W/2-45,bar_y+71),1)
        self.text("PUNTUACIÓN",W/2+68,bar_y+14,12,MUTED,True)
        self.text(f"{self.score:08d}",W/2+68,bar_y+46,24,GOLD,True)
        active=sum(e.active for e in self.enemies)
        pygame.draw.line(self.canvas,(45,82,105),(W/2+181,bar_y+14),(W/2+181,bar_y+71),1)
        self.text("CONTACTOS",bar_x+bar_w-130,bar_y+15,12,MUTED,True)
        self.text(f"{active:02d}",bar_x+bar_w-130,bar_y+49,24,(236,247,255),True)
        # Integridad centrada bajo la nave y controles alineados en el borde inferior.
        self.panel((W/2-250,H-126,500,46),fill=(5,17,29,220))
        self.text("ESC",W/2-210,H-103,12,MUTED,True)
        pygame.draw.rect(self.canvas,(24,39,54),(W/2-185,H-107,160,9),border_radius=4)
        pygame.draw.rect(self.canvas,RED if self.lives<=3 else CYAN,(W/2-185,H-107,160*max(0,self.lives)/10,9),border_radius=4)
        self.text(f"{max(0,self.lives):02d}",W/2-7,H-103,12,(255,222,229) if self.lives<=3 else (215,244,255),True)
        for escort in self.escorts:
            xx=W/2+escort.side*212
            color=CYAN if escort.active else (81,91,104)
            pygame.draw.polygon(self.canvas,color,[(xx,H-111),(xx-7,H-99),(xx+7,H-99)])
            pygame.draw.rect(self.canvas,(24,39,54),(xx-18,H-95,36,4),border_radius=2)
            if escort.active:
                pygame.draw.rect(self.canvas,(75,220,255),(xx-18,H-95,36*escort.lives/10,4),border_radius=2)
        self.ui_buttons.clear()
        if self.transition_timer <= 0:
            self.draw_action_buttons()
        self.text("W / ESPACIO  RÁFAGA     E  MISIL     Q  LÁSER     P  PAUSA",W/2,H-13,12,MUTED,True)

    def draw_action_buttons(self):
        """Dibuja y guarda las zonas de clic para las acciones de partida."""
        labels = (("restart", "REINICIAR"), ("pause", "CONTINUAR" if self.paused else "PAUSA"), ("finish", "FINALIZAR"))
        button_w, button_h, gap = 126, 38, 12
        x0, y = W/2-(button_w*3+gap*2)/2, H-70
        mouse_x, mouse_y = pygame.mouse.get_pos()
        screen_w, screen_h = self.screen.get_size()
        mouse_x, mouse_y = mouse_x*W/max(1,screen_w), mouse_y*H/max(1,screen_h)
        self.ui_buttons.clear()
        for i, (action, label) in enumerate(labels):
            rect = pygame.Rect(round(x0+i*(button_w+gap)), y, button_w, button_h)
            self.ui_buttons[action] = rect
            hovered = rect.collidepoint(mouse_x, mouse_y)
            edge = (91, 212, 239) if hovered else (48, 111, 146)
            fill = (15, 48, 67, 245) if hovered else (7, 22, 38, 230)
            layer = pygame.Surface(rect.size, pygame.SRCALPHA)
            pygame.draw.rect(layer, fill, layer.get_rect(), border_radius=8)
            self.canvas.blit(layer, rect)
            pygame.draw.rect(self.canvas, edge, rect, 2 if hovered else 1, border_radius=8)
            color = RED if action == "finish" else CYAN if action == "pause" else (225, 239, 250)
            self.text(label, rect.centerx, rect.centery, 15, color, True)

    def draw_game(self):
        for e in self.enemies:
            if e.active: self.draw_enemy(e)
        for escort in self.escorts:
            if not escort.active or (escort.invulnerable>0 and int(self.elapsed*12)%2):
                continue
            sprite_name="cazaf2_der.png" if escort.vx>25 else "cazaf2_izq.png" if escort.vx<-25 else "cazaf2_centro.png"
            sprite=self.image(sprite_name,(76,76))
            if sprite:
                sprite=sprite.copy()
                sprite.fill((115,202,255,220),special_flags=pygame.BLEND_RGBA_MULT)
                self.canvas.blit(sprite,sprite.get_rect(center=(int(escort.x),int(escort.y))))
            else:
                self.draw_ship(escort.x,escort.y,.62,(115,220,255))
            pygame.draw.rect(self.canvas,(24,39,54),(escort.x-24,escort.y+39,48,4),border_radius=2)
            pygame.draw.rect(self.canvas,CYAN,(escort.x-24,escort.y+39,48*escort.lives/10,4),border_radius=2)
        for s in self.shots:
            if s.kind=="burst":
                pygame.draw.line(self.canvas,(255,215,103),(s.x,s.y-10),(s.x,s.y+11),3)
                pygame.draw.line(self.canvas,(255,255,220),(s.x,s.y-10),(s.x,s.y+11),1)
            elif s.kind=="missile":
                pygame.draw.polygon(self.canvas,GOLD,[(s.x,s.y-13),(s.x-5,s.y+8),(s.x,s.y+5),(s.x+5,s.y+8)])
                pygame.draw.line(self.canvas,RED,(s.x,s.y+9),(s.x,s.y+22),2)
            elif s.kind=="escort":
                pygame.draw.line(self.canvas,(86,211,255),(s.x,s.y-14),(s.x,s.y+9),4)
                pygame.draw.circle(self.canvas,(226,250,255),(int(s.x),int(s.y-12)),2)
            else:
                pygame.draw.line(self.canvas,(255,110,239),(s.x,s.y-34),(s.x,s.y+10),9)
                pygame.draw.line(self.canvas,(255,235,255),(s.x,s.y-32),(s.x,s.y+9),3)
        for s in self.hostile:
            pygame.draw.circle(self.canvas,RED,(int(s.x),int(s.y)),5)
            pygame.draw.circle(self.canvas,(255,188,133),(int(s.x),int(s.y)),2)
        for x,y,t,color in self.effects:
            r=int(14+65*t/.55)
            pygame.draw.circle(self.canvas,color,(int(x),int(y)),r,2)
            pygame.draw.circle(self.canvas,(255,236,182),(int(x),int(y)),max(2,r//3),1)
        if self.invulnerable<=0 or int(self.elapsed*12)%2==0:
            ship=self.image("cazaf2_centro.png",(100,100))
            if ship: self.canvas.blit(ship,ship.get_rect(center=(int(self.player_x),int(self.player_y))))
            else: self.draw_ship(self.player_x,self.player_y)
        self.draw_hud()

    def draw_title(self):
        im=self.image("fondo_intro.png",(W,H))
        if im: self.canvas.blit(im,(0,0)); veil=pygame.Surface((W,H),pygame.SRCALPHA); veil.fill((3,9,24,116)); self.canvas.blit(veil,(0,0))
        self.panel((W/2-345,H*.16,690,H*.61),fill=(5,13,29,205),edge=(60,157,196))
        self.text("AÑO 2147     /     ALERTA DE INVASIÓN",W/2,H*.24,18,GOLD,True)
        self.text("INVASION",W/2,H*.34,68,(224,247,255),True)
        self.text("LOS XHAR'KOR HAN LLEGADO A LA TIERRA",W/2,H*.43,22,CYAN,True)
        self.text("Comandante Thiakor Gómez: tú eres la última línea de defensa.",W/2,H*.52,18,(208,224,238),True)
        self.text("5 GALAXIAS     ·     ARMAMENTO TÁCTICO     ·     JEFE FINAL",W/2,H*.60,15,GOLD,True)
        pulse=.72+.28*math.sin(pygame.time.get_ticks()*.004)
        self.text("PULSA ESPACIO PARA DESPEGAR",W/2,H*.68,22,(int(72*pulse),int(225*pulse),255),True)
        self.text("FLECHAS / WASD: VUELO     W: RÁFAGA     E: MISIL     Q: LÁSER",W/2,H*.84,15,MUTED,True)
        self.text("M: AUDIO ACTIVADO" if self.sound_enabled else "M: AUDIO SILENCIADO",W/2,H*.89,12,MUTED,True)

    def draw_transition(self):
        from_level,to_level=self.transition_from_level,self.transition_to_level
        bg=self.images.get(f"salto{from_level}_{to_level}.png")
        if bg:
            self.canvas.blit(pygame.transform.smoothscale(bg,(W,H)),(0,0))
        veil=pygame.Surface((W,H),pygame.SRCALPHA)
        veil.fill((3,8,19,118))
        self.canvas.blit(veil,(0,0))
        progress=clamp(1-self.transition_timer/5.0,0,1)
        pulse=.55+.45*math.sin(self.elapsed*7)
        # Líneas de velocidad y estrellas convergen en la trayectoria de salto.
        travel_x=W*(.21+.58*progress)
        for i in range(24):
            yy=(i*47+int(self.elapsed*190))%H
            length=35+(i%5)*18
            pygame.draw.line(self.canvas,(34,100,151),(travel_x-length,yy),(travel_x+length,yy),1)
        self.text("SALTO INTERGALÁCTICO",W/2,H*.13,44,GOLD,True)
        self.text("RUTA DE TRANSFERENCIA  /  ESCUADRÓN DE DEFENSA",W/2,H*.205,16,(220,237,250),True)

        left_x,right_x=W*.17,W*.83
        route_y=H*.48
        for idx,(x,level,label) in enumerate(((left_x,from_level,GALAXIES[from_level-1]),(right_x,to_level,GALAXIES[to_level-1]))):
            image=self.images.get("nebulosa_1.png" if idx==0 else "nebulosa_2_nueva.png") or self.images.get("nebulosa_2.png")
            if image:
                cloud=pygame.transform.smoothscale(image,(225,154))
                cloud.set_alpha(205)
                self.canvas.blit(cloud,cloud.get_rect(center=(int(x),int(route_y))))
            pygame.draw.ellipse(self.canvas,SCENES[level-1][0],(x-112,route_y-77,224,154),3)
            self.text(label,x,route_y+100,16,(235,244,255),True)
            self.text(f"SECTOR {level:02d}",x,route_y+125,12,MUTED,True)

        pygame.draw.line(self.canvas,(69,168,215),(left_x+120,route_y),(right_x-120,route_y),3)
        pygame.draw.line(self.canvas,(16,43,65),(left_x+120,route_y+9),(right_x-120,route_y+9),1)
        convoy=self.image("cazaf2_centro.png",(58,58))
        for ox,oy,scale in ((0,0,1),(-30,-28,.72),(-30,28,.72)):
            x=travel_x+ox
            y=route_y+oy+math.sin(self.elapsed*5+oy)*4
            if convoy:
                ship=pygame.transform.smoothscale(convoy,(int(58*scale),int(58*scale)))
                ship=pygame.transform.rotate(ship,-90)
                ship.set_alpha(int(255*pulse) if scale==1 else 220)
                self.canvas.blit(ship,ship.get_rect(center=(int(x),int(y))))
            else:
                pygame.draw.polygon(self.canvas,CYAN,[(x+24*scale,y),(x-15*scale,y-12*scale),(x-15*scale,y+12*scale)])
            pygame.draw.line(self.canvas,GOLD,(x-28*scale,y),(x-43*scale,y),2)

        bar_w=740
        self.panel((W/2-bar_w/2,H*.72,bar_w,58),fill=(5,15,31,225))
        pygame.draw.rect(self.canvas,(22,38,56),(W/2-bar_w/2+20,H*.72+17,bar_w-40,12),border_radius=6)
        pygame.draw.rect(self.canvas,CYAN,(W/2-bar_w/2+20,H*.72+17,(bar_w-40)*progress,12),border_radius=6)
        self.text(f"TRÁNSITO HIPERESPACIAL   {int(progress*100):02d}%",W/2,H*.72+43,14,(225,240,250),True)
        self.text(f"NUEVO SECTOR EN {max(1,math.ceil(self.transition_timer))} s     ·     BONO DE ESCUADRÓN +{self.transition_bonus}     ·     PUNTOS {self.score:08d}",W/2,H*.85,16,GOLD,True)

    def draw_end(self, victory):
        self.panel((W/2-320,H/2-155,640,310),fill=(5,13,29,235),edge=GOLD if victory else RED)
        self.text("TIERRA SALVADA" if victory else "SEÑAL PERDIDA",W/2,H/2-77,44,GOLD if victory else RED,True)
        self.text("El Imperio Xhar'Kor ha sido derrotado." if victory else "La invasión ha superado nuestras defensas.",W/2,H/2-20,18,(219,234,246),True)
        self.text(f"PUNTUACIÓN FINAL   {self.score:07d}",W/2,H/2+28,22,CYAN,True)
        self.text("ESPACIO: NUEVA MISIÓN     ·     ESC: SALIR",W/2,H/2+94,16,MUTED,True)

    def run(self):
        running=True
        while running:
            dt=min(self.clock.tick(60)/1000, .04)
            keys=pygame.key.get_pressed()
            for ev in pygame.event.get():
                if ev.type==pygame.QUIT: running=False
                elif ev.type==pygame.MOUSEBUTTONDOWN and ev.button==1 and self.state=="game":
                    screen_w, screen_h = self.screen.get_size()
                    point=(round(ev.pos[0]*W/max(1,screen_w)), round(ev.pos[1]*H/max(1,screen_h)))
                    action=next((name for name,rect in self.ui_buttons.items() if rect.collidepoint(point)),None)
                    if action=="restart":
                        self.stop_audio(); self.reset(); self.state="game"
                    elif action=="pause": self.paused=not self.paused
                    elif action=="finish":
                        self.stop_audio(); running=False
                elif ev.type==pygame.KEYDOWN:
                    if ev.key==pygame.K_ESCAPE: running=False
                    elif self.state=="title" and ev.key in (pygame.K_SPACE,pygame.K_RETURN):
                        self.stop_audio(); self.reset(); self.state="game"
                    elif self.state in ("victory","defeat") and ev.key==pygame.K_SPACE:
                        self.stop_audio(); self.reset(); self.state="game"
                    elif self.state=="game" and ev.key==pygame.K_p: self.paused=not self.paused
                    elif ev.key==pygame.K_m:
                        self.sound_enabled=not self.sound_enabled
                        if not self.sound_enabled: self.stop_audio()
                        elif self.state=="title": self.sound("intro",loops=-1,volume=.22)
                    elif self.state=="game" and ev.key in (pygame.K_e,pygame.K_q): self.shoot("missile" if ev.key==pygame.K_e else "laser")
                elif ev.type==pygame.VIDEORESIZE:
                    self.screen=pygame.display.set_mode(ev.size,pygame.RESIZABLE|pygame.DOUBLEBUF)
            self.backdrop(dt)
            if self.state=="title": self.draw_title()
            elif self.state=="game":
                if not self.paused: self.update(dt,keys)
                self.draw_game()
                if self.transition_timer > 0:
                    self.draw_transition()
                elif self.paused:
                    self.panel((W/2-190,H/2-63,380,126)); self.text("PAUSA TÁCTICA",W/2,H/2-18,30,CYAN,True); self.text("P  /  CONTINUAR",W/2,H/2+29,18,MUTED,True)
            else: self.draw_end(self.state=="victory")
            ww,hh=self.screen.get_size()
            self.screen.blit(pygame.transform.smoothscale(self.canvas,(ww,hh)),(0,0))
            pygame.display.flip()
        pygame.quit(); sys.exit()


if __name__ == "__main__":
    Invasio().run()
