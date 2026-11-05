# What to collect at the hospital + questions for Babu sir

## A. Photos and videos to collect (with permission; never touch the oxygen line)

Shoot with the **same tablet** we will mount, from the **mounting position**, focus and exposure locked.

| # | What | How much | Why |
|---|---|---|---|
| 1 | Still photo of each panel, square-on, tablet at the intended spot | 3 per panel | Calibration + synthetic generator base image |
| 2 | Close-up of the dial face (fills the frame) | 2 per gauge | Needle removal / clean dial for synthetic data |
| 3 | 2-minute video at morning, noon, evening, night (lights on/off) | 4 × 2 min per panel | Real glare and lighting test set |
| 4 | Same as 3 with a person walking past / standing in front | 1 min | Occlusion → must give UNCERTAIN, not a wrong value |
| 5 | Photos with each lamp state lit (if the biomedical team runs a lamp test) | 5 each | Lamp reader thresholds |
| 6 | Wide photo of the wall: power socket, Wi-Fi signal, mount options | 2 | Mounting plan |
| 7 | Gauge make/model plate, scale range, any set-point label on the panel | 1 each | Calibration values, lamp set-point |
| 8 | Video during a planned cylinder/manifold changeover (if one happens) | whatever is possible | The only real "pressure moving" footage |

Freeze items 3–5 as the **held-out real test set** - never used for training.

## B. Questions for Babu sir / biomedical engineer

1. What are the LOW and CRITICAL pressure thresholds for the main oxygen line? (Our placeholders: LOW 3.5, CRITICAL 3.0 kg/cm²)
2. At what pressure does the panel's own LOW lamp switch on? (lets us cross-check needle vs lamp)
3. Which panel first: the single-dial "Alarming System" box (0–16 kg/cm²) or the Magnate 3-gauge panel (0–10 kg/cm² inner scale)?
4. Is there reliable Wi-Fi and a power socket at the panel? Is there a UPS on that socket?
5. Who should receive alerts, in what escalation order, and how long before escalating (we propose 2 min)?
6. Is it OK that alerts go to personal Android phones, or is there a ward phone / nursing station PC?
7. Can we take photos/videos of the panel over several days (list A)?
8. When will the industry partner's model arrive, and in what format (TFLite / ONNX / PyTorch)?
9. Does the panel have a relay / remote-alarm (potential-free) output? Reading it electrically is a strong extra signal.
10. What is the normal operating pressure and how fast does it fall during a real cylinder bank changeover? (sets the trend-alarm rate; placeholder 0.5 kg/cm² per minute)
11. Who in the hospital owns the tablet day-to-day (charging, cleaning, acknowledging test alarms)?
12. Any rules about cameras in that area (patient privacy)? Our camera only sees the panel and snapshots are stored only at alerts.
