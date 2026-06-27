# Wrist PPG Sensor — Enclosure Build Guide

A SolidWorks build plan for the wearable optical heart-rate module that feeds the
Wearable Health Insights pipeline. Written for someone comfortable in SolidWorks:
this is a feature-tree plan with target dimensions, not a click-by-click tutorial.

The single most important feature is the **optical window** on the underside — it is
the same problem Apple solves on the back of the Watch, and it's the detail to lead
with in interviews.

---

## 1. What it has to house (design around these real parts)

| Component | Part to buy | Footprint (mm) | Notes |
|-----------|-------------|----------------|-------|
| PPG sensor | MAX30102 breakout (GY-MAX30102) | ~21 × 16 × 3 | Optical area is the skin-facing element |
| MCU | ESP32-C3 Super Mini (or Seeed XIAO ESP32-C3) | ~22.5 × 18 × 4 | Has USB-C and Wi-Fi for streaming |
| Battery | LiPo 501235 (~150 mAh) | ~12 × 35 × 5 | Sized to fit beside the boards |

Buy the parts first (or pull exact STEP files from GrabCAD / the vendor) and model the
enclosure around **measured** dimensions. Designing to nominal numbers and discovering a
0.4 mm interference after printing is the classic first-prototype mistake.

## 2. Target envelope

- **Outer body:** ~40 (L) × 36 (W) × 14 (H) mm. It's chunky — early wearables always are.
  Don't fake a 9 mm-thin device you can't actually build; an honest bulky prototype reads
  as more credible than an impossible render.
- **Wall thickness:** 2.0 mm.
- **Internal cavity:** ~36 × 32 × 11 mm.
- **Two shells:** bottom (skin-side, holds everything) + top (lid).

## 3. Feature-tree plan

### Master layout sketch
1. New part. On the Top plane, sketch the **outer footprint** as a 40 × 36 rectangle,
   fully defined and centered on the origin. Add 3 mm corner fillets in the sketch.
2. On a second sketch, drop **reference points** for: sensor optical center, MCU USB-C
   edge, battery pocket, and the four corner screw bosses. Everything downstream
   references this layout sketch, so changes propagate cleanly.

### Bottom shell
3. **Extrude** the footprint up 12 mm.
4. **Shell** the part 2.0 mm, removing the top face → open box.
5. **Sensor pocket (the optical window):** on the underside, cut a pocket sized to seat
   the MAX30102 so its optical face sits ~0.3–0.5 mm proud of (or flush with) the skin
   surface. Then cut the actual **window opening** ~8 × 8 mm straight through to skin.
   - Add a **raised sealing rim** ~0.5 mm proud around the window. It presses lightly into
     the skin and blocks ambient light from leaking into the photodiode — this is the
     PPG-quality detail.
   - Add a thin internal **light-isolation wall** between the LED side and photodiode side
     if your breakout doesn't already provide one.
   - Optional: a 0.5 mm clear cover (acrylic/clear resin) if you want a sealed window;
     direct skin contact generally gives a stronger signal, so open + sealing rim is fine.
6. **PCB bosses:** add standoffs/bosses to mount the MCU and sensor boards at their hole
   locations (M1.6 or M2). Keep 0.3 mm clearance around board edges.
7. **Battery pocket:** a 13 × 36 × 5.5 mm walled pocket beside the boards. Add a small
   foam/ribbing allowance so it isn't crushed.
8. **USB-C cutout:** ~9.0 × 3.5 mm on the side wall, aligned to the MCU port, with
   0.5 mm clearance all around so a cable seats fully.
9. **Strap slots:** two 22 × 3 mm through-slots near each end for a velcro/NATO band
   (easiest), or model 20 mm lug pairs with 1.5 mm spring-bar holes for a standard watch
   strap (cleaner, more "product").
10. **Screw bosses:** four corner bosses sized for **M2 brass heat-set inserts**
    (~3.2 mm hole, 4 mm deep).

### Top shell (lid)
11. New extrude from the same footprint, ~3 mm tall, shelled 2.0 mm.
12. Add a **perimeter lip** (0.8 mm wide × 1.5 mm tall) that nests inside the bottom
    shell wall for alignment and light/dust sealing.
13. Counterbored **clearance holes** (Ø2.2 mm) over the four screw bosses.
14. *(Alternative to screws:* cantilever **snap-fit** hooks on the lip — 4 hooks, ~1 mm
    deflection, 30–45° lead-in. More elegant, less reworkable. For a portfolio prototype
    you'll open repeatedly, screws + inserts are the pragmatic call.)*

### Finishing
15. **Fillets/chamfers:** 2–3 mm on all outer edges for comfort and an Apple-grade feel;
    1 mm on internal edges. Do these last so they don't break downstream references.
16. **Appearances + render:** matte white or anodized-look aluminum appearance, soft studio
    lighting. Apple cares about fit/finish — spend time here.

### Assembly + deliverables
17. New assembly: insert both shells + the component STEP files. Mate boards to bosses,
    battery to pocket.
18. Produce, at minimum:
    - **Exploded view** (animated exploded view is a nice touch)
    - **Section view** through the sensor window showing the optical path
    - **Two isometric renders** (one bare, one on a wrist/context)
    - **STEP + STL export**

## 4. Tolerances & clearances (FDM default)

| Fit | Clearance |
|-----|-----------|
| Lip into shell wall | 0.20 mm per side |
| Board edge to wall | 0.30 mm |
| USB-C cutout | 0.50 mm all around |
| Snap-fit engagement | 0.15–0.25 mm |
| Heat-set insert hole | size to insert spec (~Ø3.2 for M2) |

Tighten all of these by ~0.1 mm if you switch to SLA resin (next section).

## 5. Material — what to print, and what to *say*

**You'll print it in:**

- **PETG (recommended default).** Tougher and more heat/skin-contact tolerant than PLA,
  slight flex so snap features survive, and it tolerates the warmth of being worn. Best
  all-round choice if you're unsure how you'll fabricate.
- **PLA** — fine for a first form/fit check; stiff and easy to print, but brittle and it
  softens with body/sun heat, so it's not a great "worn" material. Use it to validate the
  model cheaply, then reprint the keeper in PETG.
- **SLA resin (if you have access)** — much finer detail on the optical window and sealing
  rim, and a more premium surface finish for renders/photos. Use a **tough/ABS-like resin**,
  not standard brittle resin. Note: many standard resins aren't skin-safe for long wear —
  use a bio-compatible / "skin-safe" resin (e.g. a Class I/IIa-rated dental-adjacent resin)
  if it'll actually touch skin for more than a few minutes.
- **Strap / soft parts:** print a band or a thin skin-contact gasket in **TPU** (flexible).

**What a real device would use (interview talking points):**

- Housing: **PC/ABS blend** or **glass-filled nylon** (injection-molded) for impact and
  thinness; premium devices use **anodized aluminum** or **Series 7000 aluminum** like the
  Watch, or zirconia ceramic on the sensor side.
- Skin-contact + optical window: the Apple Watch uses a **crystalline sapphire** or ceramic
  back for scratch resistance and optical clarity. Your analog is a **skin-safe clear
  resin/acrylic** window.
- Sealing: a real wearable needs an **ingress (IP) rating** — gaskets/O-rings or
  ultrasonic welding. Mention you'd add a perimeter gasket groove for IPX7 in a v2.

Being able to contrast "what I printed" vs "what production would use, and why" is exactly
the materials-engineering judgment an Apple R&D screen is looking for.

## 6. FDM print settings (starting point)

- Layer height 0.16 mm (0.12 mm on the sensor-window face for a crisp rim)
- 3–4 perimeters, 25–40% infill
- Supports only under the strap slots / overhangs; orient the window face up if possible
- Brim if PETG corners lift

## 7. Portfolio integration

Drop the model and exports here:

```
hardware/
├── ENCLOSURE_BUILD_GUIDE.md   (this file)
├── cad/                       (.SLDPRT / .SLDASM)
├── exports/                   (STEP, STL)
└── renders/                   (iso, exploded, section PNGs)
```

Then add a short **Hardware** section to the project README with one render, the
section view, and a 2–3 sentence design-intent note (constraints: skin contact for PPG,
ambient-light sealing, board/battery packaging, strap interface). One repo telling the
full sensor → pipeline → dashboard story is stronger than scattering it.

---

### Quick start checklist
- [ ] Buy MAX30102 + ESP32-C3 + LiPo, measure them (or grab vendor STEP files)
- [ ] Master layout sketch → bottom shell → optical window + sealing rim
- [ ] Bosses, battery pocket, USB-C cutout, strap slots, screw bosses
- [ ] Top shell + lip + clearance holes
- [ ] Fillets, appearances, assembly, exploded + section views, renders
- [ ] Print in PETG (PLA test print first), export STEP/STL
- [ ] Add Hardware section to README with renders + design-intent note
