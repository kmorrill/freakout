# MiniFreak Engine & FX Reference

Technical reference for all oscillator engines, FX algorithms, mod matrix destinations, and discrete parameter enums on the Arturia MiniFreak. Data sourced from firmware 4.x probe imports into MiniFreak V, factory preset analysis, hardware UI verification, and synthesis research.

For MIDI CC mappings see `midi-cc-mapping.md`. For preset file encoding see `parameter-analysis.md`. For preset creation see `preset-guide.md`.

---

## Engine Origins

The MiniFreak's engines come from three sources:
- **Arturia** — BasicWaves, SuperWave, VAnalog, Waveshaper, Two Op. FM, Harmo/Harm, Bass, SawX, Wavetable, Sample, and the granular engines (Cloud/Hit/Frozen/Particle)
- **Mutable Instruments Plaits** (open source) — Modal, Speech, Formant (ported from Émilie Gillet's Eurorack module)
- **Noise Engineering** (LA modular collaboration) — Lick, Skan, Raster

---

## Oscillator 1 Engines (24)

Firmware 4.x, encoded as `index / 23` in preset files.

Wave, Timbre, and Shape correspond to CC 10/11/12 (Osc1) or CC 15/16/17 (Osc2). The sonic meaning changes per engine but the CC numbers stay the same.

| Index | Engine | Wave | Timbre | Shape | Slot | Typical Use |
|-------|--------|------|--------|-------|------|-------------|
| 0 | BasicWaves | Waveform morph (Sq-Saw-DblSaw) | Pulse width / phase shift | Sub-osc sine level | Both | Fundamental subtractive waveforms |
| 1 | SuperWave | Waveform select (Saw/Sq/Tri/Sine) | Detune spread | Voice count / density | Both | Thick unison pads and leads |
| 2 | Harmo | Harmonic set selection | Harmonic level balance | Odd/even balance | Both | Additive synthesis |
| 3 | Karplus | Exciter position | Continuous excitation amount | Decay / damping time | Both | Plucked and struck strings |
| 4 | VAnalog | Osc waveform morph | Secondary osc shape | Detune amount | Both | Classic VA dual-oscillator |
| 5 | Waveshaper | Waveform select | Wavefold amount | Asymmetry | Both | Distorted / folded timbres |
| 6 | Two Op. FM | Modulator ratio | FM index (mod amount) | Feedback | Both | FM synthesis |
| 7 | Formant | Vowel / word bank select | Gender / formant shift | Word position scan | Both | Vocal / speech formants |
| 8 | Speech | Phoneme set / mode | Formant shift | Scan position | Both | Speech synthesis |
| 9 | Modal | Exciter shape | Brightness / partials | Damping | Both | Resonant body physical modeling |
| 10 | Noise | Noise type morph | Color / filter cutoff | Density | Both | Textural noise |
| 11 | Bass | Bass model type | Character / harmonics | Body / resonance | Both | Bass-optimized synthesis |
| 12 | SawX | Saw variation mode | Detune | Spread / stereo width | Both | Extended saw processing |
| 13 | Harm | Harmonic series set | Harmonic levels | Odd/even balance | Both | Harmonic oscillator variant |
| 14 | Audio In | Input level | Input filter ? | -- | Both | External audio as oscillator source |
| 15 | Wavetable | Wavetable bank select | Wavetable position scan | Wavetable filter ? | Osc1 only | Wavetable scanning |
| 16 | Sample | Sample select | Sample start position | -- ? | Osc1 only | Sample playback |
| 17 | Cloud Grains | Grain position | Grain density | Chaos / randomization | Osc1 only | Granular cloud synthesis |
| 18 | Hit Grains | Grain position | Grain density | -- ? | Osc1 only | Granular percussive hits |
| 19 | Frozen | Spectral position | Freeze depth | Chaos / randomization | Osc1 only | FFT spectral freeze |
| 20 | Skan | Spectral position | Time stretch | -- ? | Osc1 only | Spectral analysis resynthesis |
| 21 | Particle | Particle position | Particle density | -- ? | Osc1 only | Particle-based granular |
| 22 | Lick | Spectral position | Shape | -- ? | Osc1 only | Spectral lick synthesis |
| 23 | Raster | Position | Resolution / aliasing | -- ? | Osc1 only | Raster / bit-grid synthesis |

Engines 0-14 are shared between Osc1 and Osc2. Engines 15-23 are Osc1-only.

---

## Engine Deep Dives

### 0. BasicWaves — Subtractive Foundation

**What it models:** Classic analog oscillator waveforms — the building blocks of subtractive synthesis since the Moog era.

**Synthesis technique:** Morphable waveform with pulse width modulation and sub-oscillator mixing.

**Parameters:**
- **Wave:** Morphs continuously between Square → Sawtooth → Double Saw. The double saw is two saws slightly offset, creating a thicker, chorused sound.
- **Timbre:** Pulse width (at square) or phase offset (at saw). At 50% pulse width you get a hollow square; narrower values create nasal, reedy tones. On saw, shifts the phase relationship for subtle timbral changes.
- **Shape:** Sub-oscillator level. Blends in a sine wave one octave below, adding fundamental weight. Essential for bass patches.

**Sweet spots:** For classic bass, use mostly square with narrow pulse width and high sub. For leads, morph toward saw with moderate PWM from an LFO.

---

### 1. SuperWave — Unison Stacks

**What it models:** The Roland JP-8000's legendary "SuperSaw" (1997), which defined trance and EDM leads. Multiple detuned oscillators stacked together.

**Synthesis technique:** Up to 7 copies of a waveform, each slightly detuned against the others, creating massive unison thickness through beating frequencies.

**Parameters:**
- **Wave:** Selects base waveform — Sawtooth, Square, Triangle, or Sine. Saw is the classic trance choice; triangle creates softer pads.
- **Timbre:** Detune spread. Low values = subtle chorus. High values = massive, beating unison wall. The "supersaw" sound lives at moderate-to-high detune.
- **Shape:** Voice count / density. More voices = thicker sound but can become muddy. Fewer voices = cleaner but thinner.

**Sweet spots:** For anthem trance leads, use Saw with moderate detune (40-60%). For dreamy pads, use Triangle with subtle detune (20-30%).

**Historical note:** The JP-8000's SuperSaw became genre-defining for trance. Arturia analyzed the original and found it uses 7 free-running sawtooth oscillators with specific detune ratios.

---

### 2. Harmo — Additive Synthesis

**What it models:** Pipe organs and additive synthesizers (Hammond, Synclavier). Sound built from individual sine wave harmonics.

**Synthesis technique:** Additive synthesis — the opposite of subtractive. Instead of filtering harmonics out, you build them up by summing sine waves at integer frequency multiples.

**Parameters:**
- **Wave:** Selects a harmonic "recipe" or preset. Different presets emphasize different harmonic structures (organ-like drawbar settings).
- **Timbre:** Harmonic level balance. Adjusts the relative loudness of upper vs. lower harmonics.
- **Shape:** Odd/even balance. Odd harmonics (1, 3, 5...) create hollow, clarinet-like tones (square wave = only odd). Even harmonics (2, 4, 6...) create fuller, brighter sounds (saw wave = all harmonics). Adjusting this morphs between these characters.

**Sweet spots:** For organ sounds, emphasize fundamental + octave. For bright, brassy tones, boost even harmonics.

---

### 3. Karplus — Physical Modeling Strings

**What it models:** Plucked and struck strings — guitars, harps, harpsichords, marimbas, even steel drums. Based on the 1983 Karplus-Strong algorithm.

**Synthesis technique:** A burst of noise (the "pluck") is fed into a filtered delay line with feedback. The delay line length determines pitch; the filter controls brightness decay. This simple algorithm accurately models how real strings vibrate and decay.

**Parameters:**
- **Wave:** Exciter position. Simulates where on the string you're plucking — near the bridge (bright, thin) vs. middle (warm, full). Like the difference between a guitar pick near the bridge vs. over the soundhole.
- **Timbre:** Continuous excitation amount. At 0, you get one pluck that decays. Higher values continuously re-excite the string, creating bowed or sustained effects. At maximum, approaches a continuous tone.
- **Shape:** Decay / damping time. Short = palm-muted guitar, marimba. Long = sustaining harp, singing bowl. Controls how quickly the filter absorbs high frequencies, mimicking material damping.

**Sweet spots:** For plucked bass, use middle position with moderate decay. For mallets/bells, short decay with bright position. For bowed sounds, high continuous excitation.

**Why it sounds real:** The algorithm's transfer function mathematically matches actual vibrating string behavior. The filter in the feedback loop represents total string losses per period.

---

### 4. VAnalog — Virtual Analog Dual-Osc

**What it models:** Classic polysynths (Prophet-5, Juno-106, OB-X) that pair two oscillators with detuning for thickness.

**Synthesis technique:** Two oscillators with independent waveforms and slight detuning. The beating between them creates movement and warmth.

**Parameters:**
- **Wave:** Primary oscillator waveform morph. Smooth transition between classic shapes.
- **Timbre:** Secondary oscillator shape. Having different shapes creates timbral complexity; matching shapes creates pure beating.
- **Shape:** Detune amount between the two oscillators. Subtle = gentle chorus. Heavy = obvious beating, dramatic thickness.

**Sweet spots:** For vintage polysynth sounds, slight detune with saw waves. For leads, try different shapes between the two oscs.

---

### 5. Waveshaper — Wavefolding Distortion

**What it models:** West Coast synthesis (Buchla, Serge) and modern distortion units. Takes simple waveforms and creates complex spectra through nonlinear processing.

**Synthesis technique:** Waveshaping/wavefolding. A triangle wave is passed through a nonlinear transfer function. When amplitude exceeds a threshold, peaks "fold" back on themselves rather than clipping, creating harmonically rich, often metallic tones.

**Parameters:**
- **Wave:** Base waveform selection. Different input waveforms produce radically different folded outputs.
- **Timbre:** Wavefold amount. Low = subtle harmonics. High = aggressive, metallic squelch. The classic "acid" sound at high fold amounts.
- **Shape:** Asymmetry / offset. Shifts the center point of folding, so positive and negative halves of the wave are processed differently. Creates odd harmonics and asymmetric distortion. Center = symmetric, pure. Off-center = gritty, edgy.

**Sweet spots:** For acid bass, high fold with LFO modulation. For metallic percussion, maximum fold with short envelopes. The asymmetry control adds "character" — like tube vs. transistor distortion.

**Technical note:** Wavefolding differs from clipping/saturation. Clipping flattens peaks; folding inverts them. This creates a distinctively "synthesizer" distortion rather than amp-style overdrive.

---

### 6. Two Op. FM — Frequency Modulation

**What it models:** DX7-style FM synthesis, simplified to two operators. Covers bell-like tones, electric pianos, metallic pads, and aggressive digital sounds.

**Synthesis technique:** One sine wave (modulator) modulates the phase of another (carrier). This creates sidebands at sum and difference frequencies, producing harmonics not present in either original wave.

**Parameters:**
- **Wave (Ratio):** Frequency ratio between modulator and carrier. Integer ratios (1:1, 2:1, 3:1) produce harmonic spectra. Non-integer ratios (1.41:1, 2.37:1) produce inharmonic, bell-like or metallic tones.
- **Timbre (FM Index):** Modulation depth. Low = subtle brightness. Medium = electric piano territory. High = aggressive, clangy, almost noisy. The index determines how many sidebands are audible.
- **Shape (Feedback):** Operator self-modulation. Routes the modulator's output back to its own input. Low feedback = pure sine modulator. High feedback = the modulator itself becomes a complex waveform (approaching a sawtooth), creating richer spectra.

**Sweet spots:** For electric piano, use 1:1 ratio with moderate index and envelope on index. For bells, use non-integer ratios (1.41 or 3.5) with high index and long decay. For aggressive basses, use 2:1 with heavy index and feedback.

**Ratio cheat sheet:**
- 1:1 = fundamental reinforcement, slight brightness
- 2:1 = octave harmonics, hollow flute-like
- 3:1 = rich harmonics, organ-like
- 3.5:1 = inharmonic, metallic bells
- 7:1 = very bright, almost harsh

---

### 7. Formant — Vowel Synthesis

**What it models:** The human vocal tract. Formants are resonant frequencies that define vowel sounds — why "ah" sounds different from "ee" even at the same pitch.

**Synthesis technique:** Fixed resonant filters (formants) that remain constant regardless of pitch, mimicking how your mouth cavity shapes sound. Based on Mutable Instruments Plaits.

**Parameters:**
- **Wave:** Vowel / word bank selection. Different presets contain different vowel sets or syllables.
- **Timbre:** Gender / formant shift. Shifts all formants up (smaller vocal tract = child/female) or down (larger = adult male). Does not change pitch, only timbre character.
- **Shape:** Word position scan. Sweeps through a sequence of vowels or a "word." With modulation, creates speech-like movement.

**Sweet spots:** For choir pads, modulate Shape with a slow LFO. For talking bass, fast envelope on Shape. For robot voice, combine with filter modulation.

**Technical note:** Formants are why instruments sound different from voices. A trumpet and voice at the same note differ because the trumpet has different (and variable) formant frequencies.

---

### 8. Speech — Digital Voice Synthesis

**What it models:** 1980s digital speech synthesizers — Texas Instruments Speak & Spell, software SAM, LPC vocoders. The slightly robotic, uncanny-valley voice of early digital technology.

**Synthesis technique:** Multiple algorithms combined: formant filtering, SAM (Software Automatic Mouth), and LPC (Linear Predictive Coding). Based on Mutable Instruments Plaits.

**Parameters:**
- **Wave:** Phoneme set / mode. Selects banks containing vowels, diphthongs, colors, numbers, letters, or synth-related words ("modulator," "waveform").
- **Timbre:** Formant shift. Raises or lowers the voice character without changing pitch.
- **Shape:** Scan position. Moves through the selected bank, cycling through phonemes or word segments.

**Sweet spots:** For talking synth, slowly modulate Shape. For choir-like drones, hold on vowel sounds. For glitchy vocals, rapidly modulate the scan position.

---

### 9. Modal — Physical Resonator Bodies

**What it models:** Resonant physical structures — bells, tubes, plates, bars, gongs, wine glasses, gamelan instruments. Anything that "rings" when struck.

**Synthesis technique:** Modal synthesis from Mutable Instruments Plaits/Rings ("green mode"). An exciter (impulse or noise) stimulates multiple band-pass filters, each representing a resonant mode (partial) of a physical body. The Q factor of each filter determines sustain.

**Parameters:**
- **Wave (Exciter):** Exciter type. From sharp mallet impulse to continuous dust/noise excitation. Mallet = struck, single decay. Noise = continuously excited, sustained drone.
- **Timbre (Brightness):** Controls higher partial levels. Low = wood, marimba, dull bell. High = glass, steel, bright gamelan. Simultaneously adjusts the exciter low-pass and modal damping.
- **Shape (Damping):** Decay time from ~100ms to ~10 seconds. Short = muted, percussive. Long = singing bowls, infinite sustain.

**Sweet spots:** For bells/chimes, use mallet exciter with high brightness and long decay. For marimba, short decay and moderate brightness. For drones, noise exciter with long decay.

**Technical note:** There's a "virtual notch" in the brightness control that produces pure harmonic series — the only setting where partials have integer frequency ratios. Other settings produce inharmonic spectra (the character of bells and gongs).

---

### 10. Noise — Textural Noise Source

**What it models:** Various noise types for texture, percussion, and effects. From white noise (all frequencies equal) to colored noise (filtered) to digital artifacts.

**Synthesis technique:** Noise generation with filtering and particle density control.

**Parameters:**
- **Wave:** Noise type morph. Transitions between different noise characters (white, pink, brown, digital, crackle).
- **Timbre:** Color / filter cutoff. Brightens or darkens the noise spectrum.
- **Shape:** Density. Affects the "graininess" — high density = smooth noise, low density = crackly particles.

**Sweet spots:** For hi-hats, use bright filtered noise with short envelope. For ocean/wind, low-pass with slow movement. For vinyl crackle, low density with subtle presence.

---

### 11. Bass — Low-End Specialist

**What it models:** Bass-optimized synthesis combining saturation, wavefolding, and harmonic generation designed specifically for low frequencies.

**Synthesis technique:** A cosine wave foundation with saturation (overdrive) and asymmetric wavefolding to generate dense low-end harmonics.

**Parameters:**
- **Wave (Saturate):** Sets saturation of the cosine wave. Pure cosine has one harmonic; saturation adds upper harmonics. The source of "warmth" and "grit."
- **Timbre (Character):** Adjusts harmonic density and coloration. Shapes the character from round to aggressive.
- **Shape (Fold):** Two-stage asymmetric wavefolder. Adds additional harmonics through folding. The source of "growl" and "bite."

**Sweet spots:** For sub bass, low saturation and minimal fold. For aggressive bass, heavy saturation with moderate fold. For dubstep growl, maximum fold with filter modulation.

---

### 12. SawX — Extended Sawtooth

**What it models:** Enhanced sawtooth processing beyond basic SuperWave — additional detuning modes, stereo spread, and saw variations.

**Synthesis technique:** Sawtooth with extended processing including phase manipulation, detuning, and stereo field control.

**Parameters:**
- **Wave:** Saw variation mode. Different processing algorithms applied to the sawtooth.
- **Timbre:** Detune amount. Spreads multiple saw copies across pitch.
- **Shape:** Spread / stereo width. Distributes detuned copies across the stereo field.

**Sweet spots:** For wide pads, use moderate detune with full spread. For focused leads, minimal spread.

---

### 13. Harm — Harmonic Oscillator Variant

**What it models:** Similar to Harmo (additive synthesis) but with different harmonic set presets and balance controls.

**Parameters:**
- **Wave:** Harmonic series set. Different preset combinations of harmonics.
- **Timbre:** Harmonic levels. Adjusts relative amplitude of upper harmonics.
- **Shape:** Odd/even balance. Same as Harmo — morphs between hollow (odd-only) and full (all harmonics) spectra.

---

### 14. Audio In — External Input

**What it models:** Not synthesis — routes external audio through the synth's filter and effects chain.

**Use case:** Process external instruments (guitar, vocals, drum machines) through MiniFreak's analog filter and digital effects. Also useful as a mod matrix source via the "Audio In hack" (see `control-strategy.md`).

**Parameters:**
- **Wave:** Input level / gain.
- **Timbre:** Input filtering (presumed).
- **Shape:** Unknown — may be unused.

---

### 15. Wavetable — Scanning Synthesis (Osc1 Only)

**What it models:** PPG Wave, Waldorf, Serum-style wavetable synthesis. A table of different waveforms scanned through over time.

**Synthesis technique:** Instead of a single static waveform, stores many different waveforms in a "table." The playback position can be modulated, creating evolving timbres as you move through different wave shapes.

**Parameters:**
- **Wave:** Wavetable bank selection. Different tables have different timbral journeys — some morph subtly, others dramatically.
- **Timbre:** Wavetable position. Scans through the current table. Static position = fixed timbre. Modulated = evolving, animated sound.
- **Shape:** Wavetable filtering or interpolation (presumed).

**Sweet spots:** For evolving pads, slowly LFO the position. For aggressive leads, envelope the position for attack-based timbral change.

---

### 16. Sample — Sample Playback (Osc1 Only)

**What it models:** Classic sampler functionality. Play back user-loaded samples as an oscillator source.

**Parameters:**
- **Wave:** Sample selection from loaded samples.
- **Timbre:** Sample start position. Where playback begins within the sample.
- **Shape:** Unknown — possibly loop or pitch behavior.

---

### Granular Engines (17-23, Osc1 Only)

Added in firmware 3.0, these engines use granular and spectral techniques to manipulate samples in ways traditional synthesis cannot.

**Core granular concept:** Audio is sliced into tiny "grains" (1-100ms). These grains can be rearranged, overlapped, time-stretched, pitch-shifted, and randomized independently, creating textures impossible with conventional sample playback.

---

### 17. Cloud Grains — Atmospheric Granular

**What it models:** Granular clouds — dense, overlapping particles creating ambient textures and soundscapes.

**Synthesis technique:** Traditional granular synthesis with high grain overlap. Many grains playing simultaneously create smooth, blurred textures.

**Parameters:**
- **Wave (Position):** Where grains are extracted from the source sample.
- **Timbre (Density):** Grain density (grains per second). Low = separated particles. High = smooth, blurred clouds. High densities create the characteristic "shimmering" granular sound.
- **Shape (Chaos):** Randomization across multiple parameters. Adds jitter to grain position, pitch, and timing. The "organic" factor.

**Sweet spots:** For ambient pads, high density with subtle chaos. For glitchy textures, low density with high chaos.

---

### 18. Hit Grains — Percussive Granular

**What it models:** Rhythmic, clicky granular effects using triangular grain envelopes that emphasize transients.

**Synthesis technique:** Granular with sharper, more percussive grain shapes. Creates stutter and click effects rather than smooth clouds.

**Parameters:**
- **Wave (Position):** Grain extraction position.
- **Timbre (Density):** Grain rate. Higher density = faster stuttering, almost continuous. Lower = distinct rhythmic clicks.
- **Shape:** Unknown — possibly grain shape or randomization.

**Sweet spots:** For glitchy drums, process percussive samples with moderate density. For stutter edits, low density with position modulation.

---

### 19. Frozen — Spectral Freeze

**What it models:** Spectral "freeze" effects — capturing a moment of sound and sustaining it indefinitely, like a photograph of audio.

**Synthesis technique:** FFT (Fast Fourier Transform) analysis captures spectral content at a moment in time, then replays it continuously using a bank of sine oscillators (additive resynthesis). The result is an "infinite sustain" of the analyzed timbre.

**Parameters:**
- **Wave (Position):** Where in the sample the spectral snapshot is taken.
- **Timbre (Depth):** Freeze depth — how much of the original spectrum is captured and sustained.
- **Shape (Chaos):** Adds movement through phase randomization and subtle variations. Prevents the static, lifeless quality of a pure freeze.

**Sweet spots:** For ethereal pads, freeze a vocal or orchestral moment. For ice-like textures, use minimal chaos. For organic sustains, add chaos for subtle movement.

---

### 20. Skan — Spectral Time-Stretch (Noise Engineering)

**What it models:** Extreme time-stretching with keyboard tracking. Stretch samples infinitely while maintaining tonal character.

**Synthesis technique:** Spectral granular with fixed density and pitch tracking. Grains are stretched to create sustained tones that follow keyboard pitch.

**Parameters:**
- **Wave (Position):** Sample position / start point.
- **Timbre (Speed):** Time-stretch rate — how fast grains advance through the sample. Slow = frozen texture. Fast = closer to original playback.
- **Shape (Chaos):** Randomizes multiple parameters for movement.

**Sweet spots:** For pad from any sample, slow speed with moderate chaos. For texture beds, minimal speed with long release.

---

### 21. Particle — Spatial Particles

**What it models:** Particles scattered across the stereo field, creating spatial, randomized granular effects.

**Synthesis technique:** Granular with emphasis on spatial distribution. Grains are positioned across the stereo field with randomization.

**Parameters:**
- **Wave (Position):** Grain extraction position.
- **Timbre (Density):** Particle density.
- **Shape:** Unknown — possibly spatial spread or randomization.

**Sweet spots:** For ambient soundscapes, let particles drift across stereo field. For rhythmic use, sync density to tempo.

---

### 22. Lick — Rhythmic Granular (Noise Engineering)

**What it models:** Rhythmic groove generation from samples. Creates percussive, repeating patterns from any source material.

**Synthesis technique:** Granular engine optimized for rhythmic, groove-based output. Generates repeating patterns from grain manipulation.

**Parameters:**
- **Wave (Position):** Grain position / sample selection.
- **Timbre (Density):** Groove density — affects the rhythmic pattern.
- **Shape:** Randomization / variation.

**Sweet spots:** For drum loops, process percussive samples with moderate density. For evolving rhythms, modulate density and position.

---

### 23. Raster — Beat Repeat / Stutter (Noise Engineering)

**What it models:** Beat-repeat and stutter effects. Fixed grain size synced to tempo creates rhythmic repetitions.

**Synthesis technique:** Tempo-synced granular with fixed grain lengths. Creates stutter effects, glitch patterns, and rhythmic deconstruction.

**Parameters:**
- **Wave (Position):** Where in the sample grains are taken.
- **Timbre (Resolution):** Resolution / aliasing — adds digital degradation artifacts.
- **Shape:** Unknown — possibly tempo division or randomization.

**Sweet spots:** For glitch drums, process beats with varying resolution. For texture, extreme settings create aliased, digital artifacts.

---

## Oscillator 2 Engines (21)

Firmware 4.x, encoded as `index / 29` in preset files (30-slot grid, indices 21-29 are unused/dummy).

Osc2 shares engines 0-13 with Osc1 (same Wave/Timbre/Shape meanings) but does not have Audio In, Wavetable, Sample, or any of the granular/spectral engines. Instead, Osc2 has 7 unique engines that **process Osc1's signal** or generate complementary sounds.

| Index | Engine | Wave | Timbre | Shape | Notes |
|-------|--------|------|--------|-------|-------|
| 0 | BasicWaves | Waveform morph | Pulse width / phase shift | Sub-osc level | Shared with Osc1 |
| 1 | SuperWave | Waveform select | Detune spread | Density | Shared with Osc1 |
| 2 | Harmo | Harmonic set | Harmonic levels | Odd/even balance | Shared with Osc1 |
| 3 | Karplus | Exciter position | Continuous excitation | Decay time | Shared with Osc1 |
| 4 | VAnalog | Waveform morph | Secondary shape | Detune | Shared with Osc1 |
| 5 | Waveshaper | Waveform select | Wavefold amount | Asymmetry | Shared with Osc1 |
| 6 | Two Op. FM | Modulator ratio | FM index | Feedback | Shared with Osc1 |
| 7 | Formant | Word bank select | Gender / formant | Word scan | Shared with Osc1 |
| **8** | **Chords** | **Chord type** | **Inversion / voicing** | **Richness / spread** | **Osc2 only** — chord generator |
| 9 | Speech | Phoneme set | Formant shift | Scan | Shared with Osc1 |
| 10 | Modal | Exciter shape | Brightness | Damping | Shared with Osc1 |
| 11 | Noise | Type morph | Color | Density | Shared with Osc1 |
| 12 | Bass | Model type | Character | Body | Shared with Osc1 |
| 13 | SawX | Saw variation | Detune | Spread | Shared with Osc1 |
| 14 | Harm | Harmonic set | Levels | Balance | Shared with Osc1 |
| **15** | **FM/RM** | **FM/RM blend** | **Ratio** | **Modulation amount** | **Osc2 only** — FM and ring mod of Osc1 |
| **16** | **Multi Filter** | **Filter type morph** | **Frequency** | **Resonance** | **Osc2 only** — multi-mode filter bank |
| **17** | **Surgeon Filter** | **Filter mode** | **Frequency** | **Q / bandwidth** | **Osc2 only** — precise surgical EQ |
| **18** | **Comb Filter** | **Comb frequency** | **Feedback** | **Damping** | **Osc2 only** — comb filter resonator |
| **19** | **Phaser Filter** | **Phaser rate** | **Depth** | **Feedback** | **Osc2 only** — phaser as filter |
| **20** | **Destroy** | **Destruction type** | **Amount / intensity** | **Tone / color** | **Osc2 only** — bit/sample destruction |

Indices 21-29 in the preset encoding are dummy slots (unused).

---

## Osc2-Only Engine Deep Dives

### 8. Chords — Paraphonic Chord Generator

**What it models:** Auto-chord generators and paraphonic synths. One key triggers a full chord.

**Synthesis technique:** Paraphonic synthesis — multiple oscillators share a common filter and envelope but can play different pitches. Triggers oscillator duplicates at fixed intervals from the played note.

**Parameters:**
- **Wave (Chord Type):** Selects chord structure — major, minor, diminished, augmented, sus2, sus4, 7ths, etc.
- **Timbre (Inversion/Voicing):** Chord inversion and spread. Determines whether chord tones are stacked close or spread across octaves.
- **Shape (Richness):** Adds thickness through detuning or additional octaves within the chord.

**Sweet spots:** For instant pads, any chord type with medium voicing. For stabs, tight voicing with short envelope. For arpeggiated chords, combine with arpeggiator.

**Use case:** Play single-finger chords. Useful when using the arpeggiator to arpeggiate full chords from one key, or for quick pad composition.

---

### 15. FM/RM — FM and Ring Modulation of Osc1

**What it models:** Cross-modulation between oscillators, as found in dual-oscillator synths with ring mod capabilities. Osc2 modulates Osc1's signal.

**Synthesis technique:** Combines FM (Frequency Modulation) and RM (Ring Modulation). FM modulates Osc1's phase; RM multiplies the two signals together. The blend control morphs between these effects.

**FM vs RM difference:**
- **FM** creates sidebands while preserving the carrier frequency. Warm to bright.
- **RM** outputs only sum and difference frequencies, suppressing the original. Metallic, bell-like, inharmonic.

**Parameters:**
- **Wave (FM/RM Blend):** Crossfades between pure FM (0%) and pure RM (100%). Middle settings combine both.
- **Timbre (Ratio):** Frequency ratio between Osc2 and Osc1. Integer ratios = harmonic. Non-integer = inharmonic, metallic.
- **Shape (Amount):** Modulation depth. Low = subtle coloration. High = dramatic timbral transformation.

**Sweet spots:** For bells, use mostly RM with non-integer ratio. For electric piano brightness, use FM with 2:1 ratio. For metallic aggression, full RM with high amount.

**Important:** This engine processes Osc1's output. Osc1's engine choice dramatically affects the result — processing BasicWaves differs vastly from processing Karplus or Modal.

---

### 16. Multi Filter — Filter Bank as Oscillator

**What it models:** Multi-mode filter as a sound source, creating resonant filter sweeps and formant-like characteristics.

**Synthesis technique:** Osc1's signal is processed through a morphable filter bank. The filter itself becomes a sound-shaping oscillator stage.

**Parameters:**
- **Wave (Filter Type Morph):** Continuously morphs through filter types — likely LP → BP → HP → Notch transitions.
- **Timbre (Frequency):** Filter cutoff frequency.
- **Shape (Resonance):** Self-oscillation amount. High resonance = filter "sings" at the cutoff frequency.

**Sweet spots:** For vowel-like sounds, morph filter type with high resonance. For dramatic sweeps, modulate frequency with envelope.

---

### 17. Surgeon Filter — Precise EQ/Filter

**What it models:** Surgical parametric EQ and precision filtering. More precise control than Multi Filter.

**Synthesis technique:** Precise band-pass or notch filtering with tight Q control for targeted frequency manipulation.

**Parameters:**
- **Wave (Filter Mode):** Selects filter type — boost, cut, notch, band-pass.
- **Timbre (Frequency):** Center frequency of the filter.
- **Shape (Q/Bandwidth):** Filter width. High Q = very narrow, surgical. Low Q = broad, gentle.

**Sweet spots:** For resonant accents, narrow Q on specific harmonics. For masking removal, notch out interfering frequencies.

---

### 18. Comb Filter — Delay-Based Resonator

**What it models:** Flanging, metallic resonance, and physical modeling of tubes and strings. A comb filter creates regularly-spaced notches/peaks in the spectrum.

**Synthesis technique:** Delay line with feedback. When the delay time is very short (1-10ms), the repeating signal creates interference patterns that produce pitched resonance. This is the same principle behind Karplus-Strong synthesis but used as a processing effect.

**Parameters:**
- **Wave (Comb Frequency):** Delay time / pitch of the comb's fundamental resonance. Acts like a tunable resonator.
- **Timbre (Feedback):** How much signal feeds back. Low = subtle flanging. High = ringing, pitched resonance approaching self-oscillation.
- **Shape (Damping):** High-frequency loss in the feedback loop. Low damping = bright, metallic. High damping = darker, warmer.

**Sweet spots:** For metallic strings, tune comb to pitch with moderate feedback. For flanging, modulate comb frequency with LFO. For physical modeling, use short feedback with damping.

**Technical note:** Comb filters are the basis of Karplus-Strong synthesis and physical modeling. Using this on Osc1 adds another resonant body to the signal chain.

---

### 19. Phaser Filter — Allpass Filter Bank

**What it models:** Phaser effects as a synthesis element. Creates moving notches that sweep through the spectrum.

**Synthesis technique:** Series of allpass filters create phase shifts. When the shifted signal is mixed with the original, certain frequencies cancel (creating notches) while others reinforce. LFO modulation sweeps the notch positions, creating the characteristic "swooshing" effect.

**Parameters:**
- **Wave (Phaser Rate):** LFO speed for notch movement. Slow = gentle sweep. Fast = wobbly, vibrato-like.
- **Timbre (Depth):** How far the notches sweep. More depth = more dramatic sweeping.
- **Shape (Feedback):** Routes output back to input. Increases resonance at notch frequencies. High feedback = more pronounced, sharper notches.

**Sweet spots:** For classic phaser, moderate rate and depth. For resonant sweeps, high feedback. For subtle motion, slow rate with minimal depth.

---

### 20. Destroy — Bit/Sample Rate Destruction

**What it models:** Lo-fi samplers (SP-1200, early Akais), digital degradation, and "bit crushing" effects. The gritty, crunchy sound of reduced digital resolution.

**Synthesis technique:** Two types of digital degradation combined:
1. **Bit depth reduction:** Reduces amplitude resolution (32-bit → 16 → 8 → 4 → 1 bit). Creates stepped, quantized waveforms.
2. **Sample rate reduction:** Reduces temporal resolution, creating aliasing artifacts where high frequencies fold back into audible range as inharmonic distortion.

**Parameters:**
- **Wave (Destruction Type):** Morphs between different destruction algorithms — bit crushing, sample rate reduction, digital clipping, etc.
- **Timbre (Amount):** Intensity of destruction. Low = subtle warmth/grit. High = severely degraded, almost unrecognizable.
- **Shape (Tone/Color):** Post-destruction filtering. Shapes the harshness of the aliasing.

**Sweet spots:** For lo-fi drums, moderate bit reduction. For harsh industrial, maximum destruction. For subtle warmth, light amount with filtered tone.

**Technical note:** The "grit" of destruction largely comes from aliasing — when sample rate is reduced below the Nyquist frequency, high frequencies get "mirrored" back into the audible range as inharmonic artifacts.

---

## FX Algorithms (13)

Firmware 4.x, encoded as `index / 12` in preset files. Three FX slots in series, each independently selectable from these 13 algorithms.

Each algorithm exposes three continuous knobs via MIDI CC (Time, Intensity, Amount per slot) plus up to 3 sub-parameters (Opt1, Opt2, Opt3) in the preset format. Opt1 is a discrete sub-mode selector for 10 of 13 algorithms. Opt2 and Opt3 are always continuous.

### Algorithm Overview

| Index | Algorithm | Time (CC x9) | Intensity (CC x0) | Amount (CC x1) |
|-------|-----------|--------------|--------------------|-----------------|
| 0 | Chorus | Rate | Depth | Mix |
| 1 | Phaser | Rate | Depth | Mix |
| 2 | Flanger | Rate | Depth | Mix |
| 3 | Reverb | Size / decay | Damping | Mix |
| 4 | Delay | Delay time | Feedback | Mix |
| 5 | Distortion | Drive | Tone | Mix |
| 6 | Bit Crusher | Sample rate reduction | Bit depth reduction | Mix |
| 7 | 3 Band EQ | Low gain | Mid gain | High gain |
| 8 | Peak EQ | Frequency | Gain | Q / bandwidth |
| 9 | Multi Comp | Threshold | Ratio | Makeup gain |
| 10 | Super Unison | Rate | Detune spread | Mix |
| 11 | Vocoder Self | Formant shift | Bandwidth | Mix |
| 12 | Vocoder Ext | Formant shift | Bandwidth | Mix |

CC column labels show the generic mapping. Actual CCs per slot: FX1 = CC 89/90/91, FX2 = CC 92/93/94, FX3 = CC 102/103/104.

---

### FX Algorithm Deep Dives

#### Chorus
**What it does:** Creates thickness and movement by mixing slightly delayed, pitch-modulated copies of the signal.

**How it works:** Multiple voices of the signal are delayed by varying amounts (typically 10-30ms) and their delay times are modulated by an LFO, creating subtle pitch variations. When mixed back, this produces the lush, shimmering quality associated with the Roland Juno chorus.

**Parameters:**
- **Rate:** LFO speed for the modulation. Slow = gentle movement. Fast = vibrato-like warble.
- **Depth:** How much the delay times vary. More depth = more pitch modulation, thicker sound.
- **Mix:** Wet/dry balance.

**Sweet spots:** For Juno-style pads, slow rate with moderate depth. For subtle widening, low depth. For extreme effects, maximum depth creates seasick pitch wobble.

#### Phaser
**What it does:** Creates sweeping, notch-filter effects by phase-cancellation.

**How it works:** Allpass filters shift the phase of certain frequencies. When mixed with the original, phase-shifted frequencies cancel, creating moving notches. The characteristic "jet plane whoosh" comes from LFO-swept notch positions.

**Parameters:**
- **Rate:** Sweep speed.
- **Depth:** How far the notches sweep through the spectrum.
- **Mix:** Wet/dry balance.

**Sub-modes:** Space modes add more allpass stages for deeper effect. SnH (Sample & Hold) modes create stepped, random phasing rather than smooth sweeps.

#### Flanger
**What it does:** Creates metallic, sweeping effects through very short modulated delays.

**How it works:** Similar to chorus but with much shorter delay times (0.1-10ms). The short delays create comb-filtering that produces the characteristic metallic, "jet" sound. When feedback is added, resonant peaks intensify.

**Parameters:**
- **Rate:** LFO speed for delay modulation.
- **Depth:** Delay modulation amount.
- **Mix:** Wet/dry balance.

**Sub-modes:** Silly mode uses extreme settings for more dramatic, unusual flanging.

#### Reverb
**What it does:** Simulates acoustic spaces from small rooms to vast halls.

**How it works:** Creates the illusion of space by adding thousands of reflections with decreasing amplitude over time. Different algorithms simulate different physical spaces.

**Parameters:**
- **Size/Decay:** Room size and how long reflections last.
- **Damping:** High-frequency absorption. High damping = warmer, darker reverb (like carpet and curtains). Low damping = brighter, more reflective (like tile or concrete).
- **Mix:** Wet/dry balance. 100% wet = fully diffused, ambient sound.

**Sub-modes:**
- **Default/Long:** General-purpose reverbs with different decay characteristics.
- **Hall:** Large concert hall simulation.
- **Echoes:** Reverb with more distinct early reflections, almost delay-like.
- **Room:** Smaller, more intimate space.
- **Dark Room:** Room with heavy high-frequency absorption.

#### Delay
**What it does:** Creates discrete echoes/repeats of the signal.

**How it works:** Stores audio in a buffer and plays it back after a set time. Feedback routes output back to input, creating repeating echoes.

**Parameters:**
- **Time:** Delay time. Sync modes lock to tempo.
- **Feedback:** Number of repeats. Low = single echo. High = many repeats, approaching infinite.
- **Mix:** Wet/dry balance.

**Sub-modes:**
- **Digital:** Clean, precise repeats.
- **Stereo:** Alternating left/right echoes for width.
- **Ping-Pong:** Bounces between left and right channels.
- **Mono:** Single-channel delay.
- **Filtered:** Adds low-pass filtering to feedback, simulating tape delay degradation.
- **Sync:** Tempo-synchronized versions of each type.

#### Distortion
**What it does:** Adds harmonic saturation, from subtle warmth to aggressive destruction.

**How it works:** Clips or saturates the signal waveform, generating additional harmonics. Different algorithms model different analog distortion circuits.

**Parameters:**
- **Drive:** Distortion intensity.
- **Tone:** Post-distortion filtering.
- **Mix:** Wet/dry balance (useful for parallel distortion).

**Sub-modes:**
- **Classic:** Hard clipping, aggressive.
- **Soft Clip:** Gentler saturation, tube-like warmth.
- **Germanium:** Models germanium transistor fuzz, fuzzy and warm.
- **Dual Fold:** Wavefolder-style distortion.
- **Climb:** Unique character, increasingly intense.
- **Tape:** Tape saturation emulation, warm compression.

#### Bit Crusher
**What it does:** Degrades audio quality for lo-fi, retro, or harsh digital effects.

**How it works:** Reduces sample rate (causing aliasing) and bit depth (causing quantization noise). The sound of 8-bit samplers and early digital.

**Parameters:**
- **Sample Rate:** Reduction amount. Lower = more aliasing, more "crunchy."
- **Bit Depth:** Reduction from 24-bit down to 1-bit. Lower = more stepped, digital.
- **Mix:** Wet/dry balance.

**Sweet spots:** For SP-1200 drums, moderate settings. For harsh digital noise, extreme reduction.

#### 3 Band EQ
**What it does:** Three-band tonal shaping.

**How it works:** Low/mid/high frequency bands with independent gain control.

**Parameters:**
- **Low:** Bass frequency gain (boost/cut).
- **Mid:** Midrange frequency gain.
- **High:** Treble frequency gain.

**Note:** This is a utility effect — no mix control, all gains are additive.

#### Peak EQ
**What it does:** Surgical parametric EQ for precise frequency targeting.

**How it works:** Single band with adjustable frequency, gain, and bandwidth.

**Parameters:**
- **Frequency:** Center frequency of the EQ band.
- **Gain:** Boost or cut at that frequency.
- **Q:** Bandwidth — narrow (surgical) to wide (gentle).

**Sub-modes:** Wide, Mid 1K modes preset the bandwidth and frequency focus.

#### Multi Comp
**What it does:** Multi-band compression for dynamic control and loudness.

**How it works:** Reduces dynamic range by attenuating loud signals. Multiband processing allows different compression settings for different frequency ranges.

**Parameters:**
- **Threshold:** Level above which compression activates.
- **Ratio:** Compression intensity (how much loud signals are reduced).
- **Makeup Gain:** Output level boost to compensate for compression.

**Sweet spots:** For punch, fast attack/release with moderate ratio. For glue, slower settings. For loudness maximizing, heavy ratio with makeup gain.

#### Super Unison
**What it does:** Thickens sound through unison detuning, like the SuperWave engine but as an effect.

**How it works:** Creates multiple copies of the signal with slight pitch offsets, similar to synthesizer unison modes.

**Parameters:**
- **Rate:** Modulation speed of the detuning (creates movement).
- **Detune Spread:** How much the copies are detuned.
- **Mix:** Wet/dry balance.

**Sub-modes:** Different unison characters — Ravey (aggressive), Soli (solo-focused), Slow/Wide variations.

#### Vocoder Self
**What it does:** Self-vocoding — uses the synth's own audio to modulate itself.

**How it works:** A vocoder analyzes the spectrum of a "modulator" signal (here, the synth itself) and imposes that spectral shape onto a "carrier" (also the synth). Creates robotic, frequency-following effects.

**Parameters:**
- **Formant Shift:** Moves the frequency bands up or down.
- **Bandwidth:** Width of each vocoder band. Narrow = more robotic, precise. Wide = smoother.
- **Mix:** Wet/dry balance.

**Sub-modes:** Clean, Vintage (warmer), Narrow (more robotic), Gated (choppy).

#### Vocoder Ext
**What it does:** External vocoding — uses an external audio source (microphone, other instrument) as the modulator.

**How it works:** Same as Vocoder Self but the modulator comes from the external audio input. Classic "talking synth" effect.

**Parameters:** Same as Vocoder Self.

**Use case:** Plug in a microphone and "play" the synth with your voice. The synth's sound takes on the spectral character of your speech.

---

### Opt1 Sub-Modes (Per Algorithm)

#### Chorus (5 modes, 1/4 spacing)

| Value | Label |
|-------|-------|
| 0.0000 | Default |
| 0.2500 | Lush |
| 0.5000 | Dark |
| 0.7500 | Shaded |
| 1.0000 | Single |

#### Phaser (6 modes, 1/5 spacing)

| Value | Label |
|-------|-------|
| 0.0000 | Default |
| 0.2000 | Default Sync |
| 0.4000 | Space |
| 0.6000 | Space Sync |
| 0.8000 | SnH |
| 1.0000 | SnH Sync |

#### Flanger (4 modes, 1/3 spacing)

| Value | Label |
|-------|-------|
| 0.0000 | Default |
| 0.3333 | Default Sync |
| 0.6667 | Silly |
| 1.0000 | Silly Sync |

#### Reverb (6 modes, 1/5 spacing)

| Value | Label |
|-------|-------|
| 0.0000 | Default |
| 0.2000 | Long |
| 0.4000 | Hall |
| 0.6000 | Echoes |
| 0.8000 | Room |
| 1.0000 | Dark Room |

#### Delay (12 modes, 1/11 spacing)

| Value | Label |
|-------|-------|
| 0.0000 | Digital |
| 0.0909 | Digital Sync |
| 0.1818 | Stereo |
| 0.2727 | Stereo Sync |
| 0.3636 | Ping-Pong |
| 0.4545 | Ping-Pong Sync |
| 0.5455 | Mono |
| 0.6364 | Mono Sync |
| 0.7273 | Filtered |
| 0.8182 | Filtered Sync |
| 0.9091 | Filtered Ping-Pong |
| 1.0000 | Filtered P-P Sync |

#### Distortion (6 modes, 1/5 spacing)

| Value | Label |
|-------|-------|
| 0.0000 | Classic |
| 0.2000 | Soft Clip |
| 0.4000 | Germanium |
| 0.6000 | Dual Fold |
| 0.8000 | Climb |
| 1.0000 | Tape |

#### Peak EQ (3 modes, 1/2 spacing)

| Value | Label |
|-------|-------|
| 0.0000 | Default |
| 0.5000 | Wide |
| 1.0000 | Mid 1K |

#### Super Unison (8 modes, 1/7 spacing)

| Value | Label |
|-------|-------|
| 0.0000 | Classic |
| 0.1429 | Ravey |
| 0.2857 | Soli |
| 0.4286 | Slow |
| 0.5714 | Slow Trig |
| 0.7143 | Wide Trig |
| 0.8571 | Mono Trig |
| 1.0000 | Wavy |

#### Vocoder Self (4 modes, 1/3 spacing)

| Value | Label |
|-------|-------|
| 0.0000 | Clean |
| 0.3333 | Vintage |
| 0.6667 | Narrow |
| 1.0000 | Gated |

#### Vocoder Ext (4 modes, 1/3 spacing)

| Value | Label |
|-------|-------|
| 0.0000 | Clean |
| 0.3333 | Vintage |
| 0.6667 | Narrow |
| 1.0000 | Gated |

#### Algorithms Without Opt1 Dropdown

**Bit Crusher**, **3 Band EQ**, **Multi Comp** -- Opt1/Opt2/Opt3 are all continuous knob values, not discrete selectors.

---

## Mod Matrix

### Source Rows (7)

| Index | Source | MIDI-Controllable? |
|-------|--------|--------------------|
| 0 | CycEnv (Cycling Envelope) | Partial -- Rise/Fall/Hold via CC 68/69/76 |
| 1 | Envelope (ADSR) | Partial -- ADSR via CC 80-83 |
| 2 | LFO 1 | Partial -- Rate via CC 85 |
| 3 | LFO 2 | Partial -- Rate via CC 87 |
| 4 | Velocity / Aftertouch | Yes -- note velocity + channel aftertouch |
| 5 | Wheel (Mod Wheel) | Yes -- CC 1 |
| 6 | Kbd (Keyboard tracking, linear) | Yes -- note number |

Source row 4 mode is configurable per preset (`Mx_VeloAt`): 0.0 = Velocity only, 0.5 = Aftertouch only, 1.0 = Velo + AT combined.

### Hardwired Destinations (4 columns, always present)

| Column | Destination |
|--------|-------------|
| 0 | Pitch 1+2 (both oscillators) |
| 1 | Osc1 Wave |
| 2 | Osc1 Timbre |
| 3 | Cutoff (filter) |

Stored as `Mx_Dot_0..27` (28 values = 7 sources x 4 destinations, row-major). All amounts bipolar: 0.5 = no modulation, 0.0 = -100%, 1.0 = +100%.

### Assignable Destinations (9 columns)

Each assignable column targets a parameter selected via `Mx_ColId_0..8` (9 values). Amounts stored as `Mx_AssignDot_0..62` (63 values = 7 sources x 9 destinations, row-major). Same bipolar encoding.

Empty/unassigned columns use raw ColId value 32769 (approximately 0.50001).

#### Routable Parameters

Two address clusters, encoded as `(base + offset) / 65536`:

**Cluster A -- Synth Parameters** (base 0x9000 = 36864)

| Offset | Destination | Category |
|--------|-------------|----------|
| 4 | Osc1 Type | Oscillator 1 |
| 5 | Osc1 Wave | Oscillator 1 |
| 6 | Osc1 Timbre | Oscillator 1 |
| 7 | Osc1 Shape | Oscillator 1 |
| 11 | Osc1 Volume | Oscillator 1 |
| 14 | Osc2 Type | Oscillator 2 |
| 15 | Osc2 Wave | Oscillator 2 |
| 16 | Osc2 Timbre | Oscillator 2 |
| 17 | Osc2 Shape | Oscillator 2 |
| 21 | Osc2 Volume | Oscillator 2 |
| 22 | Glide | Voice |
| 26 | Cutoff | Filter |
| 27 | Resonance | Filter |
| 28 | Env Amount | Filter |
| 29 | VCA | Amplifier |
| 30 | Attack | Envelope |
| 31 | Decay | Envelope |
| 32 | Sustain | Envelope |
| 33 | Release | Envelope |
| 40 | Rise | Cycling Envelope |
| 41 | Fall | Cycling Envelope |
| 42 | Hold | Cycling Envelope |
| 49 | LFO1 Rate | LFO 1 |
| 50 | LFO1 Rate (Sync) | LFO 1 |
| 51 | LFO1 Wave ? | LFO 1 |
| 55 | LFO2 Wave ? | LFO 2 |
| 56 | LFO2 Rate | LFO 2 |
| 57 | LFO2 Rate (Sync) | LFO 2 |
| 62 | Macro 1 | Performance |
| 63 | Macro 2 | Performance |
| 83 | Unison Spread | Voice |
| 193 | Vibrato AM | Vibrato |
| 197 | Pitch 1 (Osc1 only) | Pitch |
| 198 | Pitch 2 (Osc2 only) | Pitch |
| 200 | LFO1 AM | LFO 1 |
| 201 | LFO2 AM | LFO 2 |
| 202 | CycEnv AM | Cycling Envelope |
| 204 | Vibrato Rate | Vibrato |

Offsets 51, 55 are inferred from adjacent layout; marked with `?`.

**Cluster B -- FX Parameters** (base 0xA000 = 40960)

| Offset | Destination | Category |
|--------|-------------|----------|
| 3 | FX1 Time | FX Slot 1 |
| 4 | FX1 Intensity | FX Slot 1 |
| 5 | FX1 Amount | FX Slot 1 |
| 12 | FX2 Time | FX Slot 2 |
| 13 | FX2 Intensity | FX Slot 2 |
| 14 | FX2 Amount | FX Slot 2 |
| 21 | FX3 Time | FX Slot 3 |
| 22 | FX3 Intensity | FX Slot 3 |
| 23 | FX3 Amount | FX Slot 3 |

Each FX slot occupies 9 offsets but only 3 (at +3/+4/+5 within each block) are routable. FX Type, Enable, Opt, and internal params are not mod-routable.

### Meta-Modulation

The mod matrix supports modulating the **amount** of any other matrix cell (mod-of-mod). These appear in MiniFreak V as "Mod row:col" destinations.

- Hardwired cell addresses: `offset = 97 + 4*(row-1) + (col-1)` where row=1-7, col=1-4
- Assignable cell addresses: `offset = 125 + 9*(row-1) + (col-5)` where row=1-7, col=5-13

All in Cluster A. Total: 91 meta-mod destinations covering every cell in the 7x13 matrix.

---

## LFO Waveforms (9)

Encoded as `index / 8` in preset files. Applies to both LFO1 and LFO2.

| Index | Value | Waveform | Description |
|-------|-------|----------|-------------|
| 0 | 0.0000 | Sine | Smooth sinusoidal |
| 1 | 0.1250 | Tri | Triangle wave |
| 2 | 0.2500 | Saw | Sawtooth (ramp down) |
| 3 | 0.3750 | Sqr | Square wave |
| 4 | 0.5000 | SnH | Sample and Hold (stepped random) |
| 5 | 0.6250 | Slew SnH | Smoothed sample and hold |
| 6 | 0.7500 | Exp Saw | Exponential sawtooth |
| 7 | 0.8750 | Exp Ramp | Exponential ramp |
| 8 | 1.0000 | Shaper | User-drawn custom waveform |

When Shaper is selected, the custom shape is defined by `Shp1_*` / `Shp2_*` parameters (length, step amplitudes, curves, slopes, enable flags).

LFO waveform is **not controllable via MIDI CC**. Only LFO rate is accessible (CC 85 / CC 87).

### LFO Retrigger Modes (8)

Encoded as `index / 7`. Index 5 is cross-LFO: "LFO2" when on LFO1, "LFO1" when on LFO2.

| Index | Value | Mode |
|-------|-------|------|
| 0 | 0.0000 | Free |
| 1 | 0.1429 | Poly Kbd |
| 2 | 0.2857 | Mono Kbd |
| 3 | 0.4286 | Legato Kbd |
| 4 | 0.5714 | One (single cycle) |
| 5 | 0.7143 | LFO2 / LFO1 (cross-LFO) |
| 6 | 0.8571 | CycEnv |
| 7 | 1.0000 | Seq Start |

### LFO Sync Rate Divisions (27)

Encoded as `index / 26`. Active only when `LFO_SyncEn = 1.0`. Same grid for LFO1 and LFO2.

| Index | Value | Division |
|-------|-------|----------|
| 0 | 0.0000 | 8 bars dotted |
| 1 | 0.0385 | 8 bars |
| 2 | 0.0769 | 4 bars dotted |
| 3 | 0.1154 | 4 bars triplet |
| 4 | 0.1538 | 4 bars |
| 5 | 0.1923 | 2 bars dotted |
| 6 | 0.2308 | 2 bars triplet |
| 7 | 0.2692 | 2 bars |
| 8 | 0.3077 | 1 bar dotted |
| 9 | 0.3462 | 1 bar triplet |
| 10 | 0.3846 | 1 bar |
| 11 | 0.4231 | 1/2 dotted |
| 12 | 0.4615 | 1 bar triplet ? |
| 13 | 0.5000 | 1/2 |
| 14 | 0.5385 | 1/4 dotted |
| 15 | 0.5769 | 1/2 triplet |
| 16 | 0.6154 | 1/4 |
| 17 | 0.6539 | 1/8 dotted |
| 18 | 0.6923 | 1/4 triplet |
| 19 | 0.7308 | 1/8 |
| 20 | 0.7692 | 1/16 dotted |
| 21 | 0.8077 | 1/8 triplet |
| 22 | 0.8462 | 1/16 |
| 23 | 0.8846 | 1/32 dotted |
| 24 | 0.9231 | 1/16 triplet |
| 25 | 0.9615 | 1/32 |
| 26 | 1.0000 | 1/32 triplet |

### LFO Sync Filter (5 options)

Encoded as `index / 4`. Restricts which synced divisions are available in the UI.

| Index | Value | Filter |
|-------|-------|--------|
| 0 | 0.0000 | All |
| 1 | 0.2500 | Straight |
| 2 | 0.5000 | Triplet |
| 3 | 0.7500 | Dotted |
| 4 | 1.0000 | Free |

---

## Voice Modes (4)

Encoded as `index / 3` in preset files (`Gen_NoteMode`).

| Index | Value | Mode | Description |
|-------|-------|------|-------------|
| 0 | 0.0000 | Mono | Single voice, last-note priority |
| 1 | 0.3333 | Unison | All 6 voices stacked on one note |
| 2 | 0.6667 | Poly | Full 6-voice polyphony |
| 3 | 1.0000 | Para | Paraphonic (shared filter across voices) |

Factory firmware duplicate: 0.7500 also maps to Poly (old-grid 1/4 spacing).

Voice mode is **not controllable via MIDI CC**.

### Voice Sub-Parameters

| Parameter | Values | Encoding | Mapping |
|-----------|--------|----------|---------|
| `Gen_UnisonCount` | 4 | non-uniform | 0.0=2, 0.25=3, 0.5=4, 1.0=6 |
| `Gen_UnisonMode` | 3 | 1/2 spacing | 0.0=Unison, 0.5=Uni Poly, 1.0=Uni Para |
| `Gen_PolyAlloc` | 3 | 1/2 spacing | 0.0=Cycle, 0.5=Reassign, 1.0=Reset |
| `Gen_PolySteal` | 3 | 1/2 spacing | 0.0=Oldest, 0.5=Lowest, 1.0=None |
| `Gen_RetrigMode` | 2 | boolean | 0.0=Env Reset, 1.0=Env Continue |
| `Gen_LegatoMode` | 2 | boolean | 0.0=Off, 1.0=On |

---

## Cycling Envelope Modes (3)

Encoded as `index / 2` (`CycEnv_Mode`).

| Index | Value | Mode | Description |
|-------|-------|------|-------------|
| 0 | 0.0000 | Env | One-shot envelope (rise then fall) |
| 1 | 0.5000 | Run | Free-running (continuous rise/fall cycle) |
| 2 | 1.0000 | Loop | Looping with retrigger sync |

Factory firmware duplicate: 0.25 also maps to Env.

### Cycling Envelope Stage Order (3)

Encoded as `index / 2` (`CycEnv_StageOrder`).

| Index | Value | Order |
|-------|-------|-------|
| 0 | 0.0000 | Rise - Hold - Fall |
| 1 | 0.5000 | Rise - Fall - Hold |
| 2 | 1.0000 | Hold - Rise - Fall |

### Cycling Envelope Retrigger Source (5)

Encoded as `index / 4` (`CycEnv_RetrigSrc`).

| Index | Value | Source |
|-------|-------|--------|
| 0 | 0.0000 | Poly Kbd |
| 1 | 0.2500 | Mono Kbd |
| 2 | 0.5000 | Legato Kbd |
| 3 | 0.7500 | LFO1 |
| 4 | 1.0000 | LFO2 |

---

## Arpeggiator

### Seq Mode (master switch)

Encoded as `index / 2` (`Seq_Mode`). Must be set to "Arp" for arpeggiator parameters to take effect.

| Index | Value | Mode |
|-------|-------|------|
| 0 | 0.0000 | Off |
| 1 | 0.3333 | Arp |
| 2 | 0.6667 | Seq |

### Arp Mode (8)

Encoded as `index / 7`.

| Index | Value | Mode |
|-------|-------|------|
| 0 | 0.0000 | Up |
| 1 | 0.1429 | Down |
| 2 | 0.2857 | Up/Down |
| 3 | 0.4286 | Random |
| 4 | 0.5714 | ??? |
| 5 | 0.7143 | Pattern |
| 6 | 0.8571 | Order |
| 7 | 1.0000 | Poly |

Index 4 not observed in factory corpus -- mode unknown.

### Arp Octave (4)

Encoded as `index / 3`.

| Index | Value | Range |
|-------|-------|-------|
| 0 | 0.0000 | 1 octave |
| 1 | 0.3333 | 2 octaves |
| 2 | 0.6667 | 3 octaves |
| 3 | 1.0000 | 4 octaves |

MIDI CC: Spice = CC 116, Gate = CC 115. All other arp parameters require front panel.

---

## Sequencer Time Divisions (15)

Encoded as `index / 14` (`Seq_TimeDiv`).

| Index | Value | Division |
|-------|-------|----------|
| 0 | 0.0000 | 1/2 dotted |
| 1 | 0.0714 | 1/2 |
| 2 | 0.1429 | 1/4 dotted |
| 3 | 0.2143 | 1/2 triplet |
| 4 | 0.2857 | 1/4 |
| 5 | 0.3571 | 1/8 dotted |
| 6 | 0.4286 | 1/4 triplet |
| 7 | 0.5000 | 1/8 |
| 8 | 0.5714 | 1/16 dotted |
| 9 | 0.6429 | 1/8 triplet |
| 10 | 0.7143 | 1/16 |
| 11 | 0.7857 | 1/32 dotted |
| 12 | 0.8571 | 1/16 triplet |
| 13 | 0.9286 | 1/32 |
| 14 | 1.0000 | 1/32 triplet |

Pattern: each base division has 3 variants (dotted, triplet, straight) cycling through the list.

---

## Filter Modes (3)

Not MIDI-controllable. Encoded as `index / 2` with non-uniform spacing.

| Value | Mode |
|-------|------|
| 0.0000 | LPF (Low Pass) |
| 0.1667 | BPF (Band Pass) |
| 0.3333 | HPF (High Pass) |

239 of 257 factory presets use LPF.

---

## Tempo Encoding

Formula: `BPM = value * 210 + 30`

Range: 30-240 BPM. Inverse: `value = (BPM - 30) / 210`.

---

## Preset File Format Notes

- **Factory presets** (firmware ~3.x): 2368 params, 14 Osc1 engines (1/13 grid), 10 FX algorithms (1/9 grid)
- **Exported presets** (firmware 4.x): 2485 params, 24 Osc1 engines (1/23 grid), 13 FX algorithms (1/12 grid)
- The same engine has different float values between firmware versions. Always use firmware 4.x values (the tables in this document) when creating presets for import.
- General encoding pattern: `value = index / (N-1)` where N is the total number of options.
