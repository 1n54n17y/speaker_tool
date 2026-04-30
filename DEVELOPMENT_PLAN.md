# NordBass Speaker Tool - Development & Monetization Roadmap

This is a living document tracking the evolution of NordBass from a DIY tool to a commercial-grade engineering suite.

## 🎯 Project Vision
To become the modern standard for loudspeaker design software, offering professional-grade physics and manufacturing automation with a user experience that surpasses legacy industry tools.

---

## 💰 Subscription Tier Strategy

| Tier | Price | Primary Target |
| :--- | :--- | :--- |
| **Home** | $7.99 / mo | Hobbyists, DIY builders, and Students. |
| **Pro** | $29.99 / mo | Custom shops, Car Audio professionals, and Boutique brands. |
| **Enterprise** | $149.99 / mo | Manufacturers, CNC production facilities, and Engineering firms. |

---

## 🛠 Feature Roadmap

### Phase 1: Core Stability & Foundation (Completed)
- [x] High-performance simulation engine (Sealed/Vented).
- [x] 3D Box Geometry Solver (Standard & Wedge).
- [x] Pydantic-validated Data Layer (SI Units).
- [x] Driver Library with CSV Importer.
- [x] Optimized GUI performance (Matplotlib Blitting).
- [x] Unified "Check Fit" physical validation logic.
- [x] Accurate Slot Port volume displacement.
- [x] Passive Radiator simulation support.
- [x] 4th Order Bandpass enclosure support.

### Phase 2: Professional Value (Pro Tier)
- [ ] **Branded PDF Export:** Generate professional design reports with custom logos.
- [ ] **Multi-Driver Support:** Parallel, Series, and Isobaric configurations.
- [ ] **Room Gain & Cabin Gain Modeling:** Adjustable corner frequencies for car/home.
- [ ] **Semi-Inductance (Le) Modeling:** Accurate high-frequency impedance curves.
- [ ] **Advanced Baffle Step Correction:** Modeling diffraction based on baffle width.
- [ ] **Cloud Sync / Team Library:** Share driver libraries across multiple shop PCs.

### Phase 3: Manufacturing & Automation (Enterprise Tier)
- [ ] **CNC Export (.DXF / .SVG):** Direct-to-router panel exports.
- [ ] **Sheet Layout Optimizer:** Material nesting to minimize MDF/Plywood waste.
- [ ] **"Sweet Spot" Solver:** Automated optimization for target F3/Volume/Velocity.
- [ ] **6th Order Bandpass & Transmission Line support.**
- [ ] **System Impedance Correction Modeling (Zobel Networks).**
- [ ] **Batch Processing:** Run simulations for entire driver catalogs automatically.

### Phase 4: Commercial Launch & Infrastructure
- [ ] **Licensing System:** Hardware-locked activation keys.
- [ ] **Automated Update System:** Check for new versions on startup.
- [ ] **Payment Integration:** Stripe/LemonSqueezy hookup for subscriptions.
- [ ] **Documentation Wiki:** Technical manuals and "How-to" guides for acoustics.

---

## 📈 Current Status & Metrics
*   **Version:** 0.1.18
*   **Architecture Quality:** High (Modular/Surgical)
*   **Physics Accuracy:** High (Flare-it / Thiele-Small compliant)
*   **Commercial Readiness:** 45%

---

## 📝 User Notes / Feedback Loop
*(User can add notes here for specific feature requests)*
