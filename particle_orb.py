"""
particle_orb.py
================

A reactive particle-sphere "AI orb" visualization, similar to voice-assistant
UIs like Iris/Jarvis: a cloud of dots forming a sphere that

  - IDLE       gently breathes and rotates
  - LISTENING  spreads/pulses outward based on your microphone volume
  - SPEAKING   changes color and makes the dots "jump" energetically
               (driven by a simulated waveform, or by real audio level
               if you feed it one, e.g. from your TTS output)

Run it directly for a live demo (mic-reactive listening + simulated
speaking), or import ParticleOrb into your own assistant and drive it
programmatically -- see the "INTEGRATION" section at the bottom.

Controls in the demo window:
  SPACE   cycle IDLE -> LISTENING -> SPEAKING -> IDLE
  ESC / Q quit

Install:
  pip install pygame numpy sounddevice

(sounddevice/microphone input is optional -- if it's not installed or no
mic is available, LISTENING falls back to a simulated waveform so the
demo still runs.)
"""

import math
import random
import threading
import time

import numpy as np
import pygame

# Microphone input is optional.
try:
    import sounddevice as sd
    _HAS_AUDIO = True
except Exception:
    _HAS_AUDIO = False


# ----------------------------------------------------------------------
# Visual states
# ----------------------------------------------------------------------
IDLE = "idle"
LISTENING = "listening"
SPEAKING = "speaking"

# Base RGB color per state, plus a "hot" color the dots shift toward
# as their individual energy rises.
STATE_COLORS = {
    IDLE:      {"base": (70, 200, 180), "hot": (170, 255, 230)},
    LISTENING: {"base": (70, 140, 255), "hot": (150, 210, 255)},
    SPEAKING:  {"base": (200, 80, 220), "hot": (255, 170, 90)},
}


def _fibonacci_sphere(n):
    """Return n roughly evenly-spaced unit vectors on a sphere."""
    points = []
    phi = math.pi * (3.0 - math.sqrt(5.0))  # golden angle
    for i in range(n):
        y = 1 - (i / float(n - 1)) * 2       # y from 1 to -1
        r = math.sqrt(max(0.0, 1 - y * y))
        theta = phi * i
        x = math.cos(theta) * r
        z = math.sin(theta) * r
        points.append((x, y, z))
    return points


class _MicMeter:
    """Background microphone RMS-level meter, smoothed to 0..1."""

    def __init__(self):
        self.level = 0.0
        self._stream = None
        self._lock = threading.Lock()

    def _callback(self, indata, frames, time_info, status):
        rms = float(np.sqrt(np.mean(np.square(indata))))
        # Rough normalization -- typical speech RMS is small, so scale up.
        norm = min(1.0, rms * 12.0)
        with self._lock:
            # Smooth so the sphere doesn't flicker on every audio block.
            self.level = self.level * 0.7 + norm * 0.3

    def start(self):
        if not _HAS_AUDIO:
            return False
        try:
            self._stream = sd.InputStream(
                channels=1, samplerate=16000, blocksize=1024,
                callback=self._callback,
            )
            self._stream.start()
            return True
        except Exception:
            self._stream = None
            return False

    def stop(self):
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

    def get(self):
        with self._lock:
            return self.level


class ParticleOrb:
    """
    A rotating particle-sphere widget you can run standalone or embed.

    Typical integration in your own assistant:

        orb = ParticleOrb()
        orb.start()                  # opens the window, runs in background

        orb.set_state("listening")   # when you begin recording the user
        ...
        orb.set_state("speaking")    # when your TTS starts playing
        orb.feed_amplitude(level)    # optional: call repeatedly with your
                                      # TTS output's 0..1 volume for the
                                      # "jumping" motion to match real speech
        ...
        orb.set_state("idle")        # back to resting state
        orb.stop()
    """

    def __init__(self, width=760, height=760, num_particles=850, use_mic=True):
        self.width = width
        self.height = height
        self.num_particles = num_particles
        self.base_radius = min(width, height) * 0.30

        self.state = IDLE
        self._external_amp = 0.0     # amplitude fed in via feed_amplitude()
        self._running = False
        self._thread = None

        # Each particle: unit direction on the sphere + a random phase/speed
        # so they don't all pulse in lockstep -- gives the organic
        # "every ball jumping on its own" look.
        dirs = _fibonacci_sphere(num_particles)
        self._dirs = np.array(dirs)
        self._phase = np.random.uniform(0, math.tau, num_particles)
        self._speed = np.random.uniform(0.8, 2.4, num_particles)
        self._depth_jitter = np.random.uniform(0.85, 1.15, num_particles)

        self._mic = _MicMeter() if use_mic else None
        self._mic_on = False

    # -- public control API -------------------------------------------------

    def set_state(self, state):
        """state: one of IDLE, LISTENING, SPEAKING."""
        if state not in STATE_COLORS:
            raise ValueError(f"unknown state: {state}")
        if state == LISTENING and self._mic is not None and not self._mic_on:
            self._mic_on = self._mic.start()
        if state != LISTENING and self._mic_on:
            self._mic.stop()
            self._mic_on = False
        self.state = state

    def feed_amplitude(self, level):
        """Feed a 0..1 volume level (e.g. from your TTS playback) to drive
        the SPEAKING motion with real audio instead of the simulated wave."""
        self._external_amp = max(0.0, min(1.0, level))

    def start(self):
        """Run the visualization window in a background thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._mic_on:
            self._mic.stop()
        if self._thread:
            self._thread.join(timeout=1.0)

    def run_blocking(self):
        """Run the visualization on the calling thread (blocks until closed)."""
        self._running = True
        self._run_loop()

    # -- internals ------------------------------------------------------

    def _current_amplitude(self, t):
        """0..1 'energy' level depending on state."""
        if self.state == IDLE:
            # slow gentle breathing
            return 0.12 + 0.05 * math.sin(t * 0.9)
        if self.state == LISTENING:
            if self._mic_on:
                return self._mic.get()
            # simulated mic level if no audio device available
            return 0.25 + 0.25 * abs(math.sin(t * 2.3)) + 0.1 * random.random()
        if self.state == SPEAKING:
            if self._external_amp > 0.001:
                return self._external_amp
            # simulated speech waveform: layered sines + noise bursts
            wave = (
                0.5
                + 0.3 * math.sin(t * 6.0)
                + 0.2 * math.sin(t * 13.0 + 1.3)
            )
            burst = 0.15 if random.random() < 0.08 else 0.0
            return max(0.0, min(1.0, wave + burst))
        return 0.1

    def _lerp_color(self, base, hot, f):
        f = max(0.0, min(1.0, f))
        return tuple(int(base[i] + (hot[i] - base[i]) * f) for i in range(3))

    def _run_loop(self):
        pygame.init()
        screen = pygame.display.set_mode((self.width, self.height))
        pygame.display.set_caption("Particle Orb")
        clock = pygame.time.Clock()
        font = pygame.font.SysFont("consolas", 16)

        cx, cy = self.width // 2, self.height // 2
        angle = 0.0
        t0 = time.time()

        while self._running:
            t = time.time() - t0

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self._running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key in (pygame.K_ESCAPE, pygame.K_q):
                        self._running = False
                    elif event.key == pygame.K_SPACE:
                        order = [IDLE, LISTENING, SPEAKING]
                        self.set_state(order[(order.index(self.state) + 1) % 3])

            screen.fill((8, 10, 18))

            amp = self._current_amplitude(t)
            colors = STATE_COLORS[self.state]
            angle += 0.006 + amp * 0.01  # rotate faster with more "energy"

            cos_a, sin_a = math.cos(angle), math.sin(angle)
            tilt = math.radians(18)
            cos_t, sin_t = math.cos(tilt), math.sin(tilt)

            # per-particle radial jump: individual phase/speed for organic motion
            jump = 1.0 + amp * 0.55 * np.sin(t * self._speed + self._phase)
            radius = self.base_radius * self._depth_jitter * jump

            x = self._dirs[:, 0]
            y = self._dirs[:, 1]
            z = self._dirs[:, 2]

            # rotate around Y axis
            xr = x * cos_a - z * sin_a
            zr = x * sin_a + z * cos_a
            # slight tilt around X axis for a nicer angle
            yr = y * cos_t - zr * sin_t
            zr2 = y * sin_t + zr * cos_t

            xr *= radius
            yr *= radius
            zr2 *= radius

            # simple perspective projection
            fov = 620
            scale = fov / (fov + zr2)
            sx = cx + xr * scale
            sy = cy + yr * scale

            # depth sorting so far particles draw first
            order = np.argsort(zr2)

            for i in order:
                depth_f = (zr2[i] + radius[i]) / (2 * radius[i] + 1e-6)
                size = max(1, int(1.6 * scale[i] + 1))
                energy = min(1.0, amp * 1.6 * self._depth_jitter[i])
                col = self._lerp_color(colors["base"], colors["hot"], energy * (0.4 + 0.6 * depth_f))
                pygame.draw.circle(screen, col, (int(sx[i]), int(sy[i])), size)

            label = font.render(f"state: {self.state}   (SPACE to cycle, ESC to quit)", True, (140, 160, 190))
            screen.blit(label, (14, self.height - 28))

            pygame.display.flip()
            clock.tick(60)

        pygame.quit()


# ----------------------------------------------------------------------
# Standalone demo
# ----------------------------------------------------------------------
if __name__ == "__main__":
    orb = ParticleOrb()
    orb.run_blocking()

# ----------------------------------------------------------------------
# INTEGRATION NOTES
# ----------------------------------------------------------------------
# Drop this file next to your voice-assistant script and drive it like:
#
#   from particle_orb import ParticleOrb
#   orb = ParticleOrb()
#   orb.start()                    # non-blocking, opens its own window
#
#   # when you start listening for the user's voice:
#   orb.set_state("listening")     # dots spread based on YOUR mic input automatically
#
#   # when your TTS starts speaking the reply:
#   orb.set_state("speaking")
#   # optionally, if you can get your TTS engine's live output level,
#   # call this repeatedly while it plays for the jump motion to match
#   # the actual reply audio instead of the built-in simulated wave:
#   orb.feed_amplitude(current_tts_volume_0_to_1)
#
#   # back to resting:
#   orb.set_state("idle")
#
#   # on shutdown:
#   orb.stop()
