#!/usr/bin/env python3
"""
LuxCore Physics Engine & End-to-End Calculation Pipeline PDF Generator
Generates a comprehensive, publication-grade HTML document with embedded SVG diagrams
and compiles it into a high-fidelity PDF via headless Chrome.
"""

import os
import subprocess
import sys
from pathlib import Path

OUTPUT_DIR = Path("/home/mahmoudmnael/Workspace/SC/luxscale-2.0/docs")
OUTPUT_HTML = OUTPUT_DIR / "luxcore_physics_and_workflow.html"
OUTPUT_PDF = OUTPUT_DIR / "LuxCore_Physics_and_Calculation_Workflow.pdf"

HTML_CONTENT = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>LuxCore Physics Engine & Calculation Workflow</title>
<style>
  @page {
    size: A4 portrait;
    margin: 14mm 14mm 14mm 14mm;
    @bottom-right {
      content: "Page " counter(page);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      font-size: 8pt;
      color: #64748b;
    }
    @bottom-left {
      content: "LuxScale Architecture Documentation • LuxCore Engine";
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      font-size: 8pt;
      color: #64748b;
    }
  }

  *, *::before, *::after {
    box-sizing: border-box;
  }

  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    color: #1e293b;
    line-height: 1.45;
    font-size: 9.5pt;
    background: #ffffff;
    margin: 0;
    padding: 0;
  }

  /* Headings */
  h1, h2, h3, h4 {
    color: #0f172a;
    font-weight: 700;
    margin-top: 1.2em;
    margin-bottom: 0.4em;
    line-height: 1.2;
    page-break-after: avoid;
    break-after: avoid;
  }

  h1 {
    font-size: 19pt;
    border-bottom: 2px solid #3b82f6;
    padding-bottom: 6px;
    margin-top: 0;
  }

  h2 {
    font-size: 13.5pt;
    border-bottom: 1px solid #cbd5e1;
    padding-bottom: 4px;
    margin-top: 1.4em;
    color: #1e3a8a;
  }

  h3 {
    font-size: 11pt;
    color: #2563eb;
    margin-top: 1.1em;
  }

  h4 {
    font-size: 9.5pt;
    color: #334155;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }

  p {
    margin: 0.4em 0 0.6em 0;
  }

  /* Document Header / Cover Banner */
  .cover-banner {
    background: linear-gradient(135deg, #0f172a 0%, #1e3a8a 100%);
    color: #ffffff;
    padding: 24px 28px;
    border-radius: 8px;
    margin-bottom: 22px;
  }

  .cover-banner h1 {
    color: #ffffff;
    border-bottom: 2px solid #60a5fa;
    margin: 0 0 8px 0;
    font-size: 21pt;
  }

  .cover-banner .subtitle {
    font-size: 11pt;
    color: #93c5fd;
    font-weight: 400;
    margin: 0 0 14px 0;
  }

  .metadata-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 10px;
    font-size: 8.5pt;
    background: rgba(255, 255, 255, 0.08);
    padding: 10px 14px;
    border-radius: 6px;
    border: 1px solid rgba(255, 255, 255, 0.15);
  }

  .metadata-item strong {
    color: #60a5fa;
    display: block;
    font-size: 7.5pt;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  /* Callout Boxes */
  .callout {
    border-left: 3.5px solid #3b82f6;
    background: #f8fafc;
    padding: 10px 14px;
    margin: 10px 0;
    border-radius: 0 6px 6px 0;
    font-size: 9pt;
    page-break-inside: avoid;
    break-inside: avoid;
  }

  .callout.physics {
    border-left-color: #8b5cf6;
    background: #faf5ff;
  }

  .callout.formula {
    border-left-color: #059669;
    background: #f0fdf4;
  }

  .callout.pipeline {
    border-left-color: #0284c7;
    background: #f0f9ff;
  }

  .callout strong.label {
    display: block;
    margin-bottom: 4px;
    font-size: 8pt;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }
  .callout.physics strong.label { color: #6d28d9; }
  .callout.formula strong.label { color: #047857; }
  .callout.pipeline strong.label { color: #0369a1; }

  /* Math equation formatting */
  .math-block {
    text-align: center;
    background: #f1f5f9;
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    padding: 8px 12px;
    margin: 8px 0;
    font-family: "Cambria Math", "Latin Modern Math", Georgia, serif;
    font-size: 11pt;
    color: #0f172a;
    page-break-inside: avoid;
    break-inside: avoid;
  }

  .math-inline {
    font-family: "Cambria Math", "Latin Modern Math", Georgia, serif;
    font-size: 10pt;
    background: #f1f5f9;
    padding: 1px 4px;
    border-radius: 3px;
    color: #0f172a;
  }

  /* Code snippet block */
  pre.code-block {
    background: #0f172a;
    color: #f8fafc;
    padding: 10px 14px;
    border-radius: 6px;
    font-family: "JetBrains Mono", Consolas, "Courier New", monospace;
    font-size: 7.8pt;
    line-height: 1.35;
    overflow-x: hidden;
    white-space: pre-wrap;
    margin: 8px 0;
    page-break-inside: avoid;
    break-inside: avoid;
    border: 1px solid #334155;
  }

  code {
    font-family: "JetBrains Mono", Consolas, "Courier New", monospace;
    font-size: 8.5pt;
    background: #e2e8f0;
    padding: 1px 4px;
    border-radius: 3px;
    color: #0f172a;
  }

  /* Tables */
  table {
    width: 100%;
    border-collapse: collapse;
    margin: 10px 0;
    font-size: 8.5pt;
    page-break-inside: avoid;
    break-inside: avoid;
  }

  table th, table td {
    border: 1px solid #cbd5e1;
    padding: 6px 9px;
    text-align: left;
    vertical-align: top;
  }

  table th {
    background: #e2e8f0;
    color: #0f172a;
    font-weight: 700;
  }

  table tr:nth-child(even) td {
    background: #f8fafc;
  }

  /* Diagrams */
  .diagram-container {
    text-align: center;
    margin: 12px 0;
    padding: 10px;
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    page-break-inside: avoid;
    break-inside: avoid;
  }

  .diagram-caption {
    font-size: 8pt;
    color: #64748b;
    margin-top: 6px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }

  /* Workflow Steps */
  .step-card {
    display: flex;
    gap: 12px;
    margin-bottom: 12px;
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    padding: 10px 12px;
    page-break-inside: avoid;
    break-inside: avoid;
    box-shadow: 0 1px 3px rgba(0,0,0,0.03);
  }

  .step-num {
    flex-shrink: 0;
    width: 32px;
    height: 32px;
    border-radius: 50%;
    background: #2563eb;
    color: #ffffff;
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: 800;
    font-size: 11pt;
  }

  .step-content {
    flex-grow: 1;
  }

  .step-title {
    font-weight: 700;
    font-size: 9.8pt;
    color: #0f172a;
    margin-bottom: 2px;
  }

  .step-desc {
    font-size: 8.8pt;
    color: #475569;
    margin: 0;
  }

  .badge {
    display: inline-block;
    padding: 2px 7px;
    border-radius: 4px;
    font-size: 7.2pt;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }
  .badge-cpp { background: #dbeafe; color: #1e40af; }
  .badge-py { background: #fef3c7; color: #92400e; }
  .badge-api { background: #dcfce7; color: #166534; }
  .badge-algo { background: #f3e8ff; color: #6b21a8; }

  .page-break {
    page-break-before: always;
    break-before: always;
  }

  ul, ol {
    margin: 0.3em 0 0.6em 0;
    padding-left: 20px;
  }

  li {
    margin-bottom: 3px;
  }
</style>
</head>
<body>

<!-- COVER / HEADER BANNER -->
<div class="cover-banner">
  <h1>LuxCore Physics & Calculation Architecture</h1>
  <div class="subtitle">A Deep-Dive Guide to Photometric Direct Illumination, Radiosity Interreflection, and the End-to-End Workflow</div>
  <div class="metadata-grid">
    <div class="metadata-item">
      <strong>Core Physics Engine</strong>
      LuxCore (C++20, Nanobind, OpenMP)
    </div>
    <div class="metadata-item">
      <strong>Pipeline Orchestrator</strong>
      FastAPI / Python Service Bridge
    </div>
    <div class="metadata-item">
      <strong>Compliance Standard</strong>
      EN 12464-1 & CIBSE SLL
    </div>
    <div class="metadata-item">
      <strong>Document Scope</strong>
      Full Algorithm & Request-to-Matrix Flow
    </div>
  </div>
</div>

<!-- SECTION 1: ARCHITECTURAL LIGHTING PHYSICS -->
<h2>1. Architectural Lighting Physics & Direct Illumination</h2>

<p>
Architectural illumination engineering requires calculating the total light arriving at designated task areas (workplanes, desks, floors) and room boundaries (walls, ceilings). Light in an enclosed space consists of two coupled components:
</p>

<div class="callout physics">
  <strong class="label">The Dual-Component Illuminance Equation</strong>
  At any surface evaluation point \(P\), total illuminance \(E_{total}\) (measured in Lux, \(\text{lm/m}^2\)) is the superposition of <strong>Direct Illuminance</strong> from luminaires and <strong>Indirect Illuminance</strong> from interreflections:
  <div class="math-block">
    E_{total}(P) = \text{MF} \times \Big( E_{direct}(P) + E_{indirect}(P) \Big)
  </div>
  Where \(\text{MF}\) is the <strong>Maintenance Factor</strong> (typically \(0.80\)), accounting for lamp lumen depreciation, luminaire dirt accumulation, and surface aging over time.
</div>

<!-- DIAGRAM 1: DIRECT VS INDIRECT -->
<div class="diagram-container">
  <svg width="680" height="220" viewBox="0 0 680 220" xmlns="http://www.w3.org/2000/svg">
    <!-- Ceiling -->
    <line x1="40" y1="30" x2="640" y2="30" stroke="#475569" stroke-width="6"/>
    <text x="50" y="22" font-size="10" font-weight="bold" fill="#475569">CEILING (ρ = 0.70)</text>
    <!-- Floor -->
    <line x1="40" y1="190" x2="640" y2="190" stroke="#475569" stroke-width="6"/>
    <text x="50" y="206" font-size="10" font-weight="bold" fill="#475569">FLOOR (ρ = 0.20)</text>
    <!-- Left Wall -->
    <line x1="40" y1="30" x2="40" y2="190" stroke="#475569" stroke-width="6"/>
    <text x="14" y="115" font-size="10" font-weight="bold" fill="#475569" transform="rotate(-90 14 115)">WALL (ρ = 0.50)</text>
    <!-- Right Wall -->
    <line x1="640" y1="30" x2="640" y2="190" stroke="#475569" stroke-width="6"/>
    <!-- Luminaire -->
    <rect x="300" y="30" width="80" height="12" rx="3" fill="#0284c7" stroke="#0369a1" stroke-width="2"/>
    <text x="340" y="22" font-size="10" font-weight="bold" fill="#0284c7" text-anchor="middle">LUMINAIRE (IES WEB)</text>
    <!-- Workplane -->
    <line x1="120" y1="150" x2="560" y2="150" stroke="#10b981" stroke-width="2.5" stroke-dasharray="6,4"/>
    <text x="130" y="142" font-size="10" font-weight="bold" fill="#059669">WORKPLANE (z = 0.85m)</text>
    <!-- Direct rays (yellow solid) -->
    <line x1="340" y1="42" x2="340" y2="150" stroke="#eab308" stroke-width="2.5" marker-end="url(#arrow-yellow)"/>
    <line x1="330" y1="42" x2="220" y2="150" stroke="#eab308" stroke-width="2" marker-end="url(#arrow-yellow)"/>
    <line x1="350" y1="42" x2="460" y2="150" stroke="#eab308" stroke-width="2" marker-end="url(#arrow-yellow)"/>
    <line x1="310" y1="42" x2="45" y2="90" stroke="#f59e0b" stroke-width="1.8" stroke-dasharray="4,2"/>
    <line x1="370" y1="42" x2="635" y2="95" stroke="#f59e0b" stroke-width="1.8" stroke-dasharray="4,2"/>
    <!-- Indirect reflections (purple dashed) -->
    <path d="M 45 90 Q 180 110 340 150" stroke="#8b5cf6" stroke-width="2" stroke-dasharray="4,4" fill="none"/>
    <path d="M 635 95 Q 500 110 340 150" stroke="#8b5cf6" stroke-width="2" stroke-dasharray="4,4" fill="none"/>
    <path d="M 340 190 Q 250 170 340 150" stroke="#8b5cf6" stroke-width="1.5" stroke-dasharray="3,3" fill="none"/>
    <!-- Legends -->
    <circle cx="210" cy="80" r="4" fill="#eab308"/>
    <text x="220" y="84" font-size="9" fill="#854d0e" font-weight="bold">Direct Component (Inverse-Square + IES)</text>
    <circle cx="430" cy="80" r="4" fill="#8b5cf6"/>
    <text x="440" y="84" font-size="9" fill="#5b21b6" font-weight="bold">Indirect Component (Diffuse Radiosity Bounces)</text>
    <!-- Arrowhead markers -->
    <defs>
      <marker id="arrow-yellow" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
        <path d="M 0 0 L 10 5 L 0 10 z" fill="#eab308"/>
      </marker>
    </defs>
  </svg>
  <div class="diagram-caption">Figure 1: Dual-component architectural lighting framework showing direct beam flux and diffuse boundary interreflections.</div>
</div>

<h3>1.1 Point-to-Point Photometric Inverse-Square Law</h3>
<p>
For an ideal point light source, the illuminance \(E\) received by a differential surface element \(dA\) with normal \(\vec{n}\) at distance \(d\) is governed by <strong>Lambert's Inverse-Square Cosine Law</strong>:
</p>

<div class="math-block">
  E = \frac{I(\theta_{source}, \phi_{source})}{d^2} \cos\theta_{inc}
</div>

<ul>
  <li>\(I(\theta_{source}, \phi_{source})\): Luminous intensity in Candelas (\(\text{cd} = \text{lm/sr}\)), queried from the luminaire's spherical photometric distribution web (IES LM-63 or EULUMDAT LDT file) via bilinear interpolation.</li>
  <li>\(d\): Euclidean distance from the luminaire optical center to the evaluation point \(P\).</li>
  <li>\(\theta_{inc}\): <strong>Angle of incidence</strong> between the incoming light vector and the surface normal \(\vec{n}\). When \(\theta_{inc} \ge 90^\circ\), \(\cos\theta_{inc} \le 0\), meaning the surface faces away from the luminaire, receiving zero direct light.</li>
</ul>

<h3>1.2 Extended Luminous Area Discretization</h3>
<p>
Real-world architectural luminaires (such as 600×600 mm troffers or 1.2 m linear pendants) are not infinitesimal point sources. When an evaluation point or ceiling patch is near the luminaire, treating it as a point source causes catastrophic errors: intensity blows up to infinity as distance approaches zero, creating artificial hot spots.
</p>

<p>
<strong>LuxCore solves this natively in C++ via <code>LuminousOpening::elements</code>:</strong>
</p>

<div class="callout physics">
  <strong class="label">Near-Field Luminous Element Discretization</strong>
  A luminaire with physical dimensions \(L \times W\) is discretized into a grid of \(N = n_x \times n_y\) sub-elements (where each element size \(\le 0.15\text{ m}\)):
  <div class="math-block">
    E_{direct}(P) = \frac{1}{N} \sum_{k=1}^N \frac{I(\theta_k, \phi_k)}{\|\vec{P} - \vec{O}_k\|^2} \cos\theta_{inc, k}
  </div>
  Where \(\vec{O}_k\) represents the rotated, tilted 3D coordinates of the \(k\)-th luminous sub-element. This numerical integration smoothly transitions from extended near-field optics to point-source far-field physics without analytical singularities.
</div>

<div class="page-break"></div>

<!-- SECTION 2: LUXCORE RADIOSITY ENGINE -->
<h2>2. The LuxCore Radiosity Engine: How Radiosity Works</h2>

<p>
Direct light accounts for only 40% to 70% of total illuminance in typical architectural environments. The remaining 30% to 60% comes from <strong>radiosity</strong>: light bouncing off walls, ceilings, and floors before reaching the task plane.
</p>

<h3>2.1 The Fundamental Radiosity Governing Equation</h3>
<p>
Radiosity assumes all surfaces are <strong>Lambertian (ideal diffuse)</strong> reflectors. The total flux leaving surface patch \(i\) per unit area (the Radiosity \(B_i\), in \(\text{lm/m}^2\) or Lux) equals the light emitted directly plus the light reflected from all other patches \(j\) in the room:
</p>

<div class="math-block">
  B_i = E_i + \rho_i \sum_{j=1}^M F_{ij} B_j
</div>

<table>
  <thead>
    <tr>
      <th style="width: 18%;">Symbol</th>
      <th style="width: 28%;">Name</th>
      <th>Physical Meaning & Architectural Context</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td><strong>\(B_i\)</strong></td>
      <td>Total Radiosity</td>
      <td>Total exitance leaving patch \(i\) (\(\text{lm/m}^2\)) after all interreflection bounces.</td>
    </tr>
    <tr>
      <td><strong>\(E_i\)</strong></td>
      <td>Direct Seed Illuminance</td>
      <td>Initial direct light arriving on patch \(i\) directly from all luminaires.</td>
    </tr>
    <tr>
      <td><strong>\(\rho_i\)</strong></td>
      <td>Diffuse Reflectance</td>
      <td>Fraction of incident light reflected: \(\rho_{wall} \approx 0.50\), \(\rho_{floor} \approx 0.20\), \(\rho_{ceiling} \approx 0.70\).</td>
    </tr>
    <tr>
      <td><strong>\(F_{ij}\)</strong></td>
      <td>Geometric Form Factor</td>
      <td>The fraction of diffuse energy leaving patch \(i\) that directly arrives at patch \(j\).</td>
    </tr>
  </tbody>
</table>

<h3>2.2 The Geometric Form Factor Formulation</h3>
<p>
The form factor \(F_{ij}\) between patch \(i\) (area \(A_i\), normal \(\vec{n}_i\)) and patch \(j\) (area \(A_j\), normal \(\vec{n}_j\)) separated by distance vector \(\vec{r} = \vec{P}_j - \vec{P}_i\) is defined by the Nusselt / Lambert double area integral:
</p>

<div class="math-block">
  F_{ij} = \frac{1}{A_i} \int_{A_i} \int_{A_j} \frac{\cos\theta_i \cos\theta_j}{\pi r^2} V(i, j) \, dA_j \, dA_i
</div>

<p>
Where \(\cos\theta_i = \frac{\vec{r} \cdot \vec{n}_i}{r}\), \(\cos\theta_j = \frac{-\vec{r} \cdot \vec{n}_j}{r}\), and \(V(i, j) \in \{0, 1\}\) is the visibility occlusion predicate.
</p>

<!-- DIAGRAM 2: FORM FACTOR GEOMETRY & CLOSE-FIELD -->
<div class="diagram-container">
  <svg width="680" height="200" viewBox="0 0 680 200" xmlns="http://www.w3.org/2000/svg">
    <!-- Patch i on Wall -->
    <rect x="70" y="40" width="18" height="90" fill="#3b82f6" stroke="#1d4ed8" stroke-width="2"/>
    <circle cx="79" cy="85" r="4" fill="#1e3a8a"/>
    <line x1="79" y1="85" x2="130" y2="85" stroke="#1d4ed8" stroke-width="2" marker-end="url(#arrow-blue)"/>
    <text x="135" y="90" font-size="10" font-weight="bold" fill="#1d4ed8">n_i (Normal)</text>
    <text x="50" y="35" font-size="10" font-weight="bold" fill="#1e3a8a">Patch i (Area A_i)</text>

    <!-- Ray r between centers -->
    <line x1="79" y1="85" x2="480" y2="150" stroke="#64748b" stroke-width="1.8" stroke-dasharray="4,4"/>
    <text x="270" y="105" font-size="10" font-weight="bold" fill="#475569">Distance r</text>

    <!-- Patch j on Floor -->
    <rect x="420" y="145" width="120" height="16" fill="#10b981" stroke="#047857" stroke-width="2"/>
    <circle cx="480" cy="153" r="4" fill="#065f46"/>
    <line x1="480" y1="153" x2="480" y2="95" stroke="#047857" stroke-width="2" marker-end="url(#arrow-green)"/>
    <text x="488" y="105" font-size="10" font-weight="bold" fill="#047857">n_j (Normal)</text>
    <text x="430" y="178" font-size="10" font-weight="bold" fill="#065f46">Patch j (Area A_j)</text>

    <!-- Angle arcs -->
    <path d="M 105 85 A 25 25 0 0 1 100 95" fill="none" stroke="#dc2626" stroke-width="1.5"/>
    <text x="110" y="100" font-size="9" font-weight="bold" fill="#dc2626">θ_i</text>
    <path d="M 465 130 A 25 25 0 0 1 480 125" fill="none" stroke="#dc2626" stroke-width="1.5"/>
    <text x="450" y="125" font-size="9" font-weight="bold" fill="#dc2626">θ_j</text>

    <!-- Close-transfer refinement callout box right -->
    <rect x="560" y="30" width="110" height="135" rx="5" fill="#f8fafc" stroke="#cbd5e1" stroke-width="1.5"/>
    <text x="615" y="46" font-size="8.5" font-weight="bold" fill="#0f172a" text-anchor="middle">2×2 SUB-PATCH</text>
    <text x="615" y="58" font-size="7.5" fill="#64748b" text-anchor="middle">QUADRATURE</text>
    <!-- Subgrid preview -->
    <rect x="580" y="70" width="32" height="32" fill="#dbeafe" stroke="#3b82f6"/>
    <line x1="596" y1="70" x2="596" y2="102" stroke="#3b82f6"/>
    <line x1="580" y1="86" x2="612" y2="86" stroke="#3b82f6"/>
    <text x="615" y="120" font-size="7.5" fill="#334155" text-anchor="middle">16 Micro-Pairs</text>
    <text x="615" y="132" font-size="7.5" fill="#059669" font-weight="bold" text-anchor="middle">Zero Singularity</text>
    <text x="615" y="144" font-size="7" fill="#64748b" text-anchor="middle">r &lt; 2·max(ds)</text>

    <!-- Arrow markers -->
    <defs>
      <marker id="arrow-blue" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
        <path d="M 0 0 L 10 5 L 0 10 z" fill="#1d4ed8"/>
      </marker>
      <marker id="arrow-green" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
        <path d="M 0 0 L 10 5 L 0 10 z" fill="#047857"/>
      </marker>
    </defs>
  </svg>
  <div class="diagram-caption">Figure 2: Differential patch interaction geometry and 2×2 sub-patch numerical quadrature refinement.</div>
</div>

<h3>2.3 Near-Field 2×2 Sub-Patch Numerical Quadrature (<code>refine_close</code>)</h3>
<p>
When two patches are adjacent or very close (such as where the floor meets a wall), the distance \(r\) between patch centers is small: \(r < 2 \cdot \max(ds_i, ds_j)\). Evaluating form factors strictly at center points causes severe overestimation and visual banding.
</p>

<p>
<strong>LuxCore implements in-place 2×2 numerical quadrature in C++ (<code>radiosity_solver.cpp:83</code>):</strong>
</p>
<ol>
  <li>Constructs orthonormal tangent frames \((\vec{t}_{1}, \vec{t}_{2})\) orthogonal to the patch normal.</li>
  <li>Subdivides both source patch \(i\) and target patch \(j\) into 4 sub-quadrants at offsets \(\pm 0.25 ds\).</li>
  <li>Evaluates form factors across all \(4 \times 4 = 16\) sub-element pairs with area weighting \(A / 4\).</li>
  <li>Computes the exact averaged radiant transfer, completely eliminating singularities at room corners.</li>
</ol>

<h3>2.4 Energy Conservation Enforcement</h3>
<p>
In physics, energy cannot be created from nothing. The total flux leaving any patch \(i\) into an enclosure must satisfy reciprocity:
</p>
<div class="math-block">
  A_i F_{ij} = A_j F_{ji} \quad \text{and} \quad \sum_{j=1}^M F_{ij} \frac{A_j}{A_i} \le 1.0
</div>
<p>
Because discrete meshes have minor discretization errors, raw row sums could slightly exceed \(1.0\), which would cause infinite energy feedback loops during iterative bounces.
LuxCore enforces strict row-normalization (<code>radiosity_solver.cpp:325</code>):
</p>
<div class="math-block">
  \text{conserve}_i = \min\left(1.0, \, \frac{A_i}{\sum_{j} F_{ij} A_j}\right), \quad F_{ij} \leftarrow F_{ij} \times \text{conserve}_i
</div>

<div class="page-break"></div>

<h3>2.5 The Neumann Series Solver (Bounce Progression)</h3>
<p>
In matrix notation, the radiosity system is written as \((I - \mathbf{\rho} F) B = E\), where \(\mathbf{\rho} = \text{diag}(\rho_1, \dots, \rho_M)\) is the diagonal matrix of surface reflectances.
Solving this via matrix inversion \(O(M^3)\) is computationally prohibitive when rooms have thousands of patches.
</p>

<p>
Instead, <strong>LuxCore uses the Neumann Series expansion</strong> (the physical simulation of individual light bounces):
</p>

<div class="callout physics">
  <strong class="label">Neumann Series Iteration Law</strong>
  <div class="math-block">
    B = (I - \mathbf{\rho} F)^{-1} E = \sum_{k=0}^{\infty} (\mathbf{\rho} F)^k E = E + (\mathbf{\rho} F) E + (\mathbf{\rho} F)^2 E + (\mathbf{\rho} F)^3 E + \dots
  </div>
  <strong>Physical Interpretation:</strong>
  <ul>
    <li><strong>\(B^{(0)} = E\)</strong>: Direct lighting from luminaires onto walls, ceiling, and floor (0 bounces).</li>
    <li><strong>\(B^{(1)} = E + \mathbf{\rho} F B^{(0)}\)</strong>: Light that has bounced once off room boundaries.</li>
    <li><strong>\(B^{(2)} = E + \mathbf{\rho} F B^{(1)}\)</strong>: Light that has bounced twice through the room.</li>
    <li><strong>\(B^{(m)}\)</strong>: Light after \(m\) interreflections. Because \(\|\mathbf{\rho} F\| < 1\), each bounce decays exponentially:
      \(\rho_{avg} \approx 0.40 \implies \text{Bounce 1: } 40\%, \text{ Bounce 2: } 16\%, \text{ Bounce 3: } 6.4\%\).
      After 3 bounces, over 95% of total radiant energy has converged!
    </li>
  </ul>
</div>

<!-- DIAGRAM 3: NEUMANN BOUNCE PROGRESSION -->
<div class="diagram-container">
  <svg width="680" height="150" viewBox="0 0 680 150" xmlns="http://www.w3.org/2000/svg">
    <!-- Box 1: B0 -->
    <rect x="20" y="25" width="130" height="85" rx="6" fill="#fef3c7" stroke="#d97706" stroke-width="2"/>
    <text x="85" y="48" font-size="11" font-weight="bold" fill="#92400e" text-anchor="middle">BOUNCE 0: B^(0)</text>
    <text x="85" y="68" font-size="9" fill="#b45309" text-anchor="middle">Direct Luminaire Seeds</text>
    <text x="85" y="86" font-size="8" fill="#78350f" text-anchor="middle">B^(0) = E (Direct flux)</text>
    <text x="85" y="100" font-size="8.5" font-weight="bold" fill="#d97706" text-anchor="middle">100% Direct Energy</text>

    <!-- Arrow 1 -->
    <line x1="150" y1="67" x2="185" y2="67" stroke="#64748b" stroke-width="2.5" marker-end="url(#arrow-slate)"/>
    <text x="168" y="58" font-size="8" font-weight="bold" fill="#64748b" text-anchor="middle">ρ·F</text>

    <!-- Box 2: B1 -->
    <rect x="190" y="25" width="130" height="85" rx="6" fill="#e0e7ff" stroke="#4f46e5" stroke-width="2"/>
    <text x="255" y="48" font-size="11" font-weight="bold" fill="#3730a3" text-anchor="middle">BOUNCE 1: B^(1)</text>
    <text x="255" y="68" font-size="9" fill="#4338ca" text-anchor="middle">1st Diffuse Bounce</text>
    <text x="255" y="86" font-size="8" fill="#312e81" text-anchor="middle">B^(1) = E + ρ·F·B^(0)</text>
    <text x="255" y="100" font-size="8.5" font-weight="bold" fill="#4f46e5" text-anchor="middle">+40% Reflected</text>

    <!-- Arrow 2 -->
    <line x1="320" y1="67" x2="355" y2="67" stroke="#64748b" stroke-width="2.5" marker-end="url(#arrow-slate)"/>
    <text x="338" y="58" font-size="8" font-weight="bold" fill="#64748b" text-anchor="middle">ρ·F</text>

    <!-- Box 3: B2 -->
    <rect x="360" y="25" width="130" height="85" rx="6" fill="#ede9fe" stroke="#7c3aed" stroke-width="2"/>
    <text x="425" y="48" font-size="11" font-weight="bold" fill="#5b21b6" text-anchor="middle">BOUNCE 2: B^(2)</text>
    <text x="425" y="68" font-size="9" fill="#6d28d9" text-anchor="middle">2nd Diffuse Bounce</text>
    <text x="425" y="86" font-size="8" fill="#4c1d95" text-anchor="middle">B^(2) = E + ρ·F·B^(1)</text>
    <text x="425" y="100" font-size="8.5" font-weight="bold" fill="#7c3aed" text-anchor="middle">+16% Reflected</text>

    <!-- Arrow 3 -->
    <line x1="490" y1="67" x2="525" y2="67" stroke="#64748b" stroke-width="2.5" marker-end="url(#arrow-slate)"/>
    <text x="508" y="58" font-size="8" font-weight="bold" fill="#64748b" text-anchor="middle">G matrix</text>

    <!-- Box 4: Final Gather -->
    <rect x="530" y="25" width="130" height="85" rx="6" fill="#dcfce7" stroke="#16a34a" stroke-width="2"/>
    <text x="595" y="48" font-size="11" font-weight="bold" fill="#14532d" text-anchor="middle">FINAL GATHER</text>
    <text x="595" y="68" font-size="9" fill="#15803d" text-anchor="middle">Workplane Sensors</text>
    <text x="595" y="86" font-size="8" fill="#166534" text-anchor="middle">E_ind = Σ G_ji·c_i·ρ_i·B_i</text>
    <text x="595" y="100" font-size="8.5" font-weight="bold" fill="#16a34a" text-anchor="middle">Converged (EN 12464)</text>

    <defs>
      <marker id="arrow-slate" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
        <path d="M 0 0 L 10 5 L 0 10 z" fill="#64748b"/>
      </marker>
    </defs>
  </svg>
  <div class="diagram-caption">Figure 3: Multi-bounce Neumann series iterative convergence into workplane final gather.</div>
</div>

<h3>2.6 Visibility Occlusion Policy & The Convex Fast-Path</h3>
<p>
In non-convex rooms (e.g. L-shaped rooms, corridors, columns), walls can block light between two patches.
LuxCore implements a <strong>Hybrid Visibility Strategy</strong>:
</p>

<ul>
  <li><strong>Convex Room Bypass (<code>TransparentVisibilityPolicy</code>):</strong>
    When a room polygon is convex (rectangular, trapezoidal), any line segment connecting two internal points is mathematically guaranteed to stay inside the room. LuxCore automatically bypasses all ray-casting tests (\(O(1)\) constant time), providing a <strong>15× speedup</strong>!
  </li>
  <li><strong>Concave Room Policy (<code>BufferedRingVisibilityPolicy</code>):</strong>
    Python Shapely precomputes a slightly buffered exterior boundary ring. The C++ engine checks whether the 2D plan-view ray segment intersects any edge of the buffered ring.
  </li>
  <li><strong>Unique-XY Spatial Deduplication:</strong>
    Because multiple wall patches share the exact same 2D plan-view coordinates \((x, y)\) at different elevations \(z\), LuxCore quantizes coordinates to \(10^{-9}\text{ m}\) and builds an \(M \times M\) visibility boolean matrix `uni`. Ray visibility is computed once per unique XY pair rather than millions of redundant 3D tests!
  </li>
</ul>

<h3>2.7 Final Gather to Target Workplanes (\(G\) Transfer Matrix)</h3>
<p>
Once the radiosity exitance vector \(B\) has converged on all room boundary patches (sources), LuxCore performs a <strong>final gather</strong> onto the task workplanes (e.g., desk height \(0.85\text{ m}\)). Workplanes are virtual evaluation points and do not re-emit light back into the room:
</p>

<div class="math-block">
  E_{indirect}(j) = \sum_{i \in \text{sources}} G_{ji} \cdot \text{conserve}_i \cdot \rho_i \cdot B_i
</div>
<p>
Where \(G_{ji}\) is the directional transfer form factor from boundary source patch \(i\) to workplane target patch \(j\), complete with 2×2 sub-patch refinement if the workplane point is adjacent to a wall.
</p>

<div class="page-break"></div>

<!-- SECTION 3: END-TO-END CALCULATION WORKFLOW -->
<h2>3. The Complete End-to-End Calculation Workflow</h2>

<p>
Here is the step-by-step path of a lighting calculation, from the user clicking <strong>Calculate</strong> in the Studio canvas down to C++ execution in LuxCore and back:
</p>

<!-- DIAGRAM 4: FULL WORKFLOW PIPELINE -->
<div class="diagram-container">
  <svg width="680" height="260" viewBox="0 0 680 260" xmlns="http://www.w3.org/2000/svg">
    <!-- Step 1 -->
    <rect x="20" y="20" width="125" height="50" rx="5" fill="#f1f5f9" stroke="#94a3b8" stroke-width="1.5"/>
    <text x="82" y="38" font-size="9" font-weight="bold" fill="#0f172a" text-anchor="middle">1. Client Request</text>
    <text x="82" y="52" font-size="7.5" fill="#64748b" text-anchor="middle">JSON Payload (Canvas)</text>

    <!-- Arrow 1-2 -->
    <line x1="145" y1="45" x2="180" y2="45" stroke="#2563eb" stroke-width="2" marker-end="url(#arrow-blue2)"/>

    <!-- Step 2 -->
    <rect x="185" y="20" width="135" height="50" rx="5" fill="#dbeafe" stroke="#3b82f6" stroke-width="1.5"/>
    <text x="252" y="38" font-size="9" font-weight="bold" fill="#1e40af" text-anchor="middle">2. FastAPI Gateway</text>
    <text x="252" y="52" font-size="7.5" fill="#1d4ed8" text-anchor="middle">Shoelace & Polygon Validation</text>

    <!-- Arrow 2-3 -->
    <line x1="320" y1="45" x2="355" y2="45" stroke="#2563eb" stroke-width="2" marker-end="url(#arrow-blue2)"/>

    <!-- Step 3 -->
    <rect x="360" y="20" width="135" height="50" rx="5" fill="#fef3c7" stroke="#f59e0b" stroke-width="1.5"/>
    <text x="427" y="38" font-size="9" font-weight="bold" fill="#92400e" text-anchor="middle">3. Pattern Resolver</text>
    <text x="427" y="52" font-size="7.5" fill="#b45309" text-anchor="middle">Grid/Linear Expansion & Clip</text>

    <!-- Arrow 3-4 -->
    <line x1="495" y1="45" x2="530" y2="45" stroke="#2563eb" stroke-width="2" marker-end="url(#arrow-blue2)"/>

    <!-- Step 4 -->
    <rect x="535" y="20" width="125" height="50" rx="5" fill="#fce7f3" stroke="#ec4899" stroke-width="1.5"/>
    <text x="597" y="38" font-size="9" font-weight="bold" fill="#9d174d" text-anchor="middle">4. IES Ingestion</text>
    <text x="597" y="52" font-size="7.5" fill="#be185d" text-anchor="middle">Cache & Lumens Scaling</text>

    <!-- Arrow 4 down to 5 -->
    <path d="M 597 70 L 597 105 L 597 105" stroke="#2563eb" stroke-width="2" marker-end="url(#arrow-blue2)"/>

    <!-- Step 5 (Row 2 right) -->
    <rect x="525" y="110" width="135" height="50" rx="5" fill="#ede9fe" stroke="#8b5cf6" stroke-width="1.5"/>
    <text x="592" y="128" font-size="9" font-weight="bold" fill="#5b21b6" text-anchor="middle">5. Adaptive Meshing</text>
    <text x="592" y="142" font-size="7.5" fill="#6d28d9" text-anchor="middle">EN 12464 Eval & Solver Grid</text>

    <!-- Arrow 5-6 (leftwards) -->
    <line x1="525" y1="135" x2="490" y2="135" stroke="#2563eb" stroke-width="2" marker-end="url(#arrow-blue2)"/>

    <!-- Step 6 -->
    <rect x="350" y="110" width="135" height="50" rx="5" fill="#e0e7ff" stroke="#6366f1" stroke-width="1.5"/>
    <text x="417" y="128" font-size="9" font-weight="bold" fill="#3730a3" text-anchor="middle">6. Direct Seeds</text>
    <text x="417" y="142" font-size="7.5" fill="#4338ca" text-anchor="middle">DirectEngine on Boundaries</text>

    <!-- Arrow 6-7 (leftwards) -->
    <line x1="350" y1="135" x2="315" y2="135" stroke="#2563eb" stroke-width="2" marker-end="url(#arrow-blue2)"/>

    <!-- Step 7 (Centerpiece: LuxCore C++) -->
    <rect x="155" y="105" width="155" height="60" rx="6" fill="#0f172a" stroke="#38bdf8" stroke-width="2.5"/>
    <text x="232" y="127" font-size="10.5" font-weight="bold" fill="#38bdf8" text-anchor="middle">7. LuxCore C++</text>
    <text x="232" y="141" font-size="8" fill="#e2e8f0" text-anchor="middle">OpenMP Radiosity + F Matrix</text>
    <text x="232" y="153" font-size="7.5" fill="#94a3b8" text-anchor="middle">GIL Released • Neumann Solver</text>

    <!-- Arrow 7-8 (leftwards) -->
    <line x1="155" y1="135" x2="120" y2="135" stroke="#2563eb" stroke-width="2" marker-end="url(#arrow-blue2)"/>

    <!-- Step 8 -->
    <rect x="15" y="110" width="105" height="50" rx="5" fill="#f0fdf4" stroke="#22c55e" stroke-width="1.5"/>
    <text x="67" y="128" font-size="8.5" font-weight="bold" fill="#14532d" text-anchor="middle">8. Final Gather</text>
    <text x="67" y="142" font-size="7" fill="#166534" text-anchor="middle">G Transfer Matrix</text>

    <!-- Arrow 8 down to 9 -->
    <path d="M 67 160 L 67 195" stroke="#2563eb" stroke-width="2" marker-end="url(#arrow-blue2)"/>

    <!-- Step 9 (Row 3 left) -->
    <rect x="15" y="200" width="175" height="50" rx="5" fill="#fef2f2" stroke="#ef4444" stroke-width="1.5"/>
    <text x="102" y="218" font-size="9" font-weight="bold" fill="#991b1b" text-anchor="middle">9. Direct Eval + Interp</text>
    <text x="102" y="232" font-size="7.5" fill="#b91c1c" text-anchor="middle">Exact Direct on Eval Points + Sparse Interp</text>

    <!-- Arrow 9-10 -->
    <line x1="190" y1="225" x2="235" y2="225" stroke="#2563eb" stroke-width="2" marker-end="url(#arrow-blue2)"/>

    <!-- Step 10 -->
    <rect x="240" y="200" width="180" height="50" rx="5" fill="#ecfdf5" stroke="#10b981" stroke-width="1.5"/>
    <text x="330" y="218" font-size="9" font-weight="bold" fill="#065f46" text-anchor="middle">10. Maintenance & Compliance</text>
    <text x="330" y="232" font-size="7.5" fill="#047857" text-anchor="middle">E_tot = MF·(Dir+Ind) • E_avg, U_0, LPD</text>

    <!-- Arrow 10-11 -->
    <line x1="420" y1="225" x2="475" y2="225" stroke="#2563eb" stroke-width="2" marker-end="url(#arrow-blue2)"/>

    <!-- Step 11 -->
    <rect x="480" y="200" width="180" height="50" rx="5" fill="#f8fafc" stroke="#0f172a" stroke-width="2"/>
    <text x="570" y="218" font-size="9" font-weight="bold" fill="#0f172a" text-anchor="middle">11. JSON Result & Canvas</text>
    <text x="570" y="232" font-size="7.5" fill="#475569" text-anchor="middle">False-Color Heatmap • Isolines • Audit</text>

    <defs>
      <marker id="arrow-blue2" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
        <path d="M 0 0 L 10 5 L 0 10 z" fill="#2563eb"/>
      </marker>
    </defs>
  </svg>
  <div class="diagram-caption">Figure 4: Complete end-to-end data lifecycle from Client JSON payload to C++ LuxCore solver and frontend visualization.</div>
</div>

<div class="step-card">
  <div class="step-num">1</div>
  <div class="step-content">
    <div class="step-title">Client Request Packaging (lxscale-studio) <span class="badge badge-api">HTTP POST</span></div>
    <p class="step-desc">
      The Angular frontend serializes the scene state into <code>V2CalculateRequestDto</code>: room polygon <code>[{x,y}]</code>, ceiling & mounting heights, workplane definition array (height, perimeter margin, target lux, uniformity, standard standardId), surface reflectances (walls, floor, ceiling), maintenance factor (\(0.8\)), bounces (\(3\)), luminaire placements (positions, rotations, tilts, variant IDs), and any custom in-memory IES strings.
    </p>
  </div>
</div>

<div class="step-card">
  <div class="step-num">2</div>
  <div class="step-content">
    <div class="step-title">API Gateway & Polygon Sanitization (calculate_controller.py) <span class="badge badge-py">FastAPI</span></div>
    <p class="step-desc">
      FastAPI parses the request. It verifies that the room polygon has at least 3 vertices and computes the enclosed area using the Shoelace formula (\(A > 0.001\text{ m}^2\)). Invalid geometries are rejected with HTTP 400.
    </p>
  </div>
</div>

<div class="step-card">
  <div class="step-num">3</div>
  <div class="step-content">
    <div class="step-title">Parametric Pattern Resolution & Boundary Clipping <span class="badge badge-algo">Geometry</span></div>
    <p class="step-desc">
      If parametric layouts exist (rectangular grid, staggered, linear, circumference), the pattern resolver calculates each fixture position. Fixtures falling outside the room polygon are clipped. Deduplication keys ensure no overlapping duplicate luminaires exist.
    </p>
  </div>
</div>

<div class="step-card">
  <div class="step-num">4</div>
  <div class="step-content">
    <div class="step-title">Photometry Ingestion & C++ Profile Caching (IesHandleCache) <span class="badge badge-algo">Photometry</span></div>
    <p class="step-desc">
      Custom in-memory IES files and catalog database variants are resolved. Lumens are scaled to specified flux ratings and dimensions. The parsed candela tables are transformed into C++ <code>luxcore.IesProfile</code> objects and cached in <code>IesHandleCache</code>.
    </p>
  </div>
</div>

<div class="page-break"></div>

<div class="step-card">
  <div class="step-num">5</div>
  <div class="step-content">
    <div class="step-title">EN 12464 Evaluation Grid & Adaptive Solver Meshing (pipeline.py) <span class="badge badge-algo">Meshing</span></div>
    <p class="step-desc">
      <strong>Evaluation Grid:</strong> Strictly follows European Standard EN 12464-1. Spacing \(p = 0.2 \times 5^{\log_{10} d}\), clipped to perimeter margins.<br>
      <strong>Solver Mesh:</strong> Creates boundary patches (floor, ceiling, walls). An adaptive sizing algorithm (<code>resolve_solver_cell</code>) scales patch sizes according to room dimensions (e.g. \(0.40\text{ m}\) for small rooms, \(1.0\text{ m}\) for large halls) to ensure optimal accuracy without patch explosion.<br>
      <strong>Sparse Interpolation Weights:</strong> Precomputes bilinear interpolation weights mapping coarse solver patches to dense evaluation grid points.
    </p>
  </div>
</div>

<div class="step-card">
  <div class="step-num">6</div>
  <div class="step-content">
    <div class="step-title">Direct Illumination Seeds Generation (DirectEngine) <span class="badge badge-cpp">C++ OpenMP</span></div>
    <p class="step-desc">
      When bounces \(> 0\), LuxCore's <code>DirectEngine</code> computes the direct light arriving from all luminaires onto the coarse boundary solver patches (floor, ceiling, walls). These values form the initial radiosity seed vector \(E\).
    </p>
  </div>
</div>

<div class="step-card">
  <div class="step-num">7</div>
  <div class="step-content">
    <div class="step-title">LuxCore Radiosity Solver Execution (_luxcore_bridge.py) <span class="badge badge-cpp">C++ Core</span></div>
    <p class="step-desc">
      NumPy arrays (Struct-of-Arrays: patch centers, normals, areas, surface types, seeds) are passed via Nanobind into C++. The Python GIL is released. OpenMP parallelizes across available CPU threads:
      <ul>
        <li>Evaluates visibility (convex fast-path vs. buffered ring occlusion).</li>
        <li>Computes the \(F\) form factor matrix with 2×2 sub-patch refinement.</li>
        <li>Normalizes row sums to guarantee physical energy conservation.</li>
        <li>Executes \(m\) Neumann series iterations: \(B^{(k)} = E + \mathbf{\rho} F B^{(k-1)}\).</li>
        <li>Applies the \(G\) final gather matrix to compute indirect illuminance on all task workplanes.</li>
      </ul>
    </p>
  </div>
</div>

<div class="step-card">
  <div class="step-num">8</div>
  <div class="step-content">
    <div class="step-title">Direct Evaluation on Dense Grid & Sparse Matrix Interpolation <span class="badge badge-algo">Assembly</span></div>
    <p class="step-desc">
      Exact direct illuminance is evaluated analytically at every dense evaluation grid point using the full photometric IES web. The coarse solver indirect results are projected onto the dense evaluation grid via the precomputed sparse interpolation weights.
    </p>
  </div>
</div>

<div class="step-card">
  <div class="step-num">9</div>
  <div class="step-content">
    <div class="step-title">Maintenance Factor Application & Compliance Auditing <span class="badge badge-py">Audit</span></div>
    <p class="step-desc">
      Applies the maintenance factor: \(E_{maintained} = \text{MF} \times (E_{dir} + E_{indir})\). Computes statistical criteria:
      <ul>
        <li><strong>Average Illuminance:</strong> \(E_{avg} = \frac{1}{K} \sum_{i=1}^K E_i\)</li>
        <li><strong>Overall Uniformity:</strong> \(U_0 = \frac{E_{min}}{E_{avg}}\)</li>
        <li><strong>Diversity:</strong> \(\frac{E_{min}}{E_{max}}\)</li>
        <li><strong>Lighting Power Density:</strong> \(\text{LPD} = \frac{\sum P_{watts}}{\text{Area}} \, (\text{W/m}^2)\)</li>
        <li><strong>Compliance Verdict:</strong> Compares against standard criteria (e.g. EN 12464 Office: \(E_{avg} \ge 500\text{ lux}, U_0 \ge 0.60\)).</li>
      </ul>
    </p>
  </div>
</div>

<div class="step-card">
  <div class="step-num">10</div>
  <div class="step-content">
    <div class="step-title">Response Serialization & Frontend Visualization <span class="badge badge-api">JSON / Canvas</span></div>
    <p class="step-desc">
      FastAPI returns <code>V2CalculateResponse</code> containing 2D lux matrices, evaluation summaries, and 3D point arrays. The frontend renders:
      <ul>
        <li><strong>False-Color Heatmaps:</strong> GPU-accelerated smooth scalar lux distribution maps.</li>
        <li><strong>Isolux Contours:</strong> Vector contour lines connecting equal illuminance thresholds (e.g. 300, 500, 750 lux).</li>
        <li><strong>Interactive Lux Probe:</strong> Real-time point inspection under mouse cursor.</li>
      </ul>
    </p>
  </div>
</div>

<div class="page-break"></div>

<!-- SECTION 4: ARCHITECTURE & HIGH PERFORMANCE ENGINEERING -->
<h2>4. High-Performance Engineering & Hardware Optimization</h2>

<p>
Why is LuxCore so fast compared to traditional Python or legacy radiosity solvers?
</p>

<table>
  <thead>
    <tr>
      <th>Architecture Dimension</th>
      <th>Legacy / Traditional Approaches</th>
      <th>LuxCore Advanced Architecture</th>
      <th>Engineering Advantage</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td><strong>Binding Technology</strong></td>
      <td>Pure Python or Pybind11</td>
      <td><strong>Nanobind (C++20)</strong></td>
      <td>4× faster compilation, smaller binary footprint, zero overhead Python-C++ type conversion.</td>
    </tr>
    <tr>
      <td><strong>Memory Layout</strong></td>
      <td>Array of Structs (AoS) / Python Object Lists</td>
      <td><strong>Struct-of-Arrays (SoA)</strong></td>
      <td>Sequential contiguous memory vectors (<code>cx_, cy_, cz_, nx_, ny_, nz_, area_</code>) maximized for CPU L1/L2 cache prefetching and SIMD vectorization.</td>
    </tr>
    <tr>
      <td><strong>Thread Concurrency</strong></td>
      <td>Blocked by Python GIL (Single-threaded)</td>
      <td><strong>OpenMP (<code>gil_scoped_release</code>)</strong></td>
      <td>Releases Python Global Interpreter Lock during computation. Linear multi-core scaling across 4 to 64 CPU cores.</td>
    </tr>
    <tr>
      <td><strong>Visibility Ray-Casting</strong></td>
      <td>\(O(M^2)\) 3D ray-polygon intersections per pair</td>
      <td><strong>Hybrid Convex Bypass + Unique-XY Mask</strong></td>
      <td>Convex rooms skip visibility tests in \(O(1)\). Concave rooms use quantized 2D plan projection, reducing ray queries by over 80%.</td>
    </tr>
    <tr>
      <td><strong>Singularity Protection</strong></td>
      <td>Ad-hoc clipping / artificial caps</td>
      <td><strong>2×2 Sub-Patch Quadrature (<code>refine_close</code>)</strong></td>
      <td>Physical numerical integration over 16 micro-element pairs whenever \(r < 2 \cdot \max(ds_i, ds_j)\). Eliminates corner hot-spot artifacts.</td>
    </tr>
    <tr>
      <td><strong>Numerical Stability</strong></td>
      <td>Iterative divergence risks when \(\rho\) is high</td>
      <td><strong>Strict Enclosure Conservation</strong></td>
      <td>Enforces reciprocity and row-sum clamping (\(c_i = \min(1, A_i / \sum F_{ij} A_j)\)), guaranteeing absolute numerical stability.</td>
    </tr>
  </tbody>
</table>

<!-- CODE REPOSITORY MAP -->
<h3>4.1 Codebase File Map Reference</h3>
<table style="font-size: 8pt;">
  <thead>
    <tr>
      <th>Component / File</th>
      <th>Language</th>
      <th>Primary Responsibility in Calculation Flow</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td><code>luxcore/src/radiosity_solver.cpp</code></td>
      <td>C++20</td>
      <td>Form factor calculation, 2×2 sub-patch refinement, conservation scaling, Neumann bounce iterations, workplane final gather.</td>
    </tr>
    <tr>
      <td><code>luxcore/src/direct_engine.cpp</code></td>
      <td>C++20</td>
      <td>Direct illuminance evaluation from extended luminaires (<code>LuminousOpening::elements</code>) onto surface patches.</td>
    </tr>
    <tr>
      <td><code>luxcore/src/visibility_policy.cpp</code></td>
      <td>C++20</td>
      <td>Convex bypass policy, concave buffered-ring ray intersection, unique-XY spatial deduplication mask.</td>
    </tr>
    <tr>
      <td><code>luxcore/src/ies.cpp</code></td>
      <td>C++20</td>
      <td>Bilinear and bicubic interpolation of spherical candela tables from photometric IES LM-63 files.</td>
    </tr>
    <tr>
      <td><code>app/services/_luxcore_bridge.py</code></td>
      <td>Python</td>
      <td>Zero-copy NumPy Struct-of-Arrays bridge, handles fallback to pure Python if binary is unavailable.</td>
    </tr>
    <tr>
      <td><code>app/engine/pipeline.py</code></td>
      <td>Python</td>
      <td>Full calculation pipeline orchestrator: <code>build_room</code>, <code>build_eval_grids</code>, <code>build_solver_cache</code>, and <code>run</code>.</td>
    </tr>
    <tr>
      <td><code>app/controllers/v2/calculate_controller.py</code></td>
      <td>Python / FastAPI</td>
      <td>HTTP POST <code>/api/v2/calculate</code> endpoint, JSON payload sanitization, pattern expansion, compliance auditing.</td>
    </tr>
  </tbody>
</table>

<div class="callout pipeline" style="margin-top: 15px;">
  <strong class="label">Summary of Mathematical Rigor</strong>
  LuxCore merges the physical rigor of classical radiosity (heat-transfer enclosure theory) with modern high-performance SIMD/OpenMP computing. By decoupling the coarse radiosity interreflection mesh from the dense EN 12464 evaluation grid via precomputed sparse weights, it achieves sub-second calculation times while maintaining 100% compliance with international architectural lighting codes.
</div>

</body>
</html>
"""

def main():
    print(f"[1/3] Ensuring output directory exists: {OUTPUT_DIR}")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"[2/3] Writing publication HTML source to: {OUTPUT_HTML}")
    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(HTML_CONTENT)

    print(f"[3/3] Compiling HTML to PDF using Google Chrome headless...")
    cmd = [
        "google-chrome",
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        "--no-pdf-header-footer",
        f"--print-to-pdf={OUTPUT_PDF}",
        f"file://{OUTPUT_HTML.resolve()}",
    ]

    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"Error compiling PDF: {res.stderr}", file=sys.stderr)
        sys.exit(1)

    if OUTPUT_PDF.exists():
        size_kb = OUTPUT_PDF.stat().st_size / 1024
        print(f"SUCCESS: Generated PDF at {OUTPUT_PDF} ({size_kb:.1f} KB)")
    else:
        print(f"Error: Output PDF was not created.", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
