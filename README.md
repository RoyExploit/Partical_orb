<img width="530" height="490" alt="image" src="https://github.com/user-attachments/assets/10423ada-a168-43e1-88d6-ce11af6d20e6" />

# Particle Orb

A reactive particle-sphere visualization for a voice assistant UI, like the
IRIS-style orb: a cloud of dots forming a rotating sphere.

- **Idle** — gentle breathing, slow rotation
- **Listening** — dots spread/pulse based on your **live microphone volume**
- **Speaking** — dots change color and jump energetically (simulated wave by
  default, or driven by real TTS audio level if you feed it one)

## Setup

```bash
pip install pygame numpy sounddevice
```

`sounddevice` needs PortAudio installed on your system:
- **Windows / macOS**: usually works out of the box via the pip wheel.
- **Linux**: `sudo apt install portaudio19-dev` if the pip install complains.

If `sounddevice` isn't available or no microphone is found, "Listening" mode
automatically falls back to a simulated waveform, so the demo still runs.

## Try it standalone

```bash
python particle_orb.py
```

Press **SPACE** to cycle Idle → Listening → Speaking → Idle.
Press **ESC** or **Q** to quit.

While in Listening mode, talk near your mic — the sphere spreads outward with
your volume.

## Wiring it into your own assistant (e.g. IRIS AI)

```python
from particle_orb import ParticleOrb

orb = ParticleOrb()
orb.start()                 # opens the window, runs in the background

# when you begin recording the user's speech:
orb.set_state("listening")  # dots now react to the real mic automatically

# when your TTS starts speaking the reply:
orb.set_state("speaking")

# optional: if your TTS engine exposes a live output level (0..1),
# call this repeatedly while audio plays so the jump motion matches
# the actual reply instead of the built-in simulated wave:
orb.feed_amplitude(current_tts_volume_0_to_1)

# back to resting:
orb.set_state("idle")

# on shutdown:
orb.stop()
```

## Tuning it

Open `particle_orb.py` and adjust:

- `STATE_COLORS` — the base/hot color pair for each state (currently teal for
  idle, blue for listening, magenta→orange for speaking)
- `num_particles` in `ParticleOrb(...)` — more dots = denser sphere, costs
  more CPU
- `base_radius` — overall sphere size
- Inside `_current_amplitude()` — how strongly each state reacts, and the
  shape of the simulated waveforms
