import os
import sys
import threading
import subprocess
import json
import hashlib
from datetime import datetime
from functools import wraps
from werkzeug.utils import secure_filename
from flask import Flask, render_template_string, redirect, url_for, request, session, send_from_directory, make_response, jsonify

import gzip
from io import BytesIO
app = Flask(__name__)
app.secret_key = "dashboard-control-secret"

# Add custom Jinja2 filter for dirname
@app.template_filter('dirname')
def dirname_filter(path):
    return os.path.dirname(path)

# Add enumerate to Jinja2 globals
app.jinja_env.globals.update(enumerate=enumerate)

_COMPRESS_MIMETYPES = {
    "text/html",
    "text/css",
    "application/javascript",
    "application/json",
    "text/plain",
}


@app.after_request
def _compress_response(response):
    if response.direct_passthrough:
        return response
    accept = request.headers.get("Accept-Encoding", "").lower()
    if "gzip" not in accept:
        return response
    if response.status_code < 200 or response.status_code >= 300:
        return response
    if response.headers.get("Content-Encoding"):
        return response
    if (response.mimetype or "") not in _COMPRESS_MIMETYPES:
        return response
    data = response.get_data()
    if len(data) < 600:
        return response
    buffer = BytesIO()
    with gzip.GzipFile(mode="wb", fileobj=buffer) as gz:
        gz.write(data)
    response.set_data(buffer.getvalue())
    response.headers["Content-Encoding"] = "gzip"
    response.headers["Content-Length"] = len(response.get_data())
    vary = response.headers.get("Vary")
    if vary:
        if "Accept-Encoding" not in vary:
            response.headers["Vary"] = f"{vary}, Accept-Encoding"
    else:
        response.headers["Vary"] = "Accept-Encoding"
    return response

_data_path = os.path.join(os.path.dirname(__file__), "scripts.json")
_nav_path = os.path.join(os.path.dirname(__file__), "nav.json")
_users_path = os.path.join(os.path.dirname(__file__), "users.json")
_background_path = os.path.join(os.path.dirname(__file__), "background.json")
_history_path = os.path.join(os.path.dirname(__file__), "history.json")
_access_log_path = os.path.join(os.path.dirname(__file__), "access_log.json")
_ip_labels_path = os.path.join(os.path.dirname(__file__), "ip_labels.json")
_ip_protection_path = os.path.join(os.path.dirname(__file__), "ip_protection.json")
_ip_protection_access_path = os.path.join(os.path.dirname(__file__), "ip_protection_access.json")
_scripts = []
_processes = {}
_last_message = "Ready."
_lock = threading.Lock()
_upload_dir = os.path.join(os.path.dirname(__file__), "uploads")
_log_dir = os.path.join(os.path.dirname(__file__), "logs")
_nav = {"main": [], "subs": {}}
_users = []
_history = []
_access_log = []
_ip_labels = {}
_background = {"mode": "default", "image": ""}
_ip_protection = {"enabled": False}
_ip_protection_access = []

PAGE = """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <link rel="icon" type="image/svg+xml" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><defs><linearGradient id='g' x1='0%' y1='0%' x2='100%' y2='100%'><stop offset='0%' style='stop-color:%230a9fb5'/><stop offset='100%' style='stop-color:%230a6f86'/></linearGradient></defs><rect width='32' height='32' rx='6' fill='url(%23g)'/><circle cx='8' cy='8' r='2.5' fill='white' opacity='0.9'/><circle cx='24' cy='8' r='2' fill='%2300ff99' opacity='0.95'/><circle cx='24' cy='16' r='2' fill='%23ff6b6b' opacity='0.85'/><circle cx='24' cy='24' r='2' fill='%23ffd700' opacity='0.75'/><line x1='8' y1='5.5' x2='8' y2='4' stroke='white' stroke-width='1.2' opacity='0.8'/><line x1='8' y1='13.5' x2='8' y2='12' stroke='white' stroke-width='1.2' opacity='0.6'/><line x1='8' y1='21.5' x2='8' y2='20' stroke='white' stroke-width='1.2' opacity='0.4'/><rect x='14' y='11' width='6' height='10' rx='1' fill='none' stroke='white' stroke-width='0.8' opacity='0.6'/></svg>">
    <title>E6 DASHBOARD</title>
    <style>
      :root {
         --bg1: #0b1a2a;
         --bg2: #152238;
         --text: #0d1a2a;
         --muted: #5c6d7e;
         --brand: #0a6f86;
         --brand-dark: #085a6d;
         --panel: #ffffff;
         --border: #d9dde3;
         --green: #28a745;
         --red: #dc3545;
         --font-body: "Bahnschrift", "Candara", "Trebuchet MS", sans-serif;
         --font-display: "Rockwell", "Constantia", "Georgia", serif;
         --font-mono: "Cascadia Mono", "Consolas", "Courier New", monospace;
         --font-modern: "Bahnschrift", "Candara", "Trebuchet MS", sans-serif;
         --font-classic: "Rockwell", "Constantia", "Georgia", serif;
         --font-elegant: "Garamond", "Calisto MT", serif;
         --font-geometric: "Trebuchet MS", "Century Gothic", sans-serif;
         --font-tech: "Courier New", "Monaco", monospace;
         --font-serif: "Georgia", "Times New Roman", serif;
         --font-sans: "Verdana", "Arial", sans-serif;
         --font-typewriter: "Courier New", "Courier", monospace;
         --font-handwriting: "Segoe Print", "Comic Sans MS", cursive;
         --font-futuristic: "Segoe UI", "Tahoma", sans-serif;
         --font-minimal: "Helvetica", "Arial", sans-serif;
         --font-bold: "Impact", "Arial Black", sans-serif;
         --font-soft: "Trebuchet MS", "Lucida Sans", sans-serif;
         --font-corporate: "Calibri", "Segoe UI", sans-serif;
         --font-artistic: "Palatino Linotype", "Palatino", serif;
         --font-monospace: "Consolas", "Courier New", monospace;
         --font-script: "Georgia", "Garamond", serif;
         --font-modern-sans: "Tahoma", "Verdana", sans-serif;
         --font-classic-serif: "Times New Roman", "Georgia", serif;
         --font-code: "Cascadia Code", "Source Code Pro", monospace;
         --font-display-serif: "Didot", "Bodoni MT", serif;
         --font-humanist: "Segoe UI", "Roboto", sans-serif;
         --font-retro: "Courier New", "Courier", monospace;
       }
      * { box-sizing: border-box; }
      html, body {
        width: 100%;
        height: 100%;
        overflow: hidden;
      }
      body {
        margin: 0;
        font-family: var(--font-body);
        background: {{ background_style|safe }};
        color: var(--text);
        padding: 0;
        display: flex;
      }
      body.font-modern {
         font-family: var(--font-modern);
       }
       body.font-classic {
         font-family: var(--font-classic);
       }
       body.font-mono {
         font-family: var(--font-mono);
       }
       body.font-elegant {
         font-family: var(--font-elegant);
       }
       body.font-geometric {
         font-family: var(--font-geometric);
       }
       body.font-tech {
         font-family: var(--font-tech);
       }
       body.font-serif {
         font-family: var(--font-serif);
       }
       body.font-sans {
         font-family: var(--font-sans);
       }
       body.font-typewriter {
         font-family: var(--font-typewriter);
       }
       body.font-handwriting {
         font-family: var(--font-handwriting);
       }
       body.font-futuristic {
         font-family: var(--font-futuristic);
       }
       body.font-minimal {
         font-family: var(--font-minimal);
       }
       body.font-bold {
         font-family: var(--font-bold);
         font-weight: 700;
       }
       body.font-soft {
         font-family: var(--font-soft);
       }
       body.font-corporate {
         font-family: var(--font-corporate);
       }
       body.font-artistic {
         font-family: var(--font-artistic);
       }
       body.font-monospace {
         font-family: var(--font-monospace);
       }
       body.font-script {
         font-family: var(--font-script);
       }
       body.font-modern-sans {
         font-family: var(--font-modern-sans);
       }
       body.font-classic-serif {
         font-family: var(--font-classic-serif);
       }
       body.font-code {
         font-family: var(--font-code);
       }
       body.font-display-serif {
         font-family: var(--font-display-serif);
       }
       body.font-humanist {
         font-family: var(--font-humanist);
       }
       body.font-retro {
         font-family: var(--font-retro);
       }
      .shell {
        width: 100%;
        height: 100%;
        margin: 0;
        background: var(--panel);
        border-radius: 0;
        box-shadow: none;
        padding: 0;
        display: grid;
        grid-template-columns: 240px 1fr;
        overflow: hidden;
        transition: none;
      }
      .shell:hover {
        box-shadow: none;
      }
      .nav-wrap {
        background: linear-gradient(180deg, #1a2a3a 0%, #0f1f2f 100%);
        border-right: 1px solid rgba(255,255,255,0.1);
        padding: 18px 16px;
        display: flex;
        flex-direction: column;
        gap: 16px;
        position: sticky;
        top: 0;
        height: 100vh;
        overflow-y: auto;
        z-index: 20;
      }
      .nav-content {
        flex: 1;
        display: flex;
        flex-direction: column;
        gap: 16px;
        overflow-y: auto;
      }
      .nav-footer {
        display: flex;
        flex-direction: column;
        gap: 8px;
        padding-top: 12px;
        border-top: 1px solid rgba(255,255,255,0.1);
        margin-top: auto;
      }
      .nav-footer .btn {
        width: 100%;
        justify-content: flex-start;
        padding: 10px 12px;
        border-radius: 6px;
        font-size: 11px;
        gap: 8px;
        display: flex;
        align-items: center;
        border: none;
        cursor: pointer;
        text-decoration: none;
        text-transform: none;
        letter-spacing: 0;
        box-shadow: none;
        transition: all 150ms ease;
      }
      .nav-footer .btn-primary {
        background: rgba(10,111,134,0.2);
        color: #a8c5d1;
        border: 1px solid rgba(10,111,134,0.3);
      }
      .nav-footer .btn-primary:hover {
        background: rgba(10,111,134,0.35);
        color: #fff;
        animation: rgbGlow 2s ease-in-out infinite;
      }
      .nav-footer .btn-ghost {
        background: rgba(10,111,134,0.15);
        color: #a8c5d1;
        border: 1px solid rgba(10,111,134,0.2);
      }
      .nav-footer .btn-ghost:hover {
        background: rgba(10,111,134,0.3);
        color: #fff;
        animation: rgbGlow 2s ease-in-out infinite;
      }
      .nav-footer .btn-danger {
        background: linear-gradient(135deg, #d72638, #ff5a66);
        color: #fff;
        border: none;
      }
      .nav-footer .btn-danger:hover {
        transform: translateY(-1px);
        animation: rgbGlow 2s ease-in-out infinite;
      }
      .emergency-button-container {
        display: flex;
        gap: 6px;
        margin-bottom: 8px;
      }
      .emergency-button-container .btn {
        flex: 1;
        padding: 10px 8px;
        font-size: 11px;
        font-weight: 700;
        border-radius: 6px;
        border: none;
        cursor: pointer;
        transition: all 150ms ease;
      }
      .btn-emergency-stop {
        background: linear-gradient(135deg, #d72638, #ff5a66);
        color: white;
        text-transform: uppercase;
        letter-spacing: 0.5px;
      }
      .btn-emergency-stop:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 16px rgba(215, 38, 56, 0.4);
      }
      .btn-emergency-start {
        background: linear-gradient(135deg, #28a745, #34c759);
        color: white;
        text-transform: uppercase;
        letter-spacing: 0.5px;
      }
      .btn-emergency-start:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 16px rgba(40, 167, 69, 0.4);
      }
      .nav-footer .icon {
        width: 16px;
        text-align: center;
        flex-shrink: 0;
      }
      .nav-wrap::before,
      .nav-wrap::after {
        display: none;
      }
      .nav-head {
        display: flex;
        flex-direction: column;
        gap: 8px;
        margin-bottom: 8px;
        padding-bottom: 12px;
        border-bottom: 1px solid rgba(255,255,255,0.1);
      }
      .nav-title {
        font-size: 13px;
        font-weight: 800;
        letter-spacing: 0.5px;
        text-transform: uppercase;
        color: #7fa3b3;
        font-family: var(--font-display);
      }
      .nav-subtitle {
        font-size: 11px;
        color: #5a7a8a;
        font-weight: 600;
        margin-top: 0;
      }
      .nav-badge {
        padding: 6px 10px;
        border-radius: 6px;
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 0.3px;
        background: rgba(10,111,134,0.2);
        color: #7fa3b3;
        border: 1px solid rgba(10,111,134,0.3);
        text-align: center;
      }
      .nav {
        display: flex;
        flex-direction: column;
        gap: 8px;
        position: relative;
      }
      .nav-item {
        position: relative;
      }
      .nav-link {
        display: flex;
        align-items: center;
        padding: 12px;
        gap: 12px;
        border-radius: 6px;
        text-decoration: none;
        color: #a8c5d1;
        font-weight: 600;
        font-size: 13px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        cursor: pointer;
        background: rgba(10,111,134,0.08);
        border: 1px solid rgba(10,111,134,0.15);
        transition: all 200ms ease;
        position: relative;
        overflow: hidden;
      }
      .nav-link::before {
        content: '';
        position: absolute;
        inset: 0;
        background: radial-gradient(circle at 50% 50%, rgba(255,255,255,0.1), transparent);
        opacity: 0;
        transition: opacity 300ms ease;
        pointer-events: none;
        border-radius: 6px;
      }
      .nav-link:hover {
        background: rgba(10,111,134,0.3);
        color: #fff;
        border-color: rgba(10,111,134,0.5);
        transform: translateY(-2px);
        box-shadow: 0 6px 20px rgba(10,111,134,0.25);
        animation: hoverPulse 1.8s ease-in-out infinite;
      }
      .nav-link:hover::before {
        opacity: 1;
      }

      .sub-nav {
        display: none;
        flex-direction: column;
        gap: 4px;
        margin-top: 4px;
        padding-left: 8px;
        border-left: 2px solid rgba(10,111,134,0.3);
        margin-left: 6px;
      }
      .nav-item:hover .sub-nav,
      .nav-item.show-subs .sub-nav {
        display: flex;
      }
      .sub-nav-link {
        display: flex;
        align-items: center;
        padding: 8px 10px;
        gap: 10px;
        border-radius: 4px;
        text-decoration: none;
        color: #7fa3b3;
        font-weight: 500;
        font-size: 12px;
        text-transform: capitalize;
        cursor: pointer;
        background: transparent;
        border: none;
        transition: all 150ms ease;
        position: relative;
        overflow: hidden;
      }
      .sub-nav-link::before {
        content: '';
        position: absolute;
        left: 0;
        top: 0;
        width: 3px;
        height: 100%;
        background: #0a9fb5;
        transform: scaleY(0);
        transform-origin: top;
        transition: transform 200ms ease;
        border-radius: 0 2px 2px 0;
      }
      .sub-nav-link:hover {
        color: #fff;
        background: rgba(10,111,134,0.15);
        padding-left: 14px;
        box-shadow: inset 4px 0 12px rgba(10,159,181,0.2);
      }
      .sub-nav-link:hover::before {
        transform: scaleY(1);
      }
      .sub-nav-link.active {
        color: #0a9fb5;
        font-weight: 600;
        background: rgba(10,111,134,0.1);
      }
      .nav-link .icon {
        font-size: 14px;
        flex-shrink: 0;
      }
      .nav-item.draggable-enabled {
        cursor: grab;
      }
      .nav-item.draggable-enabled:active {
        cursor: grabbing;
      }
      .nav-item.dragging {
        opacity: 0.5;
        transform: scale(0.95);
      }
      .nav-item.drag-over {
        border-top: 3px solid #0a9fb5;
        padding-top: 9px;
      }
      .nav-item.drag-over-bottom {
        border-bottom: 3px solid #0a9fb5;
        padding-bottom: 9px;
      }
      @keyframes rgbGlow {
        0% {
          box-shadow: 0 0 10px rgba(10, 159, 181, 0.6), inset 0 0 10px rgba(10, 159, 181, 0.2);
        }
        33% {
          box-shadow: 0 0 15px rgba(74, 222, 128, 0.5), inset 0 0 10px rgba(74, 222, 128, 0.15);
        }
        66% {
          box-shadow: 0 0 15px rgba(168, 85, 247, 0.5), inset 0 0 10px rgba(168, 85, 247, 0.15);
        }
        100% {
          box-shadow: 0 0 10px rgba(10, 159, 181, 0.6), inset 0 0 10px rgba(10, 159, 181, 0.2);
        }
      }
      @keyframes hoverPulse {
        0%, 100% {
          box-shadow: 0 6px 20px rgba(10,111,134,0.25);
        }
        50% {
          box-shadow: 0 6px 30px rgba(10,159,181,0.4);
        }
      }
      @keyframes navHoverGlow {
        0% {
          border-color: rgba(10,159,181,0.5);
        }
        50% {
          border-color: rgba(10,159,181,0.8);
        }
        100% {
          border-color: rgba(10,159,181,0.5);
        }
      }
      .nav-link.active {
        background: linear-gradient(135deg, #0a9fb5, #0a6f86);
        color: #fff;
        border-color: rgba(255,255,255,0.2);
        box-shadow: 0 6px 20px rgba(10,159,181,0.4), inset 0 0 10px rgba(10,159,181,0.2);
        animation: activeGlow 2s ease-in-out infinite;
      }
      @keyframes activeGlow {
        0%, 100% {
          box-shadow: 0 6px 20px rgba(10,159,181,0.4), inset 0 0 10px rgba(10,159,181,0.2);
        }
        50% {
          box-shadow: 0 8px 28px rgba(10,159,181,0.6), inset 0 0 14px rgba(10,159,181,0.3);
        }
      }
      @keyframes pulse {
        0%, 100% {
          r: 1.5;
          opacity: 0.9;
        }
        50% {
          r: 2.5;
          opacity: 0.3;
        }
      }
      .nav-stack {
        display: flex;
        flex-direction: column;
        gap: 8px;
      }
      .subnav {
        display: flex;
        flex-direction: column;
        gap: 6px;
        margin-top: 6px;
      }
      .subnav a {
        background: rgba(255,255,255,0.05);
        color: #7fa3b3;
        padding: 8px 10px;
        border-radius: 4px;
        font-weight: 600;
        font-size: 11px;
        text-decoration: none;
        letter-spacing: 0.2px;
        border: 1px solid rgba(255,255,255,0.05);
        transition: all 120ms ease;
        margin-left: 8px;
        border-left: 2px solid transparent;
      }
      .subnav a:hover {
        background: rgba(255,255,255,0.1);
        color: #a8c5d1;
        animation: rgbGlow 2s ease-in-out infinite;
      }
      .subnav a.active {
        background: rgba(10,111,134,0.2);
        color: #fff;
        border-left-color: #0a9fb5;
      }
      .header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
        padding: 18px 24px;
        background: #ffffff;
        border-bottom: 1px solid #e8f0f5;
        flex-shrink: 0;
      }
      .title {
        font-size: 20px;
        font-weight: 700;
        font-family: var(--font-display);
      }
      .toolbar {
        display: flex;
        align-items: center;
        gap: 8px;
      }
      .content-layout {
        display: flex;
        flex-direction: column;
        gap: 0;
        padding: 0;
        height: 100%;
        width: 100%;
        overflow: hidden;
      }
      .status-panel {
        flex-shrink: 0;
        padding: 18px 22px 16px;
        background: var(--panel);
        border-bottom: 1px solid var(--border);
        position: sticky;
        top: 0;
        z-index: 15;
        box-shadow: 0 2px 8px rgba(15,23,42,0.05);
      }
      .scripts-panel {
        flex: 1;
        overflow-y: auto;
        padding: 16px 22px 16px;
        display: flex;
        flex-direction: column;
      }
      .scripts-panel table {
        flex: 1;
      }
      .footer-panel {
        flex-shrink: 0;
        background: var(--panel);
        border-top: 2px solid #dc3545;
        padding: 12px 22px;
        z-index: 15;
        box-shadow: 0 -2px 8px rgba(15,23,42,0.05);
      }
      .sidebar {
        display: flex;
        flex-direction: column;
        gap: 10px;
        position: sticky;
        top: 16px;
      }
      .sidebar .btn {
        width: 100%;
        justify-content: center;
      }
      .sidebar .btn-icon {
        padding: 8px 10px;
        border-radius: 10px;
        font-size: 14px;
        text-transform: none;
        letter-spacing: 0;
        justify-content: flex-start;
        gap: 8px;
      }
      .sidebar .icon {
        width: 18px;
        text-align: center;
      }
      .drawer {
        position: fixed;
        top: 0;
        right: 0;
        height: 100%;
        width: min(420px, 92vw);
        background: #ffffff;
        box-shadow: -16px 0 32px rgba(15,23,42,0.2);
        border-left: 1px solid rgba(13,24,40,0.12);
        transform: translateX(100%);
        transition: transform 200ms ease;
        z-index: 60;
        display: flex;
        flex-direction: column;
      }
      .drawer.open {
        transform: translateX(0);
      }
      .drawer-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 12px 14px;
        border-bottom: 1px solid var(--border);
        font-weight: 700;
        background: #f6f9fc;
      }
      .drawer-body {
        flex: 1;
      }
      .drawer-body iframe {
        width: 100%;
        height: 100%;
        border: 0;
      }
      .overlay {
        position: fixed;
        inset: 0;
        background: rgba(10,20,30,0.4);
        opacity: 0;
        pointer-events: none;
        transition: opacity 150ms ease;
        z-index: 55;
      }
      .overlay.open {
        opacity: 1;
        pointer-events: auto;
      }
      @media (max-width: 1024px) {
        .shell {
          grid-template-columns: 1fr;
        }
        .nav-wrap {
          height: auto;
          position: static;
          border-right: none;
          border-bottom: 1px solid rgba(255,255,255,0.1);
          flex-direction: row;
          flex-wrap: wrap;
          align-items: flex-start;
          gap: 20px;
          padding: 12px;
        }
        .nav-content {
          display: flex;
          flex-direction: row;
          flex-wrap: wrap;
          gap: 12px;
          flex: 1;
        }
        .nav-head {
          border-bottom: none;
          padding-bottom: 0;
          flex: 1 1 auto;
        }
        .nav {
          flex-direction: row;
          flex-wrap: wrap;
          gap: 8px;
        }
        .nav-footer {
          display: flex;
          flex-direction: row;
          flex-wrap: wrap;
          gap: 6px;
          border-top: none;
          padding-top: 0;
          margin-top: 0;
          flex: 1 1 100%;
          width: 100%;
        }
        .nav-footer .btn {
          flex: 1 1 auto;
          min-width: 100px;
        }
        .content-layout {
          grid-template-columns: 1fr;
        }
      }
      @media (max-width: 640px) {
        html, body {
          height: auto;
          overflow: auto;
        }
        body {
          padding: 0;
          display: block;
          background: #f5f7fa;
        }
        .shell {
          padding: 0;
          border-radius: 0;
          grid-template-columns: 1fr;
          grid-template-rows: auto auto auto;
          height: auto;
          overflow: visible;
          background: #ffffff;
          box-shadow: none;
        }
        .nav-wrap {
          position: static;
          top: auto;
          padding: 0;
          margin: 0;
          margin-bottom: 12px;
          height: auto;
          max-height: none;
          overflow: visible;
          border-right: none;
          border-bottom: none;
          background: linear-gradient(180deg, #1a2a3a 0%, #0f1f2f 100%);
          flex-direction: column;
          flex-wrap: nowrap;
          gap: 0;
          border-radius: 0;
          display: flex;
        }
        .nav-head {
          flex-direction: column;
          align-items: flex-start;
          border-bottom: 1px solid rgba(255,255,255,0.1);
          padding: 16px 16px;
          flex-shrink: 0;
          margin-bottom: 0;
          background: linear-gradient(180deg, #1a3a4a, #1a2a3a);
        }
        .nav-title {
          font-size: 12px;
          font-weight: 700;
          letter-spacing: 0.5px;
          text-transform: uppercase;
          color: #7fa3b3;
          margin-bottom: 8px;
        }
        .nav-subtitle {
          font-size: 11px;
          color: #a8c5d1;
          font-weight: 500;
          margin-top: 0;
        }
        .nav-badge {
          width: 100%;
          text-align: center;
          padding: 8px 12px;
          margin-top: 8px;
          border-radius: 6px;
          background: linear-gradient(135deg, #0a9fb5, #0a6f86);
          color: #fff;
          font-size: 11px;
          font-weight: 600;
          box-shadow: 0 2px 8px rgba(10, 159, 181, 0.3);
        }
        .nav-content {
          flex: 1;
          display: flex;
          flex-direction: column;
          gap: 0;
          overflow: visible;
          max-height: none;
          padding: 0;
          background: linear-gradient(180deg, rgba(26, 42, 58, 0.5), transparent);
        }
        .nav {
          gap: 0;
          flex-direction: column;
          flex-wrap: nowrap;
        }
        .nav-link {
          font-size: 13px;
          font-weight: 500;
          padding: 14px 16px;
          flex: none;
          width: 100%;
          border-radius: 0;
          text-align: left;
          display: flex;
          flex-direction: row;
          align-items: center;
          justify-content: space-between;
          gap: 12px;
          background: transparent;
          border: none;
          border-left: 4px solid transparent;
          color: #a8c5d1;
          transition: all 200ms cubic-bezier(0.4, 0, 0.2, 1);
          -webkit-user-select: none;
          user-select: none;
          -webkit-touch-callout: none;
          position: relative;
          cursor: pointer;
          overflow: hidden;
          min-height: 48px;
        }
        .nav-link::before {
          content: '';
          position: absolute;
          left: 0;
          top: 0;
          bottom: 0;
          width: 4px;
          background: transparent;
          transition: all 200ms ease;
          pointer-events: none;
        }
        .nav-link::after {
          content: '';
          position: absolute;
          inset: 0;
          background: linear-gradient(90deg, rgba(10,159,181,0.08), transparent);
          opacity: 0;
          transition: opacity 200ms ease;
          pointer-events: none;
        }
        .nav-link:hover {
          background: rgba(10,159,181,0.1);
          color: #fff;
          border-left-color: #0a9fb5;
        }
        .nav-link:hover::before {
          background: #0a9fb5;
        }
        .nav-link:hover::after {
          opacity: 1;
        }
        .nav-link:active {
          background: rgba(10,159,181,0.15);
        }
        .nav-link.active {
          background: linear-gradient(90deg, rgba(10,159,181,0.2), transparent);
          color: #fff;
          border-left-color: #0a9fb5;
          font-weight: 600;
        }
        .nav-link.active::before {
          background: #0a9fb5;
        }
        .nav-link .icon {
          font-size: 18px;
          width: 24px;
          text-align: center;
          flex-shrink: 0;
        }
        @keyframes navGlow {
          0%, 100% {
            box-shadow: 0 0 16px rgba(10,159,181,0.6), inset 0 0 10px rgba(10,159,181,0.25);
          }
          50% {
            box-shadow: 0 0 24px rgba(10,159,181,0.9), inset 0 0 14px rgba(10,159,181,0.4);
          }
        }
        @keyframes livePulse {
          0%, 100% {
            box-shadow: 0 0 6px #4ade80, inset 0 0 3px rgba(255,255,255,0.5);
            transform: scale(1);
          }
          50% {
            box-shadow: 0 0 12px #4ade80, inset 0 0 5px rgba(255,255,255,0.7);
            transform: scale(1.1);
          }
        }
        .nav-link .icon {
          font-size: 16px;
          flex-shrink: 0;
          width: 20px;
          text-align: center;
        }
        .nav-stack {
          width: 100%;
          padding: 0;
          margin: 0;
          display: flex;
          flex-direction: column;
          gap: 6px;
        }
        .nav-footer {
          display: flex;
          flex-direction: column;
          gap: 6px;
          padding: 12px;
          border-top: 1px solid rgba(255,255,255,0.1);
          margin-top: auto;
          flex-shrink: 0;
          width: 100%;
          background: linear-gradient(180deg, #0f1f2f 0%, #0a1520 100%);
        }
        .nav-footer .btn {
          width: 100%;
          padding: 10px 12px;
          font-size: 11px;
          font-weight: 600;
          justify-content: flex-start;
          border-radius: 6px;
          text-align: left;
          border: none;
          min-height: auto;
          display: flex;
          align-items: center;
          gap: 10px;
          background: rgba(10,111,134,0.12);
          color: #a8c5d1;
          transition: all 150ms ease;
          position: relative;
          overflow: hidden;
        }
        .nav-footer .btn::before {
          content: '';
          position: absolute;
          inset: 0;
          background: linear-gradient(90deg, rgba(10,159,181,0.15), transparent);
          opacity: 0;
          transition: opacity 150ms ease;
          pointer-events: none;
          border-radius: 6px;
        }
        .nav-footer .btn:hover {
          background: rgba(10,159,181,0.2);
          color: #fff;
          transform: translateX(2px);
        }
        .nav-footer .btn:hover::before {
          opacity: 1;
        }
        .nav-footer .btn-primary {
          background: rgba(10,111,134,0.15);
          border: 1px solid rgba(10,111,134,0.3);
        }
        .nav-footer .btn-primary:hover {
          background: rgba(10,159,181,0.25);
          border-color: rgba(10,159,181,0.5);
          color: #fff;
        }
        .nav-footer .btn-danger {
          background: linear-gradient(135deg, #d72638, #ff5a66);
          color: #fff;
          border: none;
          font-weight: 700;
        }
        .nav-footer .btn-danger:hover {
          transform: translateX(2px);
          box-shadow: 0 4px 12px rgba(215, 38, 56, 0.4);
        }
        .nav-footer .icon {
          font-size: 14px;
          width: 16px;
          text-align: center;
          flex-shrink: 0;
        }
        .content-layout {
          display: flex;
          flex-direction: column;
          gap: 0;
          padding: 0;
          height: auto;
          width: 100%;
          overflow: visible;
        }
        .status-panel {
          padding: 16px;
          padding-bottom: 12px;
          position: static;
          z-index: auto;
          box-shadow: none;
          border-bottom: 1px solid #e0e0e0;
          flex-shrink: 0;
          background: #ffffff;
          margin: 0;
        }
        .scripts-panel {
          flex: none;
          overflow-y: visible;
          padding: 12px 0;
          min-height: auto;
          height: auto;
          display: block;
          background: #ffffff;
        }
        .scripts-panel table {
          flex: none;
          width: 100%;
        }
        .footer-panel {
          flex-shrink: 0;
          padding: 14px 16px;
          background: #ffffff;
          border-top: 2px solid #dc3545;
          border-radius: 0 0 8px 8px;
        }
        .stats {
          flex-direction: column;
          align-items: flex-start;
          gap: 10px;
          margin-bottom: 0;
          border: none;
          background: transparent;
          padding: 0;
        }
        .stats strong {
          font-size: 12px;
          color: #5c6d7e;
        }
        .filters {
          width: 100%;
          justify-content: flex-start;
          flex-wrap: wrap;
          gap: 8px;
          font-size: 11px;
          align-items: center;
        }
        .filters span {
          font-size: 11px;
        }
        .filters select {
          width: auto;
          padding: 6px 8px;
          font-size: 11px;
          border-radius: 4px;
          border: 1px solid var(--border);
        }
        .script-search {
          max-width: 100%;
          width: 100%;
          padding: 12px 16px;
          font-size: 13px;
          border: none;
          border-bottom: 1px solid #e0e0e0;
          min-height: 44px;
        }
        table,
        thead,
        tbody,
        th,
        td,
        tr {
          display: block;
        }
        thead {
          display: none;
        }
        tbody tr {
          border: none;
          border-bottom: 1px solid #e0e0e0;
          border-radius: 0;
          padding: 14px 16px;
          margin: 0;
          background: #ffffff;
          box-shadow: none;
        }
        tbody tr:hover {
          background: #f8f9fa;
        }
        tbody td {
          border-bottom: none;
          padding: 6px 0;
          display: flex;
          justify-content: space-between;
          align-items: center;
        }
        tbody td::before {
          content: attr(data-label);
          font-weight: 600;
          display: inline-block;
          min-width: 70px;
          font-size: 11px;
          color: #5c6d7e;
        }
        .status-pill {
          font-size: 10px;
          padding: 4px 8px;
          border-radius: 4px;
          font-weight: 600;
        }
        .status-pill.running {
          background: #d4edda;
          color: #155724;
        }
        .status-pill.stopped {
          background: #f8d7da;
          color: #721c24;
        }
        .pid-pill {
          font-size: 10px;
          background: #e7f3ff;
          color: #0a6f86;
          padding: 4px 8px;
          border-radius: 4px;
          font-weight: 600;
        }
        .actions-cell {
          width: auto;
          padding-top: 8px;
        }
        .actions-cell::before {
          display: none;
        }
        .action-stack {
          width: 100%;
          display: flex;
          flex-direction: column;
          gap: 6px;
        }
        .action-btn {
          width: 100%;
          padding: 8px 12px;
          font-size: 10px;
          border-radius: 4px;
          border: none;
          cursor: pointer;
          transition: all 150ms ease;
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 4px;
        }
        .action-start {
          background: #28a745;
          color: #fff;
        }
        .action-stop {
          background: #dc3545;
          color: #fff;
        }
        .action-edit {
          background: #0a6f86;
          color: #fff;
        }
        .action-log {
          background: #6c757d;
          color: #fff;
        }
        .bulk-actions {
          flex-direction: column;
          gap: 8px;
        }
        .bulk-actions .btn {
          width: 100%;
          padding: 10px 12px;
          font-size: 11px;
          border-radius: 4px;
        }
        .sidebar {
          gap: 8px;
          display: none;
        }
        .sidebar .btn {
          flex: 1 1 auto;
        }
      }
      .toolbar .btn-ghost {
        background: #ffffff;
        color: var(--brand);
        border: 1px solid rgba(10,111,134,0.25);
      }
      .btn {
        border: none;
        border-radius: 999px;
        padding: 7px 14px;
        font-weight: 700;
        cursor: pointer;
        text-decoration: none;
        text-transform: uppercase;
        letter-spacing: 0.4px;
        font-size: 11px;
        box-shadow: 0 8px 16px rgba(13,24,40,0.18);
        transition: transform 120ms ease, box-shadow 120ms ease, filter 120ms ease;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        gap: 6px;
      }
      .btn:hover {
        transform: translateY(-1px);
        box-shadow: 0 10px 18px rgba(13,24,40,0.24);
        filter: brightness(1.02);
        animation: rgbGlow 2s ease-in-out infinite;
      }
      .btn-primary {
        background: linear-gradient(135deg, #0a6f86, #0e94ac);
        color: #fff;
      }
      .btn-danger {
        background: linear-gradient(135deg, #d72638, #ff5a66);
        color: #fff;
      }
      .banner {
        background: #12a0b4;
        color: #fff;
        text-align: center;
        padding: 8px;
        border-radius: 6px;
        margin: 12px 0 16px;
        font-weight: 600;
      }
      .stats {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 10px;
        border: 1px solid var(--border);
        border-radius: 6px;
        padding: 10px 12px;
        margin-bottom: 12px;
        background: #f8fafc;
      }
      .stats strong { margin-right: 12px; }
      .filters {
        display: flex;
        align-items: center;
        gap: 10px;
        padding: 0;
        margin: 0;
        font-size: 13px;
        font-weight: 600;
        color: var(--muted);
      }
      .filters span {
        white-space: nowrap;
      }
      .filters select {
        min-width: 120px;
      }
      .script-search {
        flex: 1;
        max-width: 300px;
        padding: 9px 12px;
        border: 2px solid rgba(10,111,134,0.15);
        border-radius: 8px;
        font-size: 13px;
        font-weight: 500;
        background: #ffffff;
        color: #0a3642;
        transition: all 150ms ease;
      }
      .script-search:focus {
        outline: none;
        border-color: #0a9fb5;
        background: #f0fafb;
        box-shadow: 0 0 0 3px rgba(10,159,181,0.1);
      }
      .script-search::placeholder {
        color: #a0aec0;
      }
      .status-message {
        margin-top: 8px;
        font-size: 12px;
        color: var(--muted);
      }
      .pid-pill {
        display: inline-flex;
        align-items: center;
        padding: 6px 12px;
        border-radius: 8px;
        font-size: 12px;
        font-weight: 700;
        background: linear-gradient(135deg, #e0f2fe, #cffafe);
        color: #0369a1;
        box-shadow: 0 2px 8px rgba(6, 182, 212, 0.1);
      }
      .bulk-actions {
        display: flex;
        gap: 10px;
        justify-content: center;
        margin-top: 12px;
      }
      .footer-bar {
        position: relative;
        background: transparent;
        border-top: none;
        padding: 0;
        margin-top: 0;
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 16px;
        flex-shrink: 0;
        z-index: 10;
      }
      .footer-bar .bulk-actions {
        margin-top: 0;
        margin-bottom: 0;
      }
      .footer-bar .note {
        margin-top: 0;
        font-size: 12px;
        color: var(--muted);
      }
      .btn-secondary {
        background: #5b6470;
        color: #fff;
      }
      .filters select {
        padding: 6px 10px;
        border-radius: 6px;
        border: 1px solid var(--border);
      }
      .search {
        width: 100%;
        border: 1px solid var(--border);
        border-radius: 6px;
        padding: 10px 12px;
        margin-bottom: 16px;
      }
      .add-row {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        align-items: center;
        margin-bottom: 16px;
      }
      .add-row input[type="text"] {
        flex: 1 1 260px;
        padding: 9px 12px;
        border-radius: 6px;
        border: 1px solid var(--border);
      }
      .add-row input[type="file"] {
        border: 1px solid var(--border);
        border-radius: 6px;
        padding: 6px;
        background: #fff;
      }
      table {
        width: 100%;
        border-collapse: separate;
        border-spacing: 0;
        font-size: 14px;
        flex: 1;
        display: flex;
        flex-direction: column;
      }
      thead {
        display: none;
      }
      tbody {
        display: flex;
        flex-direction: column;
        gap: 12px;
        flex: 1;
        overflow-y: auto;
        padding-right: 6px;
      }
      tbody::-webkit-scrollbar {
        width: 8px;
      }
      tbody::-webkit-scrollbar-track {
        background: transparent;
      }
      tbody::-webkit-scrollbar-thumb {
        background: rgba(10,111,134,0.2);
        border-radius: 4px;
      }
      tbody::-webkit-scrollbar-thumb:hover {
        background: rgba(10,111,134,0.4);
      }
      @keyframes rowHoverGlow {
        0%, 100% {
          box-shadow: 0 8px 24px rgba(10, 111, 134, 0.16), 0 2px 8px rgba(10, 111, 134, 0.08);
        }
        50% {
          box-shadow: 0 10px 32px rgba(10, 159, 181, 0.24), 0 4px 12px rgba(10, 159, 181, 0.12);
        }
      }
      @keyframes btnPulse {
        0%, 100% {
          box-shadow: 0 6px 18px rgba(15,23,42,0.2);
        }
        50% {
          box-shadow: 0 8px 24px rgba(15,23,42,0.28);
        }
      }
      tbody tr {
        transition: all 200ms ease;
        background: var(--panel);
        border: 1px solid var(--border);
        border-radius: 12px;
        padding: 16px 18px;
        display: grid;
        grid-template-columns: 2fr 1.5fr 1.5fr auto;
        gap: 16px;
        align-items: center;
        box-shadow: 0 2px 8px rgba(15,23,42,0.05);
        position: relative;
        overflow: hidden;
        flex-shrink: 0;
      }
      tbody tr::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        height: 3px;
        background: linear-gradient(90deg, #0a6f86, #10a1b5);
        opacity: 0;
        transition: opacity 200ms ease;
      }
      tbody tr::after {
        content: '';
        position: absolute;
        inset: 0;
        background: radial-gradient(ellipse at center, rgba(10,159,181,0.05), transparent);
        opacity: 0;
        transition: opacity 300ms ease;
        pointer-events: none;
        border-radius: 12px;
      }
      tbody tr:hover {
        background: #f8fbfd;
        box-shadow: 0 8px 24px rgba(10, 111, 134, 0.16), 0 2px 8px rgba(10, 111, 134, 0.08);
        border-color: rgba(10,111,134,0.35);
        transform: translateY(-3px);
        animation: rowHoverGlow 1.6s ease-in-out infinite;
      }
      tbody tr:hover::before {
        opacity: 1;
      }
      tbody tr:hover::after {
        opacity: 1;
      }
      tbody td {
        padding: 0;
        border: none;
        vertical-align: middle;
        transition: color 200ms ease;
      }
      tbody tr:hover td {
        color: inherit;
      }
      @media (max-width: 980px) {
        tbody tr {
          grid-template-columns: 1fr;
          gap: 12px;
        }
      }
      .status-pill {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        padding: 8px 14px;
        border-radius: 8px;
        font-weight: 700;
        color: #fff;
        min-width: 120px;
        justify-content: center;
        transition: all 150ms ease;
        font-size: 12px;
        box-shadow: 0 2px 8px rgba(15,23,42,0.1);
        position: relative;
        overflow: hidden;
      }
      .status-pill::before {
        content: '';
        position: absolute;
        inset: 0;
        background: radial-gradient(circle at center, rgba(255,255,255,0.25), transparent);
        opacity: 0;
        transition: opacity 300ms ease;
        pointer-events: none;
      }
      .status-pill:hover {
        transform: translateY(-2px) scale(1.03);
        box-shadow: 0 6px 16px rgba(15,23,42,0.18);
        animation: statusPulse 1.5s ease-in-out infinite;
      }
      .status-pill:hover::before {
        opacity: 1;
      }
      @keyframes statusPulse {
        0%, 100% {
          box-shadow: 0 6px 16px rgba(15,23,42,0.18);
        }
        50% {
          box-shadow: 0 8px 22px rgba(15,23,42,0.25);
        }
      }
      .status-pill.running {
        background: linear-gradient(135deg, #28a745, #20c997);
      }
      .status-pill.stopped {
        background: linear-gradient(135deg, #dc3545, #e74c63);
      }
      .action-btn {
        border: none;
        border-radius: 8px;
        padding: 8px 14px;
        color: #fff;
        font-weight: 700;
        cursor: pointer;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        min-width: 90px;
        font-size: 12px;
        transition: all 150ms ease;
        box-shadow: 0 2px 8px rgba(15,23,42,0.1);
        position: relative;
        overflow: hidden;
      }
      .action-btn::before {
        content: '';
        position: absolute;
        inset: 0;
        background: radial-gradient(circle at center, rgba(255,255,255,0.2), transparent);
        opacity: 0;
        transition: opacity 300ms ease;
        pointer-events: none;
      }
      .action-btn:hover {
        transform: translateY(-2px) scale(1.02);
        box-shadow: 0 6px 18px rgba(15,23,42,0.2);
        animation: btnPulse 1.4s ease-in-out infinite;
      }
      .action-btn:hover::before {
        opacity: 1;
      }
      .action-start {
        background: linear-gradient(135deg, #28a745, #20c997);
      }
      .action-stop {
        background: linear-gradient(135deg, #dc3545, #e74c63);
      }
      .action-log {
        background: linear-gradient(135deg, #0a6f86, #10a1b5);
        text-decoration: none;
        display: inline-flex;
        align-items: center;
      }
      .action-edit {
        background: linear-gradient(135deg, #64748b, #78849f);
        text-decoration: none;
        display: inline-flex;
        align-items: center;
      }
      .actions-cell {
        width: auto;
      }
      .action-stack {
        display: inline-flex;
        flex-direction: row;
        gap: 8px;
      }
      @media (max-width: 640px) {
        .action-stack {
          flex-direction: column;
        }
      }
      .action-stack form {
        margin: 0;
      }
      .script-name-cell {
        cursor: pointer;
        user-select: none;
        padding: 0;
        border-radius: 0;
        transition: color 200ms ease;
        font-weight: 600;
        color: var(--text);
      }
      .script-name-cell:hover {
        background-color: transparent;
        color: #0a6f86;
      }
      .script-name-cell.editing {
        padding: 0;
      }
      .script-name-input {
        width: 100%;
        padding: 8px;
        border: 2px solid #0a6f86;
        border-radius: 4px;
        font-size: 14px;
        font-weight: 600;
      }
      .note {
        color: var(--muted);
        margin-top: 10px;
        font-size: 12px;
      }
      .modal {
        position: fixed;
        inset: 0;
        background: rgba(10,20,30,0.65);
        display: none;
        align-items: center;
        justify-content: center;
        padding: 20px;
        z-index: 50;
        backdrop-filter: blur(4px);
      }
      .modal.open {
        display: flex;
      }
      .modal-card {
        width: 100%;
        max-width: 480px;
        background: linear-gradient(135deg, #ffffff 0%, #f8fafc 100%);
        border-radius: 20px;
        border: 2px solid rgba(10,111,134,0.2);
        box-shadow: 0 25px 50px rgba(10,20,30,0.35), 0 0 60px rgba(10,111,134,0.15);
        overflow: hidden;
      }
      .modal-header {
        padding: 20px 24px;
        font-weight: 800;
        font-size: 16px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        border-bottom: 2px solid rgba(10,111,134,0.1);
        background: linear-gradient(135deg, #0a9fb5 0%, #0a6f86 100%);
        color: #ffffff;
        letter-spacing: 0.5px;
      }
      .modal-header button {
        background: rgba(255,255,255,0.2);
        color: #fff;
        border: none;
        border-radius: 6px;
        width: 32px;
        height: 32px;
        font-size: 18px;
        cursor: pointer;
        display: flex;
        align-items: center;
        justify-content: center;
        transition: all 150ms ease;
      }
      .modal-header button:hover {
        background: rgba(255,255,255,0.35);
        transform: scale(1.05);
      }
      .modal-body {
        padding: 24px;
        display: grid;
        gap: 14px;
        font-size: 13px;
      }
      .modal-body > div {
        display: flex;
        flex-direction: column;
        gap: 6px;
      }
      .modal-body label {
        font-size: 12px;
        color: #0a3642;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.5px;
      }
      .modal-body input,
      .modal-body select {
        width: 100%;
        padding: 11px 14px;
        border-radius: 10px;
        border: 2px solid rgba(10,111,134,0.15);
        font-size: 13px;
        font-weight: 500;
        background: #ffffff;
        color: #0a3642;
        transition: all 150ms ease;
      }
      .modal-body input:focus,
      .modal-body select:focus {
        outline: none;
        border-color: #0a9fb5;
        background: #f0fafb;
        box-shadow: 0 0 0 3px rgba(10,159,181,0.1);
      }
      .modal-body input::placeholder {
        color: #a0aec0;
      }
      .modal-footer {
        padding: 16px 24px;
        display: flex;
        justify-content: flex-end;
        gap: 10px;
        border-top: 2px solid rgba(10,111,134,0.1);
        background: #f8fafc;
      }
      .btn-secondary {
        background: linear-gradient(135deg, #e8ecf1 0%, #dce4eb 100%);
        color: #0a3642;
        border: 2px solid rgba(10,111,134,0.18);
        padding: 11px 26px;
        border-radius: 8px;
        font-weight: 700;
        font-size: 12px;
        cursor: pointer;
        transition: all 200ms ease;
        text-transform: uppercase;
        letter-spacing: 0.6px;
        box-shadow: 0 2px 8px rgba(10,20,30,0.1);
        position: relative;
        overflow: hidden;
      }
      .btn-secondary::before {
        content: '';
        position: absolute;
        top: 0;
        left: -100%;
        width: 100%;
        height: 100%;
        background: rgba(255,255,255,0.25);
        transition: left 200ms ease;
        z-index: 0;
      }
      .btn-secondary:hover {
        background: linear-gradient(135deg, #d9e2e8 0%, #cdd7e1 100%);
        border-color: rgba(10,111,134,0.4);
        transform: translateY(-3px);
        box-shadow: 0 6px 16px rgba(10,20,30,0.15);
      }
      .btn-secondary:hover::before {
        left: 100%;
      }
      .btn-secondary:active {
        transform: translateY(-1px);
      }
      .modal-footer .btn-primary {
        background: linear-gradient(135deg, #0a9fb5 0%, #0a6f86 100%);
        color: #fff;
        border: none;
        padding: 10px 24px;
        border-radius: 8px;
        font-weight: 700;
        font-size: 12px;
        cursor: pointer;
        transition: all 180ms ease;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        box-shadow: 0 4px 12px rgba(10,159,181,0.2);
      }
      .modal-footer .btn-primary:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 16px rgba(10,159,181,0.3);
        background: linear-gradient(135deg, #0cbcc8 0%, #0a7d8f 100%);
      }
      .modal-footer .btn-primary:active {
        transform: translateY(0);
      }

      /* Emergency Modal Styling */
      .emergency-modal-card {
        width: 100%;
        max-width: 520px;
        background: #ffffff;
        border-radius: 24px;
        border: 3px solid #dc3545;
        box-shadow: 0 30px 60px rgba(220, 53, 69, 0.25), 0 0 80px rgba(220, 53, 69, 0.12);
        overflow: hidden;
        animation: emergencyPulse 0.6s cubic-bezier(0.34, 1.56, 0.64, 1);
      }
      @keyframes emergencyPulse {
        0% { transform: scale(0.95); opacity: 0; }
        100% { transform: scale(1); opacity: 1; }
      }
      .emergency-modal-header {
        padding: 24px 28px;
        background: linear-gradient(135deg, #d72638 0%, #ff5a66 100%);
        color: white;
        display: flex;
        justify-content: space-between;
        align-items: center;
        border-bottom: 3px solid rgba(255,255,255,0.1);
      }
      .emergency-title-wrapper {
        display: flex;
        align-items: center;
        gap: 12px;
      }
      .emergency-icon {
        font-size: 24px;
        animation: emergencyShake 0.8s ease-in-out infinite;
      }
      @keyframes emergencyShake {
        0%, 100% { transform: rotate(0deg); }
        25% { transform: rotate(-5deg); }
        75% { transform: rotate(5deg); }
      }
      .emergency-title {
        font-size: 16px;
        font-weight: 900;
        letter-spacing: 1.2px;
        text-transform: uppercase;
      }
      .emergency-close-btn {
        background: rgba(255,255,255,0.25);
        color: white;
        border: none;
        border-radius: 50%;
        width: 36px;
        height: 36px;
        font-size: 20px;
        cursor: pointer;
        display: flex;
        align-items: center;
        justify-content: center;
        transition: all 200ms ease;
        font-weight: bold;
      }
      .emergency-close-btn:hover {
        background: rgba(255,255,255,0.4);
        transform: scale(1.1) rotate(90deg);
      }
      .emergency-modal-body {
        padding: 28px;
        display: flex;
        flex-direction: column;
        gap: 22px;
      }
      .emergency-warning-box {
        background: linear-gradient(135deg, #fff5f5 0%, #ffe8e8 100%);
        border-left: 5px solid #dc3545;
        border-radius: 12px;
        padding: 18px;
        display: flex;
        gap: 14px;
        align-items: flex-start;
      }
      .warning-icon {
        font-size: 32px;
        flex-shrink: 0;
        animation: emergencyBounce 1.5s ease-in-out infinite;
      }
      @keyframes emergencyBounce {
        0%, 100% { transform: translateY(0); }
        50% { transform: translateY(-4px); }
      }
      .warning-content {
        display: flex;
        flex-direction: column;
        gap: 6px;
      }
      .warning-title {
        font-weight: 900;
        color: #8b0000;
        font-size: 13px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
      }
      .warning-text {
        color: #c41e3a;
        font-size: 13px;
        line-height: 1.5;
        font-weight: 500;
      }
      .emergency-form-group {
        display: flex;
        flex-direction: column;
        gap: 8px;
      }
      .emergency-label {
        font-size: 12px;
        font-weight: 800;
        color: #0a3642;
        text-transform: uppercase;
        letter-spacing: 0.6px;
        display: flex;
        align-items: center;
        gap: 8px;
      }
      .label-icon {
        font-size: 14px;
      }
      .emergency-input {
        width: 100%;
        padding: 13px 16px;
        border: 2px solid #e8ecf1;
        border-radius: 10px;
        font-size: 13px;
        font-weight: 500;
        background: #f8fafc;
        color: #0a3642;
        transition: all 200ms ease;
        font-family: inherit;
      }
      .emergency-input:focus {
        outline: none;
        border-color: #dc3545;
        background: #ffffff;
        box-shadow: 0 0 0 4px rgba(220, 53, 69, 0.12);
      }
      .emergency-input::placeholder {
        color: #a0aec0;
      }
      .emergency-helper-text {
        font-size: 12px;
        color: #28a745;
        font-weight: 600;
        display: flex;
        align-items: center;
        gap: 6px;
        padding: 10px 14px;
        background: #f0fdf4;
        border-radius: 8px;
        border-left: 3px solid #28a745;
      }
      .emergency-button-group {
        display: grid;
        grid-template-columns: 1fr 1.2fr;
        gap: 12px;
        margin-top: 8px;
      }
      .emergency-btn {
        padding: 14px 20px;
        border: none;
        border-radius: 10px;
        font-weight: 800;
        font-size: 12px;
        text-transform: uppercase;
        letter-spacing: 0.8px;
        cursor: pointer;
        transition: all 250ms cubic-bezier(0.34, 1.56, 0.64, 1);
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 8px;
      }
      .emergency-btn-cancel {
        background: #e8ecf1;
        color: #0a3642;
        border: 2px solid #d0dce5;
      }
      .emergency-btn-cancel:hover {
        background: #d9e2e8;
        border-color: #a0b0c0;
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(10,54,66,0.15);
      }
      .emergency-btn-confirm {
        background: linear-gradient(135deg, #dc3545 0%, #ff5a66 100%);
        color: white;
        border: none;
        position: relative;
        overflow: hidden;
      }
      .emergency-btn-confirm::before {
        content: '';
        position: absolute;
        top: 0;
        left: -100%;
        width: 100%;
        height: 100%;
        background: linear-gradient(90deg, transparent, rgba(255,255,255,0.3), transparent);
        transition: left 600ms;
      }
      .emergency-btn-confirm:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 20px rgba(220, 53, 69, 0.4);
      }
      .emergency-btn-confirm:hover::before {
        left: 100%;
      }
      .emergency-btn-confirm:active {
        transform: translateY(0);
      }
      .modal-footer .btn-ghost {
        background: #e8ecf1;
        color: #0a3642;
        border: 2px solid rgba(10,111,134,0.25);
        padding: 9px 20px;
        border-radius: 8px;
        font-weight: 700;
        font-size: 11px;
        cursor: pointer;
        transition: all 150ms ease;
        text-transform: uppercase;
        letter-spacing: 0.3px;
      }
      .modal-footer .btn-ghost:hover {
        background: #d9e2e8;
        border-color: rgba(10,111,134,0.4);
        transform: translateY(-1px);
        animation: rgbGlow 2s ease-in-out infinite;
      }
      .modal-footer .btn-link {
        background: linear-gradient(135deg, #0a9fb5, #0a6f86);
        color: #fff;
        border: none;
        padding: 9px 20px;
        border-radius: 8px;
        font-weight: 700;
        font-size: 11px;
        cursor: pointer;
        transition: all 150ms ease;
        text-transform: uppercase;
        letter-spacing: 0.3px;
      }
      .modal-footer .btn-link:hover {
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(10,111,134,0.3);
        animation: rgbGlow 2s ease-in-out infinite;
      }
      .console-header {
        margin-bottom: 16px;
      }
      .console-title {
        font-size: 20px;
        font-weight: 800;
        color: var(--text);
        margin-bottom: 2px;
        font-family: var(--font-display);
      }
      .console-subtitle {
        font-size: 12px;
        color: var(--muted);
      }
      .console-stats {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
        gap: 16px;
        margin-bottom: 14px;
        background: linear-gradient(135deg, #1e3a8a, #1e40af);
        border-radius: 12px;
        padding: 18px;
        transition: all 300ms ease;
      }
      .console-stats:hover {
        background: linear-gradient(135deg, #1e3a8a, #1e40af);
        box-shadow: 0 0 30px rgba(96, 165, 250, 0.3), inset 0 0 20px rgba(96, 165, 250, 0.1);
        transform: translateY(-2px);
      }
      .stat-card {
        background: rgba(30, 58, 138, 0.5);
        border: 1px solid rgba(96, 165, 250, 0.2);
        border-radius: 8px;
        padding: 16px;
        text-align: center;
        transition: all 200ms ease;
      }
      .console-stats:hover .stat-card {
        background: rgba(30, 58, 138, 0.7);
        border-color: rgba(96, 165, 250, 0.5);
        box-shadow: 0 4px 12px rgba(96, 165, 250, 0.2);
      }
      .stat-label {
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 1px;
        color: #60a5fa;
        margin-bottom: 8px;
        text-transform: uppercase;
        font-family: var(--font-display);
      }
      .stat-value {
        font-size: 32px;
        font-weight: 700;
        margin-bottom: 8px;
      }
      .cpu-bar {
        width: 100%;
        height: 6px;
        background: rgba(0, 0, 0, 0.3);
        border-radius: 3px;
        overflow: hidden;
      }
      .cpu-fill {
        height: 100%;
        background: #28a745;
        transition: width 0.3s ease, background-color 0.3s ease;
      }
      /* IP Access Control Form Styling */
      .modal#ipAccessModal {
        display: none;
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: rgba(11, 26, 42, 0.5);
        backdrop-filter: blur(4px);
        z-index: 1000;
        align-items: center;
        justify-content: center;
        padding: 20px;
        animation: fadeInBackdrop 200ms ease;
      }
      .modal#ipAccessModal.open {
        display: flex;
      }
      @keyframes fadeInBackdrop {
        from {
          opacity: 0;
          backdrop-filter: blur(0px);
        }
        to {
          opacity: 1;
          backdrop-filter: blur(4px);
        }
      }
      @keyframes slideInCard {
        from {
          transform: translateY(20px);
          opacity: 0;
        }
        to {
          transform: translateY(0);
          opacity: 1;
        }
      }
      .ip-access-card {
        max-width: 450px;
        width: 100%;
        border: 1px solid rgba(10,159,181,0.15);
        border-radius: 16px;
        overflow: hidden;
        box-shadow: 0 20px 60px rgba(10,20,30,0.35), 0 0 40px rgba(10,159,181,0.15);
        background: #ffffff;
        animation: slideInCard 250ms ease;
      }
      .ip-access-header {
        background: linear-gradient(135deg, #0a9fb5 0%, #085a6d 100%);
        padding: 28px 32px;
        position: relative;
        overflow: hidden;
        display: flex;
        justify-content: space-between;
        align-items: center;
      }
      .ip-access-header::before {
        content: '';
        position: absolute;
        top: -50%;
        right: -50%;
        width: 200%;
        height: 200%;
        background: radial-gradient(circle, rgba(255,255,255,0.12) 0%, transparent 70%);
        pointer-events: none;
      }
      .ip-access-title {
        display: flex;
        align-items: center;
        gap: 14px;
        font-size: 18px;
        font-weight: 800;
        letter-spacing: 0.5px;
        color: #ffffff;
        position: relative;
        z-index: 1;
      }
      .ip-access-icon {
        font-size: 28px;
        display: flex;
        align-items: center;
        filter: drop-shadow(0 2px 4px rgba(0,0,0,0.1));
      }
      #closeIpAccessModal {
        position: relative;
        z-index: 2;
        background: rgba(255,255,255,0.15);
        color: #ffffff;
        border: none;
        cursor: pointer;
        transition: all 150ms ease;
        min-width: auto;
        padding: 6px 10px;
        font-size: 20px;
        border-radius: 6px;
      }
      #closeIpAccessModal:hover {
        background: rgba(255,255,255,0.25);
        transform: rotate(90deg);
      }
      .ip-access-body {
        padding: 32px 32px;
        display: flex;
        flex-direction: column;
        gap: 20px;
        background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
      }
      .ip-access-note {
        display: flex;
        align-items: flex-start;
        gap: 12px;
        padding: 16px 18px;
        background: linear-gradient(135deg, rgba(10,159,181,0.13) 0%, rgba(10,159,181,0.06) 100%);
        border-left: 4px solid #0a9fb5;
        border-radius: 10px;
        font-size: 14px;
        color: #0a3642;
        line-height: 1.5;
        box-shadow: inset 0 1px 2px rgba(10,159,181,0.08);
      }
      .note-icon {
        font-size: 18px;
        flex-shrink: 0;
        margin-top: 2px;
        color: #0a9fb5;
      }
      .form-group {
        display: flex;
        flex-direction: column;
        gap: 10px;
        margin-bottom: 4px;
      }
      .form-label {
        font-size: 12px;
        color: #0a3642;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        display: flex;
        align-items: center;
        gap: 8px;
        font-style: normal;
      }
      .form-label span {
        font-size: 16px;
        font-style: normal;
      }
      .form-input {
        width: 100%;
        padding: 14px 16px;
        border-radius: 10px;
        border: 2px solid rgba(10,111,134,0.15);
        font-size: 14px;
        font-weight: 500;
        background: #ffffff;
        color: #0a3642;
        transition: all 250ms cubic-bezier(0.4, 0, 0.2, 1);
        font-family: var(--font-body);
        box-shadow: inset 0 1px 3px rgba(0,0,0,0.02);
      }
      .form-input:focus {
        outline: none;
        border-color: #0a9fb5;
        background: linear-gradient(135deg, #f0fafb 0%, #ffffff 100%);
        box-shadow: 0 0 0 5px rgba(10,159,181,0.12), inset 0 1px 3px rgba(0,0,0,0.02);
      }
      .form-input:hover:not(:focus) {
        border-color: rgba(10,159,181,0.25);
        background: #ffffff;
      }
      .form-input::placeholder {
        color: #a8b8c4;
      }
      .ip-access-footer {
        padding: 24px 32px;
        display: flex;
        justify-content: flex-end;
        gap: 12px;
        border-top: 1px solid rgba(10,111,134,0.08);
        background: linear-gradient(180deg, #f8fafc 0%, #f2f5f8 100%);
      }
      #cancelIpAccessModal {
        background: linear-gradient(135deg, #e8ecf1 0%, #dce4eb 100%);
        color: #0a3642;
        border: 1.5px solid rgba(10,111,134,0.15);
        padding: 12px 28px;
        border-radius: 8px;
        font-weight: 700;
        font-size: 12px;
        cursor: pointer;
        transition: all 200ms ease;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        box-shadow: 0 2px 6px rgba(10,20,30,0.08);
        position: relative;
        overflow: hidden;
      }
      #cancelIpAccessModal::before {
        content: '';
        position: absolute;
        top: 0;
        left: -100%;
        width: 100%;
        height: 100%;
        background: rgba(255,255,255,0.3);
        transition: left 200ms ease;
        z-index: 0;
      }
      #cancelIpAccessModal:hover {
        background: linear-gradient(135deg, #d9e2e8 0%, #cdd7e1 100%);
        border-color: rgba(10,111,134,0.3);
        transform: translateY(-2px);
        box-shadow: 0 6px 12px rgba(10,20,30,0.12);
      }
      #cancelIpAccessModal:hover::before {
        left: 100%;
      }
      #cancelIpAccessModal:active {
        transform: translateY(0);
      }
      .ip-access-submit {
        background: linear-gradient(135deg, #0a9fb5 0%, #085a6d 100%);
        color: #ffffff;
        border: none;
        padding: 12px 28px;
        border-radius: 8px;
        font-weight: 700;
        font-size: 12px;
        cursor: pointer;
        transition: all 200ms ease;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        box-shadow: 0 4px 14px rgba(10,159,181,0.25);
        position: relative;
        overflow: hidden;
      }
      .ip-access-submit::before {
        content: '';
        position: absolute;
        top: 0;
        left: -100%;
        width: 100%;
        height: 100%;
        background: rgba(255,255,255,0.15);
        transition: left 200ms ease;
      }
      .ip-access-submit:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 20px rgba(10,159,181,0.35);
        background: linear-gradient(135deg, #0cbcc8 0%, #0a7d8f 100%);
      }
      .ip-access-submit:hover::before {
        left: 100%;
      }
      .ip-access-submit:active {
        transform: translateY(0);
      }
      
      /* Welcome Page Animation Styles */
      @keyframes welcome-fade-in {
        from { opacity: 0; }
        to { opacity: 1; }
      }
      @keyframes welcome-slide-in {
        from { opacity: 0; transform: translateY(30px); }
        to { opacity: 1; transform: translateY(0); }
      }
      @keyframes welcome-bounce {
        0%, 100% { transform: translateY(0); }
        50% { transform: translateY(-20px); }
      }
      @keyframes welcome-pulse {
        0%, 100% { transform: scale(1); }
        50% { transform: scale(1.05); }
      }
      @keyframes welcome-typewriter {
        from { width: 0; }
        to { width: 100%; }
      }
      @keyframes welcome-neon {
        0%, 100% { text-shadow: 0 0 10px rgba(10,159,181,0.5), 0 0 20px rgba(10,159,181,0.3); }
        50% { text-shadow: 0 0 20px rgba(10,159,181,1), 0 0 30px rgba(10,159,181,0.6), 0 0 40px rgba(10,159,181,0.4); }
      }
      @keyframes welcome-wave {
        0%, 100% { transform: translateY(0px); }
        25% { transform: translateY(-15px); }
        50% { transform: translateY(0px); }
        75% { transform: translateY(-10px); }
      }
      @keyframes welcome-flip {
        from { transform: rotateY(90deg); opacity: 0; }
        to { transform: rotateY(0deg); opacity: 1; }
      }
      @keyframes welcome-zoom {
        from { transform: scale(0); opacity: 0; }
        to { transform: scale(1); opacity: 1; }
      }

      /* Welcome Background Patterns */
      .welcome-bg-gradient-blue {
        background: linear-gradient(135deg, #0a6f86 0%, #0a9fb5 50%, #0cbcc8 100%);
      }
      .welcome-bg-gradient-purple {
        background: linear-gradient(135deg, #553399 0%, #7733aa 50%, #9955cc 100%);
      }
      .welcome-bg-gradient-ocean {
        background: linear-gradient(135deg, #001a4d 0%, #003366 50%, #0066cc 100%);
      }
      .welcome-bg-gradient-sunset {
        background: linear-gradient(135deg, #ff6b35 0%, #ff8c42 50%, #ffa500 100%);
      }
      .welcome-bg-gradient-forest {
        background: linear-gradient(135deg, #1b4332 0%, #2d6a4f 50%, #40916c 100%);
      }
      .welcome-bg-solid-dark {
        background: #1a1a2e;
      }
      .welcome-bg-solid-light {
        background: #f5f5f5;
      }
      .welcome-bg-pattern-dots {
        background: radial-gradient(circle, rgba(10,159,181,0.3) 2px, transparent 2px);
        background-size: 20px 20px;
        background-color: #ffffff;
      }
      .welcome-bg-pattern-grid {
        background-image: 
          linear-gradient(rgba(10,159,181,0.1) 1px, transparent 1px),
          linear-gradient(90deg, rgba(10,159,181,0.1) 1px, transparent 1px);
        background-size: 20px 20px;
        background-color: #ffffff;
      }
      .welcome-bg-animated-waves {
        background: linear-gradient(135deg, #0a6f86 0%, #0a9fb5 100%);
        position: relative;
        overflow: hidden;
      }
      .welcome-bg-animated-waves::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        width: 200%;
        height: 200%;
        background: url('data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 120"><path d="M0,60 Q300,0 600,60 T1200,60 L1200,120 L0,120 Z" fill="rgba(255,255,255,0.1)"/></svg>');
        background-size: 600px 120px;
        animation: waves 15s linear infinite;
      }
      .welcome-bg-animated-particles {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
        position: relative;
        overflow: hidden;
      }
      .welcome-bg-animated-particles::after {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: radial-gradient(circle at 20% 50%, rgba(10,159,181,0.3) 1px, transparent 1px),
                    radial-gradient(circle at 80% 80%, rgba(10,159,181,0.2) 1px, transparent 1px),
                    radial-gradient(circle at 40% 20%, rgba(10,159,181,0.25) 1px, transparent 1px);
        background-size: 200px 200px, 150px 150px, 250px 250px;
        animation: particles 20s linear infinite;
      }
      @keyframes waves {
        0% { transform: translateX(0); }
        100% { transform: translateX(600px); }
      }
      @keyframes particles {
        0% { transform: translateX(0) translateY(0); }
        100% { transform: translateX(100px) translateY(-100px); }
      }
      
      /* Galaxy Background */
      .welcome-bg-animated-galaxy {
        background: linear-gradient(135deg, #0a0e27 0%, #1a0a3d 50%, #0d0a2b 100%);
        position: relative;
        overflow: hidden;
      }
      .welcome-bg-animated-galaxy::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: 
          radial-gradient(circle at 15% 30%, rgba(255, 100, 200, 0.4) 0%, transparent 15%),
          radial-gradient(circle at 85% 70%, rgba(100, 150, 255, 0.4) 0%, transparent 15%),
          radial-gradient(circle at 50% 50%, rgba(200, 100, 255, 0.2) 0%, transparent 20%);
        animation: galaxy 20s ease-in-out infinite;
      }
      .welcome-bg-animated-galaxy::after {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: 
          radial-gradient(circle at 10% 10%, rgba(255, 255, 255, 0.8) 1px, transparent 1px),
          radial-gradient(circle at 90% 90%, rgba(255, 255, 255, 0.6) 1px, transparent 1px),
          radial-gradient(circle at 50% 20%, rgba(255, 255, 255, 0.7) 1px, transparent 1px),
          radial-gradient(circle at 20% 80%, rgba(255, 255, 255, 0.5) 1px, transparent 1px),
          radial-gradient(circle at 80% 30%, rgba(255, 255, 255, 0.6) 1px, transparent 1px);
        background-size: 300px 300px, 400px 400px, 250px 250px, 350px 350px, 320px 320px;
        animation: twinkle 3s ease-in-out infinite;
      }
      @keyframes galaxy {
        0%, 100% { transform: scale(1) rotate(0deg); }
        50% { transform: scale(1.05) rotate(2deg); }
      }
      @keyframes twinkle {
        0%, 100% { opacity: 0.3; }
        50% { opacity: 0.8; }
      }
      
      /* Pirate Background */
      .welcome-bg-animated-pirate {
        background: linear-gradient(135deg, #2c1810 0%, #4a2820 50%, #1c0f0a 100%);
        position: relative;
        overflow: hidden;
      }
      .welcome-bg-animated-pirate::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: linear-gradient(180deg, rgba(50, 30, 20, 0.3) 0%, rgba(100, 60, 30, 0.2) 50%, rgba(30, 20, 10, 0.4) 100%);
        animation: pirateBob 4s ease-in-out infinite;
      }
      .welcome-bg-animated-pirate::after {
        content: '☠️';
        position: absolute;
        font-size: 80px;
        opacity: 0.15;
        top: 50%;
        left: 50%;
        transform: translate(-50%, -50%);
        animation: pirateWave 6s ease-in-out infinite;
      }
      @keyframes pirateBob {
        0%, 100% { transform: translateY(0px); }
        50% { transform: translateY(10px); }
      }
      @keyframes pirateWave {
        0%, 100% { transform: translate(-50%, -50%) rotateZ(-5deg); }
        50% { transform: translate(-50%, -50%) rotateZ(5deg); }
      }
      
      /* Beach Background */
      .welcome-bg-animated-beach {
        background: linear-gradient(180deg, #87CEEB 0%, #E0F6FF 30%, #FFD700 40%, #FFCC99 100%);
        position: relative;
        overflow: hidden;
      }
      .welcome-bg-animated-beach::before {
        content: '';
        position: absolute;
        bottom: 40%;
        left: 0;
        width: 100%;
        height: 30%;
        background: linear-gradient(180deg, rgba(0, 150, 200, 0.3) 0%, rgba(0, 100, 150, 0.4) 100%);
        animation: oceanWave 6s ease-in-out infinite;
      }
      .welcome-bg-animated-beach::after {
        content: '';
        position: absolute;
        bottom: 35%;
        left: 0;
        width: 100%;
        height: 5%;
        background: linear-gradient(90deg, transparent 0%, rgba(255, 255, 255, 0.6) 50%, transparent 100%);
        animation: beachWave 4s ease-in-out infinite;
      }
      @keyframes oceanWave {
        0%, 100% { transform: translateY(0px); }
        50% { transform: translateY(5px); }
      }
      @keyframes beachWave {
        0%, 100% { transform: scaleX(1); }
        50% { transform: scaleX(1.1); }
      }
      
      /* Planet Background */
      .welcome-bg-animated-planet {
        background: linear-gradient(135deg, #0a1428 0%, #1a2a4a 50%, #0d1b3d 100%);
        position: relative;
        overflow: hidden;
      }
      .welcome-bg-animated-planet::before {
        content: '';
        position: absolute;
        width: 150px;
        height: 150px;
        background: radial-gradient(circle at 30% 30%, #FF8C00 0%, #FF6347 50%, #8B4513 100%);
        border-radius: 50%;
        top: 20%;
        right: 15%;
        opacity: 0.8;
        animation: planetOrbit 12s linear infinite;
        box-shadow: 0 0 40px rgba(255, 140, 0, 0.4);
      }
      .welcome-bg-animated-planet::after {
        content: '';
        position: absolute;
        width: 80px;
        height: 80px;
        background: radial-gradient(circle at 40% 40%, #FFD700 0%, #FFA500 60%, #FF8C00 100%);
        border-radius: 50%;
        bottom: 25%;
        left: 10%;
        opacity: 0.6;
        animation: planetGlow 8s ease-in-out infinite;
        box-shadow: 0 0 30px rgba(255, 215, 0, 0.5);
      }
      @keyframes planetOrbit {
        0% { transform: translate(0, 0) rotate(0deg); }
        100% { transform: translate(20px, 10px) rotate(360deg); }
      }
      @keyframes planetGlow {
        0%, 100% { box-shadow: 0 0 20px rgba(255, 215, 0, 0.3); }
        50% { box-shadow: 0 0 40px rgba(255, 215, 0, 0.7); }
      }

      /* Welcome Font Styles */
      .welcome-font-modern { font-family: "Bahnschrift", "Candara", "Trebuchet MS", sans-serif; }
      .welcome-font-classic { font-family: "Rockwell", "Constantia", "Georgia", serif; }
      .welcome-font-elegant { font-family: "Garamond", "Calisto MT", serif; }
      .welcome-font-serif { font-family: "Georgia", "Times New Roman", serif; }
      .welcome-font-sans { font-family: "Verdana", "Arial", sans-serif; }
      .welcome-font-geometric { font-family: "Trebuchet MS", "Century Gothic", sans-serif; }
      .welcome-font-tech { font-family: "Courier New", "Monaco", monospace; }
      .welcome-font-minimal { font-family: "Helvetica", "Arial", sans-serif; }
      .welcome-font-corporate { font-family: "Calibri", "Segoe UI", sans-serif; }
      .welcome-font-artistic { font-family: "Palatino Linotype", "Palatino", serif; }
      .welcome-font-futuristic { font-family: "Segoe UI", "Tahoma", sans-serif; }
      .welcome-font-handwriting { font-family: "Segoe Print", "Comic Sans MS", cursive; }
      </style>
  </head>
  <body class="font-modern" data-user-role="{% if current_username == 'WIN2' %}ADMIN{% else %}USER{% endif %}">
    <div class="shell">
      <div class="nav-wrap">
        <div class="nav-content">
          <div class="nav-head">
            <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 8px;">
              <svg width="44" height="44" viewBox="0 0 44 44" fill="none" xmlns="http://www.w3.org/2000/svg">
                <defs>
                  <linearGradient id="e6Elegant" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" style="stop-color:#00d4ff;stop-opacity:1" />
                    <stop offset="50%" style="stop-color:#00b8e6;stop-opacity:1" />
                    <stop offset="100%" style="stop-color:#0a9fb5;stop-opacity:1" />
                  </linearGradient>
                </defs>
                <!-- Outer circle ring -->
                <circle cx="22" cy="22" r="20" fill="none" stroke="#00d4ff" stroke-width="2" opacity="0.4"/>
                <!-- Main circle background -->
                <circle cx="22" cy="22" r="18" fill="url(#e6Elegant)"/>
                <!-- Inner light circle accent -->
                <circle cx="22" cy="22" r="17" fill="none" stroke="#ffffff" stroke-width="0.8" opacity="0.25"/>
                <!-- Bold "E" in left section -->
                <g>
                  <text x="10" y="28" font-family="Arial, Helvetica, sans-serif" font-size="20" font-weight="900" fill="#ffffff" letter-spacing="-1">E</text>
                </g>
                <!-- Bold "6" in right section -->
                <g>
                  <text x="24" y="28" font-family="Arial, Helvetica, sans-serif" font-size="20" font-weight="900" fill="#ffffff" letter-spacing="-1">6</text>
                </g>
                <!-- Top center accent line -->
                <line x1="14" y1="5" x2="30" y2="5" stroke="#ffffff" stroke-width="1.5" stroke-linecap="round" opacity="0.5"/>
                <!-- Bottom center accent dot -->
                <circle cx="22" cy="38" r="1.2" fill="#ffffff" opacity="0.4"/>
              </svg>
              <div class="nav-title">E6 DASHBOARD</div>
            </div>
            <div style="display: flex; flex-direction: column; gap: 6px; width: 100%;">
              <div class="nav-badge">Active: {{ active_main }}</div>
              <div class="nav-badge" data-nav-item="User: {{ current_user.username if current_user else 'Guest' }}" style="background: rgba(42, 132, 161, 0.25); border-color: rgba(42, 132, 161, 0.4); color: #7fa3b3; cursor: context-menu;">User: {{ current_user.username if current_user else 'Guest' }}</div>
            </div>
          </div>
          <div class="nav">
            {% set nav_icons = {
              'EXPAY': '💳',
              'PAYMENT': '💰',
              'TELEGRAM': '📱',
              'UPDATE BALANCE': '📊',
              'TRANSFER': '↔️',
              'SMARTPAY': '💳',
              'BRAND DASHBOARD': '📈',
              'PG TRANSFER': '🔄',
              'ACM': '⚙️',
              'PG CHECK': '✓',
              'CT': '📄',
              'AUTOPAY': '🔄',
              'VINAI': '🏦'
            } %}
            {% for item in nav_main %}
              <div class="nav-item {% if item == active_main and nav_subs %}show-subs{% endif %} {% if current_username == 'WIN2' %}draggable-enabled{% endif %}" data-nav-item="{{ item }}" data-nav-type="main" contextmenu="navContextMenu" draggable="{% if current_username == 'WIN2' %}true{% else %}false{% endif %}">
                <a class="nav-link {{ 'active' if item == active_main else '' }}" href="{{ url_for('index', main=item) }}">
                  <span class="icon">{{ nav_icons.get(item, '📌') }}</span>
                  <span>{{ item }}</span>
                </a>
                {% if nav_subs and item == active_main %}
                <div class="sub-nav">
                  {% for sub in nav_subs %}
                  <a class="sub-nav-link {{ 'active' if sub == active_sub else '' }}" href="{{ url_for('index', main=active_main, sub=sub) }}" data-sub-nav-item="{{ sub }}" data-nav-type="sub">{{ sub }}</a>
                  {% endfor %}
                </div>
                {% endif %}
              </div>
            {% endfor %}
          </div>
        </div>
        <div class="nav-footer">
          {% if current_username == 'WIN2' %}
          <button class="btn btn-ghost btn-icon" type="button" id="bgOpen">
            <span class="icon">🖼️</span><span>Background</span>
          </button>
          <button class="btn btn-ghost btn-icon" type="button" id="welcomeOpen">
            <span class="icon">🎨</span><span>Welcome Style</span>
          </button>
          <a class="btn btn-primary btn-icon" href="{{ url_for('change_path_modal') }}" target="_blank">
            <span class="icon">📂</span><span>Change Path</span>
          </a>
          <a class="btn btn-primary btn-icon" href="{{ url_for('history') }}">
            <span class="icon">🕒</span><span>History</span>
          </a>
          <a class="btn btn-primary btn-icon" href="{{ url_for('admin') }}">
            <span class="icon">🛡️</span><span>Admin</span>
          </a>
          <a class="btn btn-primary btn-icon" href="{{ url_for('access_log') }}">
            <span class="icon">🔒</span><span>Access Log</span>
          </a>
          <button class="btn btn-primary btn-icon openSettingsBtn" type="button">
            <span class="icon">⚙</span><span>Settings</span>
          </button>
          {% else %}
          <button class="btn btn-primary btn-icon openSettingsBtn" type="button">
            <span class="icon">⚙</span><span>Settings</span>
          </button>
          {% endif %}
          <a class="btn btn-danger btn-icon" href="{{ url_for('logout') }}">
            <span class="icon">⎋</span><span>Log Out</span>
          </a>
        </div>
      </div>

      <div class="content-layout">
        <!-- Panel 1: Status Overview (Frozen) -->
        <div class="status-panel">
          <div class="console-header">
            <div class="console-title">Operations Console</div>
            <div class="console-subtitle">System overview & live status</div>
          </div>
          <div class="console-stats">
            <div class="stat-card">
              <div class="stat-label">RUNNING</div>
              <div class="stat-value" style="color: var(--green);">{{ running_count }}</div>
            </div>
            <div class="stat-card">
              <div class="stat-label">STOPPED</div>
              <div class="stat-value" style="color: var(--red);">{{ stopped_count }}</div>
            </div>
            <div class="stat-card">
              <div class="stat-label">CPU</div>
              <div class="stat-value" id="cpuValue">{{ "%.1f"|format(cpu_usage) }}%</div>
              <div class="cpu-bar">
                <div class="cpu-fill" id="cpuFill" style="width: {{ cpu_usage }}%;"></div>
              </div>
            </div>
          </div>
          <div class="filters">
            <span>Filter Status:</span>
            <select id="statusFilter">
              <option value="all">All</option>
              <option value="running">Running</option>
              <option value="stopped">Stopped</option>
            </select>
            <input type="text" id="scriptSearch" class="script-search" placeholder="Search script name..." />
            <span class="search-result-message" style="display: none; margin-left: 10px; font-weight: 600;"></span>
          </div>
          </div>

        <!-- Panel 2: Display Scripts (Scrollable) -->
        <div class="scripts-panel">
          <table>
            <thead>
              <tr>
                <th>Script Name</th>
                <th>Status</th>
                <th>Process</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {% for card in cards %}
              <tr data-status="{{ 'running' if card.running else 'stopped' }}">
                <td class="script-name-cell" ondblclick="editScriptName({{ card.id }}, this)" title="Double-click to edit">{{ card.name }}</td>
                <td>
                  <span class="status-pill {{ 'running' if card.running else 'stopped' }}">
                    {{ card.status_text }}
                  </span>
                </td>
                <td>
                  {% if card.pid %}
                  <span class="pid-pill">PID {{ card.pid }}</span>
                  {% else %}
                  -
                  {% endif %}
                </td>
                <td class="actions-cell">
                  <div class="action-stack">
                    {% if card.running %}
                    <form method="post" action="{{ url_for('stop', script_id=card.id, main=active_main, sub=active_sub) }}">
                      <button class="action-btn action-stop" type="submit">Stop</button>
                    </form>
                    {% else %}
                    <form method="post" action="{{ url_for('start', script_id=card.id, main=active_main, sub=active_sub) }}">
                      <button class="action-btn action-start" type="submit">Start</button>
                    </form>
                    {% endif %}
                    {% if current_user and current_user.role == 'ADMIN' %}
                    <button class="action-btn action-edit" type="button" onclick="openEditScriptModal({{ card.id }}, '{{ active_main }}', '{{ active_sub }}')">Edit Script</button>
                    {% endif %}
                    <a class="action-btn action-log" href="{{ url_for('view_log', script_id=card.id, main=active_main, sub=active_sub) }}">View Log</a>
                  </div>
                </td>
              </tr>
              {% endfor %}
            </tbody>
          </table>
        </div>

        <!-- Panel 3: Footer (Frozen) -->
        <div class="footer-panel">
          <div class="footer-bar">
            <div class="note">Dashboard refreshes status on each page load.</div>
            <div class="bulk-actions">
              <form method="post" action="{{ url_for('start_all', main=active_main, sub=active_sub) }}">
                <button class="btn btn-primary" type="submit">Start All</button>
              </form>
              <form method="post" action="{{ url_for('stop_all', main=active_main, sub=active_sub) }}">
                <button class="btn btn-secondary" type="submit">Stop All</button>
              </form>
            </div>
          </div>
        </div>

        <!-- Emergency Control Modal -->
        <div class="modal" id="emergencyModal" aria-hidden="true">
          <div class="emergency-modal-card">
            <div class="emergency-modal-header">
              <div class="emergency-title-wrapper">
                <span class="emergency-icon">⚠</span>
                <span class="emergency-title">EMERGENCY CONTROL</span>
              </div>
              <button class="emergency-close-btn" type="button" id="emergencyClose">✕</button>
            </div>
            
            <form class="emergency-modal-body" id="emergencyForm" method="post">
              <div class="emergency-warning-box">
                <div class="warning-icon">!</div>
                <div class="warning-content">
                  <div class="warning-title">CRITICAL ACTION</div>
                  <div class="warning-text">This will affect ALL scripts across ALL navigations. This action cannot be easily undone.</div>
                </div>
              </div>

              <input type="hidden" id="emergencyAction" name="action" value="" />
              
              <div class="emergency-form-group">
                <label for="emergency_user" class="emergency-label">
                  <span class="label-icon">👤</span>
                  Admin Username
                </label>
                <input 
                  id="emergency_user" 
                  name="admin_user" 
                  type="text" 
                  placeholder="Enter your admin username" 
                  class="emergency-input"
                  required 
                />
              </div>

              <div class="emergency-form-group">
                <label for="emergency_password" class="emergency-label">
                  <span class="label-icon">🔒</span>
                  Admin Password
                </label>
                <input 
                  id="emergency_password" 
                  name="admin_password" 
                  type="password" 
                  placeholder="Enter your admin password" 
                  class="emergency-input"
                  required 
                />
              </div>

              <div class="emergency-helper-text">
                ✓ Credentials will be verified before execution
              </div>

              <div class="emergency-button-group">
                <button class="emergency-btn emergency-btn-cancel" type="button" id="emergencyCancel">
                  <span>Cancel</span>
                </button>
                <button class="emergency-btn emergency-btn-confirm" type="submit" id="emergencyConfirm">
                  <span>CONFIRM & EXECUTE</span>
                </button>
              </div>
            </form>
          </div>
        </div>

          <div class="modal" id="bgModal" aria-hidden="true">
          <div class="modal-card">
          <div class="modal-header">
          <span>Confirm Background Change</span>
          <button class="btn btn-secondary" type="button" id="bgClose">X</button>
          </div>
        <form class="modal-body" method="post" action="{{ url_for('update_background', main=active_main, sub=active_sub) }}" enctype="multipart/form-data">
          <div>Enter Admin Credentials to change background.</div>
          <div style="background:#d8f6ff;border-radius:8px;padding:8px 10px;color:#0b5f72;font-weight:600;">
            Selected background: {{ background_label }}
          </div>
          <label for="bg_mode">Choose background</label>
          <select id="bg_mode" name="bg_mode">
            <option value="default" {% if background_mode == 'default' %}selected{% endif %}>Default</option>
            <option value="custom" {% if background_mode == 'custom' %}selected{% endif %}>Custom (Upload)</option>
          </select>
          <label for="bg_file">Upload image</label>
          <input id="bg_file" type="file" name="bg_file" accept=".jpg,.jpeg,.png,.webp,.gif" />
          <div style="font-size:12px;color:var(--muted);">
            Allowed: JPG/PNG/WEBP/GIF (max 100MB).
          </div>
          <label for="font_style">Font style</label>
          <select id="font_style" name="font_style">
            <option value="modern">Modern</option>
            <option value="classic">Classic</option>
            <option value="mono">Mono</option>
            <option value="elegant">Elegant</option>
            <option value="geometric">Geometric</option>
            <option value="tech">Tech</option>
            <option value="serif">Serif</option>
            <option value="sans">Sans-Serif</option>
            <option value="typewriter">Typewriter</option>
            <option value="handwriting">Handwriting</option>
            <option value="futuristic">Futuristic</option>
            <option value="minimal">Minimal</option>
            <option value="bold">Bold</option>
            <option value="soft">Soft</option>
            <option value="corporate">Corporate</option>
            <option value="artistic">Artistic</option>
            <option value="monospace">Monospace</option>
            <option value="script">Script</option>
            <option value="modern-sans">Modern Sans</option>
            <option value="classic-serif">Classic Serif</option>
            <option value="code">Code</option>
            <option value="display-serif">Display Serif</option>
            <option value="humanist">Humanist</option>
            <option value="retro">Retro</option>
          </select>
          <input type="text" name="admin_user" placeholder="Admin User" />
          <input type="password" name="admin_password" placeholder="Admin Password" />
          <div class="modal-footer" style="padding:0;border:none;background:transparent;justify-content:flex-end;">
            <button class="btn btn-secondary" type="button" id="bgCancel">Cancel</button>
            <button class="btn btn-primary" type="submit">Confirm</button>
          </div>
        </form>
      </div>
    </div>
    <div class="modal" id="welcomeModal" aria-hidden="true">
      <div class="modal-card">
        <div class="modal-header">
          <span>Welcome Page Style Customization</span>
          <button class="btn btn-secondary" type="button" id="welcomeClose">X</button>
        </div>
        <div class="modal-body">
          <div>Customize your welcome page appearance</div>
          
          <div style="margin-top:16px;">
            <label for="welcome_text">Welcome Text</label>
            <input type="text" id="welcome_text" name="welcome_text" placeholder="Enter welcome text" value="Welcome to Dashboard" />
          </div>

          <div style="margin-top:16px;">
            <label for="welcome_animation">Text Animation Style</label>
            <select id="welcome_animation" name="welcome_animation">
              <option value="fade">Fade In</option>
              <option value="slide">Slide In</option>
              <option value="bounce">Bounce</option>
              <option value="pulse">Pulse</option>
              <option value="typewriter">Typewriter</option>
              <option value="neon">Neon Glow</option>
              <option value="wave">Wave</option>
              <option value="flip">Flip</option>
              <option value="zoom">Zoom</option>
              <option value="none">None</option>
            </select>
          </div>

          <div style="margin-top:16px;">
            <label for="welcome_font">Welcome Text Font</label>
            <select id="welcome_font" name="welcome_font">
              <option value="modern">Modern</option>
              <option value="classic">Classic</option>
              <option value="elegant">Elegant</option>
              <option value="serif">Serif</option>
              <option value="sans">Sans-Serif</option>
              <option value="geometric">Geometric</option>
              <option value="tech">Tech</option>
              <option value="minimal">Minimal</option>
              <option value="corporate">Corporate</option>
              <option value="artistic">Artistic</option>
              <option value="futuristic">Futuristic</option>
              <option value="handwriting">Handwriting</option>
            </select>
          </div>

          <div style="margin-top:16px;">
            <label for="welcome_background">Background Style</label>
            <select id="welcome_background" name="welcome_background">
              <option value="gradient-blue">Gradient Blue</option>
              <option value="gradient-purple">Gradient Purple</option>
              <option value="gradient-ocean">Gradient Ocean</option>
              <option value="gradient-sunset">Gradient Sunset</option>
              <option value="gradient-forest">Gradient Forest</option>
              <option value="solid-dark">Solid Dark</option>
              <option value="solid-light">Solid Light</option>
              <option value="pattern-dots">Pattern Dots</option>
              <option value="pattern-grid">Pattern Grid</option>
              <option value="animated-waves">Animated Waves</option>
              <option value="animated-particles">Animated Particles</option>
              <option value="animated-galaxy">Animated Galaxy</option>
              <option value="animated-pirate">Animated Pirate</option>
              <option value="animated-beach">Animated Beach</option>
              <option value="animated-planet">Animated Planet</option>
            </select>
          </div>

          <div style="margin-top:16px;padding:12px;background:#e8f4f8;border-radius:8px;border-left:4px solid #0a9fb5;">
            <strong>Preview:</strong>
            <div id="welcomePreview" style="margin-top:8px;padding:16px;background:white;border-radius:6px;text-align:center;font-size:20px;min-height:100px;display:flex;align-items:center;justify-content:center;">
              Welcome to Dashboard
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary" type="button" id="welcomeCancel">Cancel</button>
          <button class="btn btn-primary" type="button" id="welcomeSave">Save Changes</button>
        </div>
      </div>
    </div>
    <div class="overlay" id="drawerOverlay"></div>
    <aside class="drawer" id="settingsDrawer" aria-hidden="true">
      <div class="drawer-header">
        <span>Admin Settings</span>
        <button class="btn btn-secondary" type="button" id="closeSettings">X</button>
      </div>
      <div class="drawer-body">
        <iframe src="{{ url_for('settings') }}"></iframe>
      </div>
    </aside>
    <script>
      const modal = document.getElementById("bgModal");
      const openBtn = document.getElementById("bgOpen");
       const closeBtn = document.getElementById("bgClose");
       const cancelBtn = document.getElementById("bgCancel");
       const fontSelect = document.getElementById("font_style");
       const body = document.body;
       function setFontStyle(value) {
          const fontClasses = ["font-modern", "font-classic", "font-mono", "font-elegant", "font-geometric", "font-tech", "font-serif", "font-sans", "font-typewriter", "font-handwriting", "font-futuristic", "font-minimal", "font-bold", "font-soft", "font-corporate", "font-artistic", "font-monospace", "font-script", "font-modern-sans", "font-classic-serif", "font-code", "font-display-serif", "font-humanist", "font-retro"];
          fontClasses.forEach(cls => body.classList.remove(cls));
          body.classList.add("font-" + value);
          localStorage.setItem("dashboardFontStyle", value);
        }
       const savedFont = localStorage.getItem("dashboardFontStyle");
       if (savedFont && fontSelect) {
         fontSelect.value = savedFont;
         setFontStyle(savedFont);
       }
       if (fontSelect) {
         fontSelect.addEventListener("change", (e) => {
           setFontStyle(e.target.value);
         });
       }
       if (openBtn) {
         openBtn.addEventListener("click", () => {
           modal.classList.add("open");
           modal.setAttribute("aria-hidden", "false");
         });
       }
       function closeModal() {
         if (modal) {
           modal.classList.remove("open");
           modal.setAttribute("aria-hidden", "true");
         }
       }
       if (closeBtn) {
         closeBtn.addEventListener("click", closeModal);
       }
       if (cancelBtn) {
         cancelBtn.addEventListener("click", closeModal);
       }
       if (modal) {
         modal.addEventListener("click", (event) => {
           if (event.target === modal) {
             closeModal();
           }
         });
       }
      const settingsDrawer = document.getElementById("settingsDrawer");
      const drawerOverlay = document.getElementById("drawerOverlay");
      const openSettingsButtons = document.querySelectorAll(".openSettingsBtn");
      const closeSettings = document.getElementById("closeSettings");
      function openDrawer() {
        if (settingsDrawer && drawerOverlay) {
          settingsDrawer.classList.add("open");
          drawerOverlay.classList.add("open");
          settingsDrawer.setAttribute("aria-hidden", "false");
        }
      }
      function closeDrawer() {
        if (settingsDrawer && drawerOverlay) {
          settingsDrawer.classList.remove("open");
          drawerOverlay.classList.remove("open");
          settingsDrawer.setAttribute("aria-hidden", "true");
        }
      }
      openSettingsButtons.forEach(btn => {
        btn.addEventListener("click", openDrawer);
      });
      if (closeSettings) {
        closeSettings.addEventListener("click", closeDrawer);
      }
      if (drawerOverlay) {
        drawerOverlay.addEventListener("click", closeDrawer);
      }

      // Welcome Page Style Modal
      const welcomeModal = document.getElementById("welcomeModal");
      const welcomeOpen = document.getElementById("welcomeOpen");
      const welcomeClose = document.getElementById("welcomeClose");
      const welcomeCancel = document.getElementById("welcomeCancel");
      const welcomeSave = document.getElementById("welcomeSave");
      const welcomeText = document.getElementById("welcome_text");
      const welcomeAnimation = document.getElementById("welcome_animation");
      const welcomeFont = document.getElementById("welcome_font");
      const welcomeBackground = document.getElementById("welcome_background");
      const welcomePreview = document.getElementById("welcomePreview");

      function updateWelcomePreview() {
        // Remove all animation classes
        welcomePreview.style.animation = "none";
        // Remove all font classes
        welcomePreview.className = "welcome-font-modern";
        // Remove background classes
        welcomePreview.style.background = "white";
        
        // Update text content
        if (welcomeText) {
          welcomePreview.textContent = welcomeText.value || "Welcome to Dashboard";
        }
        
        // Add selected font
        const fontClass = "welcome-font-" + welcomeFont.value;
        welcomePreview.classList.add(fontClass);
        
        // Add selected background
        const bgValue = welcomeBackground.value;
        welcomePreview.style.background = "";
        const bgClass = "welcome-bg-" + bgValue;
        welcomePreview.classList.add(bgClass);
        
        // Add selected animation
        const animValue = welcomeAnimation.value;
        if (animValue !== "none") {
          const animName = "welcome-" + animValue;
          welcomePreview.style.animation = animName + " 1.5s ease-in-out";
        }
      }

      if (welcomeText) {
        welcomeText.addEventListener("input", updateWelcomePreview);
      }
      if (welcomeAnimation) {
        welcomeAnimation.addEventListener("change", updateWelcomePreview);
      }
      if (welcomeFont) {
        welcomeFont.addEventListener("change", updateWelcomePreview);
      }
      if (welcomeBackground) {
        welcomeBackground.addEventListener("change", updateWelcomePreview);
      }

      if (welcomeOpen) {
        welcomeOpen.addEventListener("click", () => {
          welcomeModal.classList.add("open");
          welcomeModal.setAttribute("aria-hidden", "false");
          // Load saved settings from localStorage
          const savedText = localStorage.getItem("welcomeText") || "Welcome to Dashboard";
          const savedAnimation = localStorage.getItem("welcomeAnimation") || "fade";
          const savedFont = localStorage.getItem("welcomeFont") || "modern";
          const savedBackground = localStorage.getItem("welcomeBackground") || "gradient-blue";
          
          if (welcomeText) welcomeText.value = savedText;
          welcomeAnimation.value = savedAnimation;
          welcomeFont.value = savedFont;
          welcomeBackground.value = savedBackground;
          
          updateWelcomePreview();
        });
      }

      function closeWelcomeModal() {
        if (welcomeModal) {
          welcomeModal.classList.remove("open");
          welcomeModal.setAttribute("aria-hidden", "true");
        }
      }

      if (welcomeClose) {
        welcomeClose.addEventListener("click", closeWelcomeModal);
      }
      if (welcomeCancel) {
        welcomeCancel.addEventListener("click", closeWelcomeModal);
      }
      if (welcomeSave) {
        welcomeSave.addEventListener("click", () => {
          localStorage.setItem("welcomeText", welcomeText.value || "Welcome to Dashboard");
          localStorage.setItem("welcomeAnimation", welcomeAnimation.value);
          localStorage.setItem("welcomeFont", welcomeFont.value);
          localStorage.setItem("welcomeBackground", welcomeBackground.value);
          alert("Welcome page style saved successfully!");
          closeWelcomeModal();
        });
      }
      if (welcomeModal) {
        welcomeModal.addEventListener("click", (event) => {
          if (event.target === welcomeModal) {
            closeWelcomeModal();
          }
        });
      }

      // Emergency Control Modal
      const emergencyModal = document.getElementById("emergencyModal");
      const emergencyStopBtn = document.getElementById("emergencyStopBtn");
      const emergencyStartBtn = document.getElementById("emergencyStartBtn");
      const emergencyClose = document.getElementById("emergencyClose");
      const emergencyCancel = document.getElementById("emergencyCancel");
      const emergencyForm = document.getElementById("emergencyForm");
      const emergencyAction = document.getElementById("emergencyAction");
      const emergencyUser = document.getElementById("emergency_user");
      const emergencyPassword = document.getElementById("emergency_password");

      function openEmergencyModal(action) {
        emergencyAction.value = action;
        emergencyUser.value = "";
        emergencyPassword.value = "";
        emergencyModal.classList.add("open");
        emergencyModal.setAttribute("aria-hidden", "false");
        emergencyUser.focus();
      }

      function closeEmergencyModal() {
        emergencyModal.classList.remove("open");
        emergencyModal.setAttribute("aria-hidden", "true");
      }

      if (emergencyStopBtn) {
        emergencyStopBtn.addEventListener("click", () => openEmergencyModal("stop"));
      }

      if (emergencyStartBtn) {
        emergencyStartBtn.addEventListener("click", () => openEmergencyModal("start"));
      }

      if (emergencyClose) {
        emergencyClose.addEventListener("click", closeEmergencyModal);
      }

      if (emergencyCancel) {
        emergencyCancel.addEventListener("click", closeEmergencyModal);
      }

      if (emergencyModal) {
        emergencyModal.addEventListener("click", (e) => {
          if (e.target === emergencyModal) {
            closeEmergencyModal();
          }
        });
      }

      if (emergencyForm) {
        emergencyForm.addEventListener("submit", async (e) => {
          e.preventDefault();
          const action = emergencyAction.value;
          const adminUser = emergencyUser.value;
          const adminPassword = emergencyPassword.value;
          const confirmBtn = document.getElementById("emergencyConfirm");
          const originalText = confirmBtn.innerHTML;

          if (!action || !adminUser || !adminPassword) {
            alert("Please fill in all fields");
            return;
          }

          // Show loading state
          confirmBtn.disabled = true;
          confirmBtn.innerHTML = '<span>⚡ Executing...</span>';
          confirmBtn.style.opacity = "0.8";

          try {
            // Send request with minimal timeout
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 30000);

            const response = await fetch("{{ url_for('emergency_control') }}", {
              method: "POST",
              headers: { "Content-Type": "application/x-www-form-urlencoded" },
              body: `action=${encodeURIComponent(action)}&admin_user=${encodeURIComponent(adminUser)}&admin_password=${encodeURIComponent(adminPassword)}`,
              signal: controller.signal
            });

            clearTimeout(timeoutId);
            const data = await response.json();
            
            if (data.success) {
              // Show success state IMMEDIATELY
              const actionText = action === "stop" ? "STOP ALL" : "START ALL";
              confirmBtn.innerHTML = '<span>✓ ' + actionText + ' Executed</span>';
              confirmBtn.style.background = "linear-gradient(135deg, #28a745 0%, #34c759 100%)";
              
              // Close modal immediately
              closeEmergencyModal();
              
              // Show success notification
              const successMsg = document.createElement('div');
              successMsg.style.cssText = `
                position: fixed;
                top: 20px;
                right: 20px;
                background: linear-gradient(135deg, #28a745 0%, #34c759 100%);
                color: white;
                padding: 16px 24px;
                border-radius: 12px;
                font-weight: 700;
                font-size: 13px;
                box-shadow: 0 8px 24px rgba(40, 167, 69, 0.35);
                z-index: 10000;
                animation: slideIn 0.4s ease-out;
              `;
              successMsg.textContent = '✓ Emergency ' + actionText + ' Initiated - Refreshing...';
              document.body.appendChild(successMsg);
              
              // Reload page to see updated status (after brief delay)
              setTimeout(() => {
                location.reload();
              }, 800);
            } else {
              // Show error state
              confirmBtn.innerHTML = '<span>✕ Failed</span>';
              confirmBtn.style.background = "linear-gradient(135deg, #dc3545 0%, #ff5a66 100%)";
              confirmBtn.disabled = false;
              confirmBtn.style.opacity = "1";
              
              setTimeout(() => {
                confirmBtn.innerHTML = originalText;
                confirmBtn.style.background = "";
              }, 2500);
              
              alert("Error: " + (data.message || "Failed to execute emergency control"));
            }
          } catch (e) {
            // Show error state
            confirmBtn.innerHTML = '<span>✕ Error</span>';
            confirmBtn.style.background = "linear-gradient(135deg, #dc3545 0%, #ff5a66 100%)";
            confirmBtn.disabled = false;
            confirmBtn.style.opacity = "1";
            
            setTimeout(() => {
              confirmBtn.innerHTML = originalText;
              confirmBtn.style.background = "";
            }, 2500);
            
            alert("Error: " + (e.message || "Failed to execute emergency control"));
            console.error(e);
          }
        });
      }

      // Add CSS animation for success message
      const style = document.createElement('style');
      style.textContent = `
        @keyframes slideIn {
          from {
            transform: translateX(400px);
            opacity: 0;
          }
          to {
            transform: translateX(0);
            opacity: 1;
          }
        }
      `;
      document.head.appendChild(style);

      const statusFilter = document.getElementById("statusFilter");
      function applyStatusFilter(value) {
        const target = (value || "all").toLowerCase();
        const rows = document.querySelectorAll("tbody tr[data-status]");
        rows.forEach((row) => {
          const status = (row.getAttribute("data-status") || "").toLowerCase();
          row.style.display = target === "all" || status === target ? "" : "none";
        });
      }
      if (statusFilter) {
        const saved = localStorage.getItem("dashboardStatusFilter");
        if (saved) {
          statusFilter.value = saved;
        }
        applyStatusFilter(statusFilter.value);
        statusFilter.addEventListener("change", (e) => {
          const value = e.target.value;
          localStorage.setItem("dashboardStatusFilter", value);
          applyStatusFilter(value);
          // Also reapply search filter with new status filter
          const searchInput = document.getElementById("scriptSearch");
          if (searchInput && searchInput.value) {
            applyScriptSearch(searchInput.value);
          }
        });
      }

      const scriptSearch = document.getElementById("scriptSearch");
      function applyScriptSearch(searchText) {
        const rows = document.querySelectorAll("tbody tr");
        const query = (searchText || "").toLowerCase().trim();
        const statusFilter = document.getElementById("statusFilter");
        const filterValue = statusFilter ? statusFilter.value : "all";
        let visibleCount = 0;
        
        rows.forEach((row) => {
          const scriptNameCell = row.querySelector(".script-name-cell");
          const scriptName = scriptNameCell ? scriptNameCell.textContent.toLowerCase() : "";
          const rowStatus = row.getAttribute("data-status");
          
          // Check if script name matches search query
          const matchesSearch = query === "" || scriptName.includes(query);
          
          // Check if row status matches filter
          const matchesStatus = filterValue === "all" || rowStatus === filterValue;
          
          // Show only if both conditions are met
          if (matchesSearch && matchesStatus) {
            row.style.display = "";
            visibleCount++;
          } else {
            row.style.display = "none";
          }
        });
        
        // Show search result message
        const messageEl = document.querySelector(".search-result-message");
        if (messageEl) {
          if (query) {
            if (visibleCount > 0) {
              messageEl.textContent = `Found ${visibleCount} result(s)`;
              messageEl.style.color = "#28a745";
              messageEl.style.display = "inline-block";
            } else {
              messageEl.textContent = "No results found";
              messageEl.style.color = "#dc3545";
              messageEl.style.display = "inline-block";
            }
          } else {
            messageEl.style.display = "none";
          }
        }
      }
      if (scriptSearch) {
        scriptSearch.addEventListener("input", (e) => {
          applyScriptSearch(e.target.value);
        });
        scriptSearch.addEventListener("keypress", (e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            applyScriptSearch(e.target.value);
          }
        });
      }

      // Edit Script Modal
      function openEditScriptModal(scriptId, main, sub) {
        const modal = document.getElementById("editScriptModal");
        if (!modal) return;
        document.getElementById("editScriptId").value = scriptId;
        document.getElementById("editScriptMain").value = main;
        document.getElementById("editScriptSub").value = sub;
        modal.classList.add("open");
        modal.setAttribute("aria-hidden", "false");
      }

      function closeEditScriptModal() {
        const modal = document.getElementById("editScriptModal");
        if (!modal) return;
        modal.classList.remove("open");
        modal.setAttribute("aria-hidden", "true");
      }

      // Script Name Editing
      let currentEditingCell = null;
      let currentScriptId = null;

      function editScriptName(scriptId, cell) {
        if (currentEditingCell) return; // Prevent multiple edits
        
        currentScriptId = scriptId;
        currentEditingCell = cell;
        const originalName = cell.textContent.trim();
        
        cell.classList.add("editing");
        cell.innerHTML = `<input type="text" class="script-name-input" value="${originalName}" id="scriptNameInput" />`;
        
        const input = cell.querySelector("#scriptNameInput");
        input.focus();
        input.select();
        
        function saveChanges() {
          const newName = input.value.trim();
          if (newName && newName !== originalName) {
            fetch("{{ url_for('update_script_name') }}", {
              method: "POST",
              headers: { "Content-Type": "application/x-www-form-urlencoded" },
              body: `script_id=${scriptId}&new_name=${encodeURIComponent(newName)}`
            })
            .then(r => r.json())
            .then(data => {
              if (data.success) {
                cell.textContent = newName;
              } else {
                cell.textContent = originalName;
                alert("Failed to update name: " + (data.message || "Unknown error"));
              }
              cell.classList.remove("editing");
              currentEditingCell = null;
              currentScriptId = null;
            })
            .catch(e => {
              cell.textContent = originalName;
              cell.classList.remove("editing");
              currentEditingCell = null;
              currentScriptId = null;
              console.error("Error:", e);
            });
          } else {
            cell.textContent = originalName;
            cell.classList.remove("editing");
            currentEditingCell = null;
            currentScriptId = null;
          }
        }
        
        input.addEventListener("blur", saveChanges);
        input.addEventListener("keypress", (e) => {
          if (e.key === "Enter") {
            saveChanges();
          } else if (e.key === "Escape") {
            cell.textContent = originalName;
            cell.classList.remove("editing");
            currentEditingCell = null;
            currentScriptId = null;
          }
        });
      }

      document.addEventListener("DOMContentLoaded", function() {
        const editScriptModal = document.getElementById("editScriptModal");
        const editScriptCancel = document.getElementById("editScriptCancel");
        
        if (editScriptCancel) {
          editScriptCancel.addEventListener("click", closeEditScriptModal);
        }

        if (editScriptModal) {
          editScriptModal.addEventListener("click", (e) => {
            if (e.target === editScriptModal) {
              closeEditScriptModal();
            }
          });
        }
      });

      // Handle sub-navigation on touch/mobile devices
      document.querySelectorAll('.nav-item').forEach(navItem => {
        navItem.addEventListener('touchstart', function(e) {
          const subNav = this.querySelector('.sub-nav');
          if (subNav && !this.classList.contains('show-subs')) {
            e.preventDefault();
            this.classList.add('show-subs');
          }
        });
        
        navItem.addEventListener('click', function(e) {
          const navLink = this.querySelector('.nav-link');
          const subNav = this.querySelector('.sub-nav');
          // If clicking the main link and there are subs, toggle visibility
          if (e.target === navLink || e.target.closest('.nav-link')) {
            if (subNav && !window.matchMedia('(hover: hover)').matches) {
              // On touch devices, prevent default and toggle
              if (!this.classList.contains('show-subs')) {
                e.preventDefault();
                this.classList.add('show-subs');
              }
            }
          }
        });
      });

      // Close subs when clicking outside
      document.addEventListener('click', function(e) {
         if (!e.target.closest('.nav-item')) {
           document.querySelectorAll('.nav-item.show-subs').forEach(item => {
             item.classList.remove('show-subs');
           });
         }
       });

      // Navigation right-click context menu
      let contextMenuTarget = null;
      const navContextMenu = document.createElement('div');
      navContextMenu.id = 'navContextMenu';
      navContextMenu.className = 'nav-context-menu';
      navContextMenu.innerHTML = `
        <a href="#" class="context-menu-item" id="renameNavItem">
          <span class="icon">✏️</span> Rename
        </a>
      `;
      navContextMenu.style.display = 'none';
      navContextMenu.style.position = 'fixed';
      navContextMenu.style.zIndex = '10000';
      document.body.appendChild(navContextMenu);

      document.addEventListener('contextmenu', function(e) {
        const navItem = e.target.closest('[data-nav-item]');
        const subNavItem = e.target.closest('[data-sub-nav-item]');
        const userRole = document.body.getAttribute('data-user-role');
        
        // Only show context menu for ADMIN users
        if ((navItem || subNavItem) && userRole === 'ADMIN') {
          e.preventDefault();
          contextMenuTarget = navItem || subNavItem;
          console.log('[CONTEXT] Target:', {
            navItem: navItem?.getAttribute('data-nav-item'),
            subNavItem: subNavItem?.getAttribute('data-sub-nav-item'),
            userRole: userRole,
            target: contextMenuTarget
          });
          navContextMenu.style.left = e.pageX + 'px';
          navContextMenu.style.top = e.pageY + 'px';
          navContextMenu.style.display = 'block';
        }
      });

      document.addEventListener('click', function(e) {
        if (navContextMenu.style.display === 'block' && !e.target.closest('.nav-context-menu')) {
          navContextMenu.style.display = 'none';
        }
      });

      document.getElementById('renameNavItem').addEventListener('click', function(e) {
         e.preventDefault();
         navContextMenu.style.display = 'none';
         if (!contextMenuTarget) {
           console.log('[RENAME] No context menu target');
           return;
         }
         
         const navItem = contextMenuTarget.getAttribute('data-nav-item');
         const subNavItem = contextMenuTarget.getAttribute('data-sub-nav-item');
         
         console.log('[RENAME] Click detected:', { navItem, subNavItem });
         
         if (navItem && !subNavItem) {
           // Main navigation rename
           console.log('[RENAME] Opening main nav modal for:', navItem);
           openRenameNavModal('main', navItem, null);
         } else if (subNavItem) {
           // Sub-navigation rename - find parent main nav
           const parentItem = contextMenuTarget.closest('[data-nav-item]');
           const mainNav = parentItem ? parentItem.getAttribute('data-nav-item') : null;
           console.log('[RENAME] Opening sub nav modal for:', { mainNav, subNavItem });
           if (mainNav) {
             openRenameNavModal('sub', mainNav, subNavItem);
           }
         }
       });

      function openRenameNavModal(type, mainNav, subNav) {
        console.log('[MODAL] Opening with:', { type, mainNav, subNav });
        const modal = document.getElementById('renameNavModal');
        if (!modal) {
          console.log('[MODAL] Modal element not found!');
          return;
        }
        
        document.getElementById('renameNavType').value = type;
        document.getElementById('renameNavMain').value = mainNav;
        document.getElementById('renameNavOld').value = subNav || mainNav;
        document.getElementById('renameNavLabel').textContent = type === 'main' ? mainNav : subNav;
        document.getElementById('renameNavOldName').textContent = type === 'main' ? mainNav : subNav;
        
        const newInput = document.getElementById('renameNavNew');
        newInput.value = '';
        newInput.focus();
        
        modal.classList.add('open');
        modal.setAttribute('aria-hidden', 'false');
        console.log('[MODAL] Modal opened with values:', {
          type: document.getElementById('renameNavType').value,
          main: document.getElementById('renameNavMain').value,
          old: document.getElementById('renameNavOld').value
        });
      }

      function closeRenameNavModal() {
        const modal = document.getElementById('renameNavModal');
        if (!modal) return;
        modal.classList.remove('open');
        modal.setAttribute('aria-hidden', 'true');
      }

      async function handleRenameSubmit() {
        console.log('[RENAME_SUBMIT] Handler called');
        
        const type = document.getElementById('renameNavType').value;
        const mainNav = document.getElementById('renameNavMain').value;
        const oldName = document.getElementById('renameNavOld').value;
        const newName = document.getElementById('renameNavNew').value.trim();
        
        console.log('[RENAME_SUBMIT] Values:', { type, mainNav, oldName, newName });
        
        if (!newName) {
          alert('Please enter a new name');
          return;
        }
        
        const endpoint = type === 'main' ? '/nav/rename-main' : '/nav/rename-sub';
        const body = type === 'main' 
          ? `old_name=${encodeURIComponent(oldName)}&new_name=${encodeURIComponent(newName)}`
          : `main_name=${encodeURIComponent(mainNav)}&old_name=${encodeURIComponent(oldName)}&new_name=${encodeURIComponent(newName)}`;
        
        console.log('[RENAME_SUBMIT] Sending to:', endpoint, 'with body:', body);
        
        try {
          const response = await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: body
          });
          
          console.log('[RENAME_SUBMIT] Response status:', response.status, response.ok);
          
          let data = {};
          try {
            data = await response.json();
          } catch (e) {
            data = { success: response.ok };
          }
          
          console.log('[RENAME_SUBMIT] Response data:', data);
          
          if (data.success !== false && response.ok) {
            closeRenameNavModal();
            const msg = document.createElement('div');
            msg.style.cssText = `
              position: fixed;
              top: 20px;
              right: 20px;
              background: linear-gradient(135deg, #28a745 0%, #34c759 100%);
              color: white;
              padding: 16px 24px;
              border-radius: 12px;
              font-weight: 700;
              font-size: 13px;
              box-shadow: 0 8px 24px rgba(40, 167, 69, 0.35);
              z-index: 10000;
            `;
            msg.textContent = '✓ ' + (data.message || 'Navigation renamed successfully');
            document.body.appendChild(msg);
            
            setTimeout(() => {
              location.reload();
            }, 1500);
          } else {
            alert('Error: ' + (data.message || 'Failed to rename'));
          }
        } catch (error) {
          console.error('Rename error:', error);
          alert('Error: ' + error.message);
        }
      }

      // Rename Navigation - Using event delegation for button click (backup)
      document.addEventListener('click', async function(e) {
        if (e.target && e.target.id === 'renameNavSubmit') {
          e.preventDefault();
          console.log('[RENAME_SUBMIT] Button clicked');
          
          const type = document.getElementById('renameNavType').value;
          const mainNav = document.getElementById('renameNavMain').value;
          const oldName = document.getElementById('renameNavOld').value;
          const newName = document.getElementById('renameNavNew').value.trim();
          
          console.log('[RENAME_SUBMIT] Values:', { type, mainNav, oldName, newName });
          
          if (!newName) {
            alert('Please enter a new name');
            return;
          }
          
          const endpoint = type === 'main' ? '/nav/rename-main' : '/nav/rename-sub';
          const body = type === 'main' 
            ? `old_name=${encodeURIComponent(oldName)}&new_name=${encodeURIComponent(newName)}`
            : `main_name=${encodeURIComponent(mainNav)}&old_name=${encodeURIComponent(oldName)}&new_name=${encodeURIComponent(newName)}`;
          
          console.log('[RENAME_SUBMIT] Sending to:', endpoint, 'with body:', body);
          
          try {
            const response = await fetch(endpoint, {
              method: 'POST',
              headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
              body: body
            });
            
            console.log('[RENAME_SUBMIT] Response status:', response.status, response.ok);
            
            let data = {};
            try {
              data = await response.json();
            } catch (e) {
              // Response isn't JSON
              data = { success: response.ok };
            }
            
            console.log('[RENAME_SUBMIT] Response data:', data);
            
            if (data.success !== false && response.ok) {
              closeRenameNavModal();
              // Show success message
              const msg = document.createElement('div');
              msg.style.cssText = `
                position: fixed;
                top: 20px;
                right: 20px;
                background: linear-gradient(135deg, #28a745 0%, #34c759 100%);
                color: white;
                padding: 16px 24px;
                border-radius: 12px;
                font-weight: 700;
                font-size: 13px;
                box-shadow: 0 8px 24px rgba(40, 167, 69, 0.35);
                z-index: 10000;
              `;
              msg.textContent = '✓ ' + (data.message || 'Navigation renamed successfully');
              document.body.appendChild(msg);
              
              setTimeout(() => {
                location.reload();
              }, 1500);
            } else {
              alert('Error: ' + (data.message || 'Failed to rename'));
            }
          } catch (error) {
            console.error('Rename error:', error);
            alert('Error: ' + error.message);
          }
        }
      });

      const renameNavCancel = document.getElementById('renameNavCancel');
      if (renameNavCancel) {
       renameNavCancel.addEventListener('click', closeRenameNavModal);
      }

      const renameNavModal = document.getElementById('renameNavModal');
      if (renameNavModal) {
       renameNavModal.addEventListener('click', (e) => {
         if (e.target === renameNavModal) {
           closeRenameNavModal();
         }
       });
      }

      // Drag and drop reordering - WIN2 only
      const userRole = document.body.getAttribute('data-user-role');
      if (userRole === 'ADMIN') {
        let draggedElement = null;
        const navItems = document.querySelectorAll('.nav-item.draggable-enabled');
        
        navItems.forEach(item => {
          item.addEventListener('dragstart', (e) => {
            draggedElement = item;
            item.classList.add('dragging');
            e.dataTransfer.effectAllowed = 'move';
            console.log('[DRAG] Started dragging:', item.getAttribute('data-nav-item'));
          });
          
          item.addEventListener('dragend', (e) => {
            item.classList.remove('dragging');
            navItems.forEach(i => {
              i.classList.remove('drag-over', 'drag-over-bottom');
            });
            draggedElement = null;
            console.log('[DRAG] Ended dragging');
          });
          
          item.addEventListener('dragover', (e) => {
            e.preventDefault();
            e.dataTransfer.dropEffect = 'move';
            
            if (draggedElement && draggedElement !== item) {
              const rect = item.getBoundingClientRect();
              const midpoint = rect.top + rect.height / 2;
              
              item.classList.remove('drag-over', 'drag-over-bottom');
              if (e.clientY < midpoint) {
                item.classList.add('drag-over');
              } else {
                item.classList.add('drag-over-bottom');
              }
            }
          });
          
          item.addEventListener('dragleave', (e) => {
            if (e.target === item) {
              item.classList.remove('drag-over', 'drag-over-bottom');
            }
          });
          
          item.addEventListener('drop', async (e) => {
            e.preventDefault();
            e.stopPropagation();
            
            if (!draggedElement || draggedElement === item) {
              item.classList.remove('drag-over', 'drag-over-bottom');
              return;
            }
            
            const draggedName = draggedElement.getAttribute('data-nav-item');
            const targetName = item.getAttribute('data-nav-item');
            const rect = item.getBoundingClientRect();
            const midpoint = rect.top + rect.height / 2;
            const insertBefore = e.clientY < midpoint;
            
            console.log('[DROP] Reordering:', { draggedName, targetName, insertBefore });
            
            // Visual reordering
            if (insertBefore) {
              item.parentNode.insertBefore(draggedElement, item);
            } else {
              item.parentNode.insertBefore(draggedElement, item.nextSibling);
            }
            
            item.classList.remove('drag-over', 'drag-over-bottom');
            
            // Send to backend
            try {
              const response = await fetch('/nav/reorder', {
                method: 'POST',
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                body: `dragged=${encodeURIComponent(draggedName)}&target=${encodeURIComponent(targetName)}&before=${insertBefore}`
              });
              
              const data = await response.json();
              if (data.success) {
                console.log('[DROP] Reorder successful');
              } else {
                alert('Error: ' + (data.message || 'Failed to reorder'));
              }
            } catch (error) {
              console.error('[DROP] Error:', error);
              alert('Error reordering navigation');
            }
          });
        });
      }

      // Real-time CPU monitoring
      async function updateCPUUsage() {
        try {
          const response = await fetch('/api/cpu-usage');
          const data = await response.json();
          if (data.success) {
            const cpuValue = document.getElementById('cpuValue');
            const cpuFill = document.getElementById('cpuFill');
            if (cpuValue && cpuFill) {
              cpuValue.textContent = data.cpu_usage + '%';
              cpuFill.style.width = data.cpu_usage + '%';
              
              // Change color based on usage
              if (data.cpu_usage > 80) {
                cpuValue.style.color = '#dc3545'; // Red
                cpuFill.style.backgroundColor = '#dc3545';
              } else if (data.cpu_usage > 50) {
                cpuValue.style.color = '#ffc107'; // Yellow
                cpuFill.style.backgroundColor = '#ffc107';
              } else {
                cpuValue.style.color = '#28a745'; // Green
                cpuFill.style.backgroundColor = '#28a745';
              }
            }
          }
        } catch (error) {
          console.error('[CPU] Error updating CPU usage:', error);
        }
      }

      // Update CPU usage every 2 seconds
      setInterval(updateCPUUsage, 2000);
      </script>
      <style>
      .nav-context-menu {
        background: linear-gradient(135deg, #0f2a3a 0%, #0a1f2e 100%);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 8px;
        box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3);
        min-width: 140px;
        overflow: hidden;
      }
      .context-menu-item {
        display: flex;
        align-items: center;
        gap: 10px;
        padding: 10px 16px;
        color: #a8c5d1;
        text-decoration: none;
        transition: all 150ms ease;
        font-size: 13px;
      }
      .context-menu-item:hover {
        background: rgba(10, 159, 181, 0.2);
        color: #fff;
      }
      .context-menu-item .icon {
        font-size: 14px;
      }
      </style>
      <div class="modal" id="editScriptModal" aria-hidden="true">
        <div class="modal-card">
          <div class="modal-header">
            <span>Confirm Admin Access</span>
            <button class="btn-ghost" type="button" onclick="closeEditScriptModal();">X</button>
          </div>
          <form class="modal-body" id="editScriptForm" method="post" action="{{ url_for('edit_script_verify') }}">
            <div class="modal-note">Enter admin credentials to edit the script.</div>
            <input type="hidden" id="editScriptId" name="script_id" />
            <input type="hidden" id="editScriptMain" name="main" />
            <input type="hidden" id="editScriptSub" name="sub" />
            <label for="edit_admin_user">Admin User</label>
            <input id="edit_admin_user" name="admin_user" type="text" placeholder="Admin User" />
            <label for="edit_admin_password">Admin Password</label>
            <input id="edit_admin_password" name="admin_password" type="password" placeholder="Admin Password" />
            <div class="modal-footer">
              <button class="btn-ghost" type="button" id="editScriptCancel">Cancel</button>
              <button class="btn-link" type="submit">Confirm</button>
            </div>
          </form>
        </div>
      </div>

      <div class="modal" id="renameNavModal" aria-hidden="true">
        <div class="modal-card">
          <div class="modal-header">
            <span>Rename Navigation</span>
            <button class="btn-ghost" type="button" onclick="closeRenameNavModal();">X</button>
          </div>
          <div class="modal-body" id="renameNavForm">
            <div class="modal-note">Rename <strong id="renameNavLabel"></strong> (all scripts will be updated automatically)</div>
            <input type="hidden" id="renameNavType" value="main" />
            <input type="hidden" id="renameNavMain" value="" />
            <input type="hidden" id="renameNavOld" value="" />
            <label for="renameNavNew">New Name</label>
            <input id="renameNavNew" type="text" placeholder="Enter new name" required />
            <div style="font-size: 12px; color: #666; margin-top: 8px;">
              Current: <strong id="renameNavOldName"></strong>
            </div>
            <div class="modal-footer">
              <button class="btn-ghost" type="button" id="renameNavCancel" onclick="closeRenameNavModal()">Cancel</button>
              <button class="btn-link" type="button" id="renameNavSubmit" onclick="handleRenameSubmit()">Rename</button>
            </div>
          </div>
        </div>
      </div>
      </body>
      </html>
"""

LOGIN_PAGE = """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <link rel="icon" type="image/svg+xml" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><defs><linearGradient id='g' x1='0%' y1='0%' x2='100%' y2='100%'><stop offset='0%' style='stop-color:%230a9fb5'/><stop offset='100%' style='stop-color:%230a6f86'/></linearGradient></defs><rect width='32' height='32' rx='6' fill='url(%23g)'/><circle cx='8' cy='8' r='2.5' fill='white' opacity='0.9'/><circle cx='24' cy='8' r='2' fill='%2300ff99' opacity='0.95'/><circle cx='24' cy='16' r='2' fill='%23ff6b6b' opacity='0.85'/><circle cx='24' cy='24' r='2' fill='%23ffd700' opacity='0.75'/><line x1='8' y1='5.5' x2='8' y2='4' stroke='white' stroke-width='1.2' opacity='0.8'/><line x1='8' y1='13.5' x2='8' y2='12' stroke='white' stroke-width='1.2' opacity='0.6'/><line x1='8' y1='21.5' x2='8' y2='20' stroke='white' stroke-width='1.2' opacity='0.4'/><rect x='14' y='11' width='6' height='10' rx='1' fill='none' stroke='white' stroke-width='0.8' opacity='0.6'/></svg>">
    <title>Dashboard Login</title>
    <style>
      :root {
        --ink: #0b1220;
        --muted: #5f6b7a;
        --panel: #ffffff;
        --border: #d7dee6;
        --brand: #0a6f86;
        --brand-light: #0d8fa3;
        --bg: #e9eef4;
        --font-body: "Bahnschrift", "Candara", "Trebuchet MS", sans-serif;
        --font-display: "Rockwell", "Constantia", "Georgia", serif;
        --font-mono: "Cascadia Mono", "Consolas", "Courier New", monospace;
      }
      * { box-sizing: border-box; }
      body {
        margin: 0;
        font-family: var(--font-body);
        background: {{ background_style|safe }};
        color: var(--ink);
        min-height: 100vh;
        display: grid;
        place-items: center;
        padding: 24px;
      }
      .card {
        width: 100%;
        max-width: 420px;
        background: rgba(255, 255, 255, 0.98);
        border-radius: 20px;
        border: 1px solid rgba(13, 24, 40, 0.1);
        box-shadow: 0 30px 60px rgba(15, 23, 42, 0.2);
        padding: 36px;
        position: relative;
        overflow: hidden;
        backdrop-filter: blur(10px);
      }
      .card::before {
        content: "";
        position: absolute;
        inset: 0;
        background: linear-gradient(135deg, rgba(10, 111, 134, 0.08), transparent 45%);
        pointer-events: none;
      }
      .card-content {
        position: relative;
        z-index: 1;
      }
      .logo-area {
        text-align: center;
        margin-bottom: 24px;
      }
      .logo-icon {
        font-size: 40px;
        margin-bottom: 12px;
      }
      h1 {
        margin: 0 0 6px;
        font-size: 24px;
        font-weight: 700;
        text-align: center;
        letter-spacing: -0.3px;
        color: var(--ink);
        font-family: var(--font-display);
      }
      .subtitle {
        font-size: 13px;
        color: var(--muted);
        text-align: center;
        font-weight: 500;
        margin-bottom: 8px;
      }
      .form-group {
        margin-bottom: 18px;
      }
      label {
        display: block;
        font-size: 12px;
        color: var(--muted);
        margin-bottom: 8px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.3px;
      }
      input {
        width: 100%;
        padding: 12px 14px;
        border-radius: 10px;
        border: 1.5px solid rgba(13, 24, 40, 0.15);
        background: #f8fafc;
        font-size: 14px;
        transition: all 200ms ease;
        color: var(--ink);
      }
      input::placeholder {
        color: rgba(95, 107, 122, 0.5);
      }
      input:hover {
        border-color: rgba(10, 111, 134, 0.3);
        background: #f0f6fa;
      }
      input:focus {
        outline: none;
        border-color: var(--brand);
        box-shadow: 0 0 0 4px rgba(10, 111, 134, 0.1);
        background: #fff;
      }
      .btn {
        width: 100%;
        border: none;
        border-radius: 12px;
        padding: 13px 14px;
        font-weight: 700;
        font-size: 13px;
        cursor: pointer;
        background: linear-gradient(135deg, var(--brand) 0%, var(--brand-light) 100%);
        color: #fff;
        text-transform: uppercase;
        letter-spacing: 0.6px;
        box-shadow: 0 12px 24px rgba(10, 111, 134, 0.3);
        transition: all 200ms ease;
        position: relative;
        overflow: hidden;
      }
      .btn::before {
        content: "";
        position: absolute;
        inset: 0;
        background: radial-gradient(circle at 50% 50%, rgba(255, 255, 255, 0.2), transparent);
        opacity: 0;
        transition: opacity 300ms ease;
      }
      .btn:hover {
        transform: translateY(-2px);
        box-shadow: 0 16px 32px rgba(10, 111, 134, 0.35);
      }
      .btn:active {
        transform: translateY(0);
      }
      .divider {
        margin: 20px 0;
        text-align: center;
        font-size: 12px;
        color: var(--muted);
      }
      .link {
        text-align: center;
        font-size: 12px;
      }
      .link a {
        color: var(--brand);
        text-decoration: none;
        font-weight: 700;
        transition: all 150ms ease;
      }
      .link a:hover {
        color: var(--brand-light);
        text-decoration: underline;
      }
      .message {
        background: linear-gradient(135deg, #fff3cd 0%, #fffaeb 100%);
        border: 1px solid #ffe5a1;
        color: #664d03;
        padding: 12px 14px;
        border-radius: 10px;
        font-size: 12px;
        margin-bottom: 18px;
        border-left: 3px solid #ffc107;
        font-weight: 500;
      }
      .message.error {
        background: linear-gradient(135deg, #fee2e2 0%, #fef2f2 100%);
        border-color: #fca5a5;
        color: #991b1b;
        border-left-color: #dc2626;
      }
      .message.success {
        background: linear-gradient(135deg, #dcfce7 0%, #f0fdf4 100%);
        border-color: #a7f3d0;
        color: #166534;
        border-left-color: #16a34a;
      }
      .password-wrapper {
        position: relative;
        display: flex;
        align-items: center;
      }
      .password-wrapper input {
        width: 100%;
        padding-right: 40px;
      }
      .password-toggle {
        position: absolute;
        right: 12px;
        background: none;
        border: none;
        cursor: pointer;
        font-size: 18px;
        color: var(--muted);
        padding: 6px;
        transition: color 150ms ease;
        display: flex;
        align-items: center;
        justify-content: center;
      }
      .password-toggle:hover {
        color: var(--brand);
      }
      @media (max-width: 480px) {
        .card {
          padding: 28px 20px;
        }
        h1 {
          font-size: 22px;
        }
        .logo-icon {
          font-size: 36px;
        }
      }
    </style>
  </head>
  <body>
    <form class="card" method="post">
      <div class="card-content">
        <div class="logo-area">
          <div class="logo-icon">🔐</div>
          <h1>Dashboard</h1>
          <div class="subtitle">Secure Access Portal</div>
        </div>
        
        {% if message %}
        <div class="message {% if 'success' in message.lower() %}success{% elif 'error' in message.lower() %}error{% endif %}">
          {{ message }}
        </div>
        {% endif %}
        
        <div class="form-group">
          <label for="username">👤 User Name</label>
          <input 
            id="username" 
            name="username" 
            type="text" 
            autocomplete="username"
            placeholder="Enter your username"
            required 
          />
        </div>
        
        <div class="form-group">
          <label for="password">🔒 Password</label>
          <div class="password-wrapper">
            <input 
              id="password" 
              name="password" 
              type="password" 
              autocomplete="current-password"
              placeholder="Enter your password"
              required 
            />
            <button type="button" class="password-toggle" id="passwordToggle" tabindex="-1">👁</button>
          </div>
        </div>
        
        <button class="btn" type="submit">🚪 LOGIN</button>
        
        <div class="divider">━━━━━━━━━━━━━━━</div>
        
        <div class="link">
          Don't have an account? <a href="{{ url_for('register') }}">Create one</a>
        </div>
      </div>
    </form>
    <script>
      const passwordInput = document.getElementById('password');
      const passwordToggle = document.getElementById('passwordToggle');
      
      if (passwordToggle) {
        passwordToggle.addEventListener('click', (e) => {
          e.preventDefault();
          const isPassword = passwordInput.type === 'password';
          passwordInput.type = isPassword ? 'text' : 'password';
          passwordToggle.textContent = isPassword ? '🙈' : '👁';
        });
      }
    </script>
  </body>
</html>
"""

WELCOME_PAGE = """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <link rel="icon" type="image/svg+xml" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><defs><linearGradient id='g' x1='0%' y1='0%' x2='100%' y2='100%'><stop offset='0%' style='stop-color:%230a9fb5'/><stop offset='100%' style='stop-color:%230a6f86'/></linearGradient></defs><rect width='32' height='32' rx='6' fill='url(%23g)'/><circle cx='8' cy='8' r='2.5' fill='white' opacity='0.9'/><circle cx='24' cy='8' r='2' fill='%2300ff99' opacity='0.95'/><circle cx='24' cy='16' r='2' fill='%23ff6b6b' opacity='0.85'/><circle cx='24' cy='24' r='2' fill='%23ffd700' opacity='0.75'/><line x1='8' y1='5.5' x2='8' y2='4' stroke='white' stroke-width='1.2' opacity='0.8'/><line x1='8' y1='13.5' x2='8' y2='12' stroke='white' stroke-width='1.2' opacity='0.6'/><line x1='8' y1='21.5' x2='8' y2='20' stroke='white' stroke-width='1.2' opacity='0.4'/><rect x='14' y='11' width='6' height='10' rx='1' fill='none' stroke='white' stroke-width='0.8' opacity='0.6'/></svg>">
    <title>Welcome</title>
    <style>
      :root {
        --ink: #0b1220;
        --brand: #0a6f86;
        --brand-light: #0d8fa3;
        --bg: #e9eef4;
        --font-body: "Bahnschrift", "Candara", "Trebuchet MS", sans-serif;
        --font-display: "Rockwell", "Constantia", "Georgia", serif;
        --font-mono: "Cascadia Mono", "Consolas", "Courier New", monospace;
        --welcome-bg: linear-gradient(140deg, #d8eef3 0%, #f4f7fb 45%, #cfe7f0 100%);
      }
      * { box-sizing: border-box; }
      html, body {
        height: 100%;
      }
      body {
        margin: 0;
        font-family: var(--font-body);
        background:
          radial-gradient(ellipse 1500px 900px at 25% 35%, rgba(30, 150, 200, 0.35) 0%, transparent 45%),
          radial-gradient(ellipse 1200px 1000px at 75% 25%, rgba(100, 50, 180, 0.3) 0%, transparent 50%),
          radial-gradient(ellipse 800px 600px at 50% 50%, rgba(0, 100, 180, 0.25) 0%, transparent 45%),
          radial-gradient(ellipse 1000px 800px at 80% 70%, rgba(20, 120, 200, 0.2) 0%, transparent 50%),
          radial-gradient(ellipse 1300px 900px at 10% 60%, rgba(80, 40, 150, 0.25) 0%, transparent 48%),
          radial-gradient(ellipse 2000px 1500px at 50% 50%, #001a40 0%, #0a0e20 50%, #000000 100%);
        background-color: #000000;
        background-attachment: fixed;
        display: grid;
        place-items: center;
        color: var(--ink);
        overflow: hidden;
        position: relative;
      }
      body::before {
        content: '';
        position: absolute;
        inset: 0;
        background-image: 
          radial-gradient(2px 2px at 10px 20px, rgba(220, 240, 255, 0.9), transparent 2px),
          radial-gradient(1px 1px at 60px 70px, rgba(200, 220, 255, 0.7), transparent 1px),
          radial-gradient(1.5px 1.5px at 50px 50px, rgba(230, 245, 255, 0.8), transparent 1.5px),
          radial-gradient(1px 1px at 130px 80px, rgba(210, 230, 255, 0.6), transparent 1px),
          radial-gradient(2px 2px at 90px 10px, rgba(240, 250, 255, 0.85), transparent 2px),
          radial-gradient(1px 1px at 30px 80px, rgba(200, 220, 255, 0.5), transparent 1px),
          radial-gradient(1px 1px at 130px 50px, rgba(220, 235, 255, 0.65), transparent 1px),
          radial-gradient(1.5px 1.5px at 70px 120px, rgba(200, 215, 255, 0.75), transparent 1.5px),
          radial-gradient(1px 1px at 150px 30px, rgba(210, 230, 255, 0.6), transparent 1px),
          radial-gradient(2px 2px at 20px 90px, rgba(230, 245, 255, 0.8), transparent 2px),
          radial-gradient(1px 1px at 110px 40px, rgba(200, 220, 255, 0.55), transparent 1px),
          radial-gradient(1.5px 1.5px at 80px 100px, rgba(220, 240, 255, 0.7), transparent 1.5px);
        background-size: 250px 280px;
        background-position: 0 0, 40px 60px, 130px 270px, 70px 100px, 0 40px, 60px 20px, 150px 140px, 90px 60px, 40px 150px, 120px 10px, 30px 110px, 170px 90px;
        pointer-events: none;
        animation: starTwinkle 3.5s ease-in-out infinite;
      }
      body::after {
        content: '';
        position: absolute;
        inset: 0;
        background: 
          radial-gradient(ellipse 1000px 700px at 30% 40%, rgba(30, 150, 220, 0.25) 0%, transparent 35%),
          radial-gradient(ellipse 900px 800px at 70% 25%, rgba(138, 43, 226, 0.2) 0%, transparent 40%),
          radial-gradient(ellipse 1100px 600px at 50% 65%, rgba(0, 191, 255, 0.2) 0%, transparent 38%),
          radial-gradient(ellipse 800px 900px at 15% 70%, rgba(80, 60, 180, 0.15) 0%, transparent 42%),
          radial-gradient(ellipse 1200px 700px at 85% 45%, rgba(20, 140, 200, 0.18) 0%, transparent 40%);
        pointer-events: none;
        animation: nebulaPulse 9s ease-in-out infinite;
      }
      .stage {
        width: min(92vw, 980px);
        text-align: center;
        padding: 40px 20px;
        position: relative;
        z-index: 10;
      }
      .welcome {
        font-size: clamp(32px, 6vw, 72px);
        font-weight: 900;
        letter-spacing: 2px;
        text-transform: uppercase;
        color: #0a9fb5;
        font-family: var(--font-display);
        white-space: nowrap;
        animation: rgbColorCycle 4s ease-in-out infinite;
        filter: drop-shadow(0 0 8px rgba(10, 159, 181, 0.6)) drop-shadow(0 4px 12px rgba(10, 111, 134, 0.3));
      }
      .welcome.wave {
        display: inline-block;
      }
      .welcome.wave .wave-char {
        display: inline-block;
        animation: waveText 1.6s ease-in-out infinite;
        animation-delay: calc(var(--i) * 0.08s);
        transform-origin: center bottom;
      }
      @keyframes waveText {
        0%, 100% { transform: translateY(0); }
        50% { transform: translateY(-12px); }
      }
      .sub {
        margin-top: 12px;
        font-size: clamp(12px, 1.6vw, 16px);
        color: #ffffff;
        letter-spacing: 0.6px;
        font-weight: 700;
        display: inline-block;
        background: rgba(10, 111, 134, 0.85);
        padding: 8px 16px;
        border-radius: 999px;
        box-shadow: 0 0 12px rgba(0, 212, 255, 0.4), 0 6px 16px rgba(10, 20, 30, 0.3);
        animation: rgbShadowCycle 4s ease-in-out infinite;
      }
      .spark {
        position: absolute;
        inset: -40% -20%;
        background:
          radial-gradient(circle at 20% 30%, rgba(10,159,181,0.22), transparent 40%),
          radial-gradient(circle at 70% 70%, rgba(10,111,134,0.18), transparent 45%),
          repeating-linear-gradient(135deg, rgba(10,111,134,0.05) 0 2px, transparent 2px 10px);
        animation: slowFloat 7s ease-in-out infinite;
        pointer-events: none;
      }
      @keyframes textRun {
        0% {
          background-position: 0% 50%;
          transform: translateX(-12px);
          text-shadow: 0 10px 26px rgba(10,111,134,0.2);
        }
        50% {
          background-position: 100% 50%;
          transform: translateX(12px);
          text-shadow: 0 14px 30px rgba(10,159,181,0.35);
        }
        100% {
          background-position: 0% 50%;
          transform: translateX(-12px);
          text-shadow: 0 10px 26px rgba(10,111,134,0.2);
        }
      }
      @keyframes slowFloat {
        0%, 100% { transform: translateY(0); }
        50% { transform: translateY(18px); }
      }
      @keyframes rgbColorCycle {
        0% {
          color: #00d4ff;
          text-shadow: 0 0 20px rgba(0, 212, 255, 0.6), 0 0 40px rgba(10, 159, 181, 0.3);
        }
        25% {
          color: #0a9fb5;
          text-shadow: 0 0 20px rgba(10, 159, 181, 0.6), 0 0 40px rgba(10, 111, 134, 0.3);
        }
        50% {
          color: #40e0d0;
          text-shadow: 0 0 20px rgba(64, 224, 208, 0.6), 0 0 40px rgba(10, 159, 181, 0.3);
        }
        75% {
          color: #0066cc;
          text-shadow: 0 0 20px rgba(0, 102, 204, 0.6), 0 0 40px rgba(10, 111, 134, 0.3);
        }
        100% {
          color: #00d4ff;
          text-shadow: 0 0 20px rgba(0, 212, 255, 0.6), 0 0 40px rgba(10, 159, 181, 0.3);
        }
      }
      @keyframes rgbShadowCycle {
        0% {
          box-shadow: 0 0 12px rgba(0, 212, 255, 0.6), 0 6px 16px rgba(10, 20, 30, 0.3);
        }
        25% {
          box-shadow: 0 0 12px rgba(10, 159, 181, 0.6), 0 6px 16px rgba(10, 20, 30, 0.3);
        }
        50% {
          box-shadow: 0 0 12px rgba(64, 224, 208, 0.6), 0 6px 16px rgba(10, 20, 30, 0.3);
        }
        75% {
          box-shadow: 0 0 12px rgba(0, 102, 204, 0.6), 0 6px 16px rgba(10, 20, 30, 0.3);
        }
        100% {
          box-shadow: 0 0 12px rgba(0, 212, 255, 0.6), 0 6px 16px rgba(10, 20, 30, 0.3);
        }
      }
      @keyframes starTwinkle {
        0%, 100% {
          opacity: 0.3;
        }
        50% {
          opacity: 1;
        }
      }
      @keyframes nebulaPulse {
        0%, 100% {
          opacity: 0.5;
          filter: blur(40px);
        }
        50% {
          opacity: 0.8;
          filter: blur(50px);
        }
      }
      
      /* Welcome Animation Classes */
      .welcome.welcome-fade-in {
        animation: welcome-fade-in 2s ease-in-out !important;
      }
      .welcome.welcome-slide-in {
        animation: welcome-slide-in 2s ease-in-out !important;
      }
      .welcome.welcome-bounce {
        animation: welcome-bounce 2s ease-in-out !important;
      }
      .welcome.welcome-pulse {
        animation: welcome-pulse 2s ease-in-out !important;
      }
      .welcome.welcome-typewriter {
        animation: welcome-typewriter 2s ease-in-out !important;
      }
      .welcome.welcome-neon {
        animation: welcome-neon 2s ease-in-out !important;
      }
      .welcome.welcome-wave {
        animation: none !important;
      }
      .welcome.welcome-wave .wave-char {
        animation: waveText 1.6s ease-in-out infinite;
      }
      .welcome.welcome-zoom {
        animation: welcome-zoom 2s ease-in-out !important;
      }
      @keyframes welcome-fade-in {
        from { opacity: 0; }
        to { opacity: 1; }
      }
      @keyframes welcome-slide-in {
        from { opacity: 0; transform: translateY(30px); }
        to { opacity: 1; transform: translateY(0); }
      }
      @keyframes welcome-bounce {
        0%, 100% { transform: translateY(0); }
        50% { transform: translateY(-20px); }
      }
      @keyframes welcome-pulse {
        0%, 100% { transform: scale(1); }
        50% { transform: scale(1.05); }
      }
      @keyframes welcome-typewriter {
        from { width: 0; }
        to { width: 100%; }
      }
      @keyframes welcome-neon {
        0%, 100% { text-shadow: 0 0 10px rgba(10,159,181,0.5), 0 0 20px rgba(10,159,181,0.3); }
        50% { text-shadow: 0 0 20px rgba(10,159,181,1), 0 0 30px rgba(10,159,181,0.6), 0 0 40px rgba(10,159,181,0.4); }
      }
      @keyframes welcome-zoom {
        from { transform: scale(0); opacity: 0; }
        to { transform: scale(1); opacity: 1; }
      }
      
      /* Welcome Font Classes */
      .welcome.welcome-font-modern { font-family: "Bahnschrift", "Candara", "Trebuchet MS", sans-serif; }
      .welcome.welcome-font-classic { font-family: "Rockwell", "Constantia", "Georgia", serif; }
      .welcome.welcome-font-elegant { font-family: "Garamond", "Calisto MT", serif; }
      .welcome.welcome-font-serif { font-family: "Georgia", "Times New Roman", serif; }
      .welcome.welcome-font-sans { font-family: "Verdana", "Arial", sans-serif; }
      .welcome.welcome-font-geometric { font-family: "Trebuchet MS", "Century Gothic", sans-serif; }
      .welcome.welcome-font-tech { font-family: "Courier New", "Monaco", monospace; }
      .welcome.welcome-font-minimal { font-family: "Helvetica", "Arial", sans-serif; }
      .welcome.welcome-font-corporate { font-family: "Calibri", "Segoe UI", sans-serif; }
      .welcome.welcome-font-artistic { font-family: "Palatino Linotype", "Palatino", serif; }
      .welcome.welcome-font-futuristic { font-family: "Segoe UI", "Tahoma", sans-serif; }
      .welcome.welcome-font-handwriting { font-family: "Segoe Print", "Comic Sans MS", cursive; }
    </style>
  </head>
  <body>
    <div class="spark"></div>
    <div class="stage">
      <div class="welcome wave" data-text="Welcome to Control E6" aria-label="Welcome to Control E6">Welcome to Control E6</div>
      <div class="sub">Initializing dashboard...</div>
    </div>
    <script>
      // Load saved welcome style settings
      const savedText = localStorage.getItem("welcomeText") || "Welcome to Control E6";
      const savedAnimation = localStorage.getItem("welcomeAnimation") || "wave";
      const savedFont = localStorage.getItem("welcomeFont") || "modern";
      const savedBackground = localStorage.getItem("welcomeBackground") || "gradient-blue";
      
      // Apply background style to body
      const body = document.body;
      const bgClass = "welcome-bg-" + savedBackground;
      body.classList.add(bgClass);
      
      const waveEl = document.querySelector('.welcome.wave');
      if (waveEl) {
        // Use saved text instead of default
        waveEl.setAttribute('data-text', savedText);
        const rawText = waveEl.getAttribute('data-text') || waveEl.textContent.trim();
        waveEl.textContent = '';
        Array.from(rawText).forEach((char, index) => {
          const span = document.createElement('span');
          span.className = 'wave-char';
          span.style.setProperty('--i', String(index));
          span.textContent = char === ' ' ? ' ' : char;
          waveEl.appendChild(span);
        });
        
        // Apply font style
        const fontClass = "welcome-font-" + savedFont;
        waveEl.classList.add(fontClass);
        
        // Apply animation style
        waveEl.classList.remove('wave');
        const animClass = 'welcome-' + savedAnimation;
        waveEl.classList.add(animClass);
      }
      setTimeout(() => {
        window.location.href = "{{ url_for('index') }}";
      }, 2200);
    </script>
  </body>
</html>
"""

REGISTER_PAGE = """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <link rel="icon" type="image/svg+xml" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><defs><linearGradient id='g' x1='0%' y1='0%' x2='100%' y2='100%'><stop offset='0%' style='stop-color:%230a9fb5'/><stop offset='100%' style='stop-color:%230a6f86'/></linearGradient></defs><rect width='32' height='32' rx='6' fill='url(%23g)'/><circle cx='8' cy='8' r='2.5' fill='white' opacity='0.9'/><circle cx='24' cy='8' r='2' fill='%2300ff99' opacity='0.95'/><circle cx='24' cy='16' r='2' fill='%23ff6b6b' opacity='0.85'/><circle cx='24' cy='24' r='2' fill='%23ffd700' opacity='0.75'/><line x1='8' y1='5.5' x2='8' y2='4' stroke='white' stroke-width='1.2' opacity='0.8'/><line x1='8' y1='13.5' x2='8' y2='12' stroke='white' stroke-width='1.2' opacity='0.6'/><line x1='8' y1='21.5' x2='8' y2='20' stroke='white' stroke-width='1.2' opacity='0.4'/><rect x='14' y='11' width='6' height='10' rx='1' fill='none' stroke='white' stroke-width='0.8' opacity='0.6'/></svg>">
    <title>Create Account</title>
    <style>
      :root {
        --ink: #0b1220;
        --muted: #5f6b7a;
        --panel: #ffffff;
        --border: #d7dee6;
        --brand: #0a6f86;
        --brand-light: #0d8fa3;
        --bg: #e9eef4;
        --font-body: "Bahnschrift", "Candara", "Trebuchet MS", sans-serif;
        --font-display: "Rockwell", "Constantia", "Georgia", serif;
        --font-mono: "Cascadia Mono", "Consolas", "Courier New", monospace;
      }
      * { box-sizing: border-box; }
      body {
        margin: 0;
        font-family: var(--font-body);
        background: {{ background_style|safe }};
        color: var(--ink);
        min-height: 100vh;
        display: grid;
        place-items: center;
        padding: 24px;
      }
      .card {
        width: 100%;
        max-width: 480px;
        background: rgba(255, 255, 255, 0.98);
        border-radius: 20px;
        border: 1px solid rgba(13, 24, 40, 0.1);
        box-shadow: 0 30px 60px rgba(15, 23, 42, 0.2);
        padding: 36px;
        position: relative;
        overflow: hidden;
        backdrop-filter: blur(10px);
      }
      .card::before {
        content: "";
        position: absolute;
        inset: 0;
        background: linear-gradient(135deg, rgba(10, 111, 134, 0.08), transparent 45%);
        pointer-events: none;
      }
      .card-content {
        position: relative;
        z-index: 1;
      }
      .logo-area {
        text-align: center;
        margin-bottom: 24px;
      }
      .logo-icon {
        font-size: 40px;
        margin-bottom: 12px;
      }
      h1 {
        margin: 0 0 6px;
        font-size: 24px;
        font-weight: 700;
        text-align: center;
        letter-spacing: -0.3px;
        color: var(--ink);
        font-family: var(--font-display);
      }
      .subtitle {
        font-size: 13px;
        color: var(--muted);
        text-align: center;
        font-weight: 500;
      }
      .form-group {
        margin-bottom: 18px;
      }
      label {
        display: block;
        font-size: 12px;
        color: var(--muted);
        margin-bottom: 8px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.3px;
      }
      input, select {
        width: 100%;
        padding: 12px 14px;
        border-radius: 10px;
        border: 1.5px solid rgba(13, 24, 40, 0.15);
        background: #f8fafc;
        font-size: 14px;
        transition: all 200ms ease;
        color: var(--ink);
      }
      input::placeholder {
        color: rgba(95, 107, 122, 0.5);
      }
      input:hover, select:hover {
        border-color: rgba(10, 111, 134, 0.3);
        background: #f0f6fa;
      }
      input:focus, select:focus {
        outline: none;
        border-color: var(--brand);
        box-shadow: 0 0 0 4px rgba(10, 111, 134, 0.1);
        background: #fff;
      }
      .checklist {
        border: 1.5px solid rgba(13, 24, 40, 0.15);
        border-radius: 12px;
        padding: 14px;
        max-height: 200px;
        overflow-y: auto;
        margin-bottom: 18px;
        background: linear-gradient(135deg, #f8fafc 0%, #f0f5fa 100%);
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 10px;
      }
      .checklist label {
        display: flex;
        align-items: center;
        gap: 10px;
        margin: 0;
        font-size: 13px;
        color: var(--ink);
        padding: 10px 12px;
        border-radius: 8px;
        background: #ffffff;
        border: 2px solid rgba(10, 111, 134, 0.15);
        cursor: pointer;
        transition: all 200ms ease;
        font-weight: 500;
        text-transform: none;
        letter-spacing: 0;
      }
      .checklist label:hover {
        background: #f0f9fc;
        border-color: rgba(10, 111, 134, 0.3);
        box-shadow: 0 2px 8px rgba(10, 111, 134, 0.1);
      }
      .checklist label input[type="checkbox"] {
        width: 18px;
        height: 18px;
        cursor: pointer;
        accent-color: var(--brand);
      }
      @media (max-width: 540px) {
        .checklist { grid-template-columns: 1fr; }
      }
      .divider {
        margin: 20px 0 16px;
        font-size: 12px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.3px;
        color: var(--muted);
      }
      .btn {
        width: 100%;
        border: none;
        border-radius: 12px;
        padding: 13px 14px;
        font-weight: 700;
        font-size: 13px;
        cursor: pointer;
        background: linear-gradient(135deg, var(--brand) 0%, var(--brand-light) 100%);
        color: #fff;
        text-transform: uppercase;
        letter-spacing: 0.6px;
        box-shadow: 0 12px 24px rgba(10, 111, 134, 0.3);
        transition: all 200ms ease;
        position: relative;
        overflow: hidden;
      }
      .btn:hover {
        transform: translateY(-2px);
        box-shadow: 0 16px 32px rgba(10, 111, 134, 0.35);
      }
      .btn:active {
        transform: translateY(0);
      }
      .link {
        margin-top: 16px;
        text-align: center;
        font-size: 12px;
      }
      .link a {
        color: var(--brand);
        text-decoration: none;
        font-weight: 700;
        transition: all 150ms ease;
      }
      .link a:hover {
        color: var(--brand-light);
        text-decoration: underline;
      }
      .message {
        background: linear-gradient(135deg, #fff3cd 0%, #fffaeb 100%);
        border: 1px solid #ffe5a1;
        color: #664d03;
        padding: 12px 14px;
        border-radius: 10px;
        font-size: 12px;
        margin-bottom: 18px;
        border-left: 3px solid #ffc107;
        font-weight: 500;
      }
      .message.error {
        background: linear-gradient(135deg, #fee2e2 0%, #fef2f2 100%);
        border-color: #fca5a5;
        color: #991b1b;
        border-left-color: #dc2626;
      }
      .password-wrapper {
        position: relative;
        display: flex;
        align-items: center;
      }
      .password-wrapper input {
        width: 100%;
        padding-right: 40px;
      }
      .password-toggle {
        position: absolute;
        right: 12px;
        background: none;
        border: none;
        cursor: pointer;
        font-size: 18px;
        color: var(--muted);
        padding: 6px;
        transition: color 150ms ease;
        display: flex;
        align-items: center;
        justify-content: center;
      }
      .password-toggle:hover {
        color: var(--brand);
      }
      @media (max-width: 480px) {
        .card {
          padding: 28px 20px;
        }
        h1 {
          font-size: 22px;
        }
        .logo-icon {
          font-size: 36px;
        }
      }
    </style>
  </head>
  <body>
    <form class="card" method="post">
      <div class="card-content">
        <div class="logo-area">
          <div class="logo-icon">✨</div>
          <h1>Create Account</h1>
          <div class="subtitle">Join the Dashboard</div>
        </div>
        
        {% if message %}
        <div class="message {% if 'success' in message.lower() %}success{% elif 'error' in message.lower() %}error{% endif %}">
          {{ message }}
        </div>
        {% endif %}
        
        <div class="form-group">
          <label for="new_username">👤 User Name</label>
          <input 
            id="new_username" 
            name="new_username" 
            type="text"
            placeholder="Choose a username"
            required 
          />
        </div>
        
        <div class="form-group">
          <label for="new_password">🔒 New Password</label>
          <div class="password-wrapper">
            <input 
              id="new_password" 
              name="new_password" 
              type="password"
              placeholder="Create a strong password"
              required 
            />
            <button type="button" class="password-toggle" id="newPasswordToggle" tabindex="-1">👁</button>
          </div>
        </div>
        
        <div class="form-group">
          <label for="confirm_password">✓ Confirm Password</label>
          <div class="password-wrapper">
            <input 
              id="confirm_password" 
              name="confirm_password" 
              type="password"
              placeholder="Confirm your password"
              required 
            />
            <button type="button" class="password-toggle" id="confirmPasswordToggle" tabindex="-1">👁</button>
          </div>
        </div>
        
        <div class="form-group">
          <label for="role">⚙ Role</label>
          <select id="role" name="role">
            <option value="PAYMENT EDITOR">Payment Editor</option>
            <option value="ADMIN">Admin</option>
          </select>
        </div>
        
        <div class="form-group">
          <label>📋 Navigation Access</label>
          <div class="checklist">
            {% for item in nav_main %}
            <label><input type="checkbox" name="nav_access" value="{{ item }}" /> {{ item }}</label>
            {% endfor %}
          </div>
        </div>
        
        <div class="divider">🔐 Admin Verification</div>
        
        <div class="form-group">
          <label for="admin_user">Admin User</label>
          <input 
            id="admin_user" 
            name="admin_user" 
            type="text"
            placeholder="Admin username"
            required 
          />
        </div>
        
        <div class="form-group">
          <label for="admin_password">Admin Password</label>
          <div class="password-wrapper">
            <input 
              id="admin_password" 
              name="admin_password" 
              type="password"
              placeholder="Admin password"
              required 
            />
            <button type="button" class="password-toggle" id="adminPasswordToggle" tabindex="-1">👁</button>
          </div>
        </div>
        
        <button class="btn" type="submit">✨ Create Account</button>
        
        <div class="link">
          Already have an account? <a href="{{ url_for('login') }}">Login here</a>
        </div>
      </div>
    </form>
    <script>
      function togglePasswordVisibility(inputId, toggleId) {
        const input = document.getElementById(inputId);
        const toggle = document.getElementById(toggleId);
        
        if (toggle) {
          toggle.addEventListener('click', (e) => {
            e.preventDefault();
            const isPassword = input.type === 'password';
            input.type = isPassword ? 'text' : 'password';
            toggle.textContent = isPassword ? '🙈' : '👁';
          });
        }
      }
      
      togglePasswordVisibility('new_password', 'newPasswordToggle');
       togglePasswordVisibility('confirm_password', 'confirmPasswordToggle');
       togglePasswordVisibility('admin_password', 'adminPasswordToggle');
      </script>
      </body>
      </html>
      """

    
IP_ACCESS_PAGE = """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <link rel="icon" type="image/svg+xml" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><defs><linearGradient id='g' x1='0%' y1='0%' x2='100%' y2='100%'><stop offset='0%' style='stop-color:%230a9fb5'/><stop offset='100%' style='stop-color:%230a6f86'/></linearGradient></defs><rect width='32' height='32' rx='6' fill='url(%23g)'/><circle cx='8' cy='8' r='2.5' fill='white' opacity='0.9'/><circle cx='24' cy='8' r='2' fill='%2300ff99' opacity='0.95'/><circle cx='24' cy='16' r='2' fill='%23ff6b6b' opacity='0.85'/><circle cx='24' cy='24' r='2' fill='%23ffd700' opacity='0.75'/><line x1='8' y1='5.5' x2='8' y2='4' stroke='white' stroke-width='1.2' opacity='0.8'/><line x1='8' y1='13.5' x2='8' y2='12' stroke='white' stroke-width='1.2' opacity='0.6'/><line x1='8' y1='21.5' x2='8' y2='20' stroke='white' stroke-width='1.2' opacity='0.4'/><rect x='14' y='11' width='6' height='10' rx='1' fill='none' stroke='white' stroke-width='0.8' opacity='0.6'/></svg>">
    <title>IP Protection Access Control</title>
    <style>
      :root {
        --ink: #0b1220;
        --muted: #5f6b7a;
        --panel: #ffffff;
        --border: #d7dee6;
        --brand: #0a6f86;
        --brand-light: #0d8fa3;
        --bg: #e9eef4;
        --green: #16a34a;
        --red: #dc2626;
        --font-body: "Bahnschrift", "Candara", "Trebuchet MS", sans-serif;
        --font-display: "Rockwell", "Constantia", "Georgia", serif;
        --font-mono: "Cascadia Mono", "Consolas", "Courier New", monospace;
      }
      * { box-sizing: border-box; }
      body {
        margin: 0;
        font-family: var(--font-body);
        background: {{ background_style|safe }};
        color: var(--ink);
        min-height: 100vh;
        padding: 28px;
      }
      .shell {
        max-width: 900px;
        margin: 0 auto;
        background: var(--panel);
        border-radius: 12px;
        border: 1px solid var(--border);
        box-shadow: 0 4px 6px rgba(0,0,0,0.07);
        padding: 28px 32px;
      }
      .header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 24px;
        padding-bottom: 16px;
        border-bottom: 2px solid var(--border);
      }
      .header h1 {
        margin: 0;
        font-size: 24px;
        font-weight: 700;
        color: var(--ink);
        font-family: var(--font-display);
      }
      .back-link {
        background: linear-gradient(135deg, var(--brand) 0%, var(--brand-light) 100%);
        color: white;
        padding: 8px 16px;
        border-radius: 6px;
        text-decoration: none;
        font-weight: 600;
        font-size: 12px;
        transition: all 200ms ease;
      }
      .back-link:hover {
        transform: translateY(-2px);
      }
      .message {
        background: linear-gradient(135deg, #e7f5ff 0%, #f0f9ff 100%);
        border: 1px solid #b6e0fe;
        color: #0c4a6e;
        padding: 12px 14px;
        border-radius: 8px;
        margin-bottom: 16px;
        border-left: 3px solid var(--brand);
      }
      .section {
        margin-bottom: 24px;
      }
      .section-title {
        font-size: 14px;
        font-weight: 700;
        color: var(--muted);
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin-bottom: 12px;
      }
      .form-group {
        display: grid;
        gap: 8px;
        margin-bottom: 12px;
      }
      label {
        font-size: 12px;
        color: var(--muted);
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.3px;
      }
      select, input {
        padding: 10px 12px;
        border-radius: 6px;
        border: 1px solid var(--border);
        font-size: 13px;
        font-family: inherit;
        transition: all 150ms ease;
      }
      select:focus, input:focus {
        outline: none;
        border-color: var(--brand);
        box-shadow: 0 0 0 3px rgba(10,111,134,0.1);
      }
      .btn {
        padding: 10px 16px;
        border-radius: 6px;
        border: none;
        font-weight: 600;
        font-size: 12px;
        cursor: pointer;
        transition: all 150ms ease;
      }
      .btn-primary {
        background: linear-gradient(135deg, var(--brand) 0%, var(--brand-light) 100%);
        color: white;
      }
      .btn-primary:hover {
        transform: translateY(-2px);
      }
      .list-container {
        background: #fafbfd;
        border: 1px solid var(--border);
        border-radius: 8px;
        padding: 16px;
      }
      .list-item {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 12px;
        border-bottom: 1px solid var(--border);
        background: white;
        border-radius: 6px;
        margin-bottom: 8px;
      }
      .list-item:last-child {
        margin-bottom: 0;
      }
      .list-item-username {
        font-weight: 600;
        color: var(--ink);
      }
      .remove-btn {
        background: #fee2e2;
        color: var(--red);
        border: 1px solid #fca5a5;
        padding: 6px 12px;
        border-radius: 4px;
        font-size: 11px;
        cursor: pointer;
        transition: all 150ms ease;
      }
      .remove-btn:hover {
        background: #fecaca;
      }
      .empty-state {
        text-align: center;
        padding: 24px;
        color: var(--muted);
      }
    </style>
  </head>
  <body>
    <div class="shell">
      <div class="header">
        <h1>IP Protection Access Control</h1>
        <a href="{{ url_for('admin') }}" class="back-link">Back to Admin</a>
      </div>

      {% if message %}
      <div class="message">{{ message }}</div>
      {% endif %}

      <div class="section">
        <div class="section-title">Add User Access</div>
        <form method="post" class="form-group">
          <label for="username">Select User</label>
          <div style="display: grid; grid-template-columns: 1fr auto; gap: 8px;">
            <select name="username" id="username" required>
              <option value="">-- Select a user --</option>
              {% for user in all_users %}
              <option value="{{ user }}">{{ user }}</option>
              {% endfor %}
            </select>
            <input type="hidden" name="action" value="add" />
            <button type="submit" class="btn btn-primary">Add User</button>
          </div>
        </form>
      </div>

      <div class="section">
        <div class="section-title">Authorized Users ({{ authorized_users|length }})</div>
        <div class="list-container">
          {% if authorized_users %}
            {% for user in authorized_users %}
            <div class="list-item">
              <span class="list-item-username">{{ user }}</span>
              <form method="post" style="display: inline;">
                <input type="hidden" name="action" value="remove" />
                <input type="hidden" name="username" value="{{ user }}" />
                <button type="submit" class="remove-btn">Remove</button>
              </form>
            </div>
            {% endfor %}
          {% else %}
          <div class="empty-state">No users have IP protection access yet.</div>
          {% endif %}
        </div>
      </div>
    </div>
  </body>
</html>
"""

ADMIN_PAGE = """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <link rel="icon" type="image/svg+xml" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><defs><linearGradient id='g' x1='0%' y1='0%' x2='100%' y2='100%'><stop offset='0%' style='stop-color:%230a9fb5'/><stop offset='100%' style='stop-color:%230a6f86'/></linearGradient></defs><rect width='32' height='32' rx='6' fill='url(%23g)'/><circle cx='8' cy='8' r='2.5' fill='white' opacity='0.9'/><circle cx='24' cy='8' r='2' fill='%2300ff99' opacity='0.95'/><circle cx='24' cy='16' r='2' fill='%23ff6b6b' opacity='0.85'/><circle cx='24' cy='24' r='2' fill='%23ffd700' opacity='0.75'/><line x1='8' y1='5.5' x2='8' y2='4' stroke='white' stroke-width='1.2' opacity='0.8'/><line x1='8' y1='13.5' x2='8' y2='12' stroke='white' stroke-width='1.2' opacity='0.6'/><line x1='8' y1='21.5' x2='8' y2='20' stroke='white' stroke-width='1.2' opacity='0.4'/><rect x='14' y='11' width='6' height='10' rx='1' fill='none' stroke='white' stroke-width='0.8' opacity='0.6'/></svg>">
    <title>Admin Settings</title>
    <style>
      :root {
        --ink: #0b1220;
        --muted: #5f6b7a;
        --panel: #ffffff;
        --border: #d7dee6;
        --brand: #0a6f86;
        --bg: #e9eef4;
        --font-body: "Bahnschrift", "Candara", "Trebuchet MS", sans-serif;
        --font-display: "Rockwell", "Constantia", "Georgia", serif;
        --font-mono: "Cascadia Mono", "Consolas", "Courier New", monospace;
      }
      * { box-sizing: border-box; }
      body {
        margin: 0;
        font-family: var(--font-body);
        background: {{ background_style|safe }};
        color: var(--ink);
        min-height: 100vh;
        padding: 24px;
      }
      .shell {
        max-width: 760px;
        margin: 0 auto;
        background: linear-gradient(180deg, #ffffff 0%, #f7fafc 100%);
        border-radius: 18px;
        border: 1px solid rgba(10,111,134,0.16);
        box-shadow: 0 24px 50px rgba(10,20,30,0.18);
        padding: 18px 22px 24px;
        position: relative;
        overflow: hidden;
      }
      .shell::before {
        content: "";
        position: absolute;
        inset: 0;
        background: radial-gradient(circle at 20% -10%, rgba(10,159,181,0.12), transparent 45%);
        pointer-events: none;
      }
      .header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        border-bottom: 1px solid rgba(10,111,134,0.12);
        padding: 12px 6px 16px;
        margin-bottom: 16px;
        position: relative;
        z-index: 1;
      }
      .header h1 {
        margin: 0;
        font-size: 18px;
        font-weight: 800;
        letter-spacing: 0.4px;
        color: #0a3642;
        font-family: var(--font-display);
      }
      .btn-link {
        background: linear-gradient(135deg, #0a9fb5 0%, #0a6f86 100%);
        color: #fff;
        padding: 7px 12px;
        border-radius: 10px;
        text-decoration: none;
        font-weight: 700;
        font-size: 11px;
        letter-spacing: 0.3px;
        box-shadow: 0 6px 14px rgba(10,111,134,0.2);
        transition: all 150ms ease;
      }
      .btn-link:hover {
        transform: translateY(-1px);
        box-shadow: 0 8px 18px rgba(10,111,134,0.3);
      }
      label {
        display: block;
        font-size: 12px;
        color: var(--muted);
        margin: 10px 0 6px;
        font-weight: 600;
      }
      input, select {
        width: 100%;
        padding: 10px 12px;
        border-radius: 10px;
        border: 1.5px solid rgba(10,111,134,0.2);
        background: #ffffff;
        font-size: 13px;
        transition: all 150ms ease;
      }
      input:focus, select:focus {
        outline: none;
        border-color: #0a9fb5;
        box-shadow: 0 0 0 4px rgba(10,159,181,0.12);
      }
      .checklist {
        border: 1px solid rgba(10,111,134,0.18);
        border-radius: 14px;
        padding: 14px;
        max-height: 280px;
        overflow-y: auto;
        margin-bottom: 12px;
        background: linear-gradient(135deg, #f8fbfd 0%, #f0f7fa 100%);
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 10px;
      }
      .checklist label {
        display: flex;
        align-items: center;
        gap: 10px;
        margin: 0;
        font-size: 12px;
        color: var(--ink);
        padding: 10px 12px;
        border-radius: 10px;
        background: #ffffff;
        border: 1.5px solid rgba(10, 111, 134, 0.15);
        cursor: pointer;
        transition: all 200ms ease;
        font-weight: 600;
        letter-spacing: 0.2px;
      }
      .checklist label:hover {
        background: #f0f9fc;
        border-color: rgba(10, 111, 134, 0.3);
        box-shadow: 0 2px 8px rgba(10, 111, 134, 0.1);
      }
      .checklist label input[type="checkbox"] {
        width: 18px;
        height: 18px;
        cursor: pointer;
        accent-color: #0a6f86;
      }
      .checklist::-webkit-scrollbar {
        width: 8px;
      }
      .checklist::-webkit-scrollbar-thumb {
        background: rgba(10,111,134,0.25);
        border-radius: 6px;
      }
      .checklist label input[type="checkbox"]:checked + * {
        color: #0a6f86;
        font-weight: 600;
      }
      @media (max-width: 520px) {
        .checklist { grid-template-columns: 1fr; }
      }
      .btn {
        border: none;
        border-radius: 10px;
        padding: 11px 14px;
        font-weight: 800;
        cursor: pointer;
        background: linear-gradient(135deg, #0a9fb5 0%, #0a6f86 100%);
        color: #fff;
        width: 100%;
        text-transform: uppercase;
        letter-spacing: 0.4px;
        box-shadow: 0 8px 20px rgba(10,111,134,0.25);
        transition: all 150ms ease;
      }
      .btn:hover {
        transform: translateY(-1px);
        box-shadow: 0 10px 24px rgba(10,111,134,0.35);
      }
      .message {
        background: #e7f5ff;
        border: 1px solid #b6e0fe;
        color: #094067;
        padding: 8px 10px;
        border-radius: 8px;
        font-size: 12px;
        margin-bottom: 12px;
      }
      .modal {
        position: fixed;
        inset: 0;
        background: rgba(10,20,30,0.55);
        display: none;
        align-items: center;
        justify-content: center;
        padding: 20px;
        z-index: 50;
        backdrop-filter: blur(2px);
      }
      .modal.open {
        display: flex;
        animation: fadeIn 200ms ease;
      }
      @keyframes fadeIn {
        from { opacity: 0; }
        to { opacity: 1; }
      }
      .modal-card {
        width: 100%;
        max-width: 460px;
        background: #ffffff;
        border-radius: 16px;
        border: 1px solid rgba(13,24,40,0.12);
        box-shadow: 0 25px 50px rgba(15,23,42,0.3);
        overflow: hidden;
        animation: slideUp 250ms ease;
      }
      @keyframes slideUp {
        from { transform: translateY(20px); opacity: 0; }
        to { transform: translateY(0); opacity: 1; }
      }
      .modal-header {
        padding: 16px 20px;
        font-weight: 700;
        display: flex;
        justify-content: space-between;
        align-items: center;
        border-bottom: 1px solid var(--border);
        background: linear-gradient(90deg, #f6f9fc 0%, #f0f5fa 100%);
        font-size: 14px;
      }
      .modal-body {
        padding: 20px;
        display: grid;
        gap: 12px;
        font-size: 13px;
      }
      .modal-body label {
        font-size: 12px;
        color: var(--muted);
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.3px;
        margin-top: 4px;
        margin-bottom: 6px;
        display: block;
      }
      .modal-body input {
        width: 100%;
        padding: 10px 12px;
        border-radius: 8px;
        border: 1px solid var(--border);
        font-size: 13px;
        transition: all 150ms ease;
      }
      .modal-body input:focus {
        outline: none;
        border-color: var(--brand);
        box-shadow: 0 0 0 3px rgba(10,111,134,0.1);
      }
      .modal-note {
        font-size: 12px;
        color: var(--muted);
        background: #f8fafc;
        padding: 10px 12px;
        border-radius: 6px;
        border-left: 3px solid rgba(10,111,134,0.2);
      }
      .modal-footer {
        padding: 16px 20px;
        display: flex;
        justify-content: flex-end;
        gap: 12px;
        border-top: 1px solid var(--border);
        background: #f9fbfd;
      }
      .modal .btn-ghost {
        background: #ffffff;
        color: var(--muted);
        border: 1.5px solid var(--border);
        padding: 10px 20px;
        border-radius: 8px;
        font-weight: 600;
        font-size: 13px;
        cursor: pointer;
        transition: all 200ms ease;
        min-width: 100px;
        text-align: center;
      }
      .modal .btn-ghost:hover {
        background: #f5f7fa;
        border-color: #c0c6ce;
        color: var(--ink);
      }
      .modal .btn-ghost:active {
        transform: scale(0.98);
      }
      .modal .btn-link {
        background: linear-gradient(135deg, var(--brand) 0%, var(--brand-light) 100%);
        color: #fff;
        padding: 10px 24px;
        border-radius: 8px;
        border: none;
        font-weight: 600;
        font-size: 13px;
        cursor: pointer;
        transition: all 200ms ease;
        box-shadow: 0 4px 12px rgba(10,111,134,0.25);
        min-width: 130px;
        text-align: center;
      }
      .modal .btn-link:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 16px rgba(10,111,134,0.35);
      }
      .modal .btn-link:active {
        transform: translateY(0);
        box-shadow: 0 2px 8px rgba(10,111,134,0.2);
      }
      /* IP Access Control Modal */
      .modal#ipAccessModal {
        background: radial-gradient(circle at top, rgba(10,159,181,0.18), rgba(10,20,30,0.6));
        backdrop-filter: blur(6px);
      }
      .ip-access-card {
        width: 100%;
        max-width: 520px;
        background: linear-gradient(180deg, #ffffff 0%, #f7fafc 100%);
        border-radius: 18px;
        border: 1px solid rgba(10,111,134,0.2);
        box-shadow: 0 30px 70px rgba(10,20,30,0.35);
        overflow: hidden;
      }
      .ip-access-header {
        background: linear-gradient(135deg, #0a9fb5 0%, #0a6f86 100%);
        padding: 20px 22px;
        border-bottom: 1px solid rgba(255,255,255,0.15);
        display: flex;
        align-items: center;
        justify-content: space-between;
      }
      .ip-access-title {
        display: flex;
        align-items: center;
        gap: 10px;
        color: #ffffff;
        font-size: 16px;
        font-weight: 800;
        letter-spacing: 0.4px;
      }
      .ip-access-icon {
        font-size: 20px;
        filter: drop-shadow(0 2px 4px rgba(0,0,0,0.2));
      }
      #closeIpAccessModal {
        background: rgba(255,255,255,0.2);
        color: #ffffff;
        border: none;
        border-radius: 8px;
        width: 34px;
        height: 34px;
        cursor: pointer;
        font-size: 18px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        transition: all 150ms ease;
      }
      #closeIpAccessModal:hover {
        background: rgba(255,255,255,0.35);
        transform: rotate(90deg);
      }
      .ip-access-body {
        padding: 22px 24px 24px;
        display: grid;
        gap: 14px;
        background: linear-gradient(180deg, #ffffff 0%, #f6fafc 100%);
      }
      .ip-access-note {
        display: flex;
        gap: 10px;
        align-items: flex-start;
        background: linear-gradient(135deg, rgba(10,159,181,0.14), rgba(10,159,181,0.06));
        border-left: 3px solid #0a9fb5;
        padding: 12px 14px;
        border-radius: 10px;
        color: #0a3642;
        font-size: 13px;
        font-weight: 600;
      }
      .note-icon {
        font-size: 16px;
        margin-top: 2px;
        color: #0a9fb5;
      }
      .form-label {
        font-size: 11px;
        color: #0a3642;
        font-weight: 800;
        text-transform: uppercase;
        letter-spacing: 0.6px;
        display: flex;
        align-items: center;
        gap: 6px;
      }
      .form-input {
        width: 100%;
        padding: 12px 14px;
        border-radius: 10px;
        border: 2px solid rgba(10,111,134,0.15);
        font-size: 13px;
        font-weight: 600;
        background: #ffffff;
        color: #0a3642;
        transition: all 200ms ease;
        box-shadow: inset 0 1px 2px rgba(0,0,0,0.03);
      }
      .form-input:focus {
        outline: none;
        border-color: #0a9fb5;
        box-shadow: 0 0 0 4px rgba(10,159,181,0.12);
        background: #f7fdff;
      }
      .ip-access-footer {
        padding: 16px 22px 20px;
        display: flex;
        justify-content: flex-end;
        gap: 10px;
        border-top: 1px solid rgba(10,111,134,0.1);
        background: #f8fafc;
      }
      #cancelIpAccessModal {
        background: #eef2f6;
        color: #0a3642;
        border: 1.5px solid rgba(10,111,134,0.2);
        padding: 10px 18px;
        border-radius: 8px;
        font-weight: 700;
        font-size: 12px;
        cursor: pointer;
        transition: all 150ms ease;
      }
      #cancelIpAccessModal:hover {
        background: #e2e8f0;
        transform: translateY(-1px);
      }
      .ip-access-submit {
        background: linear-gradient(135deg, #0a9fb5 0%, #0a6f86 100%);
        color: #ffffff;
        border: none;
        padding: 10px 20px;
        border-radius: 8px;
        font-weight: 800;
        font-size: 12px;
        cursor: pointer;
        transition: all 180ms ease;
        box-shadow: 0 6px 18px rgba(10,159,181,0.25);
        text-transform: uppercase;
        letter-spacing: 0.4px;
      }
      .ip-access-submit:hover {
        transform: translateY(-1px);
        box-shadow: 0 8px 22px rgba(10,159,181,0.35);
        background: linear-gradient(135deg, #0cbcc8 0%, #0a7d8f 100%);
      }
      .modal-body button[type="submit"] {
        background: linear-gradient(135deg, var(--brand) 0%, var(--brand-light) 100%);
        color: #fff;
        padding: 10px 24px;
        border-radius: 8px;
        border: none;
        font-weight: 600;
        font-size: 13px;
        cursor: pointer;
        transition: all 200ms ease;
        box-shadow: 0 4px 12px rgba(10,111,134,0.25);
        min-width: 130px;
        text-align: center;
      }
      .modal-body button[type="submit"]:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 16px rgba(10,111,134,0.35);
      }
      </style>
  </head>
  <body>
    <div class="shell">
      <div class="header">
         <h1>Admin Settings</h1>
         <div style="display: flex; gap: 8px;">
           {% if current_username == 'WIN2' %}
           <button class="btn-link" type="button" id="openIpAccessModal" style="border: none; cursor: pointer;">IP Access Control</button>
           {% endif %}
           <a class="btn-link" href="{{ url_for('index') }}">Back</a>
         </div>
       </div>
      {% if message %}
      <div class="message">{{ message }}</div>
      {% endif %}
      <form method="post">
        <label for="user_select">Select User</label>
        <select id="user_select" name="username">
          {% for user in users %}
          <option value="{{ user.username }}" {% if user.username == selected_user %}selected{% endif %}>
            {{ user.username }} ({{ user.role }})
          </option>
          {% endfor %}
        </select>
        <label for="role">Role</label>
        <select id="role" name="role">
          <option value="PAYMENT EDITOR" {% if selected_role == 'PAYMENT EDITOR' %}selected{% endif %}>Payment Editor</option>
          <option value="ADMIN" {% if selected_role == 'ADMIN' %}selected{% endif %}>Admin</option>
        </select>
        <label>Navigation Access</label>
        <div class="checklist">
          {% for item in nav_main %}
          <label>
            <input type="checkbox" name="nav_access" value="{{ item }}" {% if item in selected_nav %}checked{% endif %} />
            {{ item }}
          </label>
          {% endfor %}
        </div>
        <button class="btn" type="submit">Save Permissions</button>
      </form>
      </div>
      <div class="modal" id="ipAccessModal" aria-hidden="true">
      <div class="modal-card ip-access-card">
        <div class="modal-header ip-access-header">
          <div class="ip-access-title">
            <span class="ip-access-icon">🔐</span>
            <span>IP Access Control</span>
          </div>
          <button type="button" id="closeIpAccessModal">✕</button>
        </div>
        <form method="post" action="{{ url_for('admin_ip_access') }}">
          <div class="modal-body ip-access-body">
            <div class="ip-access-note">
              <span class="note-icon">ℹ</span>
              <span>Confirm credentials to access IP protection controls.</span>
            </div>
            <div class="form-group">
              <label for="ip_access_admin_user" class="form-label">
                <span>👤</span> Admin Username
              </label>
              <input 
                id="ip_access_admin_user" 
                name="admin_user" 
                type="text" 
                placeholder="Enter your admin username" 
                class="form-input"
                required 
              />
            </div>
            <div class="form-group">
              <label for="ip_access_admin_password" class="form-label">
                <span>🔒</span> Admin Password
              </label>
              <input 
                id="ip_access_admin_password" 
                name="admin_password" 
                type="password" 
                placeholder="Enter your admin password" 
                class="form-input"
                required 
              />
            </div>
          </div>
          <div class="modal-footer ip-access-footer">
            <button class="btn-secondary" type="button" id="cancelIpAccessModal">Cancel</button>
            <button class="btn-primary ip-access-submit" type="submit">Access Controls</button>
          </div>
        </form>
      </div>
      </div>
      <script>
      const ipAccessModal = document.getElementById("ipAccessModal");
      const openIpAccessModal = document.getElementById("openIpAccessModal");
      const closeIpAccessModal = document.getElementById("closeIpAccessModal");
      const cancelIpAccessModal = document.getElementById("cancelIpAccessModal");
      
      function openIpAccess() {
        ipAccessModal.classList.add("open");
        ipAccessModal.setAttribute("aria-hidden", "false");
      }
      
      function closeIpAccess() {
        ipAccessModal.classList.remove("open");
        ipAccessModal.setAttribute("aria-hidden", "true");
      }
      
      if (openIpAccessModal) {
        openIpAccessModal.addEventListener("click", openIpAccess);
      }
      if (closeIpAccessModal) {
        closeIpAccessModal.addEventListener("click", closeIpAccess);
      }
      if (cancelIpAccessModal) {
        cancelIpAccessModal.addEventListener("click", closeIpAccess);
      }
      ipAccessModal.addEventListener("click", (event) => {
        if (event.target === ipAccessModal) {
          closeIpAccess();
        }
      });
      </script>
      </body>
      </html>
      """

HISTORY_PAGE = """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <link rel="icon" type="image/svg+xml" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><defs><linearGradient id='g' x1='0%' y1='0%' x2='100%' y2='100%'><stop offset='0%' style='stop-color:%230a9fb5'/><stop offset='100%' style='stop-color:%230a6f86'/></linearGradient></defs><rect width='32' height='32' rx='6' fill='url(%23g)'/><circle cx='8' cy='8' r='2.5' fill='white' opacity='0.9'/><circle cx='24' cy='8' r='2' fill='%2300ff99' opacity='0.95'/><circle cx='24' cy='16' r='2' fill='%23ff6b6b' opacity='0.85'/><circle cx='24' cy='24' r='2' fill='%23ffd700' opacity='0.75'/><line x1='8' y1='5.5' x2='8' y2='4' stroke='white' stroke-width='1.2' opacity='0.8'/><line x1='8' y1='13.5' x2='8' y2='12' stroke='white' stroke-width='1.2' opacity='0.6'/><line x1='8' y1='21.5' x2='8' y2='20' stroke='white' stroke-width='1.2' opacity='0.4'/><rect x='14' y='11' width='6' height='10' rx='1' fill='none' stroke='white' stroke-width='0.8' opacity='0.6'/></svg>">
    <title>Action History</title>
    <style>
      :root {
        --ink: #0b1220;
        --muted: #5f6b7a;
        --panel: #ffffff;
        --border: #d7dee6;
        --brand: #0a6f86;
        --brand-light: #0d8fa3;
        --bg: #e9eef4;
        --green: #16a34a;
        --red: #dc2626;
        --blue: #0284c7;
        --font-body: "Bahnschrift", "Candara", "Trebuchet MS", sans-serif;
        --font-display: "Rockwell", "Constantia", "Georgia", serif;
        --font-mono: "Cascadia Mono", "Consolas", "Courier New", monospace;
      }
      * { box-sizing: border-box; }
      body {
        margin: 0;
        font-family: var(--font-body);
        background: {{ background_style|safe }};
        color: var(--ink);
        min-height: 100vh;
        padding: 28px;
      }
      .shell {
        max-width: 1200px;
        margin: 0 auto;
        background: var(--panel);
        border-radius: 16px;
        border: 1px solid var(--border);
        box-shadow: 0 20px 40px rgba(15,23,42,0.15);
        overflow: hidden;
        display: flex;
        flex-direction: column;
        max-height: 90vh;
      }
      .header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        border-bottom: 2px solid var(--border);
        padding-bottom: 18px;
        margin-bottom: 20px;
      }
      .header h1 {
        margin: 0;
        font-size: 24px;
        font-weight: 700;
        color: var(--ink);
        letter-spacing: -0.3px;
        font-family: var(--font-display);
      }
      .btn-link {
        background: linear-gradient(135deg, var(--brand) 0%, var(--brand-light) 100%);
        color: #fff;
        padding: 8px 16px;
        border-radius: 8px;
        text-decoration: none;
        font-weight: 600;
        font-size: 12px;
        border: none;
        cursor: pointer;
        transition: all 200ms ease;
        box-shadow: 0 4px 12px rgba(10,111,134,0.25);
      }
      .btn-link:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 16px rgba(10,111,134,0.35);
      }
      .table-wrapper {
        overflow-y: auto;
        overflow-x: auto;
        border-radius: 12px;
        border: 2px solid #0a9fb5;
        background: #ffffff;
        max-height: 60vh;
        margin: 0 24px 24px 24px;
        flex-shrink: 0;
      }
      table {
        width: 100%;
        border-collapse: collapse;
        font-size: 12px;
      }
      thead {
        background: linear-gradient(90deg, #0a9fb5 0%, #085a6d 100%);
        position: sticky;
        top: 0;
        z-index: 10;
      }
      thead th {
        text-align: left;
        padding: 14px 16px;
        border-bottom: 2px solid #0a6f86;
        color: #ffffff;
        font-weight: 700;
        font-size: 11px;
        letter-spacing: 0.5px;
        text-transform: uppercase;
      }
      tbody tr {
        transition: all 150ms ease;
        border-bottom: 1px solid #e8f0f5;
      }
      tbody tr:hover {
        background-color: rgba(10, 159, 181, 0.08);
        box-shadow: inset 0 0 8px rgba(10, 159, 181, 0.1);
      }
      tbody tr:nth-child(even) {
        background-color: rgba(10, 159, 181, 0.02);
      }
      tbody tr:last-child {
        border-bottom: none;
      }
      tbody td {
        padding: 14px 16px;
        color: #0a3642;
      }
      tbody td:first-child {
        color: #0a6f86;
        font-weight: 600;
      }
      .pill {
        display: inline-flex;
        align-items: center;
        padding: 5px 12px;
        border-radius: 6px;
        font-weight: 700;
        font-size: 11px;
        letter-spacing: 0.3px;
      }
      .pill-start {
        background: #dcfce7;
        color: #15803d;
        border: 1px solid #a7f3d0;
      }
      .pill-stop {
        background: #fee2e2;
        color: #b91c1c;
        border: 1px solid #fca5a5;
      }
      .pill-emergency {
        background: #fef08a;
        color: #92400e;
        border: 1px solid #fde047;
      }
      .pill-edit {
        background: #e0f2fe;
        color: #0369a1;
        border: 1px solid #0ea5e9;
      }
      .meta {
        color: var(--muted);
        font-size: 13px;
        margin-bottom: 14px;
        font-weight: 500;
        padding: 0 24px;
        flex-shrink: 0;
      }
      .message {
        background: linear-gradient(135deg, #e7f5ff 0%, #f0f9ff 100%);
        border: 1px solid #b6e0fe;
        color: #0c4a6e;
        padding: 12px 24px;
        border-radius: 8px;
        font-size: 13px;
        margin: 0;
        border-left: 3px solid var(--brand);
        flex-shrink: 0;
      }
    </style>
  </head>
  <body>
    <div class="shell">
      <div class="header">
        <h1>📋 Action History</h1>
        <a class="btn-link" href="{{ url_for('index') }}">Back</a>
      </div>
      {% if message %}
      <div class="message">{{ message }}</div>
      {% endif %}
      <div class="meta">📊 Showing <strong>{{ entries|length }}</strong> actions</div>
      <div class="table-wrapper">
        <table>
          <thead>
            <tr>
              <th>⏱ Time</th>
              <th>👤 User</th>
              <th>⚙ Action</th>
              <th>📝 Script</th>
              <th>🌐 IP</th>
            </tr>
          </thead>
          <tbody>
            {% for item in entries %}
            <tr>
              <td>{{ item.time }}</td>
              <td><strong>{{ item.user }}</strong></td>
              <td>
                {% if item.action == 'START' %}
                  <span class="pill pill-start">▶ START</span>
                {% elif item.action == 'STOP' %}
                  <span class="pill pill-stop">⏹ STOP</span>
                {% elif 'EMERGENCY' in item.action %}
                  <span class="pill pill-emergency">⚡ {{ item.action }}</span>
                {% else %}
                  <span class="pill pill-edit">✏ {{ item.action }}</span>
                {% endif %}
              </td>
              <td><code style="background: #f0f3f8; padding: 3px 8px; border-radius: 4px; font-family: monospace; color: #5f6b7a; font-size: 12px;">{{ item.script }}</code></td>
              <td><code style="background: #f0f3f8; padding: 2px 6px; border-radius: 4px; font-family: monospace; color: #5f6b7a;">{{ item.ip or '-' }}</code></td>
            </tr>
            {% endfor %}
          </tbody>
        </table>
      </div>
    </div>
  </body>
</html>
"""

RESTRICTED_PAGE = """
<!doctype html>
<html lang="en"><head><meta charset="utf-8" /><meta name="viewport" content="width=device-width, initial-scale=1" /><title>Access Restricted</title><style>:root{--ink:#0b1220;--muted:#5f6b7a;--panel:#fff;--border:#d7dee6;--font-body:"Bahnschrift","Candara","Trebuchet MS",sans-serif;--font-display:"Rockwell","Constantia","Georgia",serif;--font-mono:"Cascadia Mono","Consolas","Courier New",monospace;}*{box-sizing:border-box;}body{margin:0;font-family:var(--font-body);background:{{ background_style|safe }};color:var(--ink);min-height:100vh;padding:24px;display:flex;align-items:center;justify-content:center;}.shell{max-width:480px;width:100%;background:var(--panel);border-radius:16px;border:1px solid var(--border);box-shadow:0 18px 32px rgba(15,23,42,0.12);padding:32px;text-align:center;}.icon{font-size:64px;margin-bottom:16px;}h1{margin:0 0 12px;font-size:22px;font-family:var(--font-display);}.message{color:var(--muted);margin-bottom:24px;font-size:14px;}.btn{background:#0a6f86;color:#fff;padding:10px 20px;border-radius:8px;border:none;text-decoration:none;font-weight:600;cursor:pointer;display:inline-block;}.btn:hover{background:#085a6d;}</style></head><body><div class="shell"><div class="icon">🔒</div><h1>Access Restricted</h1><div class="message">{{ message }}</div><a class="btn" href="{{ url_for('logout') }}">Logout</a></div></body></html>
"""

ACCESS_LOG_PAGE = """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <link rel="icon" type="image/svg+xml" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><defs><linearGradient id='g' x1='0%' y1='0%' x2='100%' y2='100%'><stop offset='0%' style='stop-color:%230a9fb5'/><stop offset='100%' style='stop-color:%230a6f86'/></linearGradient></defs><rect width='32' height='32' rx='6' fill='url(%23g)'/><circle cx='8' cy='8' r='2.5' fill='white' opacity='0.9'/><circle cx='24' cy='8' r='2' fill='%2300ff99' opacity='0.95'/><circle cx='24' cy='16' r='2' fill='%23ff6b6b' opacity='0.85'/><circle cx='24' cy='24' r='2' fill='%23ffd700' opacity='0.75'/><line x1='8' y1='5.5' x2='8' y2='4' stroke='white' stroke-width='1.2' opacity='0.8'/><line x1='8' y1='13.5' x2='8' y2='12' stroke='white' stroke-width='1.2' opacity='0.6'/><line x1='8' y1='21.5' x2='8' y2='20' stroke='white' stroke-width='1.2' opacity='0.4'/><rect x='14' y='11' width='6' height='10' rx='1' fill='none' stroke='white' stroke-width='0.8' opacity='0.6'/></svg>">
    <title>Access Log</title>
    <style>
      :root {
        --ink: #0b1220;
        --muted: #5f6b7a;
        --panel: #ffffff;
        --border: #d7dee6;
        --brand: #0a6f86;
        --brand-light: #0d8fa3;
        --bg: #e9eef4;
        --green: #16a34a;
        --red: #dc2626;
        --yellow: #ea8c55;
        --font-body: "Bahnschrift", "Candara", "Trebuchet MS", sans-serif;
        --font-display: "Rockwell", "Constantia", "Georgia", serif;
        --font-mono: "Cascadia Mono", "Consolas", "Courier New", monospace;
      }
      * { box-sizing: border-box; }
      body {
        margin: 0;
        font-family: var(--font-body);
        background: {{ background_style|safe }};
        color: var(--ink);
        min-height: 100vh;
        padding: 28px;
      }
      .shell {
        max-width: 1200px;
        margin: 0 auto;
        background: var(--panel);
        border-radius: 16px;
        border: 1px solid var(--border);
        box-shadow: 0 20px 40px rgba(15,23,42,0.15);
        padding: 28px 32px;
        overflow: hidden;
      }
      .header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        border-bottom: 2px solid var(--border);
        padding-bottom: 18px;
        margin-bottom: 20px;
      }
      .header h1 {
        margin: 0;
        font-size: 24px;
        font-weight: 700;
        color: var(--ink);
        letter-spacing: -0.3px;
        font-family: var(--font-display);
      }
      .header-actions {
        display: flex;
        align-items: center;
        gap: 10px;
        flex-wrap: wrap;
      }
      .btn-link {
        background: linear-gradient(135deg, var(--brand) 0%, var(--brand-light) 100%);
        color: #fff;
        padding: 8px 16px;
        border-radius: 8px;
        text-decoration: none;
        font-weight: 600;
        font-size: 12px;
        border: none;
        cursor: pointer;
        transition: all 200ms ease;
        box-shadow: 0 4px 12px rgba(10,111,134,0.25);
      }
      .btn-link:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 16px rgba(10,111,134,0.35);
      }
      .btn-ghost {
        background: #f0f7fa;
        color: var(--brand);
        border: 1.5px solid rgba(10,111,134,0.3);
        padding: 7px 14px;
        border-radius: 8px;
        font-weight: 600;
        font-size: 12px;
        cursor: pointer;
        transition: all 200ms ease;
      }
      .btn-ghost:hover {
        background: rgba(10,111,134,0.08);
        border-color: rgba(10,111,134,0.5);
        transform: translateY(-1px);
      }
      .table-wrapper {
        overflow-x: auto;
        overflow-y: auto;
        max-height: 70vh;
        border-radius: 12px;
        border: 1px solid var(--border);
        background: #fafbfd;
      }
      table {
        width: 100%;
        border-collapse: collapse;
        font-size: 13px;
      }
      thead {
        background: linear-gradient(90deg, #f6f9fc 0%, #f0f5fa 100%);
        position: sticky;
        top: 0;
        z-index: 10;
      }
      thead th {
        text-align: left;
        padding: 14px 16px;
        border-bottom: 2px solid var(--border);
        color: var(--muted);
        font-weight: 700;
        font-size: 11px;
        letter-spacing: 0.5px;
        text-transform: uppercase;
      }
      tbody tr {
        transition: background-color 150ms ease;
        border-bottom: 1px solid #f0f3f8;
      }
      tbody tr:hover {
        background-color: #f8fafc;
      }
      tbody tr:last-child {
        border-bottom: none;
      }
      tbody td {
        padding: 12px 16px;
      }
      .pill {
        display: inline-flex;
        align-items: center;
        padding: 5px 12px;
        border-radius: 6px;
        font-weight: 700;
        font-size: 11px;
        letter-spacing: 0.3px;
      }
      .pill-success {
        background: #dcfce7;
        color: #15803d;
        border: 1px solid #a7f3d0;
      }
      .pill-fail {
        background: #fee2e2;
        color: #b91c1c;
        border: 1px solid #fca5a5;
      }
      .pill-blocked {
        background: #fed7aa;
        color: #92400e;
        border: 1px solid #fdba74;
      }
      .meta {
        color: var(--muted);
        font-size: 13px;
        margin-bottom: 14px;
        font-weight: 500;
      }
      .message {
        background: linear-gradient(135deg, #e7f5ff 0%, #f0f9ff 100%);
        border: 1px solid #b6e0fe;
        color: #0c4a6e;
        padding: 12px 14px;
        border-radius: 8px;
        font-size: 13px;
        margin-bottom: 16px;
        border-left: 3px solid var(--brand);
      }
      .modal {
        position: fixed;
        inset: 0;
        background: rgba(10,20,30,0.55);
        display: none;
        align-items: center;
        justify-content: center;
        padding: 20px;
        z-index: 50;
        backdrop-filter: blur(2px);
      }
      .modal.open {
        display: flex;
        animation: fadeIn 200ms ease;
      }
      @keyframes fadeIn {
        from { opacity: 0; }
        to { opacity: 1; }
      }
      .modal-card {
        width: 100%;
        max-width: 460px;
        background: #ffffff;
        border-radius: 16px;
        border: 1px solid rgba(13,24,40,0.12);
        box-shadow: 0 25px 50px rgba(15,23,42,0.3);
        overflow: hidden;
        animation: slideUp 250ms ease;
      }
      @keyframes slideUp {
        from { transform: translateY(20px); opacity: 0; }
        to { transform: translateY(0); opacity: 1; }
      }
      .modal-header {
        padding: 16px 20px;
        font-weight: 700;
        display: flex;
        justify-content: space-between;
        align-items: center;
        border-bottom: 1px solid var(--border);
        background: linear-gradient(90deg, #f6f9fc 0%, #f0f5fa 100%);
        font-size: 14px;
      }
      .modal-body {
        padding: 20px;
        display: grid;
        gap: 12px;
        font-size: 13px;
        max-height: 60vh;
        overflow-y: auto;
      }
      .modal-body label {
        font-size: 12px;
        color: var(--muted);
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.3px;
        margin-top: 4px;
      }
      .modal-body input {
        width: 100%;
        padding: 10px 12px;
        border-radius: 8px;
        border: 1px solid var(--border);
        font-size: 13px;
        transition: all 150ms ease;
      }
      .modal-body input:focus {
        outline: none;
        border-color: var(--brand);
        box-shadow: 0 0 0 3px rgba(10,111,134,0.1);
      }
      .modal-note {
        font-size: 12px;
        color: var(--muted);
        background: #f8fafc;
        padding: 10px 12px;
        border-radius: 6px;
        border-left: 3px solid rgba(10,111,134,0.2);
      }
      .modal-divider {
        height: 1px;
        background: var(--border);
        margin: 8px 0;
      }
      .modal-footer {
        padding: 14px 20px;
        display: flex;
        justify-content: flex-end;
        gap: 10px;
        border-top: 1px solid var(--border);
        background: #f9fbfd;
      }
      .modal-table {
        width: 100%;
        border-collapse: collapse;
        font-size: 12px;
      }
      .modal-table th,
      .modal-table td {
        text-align: left;
        padding: 8px 6px;
        border-bottom: 1px solid var(--border);
      }
      .modal-table th {
        color: var(--muted);
        font-weight: 700;
        font-size: 11px;
        text-transform: uppercase;
        letter-spacing: 0.3px;
      }
    </style>
  </head>
  <body>
    <div class="shell">
      <div class="header">
        <h1>Access Log</h1>
        <div class="header-actions">
          {% if show_ip_protection %}
          <button class="btn-ghost" type="button" id="openIpListModal">View IP List</button>
          <button class="btn-ghost" type="button" id="openIpModal">Add IP</button>
          {% if ip_protection_enabled %}
          <button class="btn-ghost" type="button" id="stopProtectionBtn" style="background: #dc3545; color: white;">Stop IP Protection</button>
          {% else %}
          <button class="btn-ghost" type="button" id="openProtectionModal" style="background: #28a745; color: white;">Start IP Protection</button>
          {% endif %}
          {% endif %}
          <a class="btn-link" href="{{ url_for('index') }}">Back</a>
        </div>
      </div>
      {% if message %}
      <div class="message">{{ message }}</div>
      {% endif %}
      <div class="meta" style="display: flex; justify-content: space-between; align-items: center;">
        <div>📊 Showing <strong>{{ entries|length }}</strong> logins</div>
        <div class="protection-status" id="protectionStatus" style="display: flex; align-items: center; gap: 8px; padding: 8px 16px; border-radius: 8px; background: {% if ip_protection_enabled %}rgba(40, 167, 69, 0.15); border: 1px solid #28a745;{% else %}rgba(220, 53, 69, 0.15); border: 1px solid #dc3545;{% endif %}">
          <span style="font-size: 16px;">{% if ip_protection_enabled %}🔐{% else %}🔓{% endif %}</span>
          <span style="font-weight: 700; font-size: 13px; color: {% if ip_protection_enabled %}#28a745;{% else %}#dc3545;{% endif %}letter-spacing: 0.3px;">Protection IP: <strong>{% if ip_protection_enabled %}ON{% else %}OFF{% endif %}</strong></span>
        </div>
      </div>
      <div class="table-wrapper">
        <table>
          <thead>
            <tr>
              <th>⏱ Time</th>
              <th>👤 User</th>
              <th>✓ Status</th>
              <th>🏷 IP Label</th>
              <th>🌐 IP</th>
            </tr>
          </thead>
          <tbody>
            {% for item in entries %}
            <tr>
              <td>{{ item.time }}</td>
              <td><strong>{{ item.user }}</strong></td>
              <td>
                <span class="pill {{ 'pill-success' if item.status == 'SUCCESS' else 'pill-blocked' if item.status == 'BLOCKED_IP' else 'pill-fail' }}">{{ item.status }}</span>
              </td>
              <td>{{ item.label }}</td>
              <td><code style="background: #f0f3f8; padding: 2px 6px; border-radius: 4px; font-family: monospace; color: #5f6b7a;">{{ item.ip or '-' }}</code></td>
            </tr>
            {% endfor %}
          </tbody>
        </table>
      </div>
    </div>
    <div class="modal" id="ipListModal" aria-hidden="true">
      <div class="modal-card">
        <div class="modal-header">
          <span>🔍 View IP List</span>
          <button class="btn-ghost" type="button" id="closeIpListModal" style="padding: 4px 8px; font-size: 18px; min-width: auto;">✕</button>
        </div>
        <form class="modal-body" method="post" action="{{ url_for('view_ip_list') }}">
          <div class="modal-note">Confirm admin credentials to view IP labels.</div>
          <label for="ip_list_admin_user">Admin User</label>
          <input id="ip_list_admin_user" name="admin_user" type="text" placeholder="Admin User" />
          <label for="ip_list_admin_password">Admin Password</label>
          <input id="ip_list_admin_password" name="admin_password" type="password" placeholder="Admin Password" />
          <div class="modal-footer">
            <button class="btn-ghost" type="button" id="cancelIpListModal">Cancel</button>
            <button class="btn-link" type="submit">View</button>
          </div>
        </form>
      </div>
    </div>
    <div class="modal" id="ipModal" aria-hidden="true">
      <div class="modal-card">
        <div class="modal-header">
          <span>🔐 Security Check</span>
          <button class="btn-ghost" type="button" id="closeIpModal" style="padding: 4px 8px; font-size: 18px; min-width: auto;">✕</button>
        </div>
        <form class="modal-body" method="post" action="{{ url_for('add_ip_label') }}">
          <div class="modal-note">Add an IP label, then verify admin identity.</div>
          <label for="ip_address">IP Address</label>
          <input id="ip_address" name="ip_address" type="text" placeholder="123.123.123.123" />
          <label for="ip_label">Label</label>
          <input id="ip_label" name="ip_label" type="text" placeholder="Office / Home" />
          <div class="modal-divider">Admin Confirmation</div>
          <label for="admin_user">Admin User</label>
          <input id="admin_user" name="admin_user" type="text" placeholder="Admin User" />
          <label for="admin_password">Admin Password</label>
          <input id="admin_password" name="admin_password" type="password" placeholder="Admin Password" />
          <div class="modal-footer">
            <button class="btn-ghost" type="button" id="cancelIpModal">Cancel</button>
            <button class="btn-link" type="submit">Save</button>
          </div>
        </form>
      </div>
    </div>
    <div class="modal" id="ipListResult" aria-hidden="true">
      <div class="modal-card">
        <div class="modal-header">
          <span>📋 IP Label List</span>
          <button class="btn-ghost" type="button" id="closeIpListResult" style="padding: 4px 8px; font-size: 18px; min-width: auto;">✕</button>
        </div>
        <div class="modal-body">
          {% if ip_list %}
          <table class="modal-table">
            <thead>
              <tr>
                <th>IP</th>
                <th>Label</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {% for item in ip_list %}
              <tr>
                <td>{{ item.ip }}</td>
                <td>{{ item.label }}</td>
                <td>
                  <form method="post" action="{{ url_for('remove_ip_label') }}" style="display:inline;">
                    <input type="hidden" name="ip_address" value="{{ item.ip }}" />
                    <button class="btn-ghost" type="submit" style="background: #dc3545; color: white; padding: 4px 8px; font-size: 11px;">Remove</button>
                  </form>
                </td>
              </tr>
              {% endfor %}
            </tbody>
          </table>
          {% else %}
          <div class="modal-note">No IP labels saved yet.</div>
          {% endif %}
          <div class="modal-footer">
            <button class="btn-ghost" type="button" id="closeIpListResultFooter">Close</button>
          </div>
        </div>
      </div>
      </div>
      <div class="modal" id="protectionModal" aria-hidden="true">
      <div class="modal-card">
        <div class="modal-header">
          <span>🔐 Enable IP Protection</span>
          <button class="btn-ghost" type="button" id="closeProtectionModal" style="padding: 4px 8px; font-size: 18px; min-width: auto;">✕</button>
        </div>
        <form class="modal-body" method="post" action="{{ url_for('toggle_ip_protection') }}">
          <div class="modal-note">Confirm admin credentials to enable IP protection.</div>
          <input type="hidden" name="action" value="start" />
          <label for="protection_admin_user">Admin User</label>
          <input id="protection_admin_user" name="admin_user" type="text" placeholder="Admin User" required />
          <label for="protection_admin_password">Admin Password</label>
          <input id="protection_admin_password" name="admin_password" type="password" placeholder="Admin Password" required />
          <div class="modal-footer">
            <button class="btn-ghost" type="button" id="cancelProtectionModal">Cancel</button>
            <button class="btn-link" type="submit">Enable Protection</button>
          </div>
        </form>
      </div>
      </div>
      <div class="modal" id="stopProtectionModal" aria-hidden="true">
      <div class="modal-card">
        <div class="modal-header">
          <span>🔓 Disable IP Protection</span>
          <button class="btn-ghost" type="button" id="closeStopProtectionModal" style="padding: 4px 8px; font-size: 18px; min-width: auto;">✕</button>
        </div>
        <form class="modal-body" method="post" action="{{ url_for('toggle_ip_protection') }}" id="stopProtectionForm">
          <div class="modal-note">⚠️ Confirm admin credentials to disable IP protection.</div>
          <input type="hidden" name="action" value="stop" />
          <label for="stop_protection_admin_user">Admin User</label>
          <input id="stop_protection_admin_user" name="admin_user" type="text" placeholder="Admin User" required />
          <label for="stop_protection_admin_password">Admin Password</label>
          <input id="stop_protection_admin_password" name="admin_password" type="password" placeholder="Admin Password" required />
          <div class="modal-footer">
            <button class="btn-ghost" type="button" id="cancelStopProtectionModal">Cancel</button>
            <button class="btn-link" type="submit" style="background: #dc3545;">Disable Protection</button>
          </div>
        </form>
      </div>
      </div>
      <script>
      const ipModal = document.getElementById("ipModal");
      const openIpModal = document.getElementById("openIpModal");
      const closeIpModal = document.getElementById("closeIpModal");
      const cancelIpModal = document.getElementById("cancelIpModal");
      const ipListModal = document.getElementById("ipListModal");
      const openIpListModal = document.getElementById("openIpListModal");
      const closeIpListModal = document.getElementById("closeIpListModal");
      const cancelIpListModal = document.getElementById("cancelIpListModal");
      const ipListResult = document.getElementById("ipListResult");
      const closeIpListResult = document.getElementById("closeIpListResult");
      const closeIpListResultFooter = document.getElementById("closeIpListResultFooter");
      function openIp() {
        ipModal.classList.add("open");
        ipModal.setAttribute("aria-hidden", "false");
      }
      function closeIp() {
        ipModal.classList.remove("open");
        ipModal.setAttribute("aria-hidden", "true");
      }
      function openIpList() {
        ipListModal.classList.add("open");
        ipListModal.setAttribute("aria-hidden", "false");
      }
      function closeIpList() {
        ipListModal.classList.remove("open");
        ipListModal.setAttribute("aria-hidden", "true");
      }
      function openIpListResult() {
        ipListResult.classList.add("open");
        ipListResult.setAttribute("aria-hidden", "false");
      }
      function closeIpListResultModal() {
        ipListResult.classList.remove("open");
        ipListResult.setAttribute("aria-hidden", "true");
      }
      if (openIpModal) {
        openIpModal.addEventListener("click", openIp);
      }
      if (closeIpModal) {
        closeIpModal.addEventListener("click", closeIp);
      }
      if (cancelIpModal) {
        cancelIpModal.addEventListener("click", closeIp);
      }
      if (openIpListModal) {
        openIpListModal.addEventListener("click", openIpList);
      }
      if (closeIpListModal) {
        closeIpListModal.addEventListener("click", closeIpList);
      }
      if (cancelIpListModal) {
        cancelIpListModal.addEventListener("click", closeIpList);
      }
      if (closeIpListResult) {
        closeIpListResult.addEventListener("click", closeIpListResultModal);
      }
      if (closeIpListResultFooter) {
        closeIpListResultFooter.addEventListener("click", closeIpListResultModal);
      }
      ipModal.addEventListener("click", (event) => {
        if (event.target === ipModal) {
          closeIp();
        }
      });
      ipListModal.addEventListener("click", (event) => {
        if (event.target === ipListModal) {
          closeIpList();
        }
      });
      ipListResult.addEventListener("click", (event) => {
        if (event.target === ipListResult) {
          closeIpListResultModal();
        }
      });
      // Notification function
      function showNotification(message, type = "info") {
        const notification = document.createElement("div");
        notification.style.cssText = `
          position: fixed;
          top: 20px;
          right: 20px;
          padding: 16px 24px;
          border-radius: 8px;
          font-weight: 600;
          z-index: 10000;
          animation: slideIn 0.3s ease-out;
          box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        `;
        
        if (type === "success") {
          notification.style.background = "#28a745";
          notification.style.color = "white";
        } else if (type === "error") {
          notification.style.background = "#dc3545";
          notification.style.color = "white";
        } else {
          notification.style.background = "#0a9fb5";
          notification.style.color = "white";
        }
        
        notification.textContent = message;
        document.body.appendChild(notification);
        
        setTimeout(() => {
          notification.style.animation = "slideOut 0.3s ease-out";
          setTimeout(() => notification.remove(), 300);
        }, 3000);
      }
      
      if (!document.querySelector('style[data-notification]')) {
        const style = document.createElement('style');
        style.setAttribute('data-notification', 'true');
        style.textContent = `
          @keyframes slideIn {
            from { transform: translateX(400px); opacity: 0; }
            to { transform: translateX(0); opacity: 1; }
          }
          @keyframes slideOut {
            from { transform: translateX(0); opacity: 1; }
            to { transform: translateX(400px); opacity: 0; }
          }
        `;
        document.head.appendChild(style);
      }
      
      const protectionModal = document.getElementById("protectionModal");
      const openProtectionModal = document.getElementById("openProtectionModal");
      const closeProtectionModal = document.getElementById("closeProtectionModal");
      const cancelProtectionModal = document.getElementById("cancelProtectionModal");
      function openProtection() {
        protectionModal.classList.add("open");
        protectionModal.setAttribute("aria-hidden", "false");
      }
      function closeProtection() {
        protectionModal.classList.remove("open");
        protectionModal.setAttribute("aria-hidden", "true");
        const protectionForm = document.querySelector('#protectionModal form');
        if (protectionForm) protectionForm.reset();
      }
      if (openProtectionModal) {
        openProtectionModal.addEventListener("click", openProtection);
      }
      if (closeProtectionModal) {
        closeProtectionModal.addEventListener("click", closeProtection);
      }
      if (cancelProtectionModal) {
        cancelProtectionModal.addEventListener("click", closeProtection);
      }
      protectionModal.addEventListener("click", (event) => {
        if (event.target === protectionModal) {
          closeProtection();
        }
      });
      
      // Update Protection Status Display
      function updateProtectionStatus(enabled) {
        const statusEl = document.getElementById("protectionStatus");
        if (statusEl) {
          if (enabled) {
            statusEl.style.background = "rgba(40, 167, 69, 0.15)";
            statusEl.style.border = "1px solid #28a745";
            statusEl.querySelector("span:first-child").textContent = "🔐";
            statusEl.querySelector("span:last-child").style.color = "#28a745";
            statusEl.querySelector("span:last-child").innerHTML = 'Protection IP: <strong>ON</strong>';
          } else {
            statusEl.style.background = "rgba(220, 53, 69, 0.15)";
            statusEl.style.border = "1px solid #dc3545";
            statusEl.querySelector("span:first-child").textContent = "🔓";
            statusEl.querySelector("span:last-child").style.color = "#dc3545";
            statusEl.querySelector("span:last-child").innerHTML = 'Protection IP: <strong>OFF</strong>';
          }
        }
      }
      
      // Handle Start Protection Form Submission via AJAX
      const protectionForm = document.querySelector('#protectionModal form');
      if (protectionForm) {
        protectionForm.addEventListener("submit", function(e) {
          e.preventDefault();
          const formData = new FormData(protectionForm);
          fetch("{{ url_for('toggle_ip_protection') }}", {
            method: "POST",
            body: formData
          })
          .then(response => response.text())
          .then(data => {
            closeProtection();
            updateProtectionStatus(true);
            showNotification("IP Protection enabled successfully", "success");
            setTimeout(() => location.reload(), 2000);
          })
          .catch(error => {
            showNotification("Error enabling IP Protection", "error");
            console.error("Error:", error);
          });
        });
      }
      
      const stopProtectionModal = document.getElementById("stopProtectionModal");
      const stopProtectionBtn = document.getElementById("stopProtectionBtn");
      const closeStopProtectionModal = document.getElementById("closeStopProtectionModal");
      const cancelStopProtectionModal = document.getElementById("cancelStopProtectionModal");
      const stopProtectionForm = document.getElementById("stopProtectionForm");
      
      function openStopProtection() {
        stopProtectionModal.classList.add("open");
        stopProtectionModal.setAttribute("aria-hidden", "false");
      }
      function closeStopProtection() {
        stopProtectionModal.classList.remove("open");
        stopProtectionModal.setAttribute("aria-hidden", "true");
        stopProtectionForm.reset();
      }
      if (stopProtectionBtn) {
        stopProtectionBtn.addEventListener("click", openStopProtection);
      }
      if (closeStopProtectionModal) {
        closeStopProtectionModal.addEventListener("click", closeStopProtection);
      }
      if (cancelStopProtectionModal) {
        cancelStopProtectionModal.addEventListener("click", closeStopProtection);
      }
      stopProtectionModal.addEventListener("click", (event) => {
        if (event.target === stopProtectionModal) {
          closeStopProtection();
        }
      });
      
      // Handle Stop Protection Form Submission via AJAX
      if (stopProtectionForm) {
        stopProtectionForm.addEventListener("submit", function(e) {
          e.preventDefault();
          const formData = new FormData(stopProtectionForm);
          fetch("{{ url_for('toggle_ip_protection') }}", {
            method: "POST",
            body: formData
          })
          .then(response => response.text())
          .then(data => {
            closeStopProtection();
            updateProtectionStatus(false);
            showNotification("IP Protection disabled successfully", "success");
            setTimeout(() => location.reload(), 2000);
          })
          .catch(error => {
            showNotification("Error disabling IP Protection", "error");
            console.error("Error:", error);
          });
        });
      }
      
      const showIpList = {{ "true" if show_ip_list else "false" }};
      if (showIpList) {
        openIpListResult();
      }
      </script>
  </body>
</html>
"""

CHANGE_PATH_MODAL = r"""
<!doctype html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <link rel="icon" type="image/svg+xml" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><defs><linearGradient id='g' x1='0%' y1='0%' x2='100%' y2='100%'><stop offset='0%' style='stop-color:%230a9fb5'/><stop offset='100%' style='stop-color:%230a6f86'/></linearGradient></defs><rect width='32' height='32' rx='6' fill='url(%23g)'/><circle cx='8' cy='8' r='2.5' fill='white' opacity='0.9'/><circle cx='24' cy='8' r='2' fill='%2300ff99' opacity='0.95'/><circle cx='24' cy='16' r='2' fill='%23ff6b6b' opacity='0.85'/><circle cx='24' cy='24' r='2' fill='%23ffd700' opacity='0.75'/><line x1='8' y1='5.5' x2='8' y2='4' stroke='white' stroke-width='1.2' opacity='0.8'/><line x1='8' y1='13.5' x2='8' y2='12' stroke='white' stroke-width='1.2' opacity='0.6'/><line x1='8' y1='21.5' x2='8' y2='20' stroke='white' stroke-width='1.2' opacity='0.4'/><rect x='14' y='11' width='6' height='10' rx='1' fill='none' stroke='white' stroke-width='0.8' opacity='0.6'/></svg>">
    <title>Change Script Path</title>
    <style>
        :root {
            --ink: #0b1220;
            --muted: #5f6b7a;
            --panel: #ffffff;
            --border: #d7dee6;
            --brand: #0a6f86;
            --bg: #e9eef4;
            --font-body: "Bahnschrift", "Candara", "Trebuchet MS", sans-serif;
            --font-display: "Rockwell", "Constantia", "Georgia", serif;
            --font-mono: "Cascadia Mono", "Consolas", "Courier New", monospace;
        }
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            font-family: var(--font-body);
            background: {{ background_style|safe }};
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }
        .modal-card {
            background: var(--panel);
            border-radius: 14px;
            border: 1px solid var(--border);
            box-shadow: 0 20px 40px rgba(15,23,42,0.25);
            padding: 0;
            max-width: 520px;
            width: 100%;
            overflow: hidden;
        }
        .modal-header {
            background: linear-gradient(135deg, #0a9fb5 0%, #0a6f86 100%);
            color: white;
            padding: 20px 24px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 20px;
            min-height: 100px;
        }
        .header-stats {
            flex: 1;
            display: flex;
            gap: 20px;
            justify-content: center;
        }
        .stat-box {
            background: rgba(255,255,255,0.1);
            border-radius: 8px;
            padding: 12px 16px;
            text-align: center;
            min-width: 100px;
            border: 1px solid rgba(255,255,255,0.2);
        }
        .stat-number {
            font-size: 24px;
            font-weight: 800;
            color: #fff;
        }
        .stat-label {
            font-size: 11px;
            color: rgba(255,255,255,0.8);
            margin-top: 4px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        .modal-header-content {
            flex: 1;
        }
        .modal-header h2 {
            color: white;
            margin: 0 0 6px 0;
            font-size: 18px;
            font-weight: 700;
        }
        .modal-header-desc {
            color: rgba(255,255,255,0.9);
            font-size: 12px;
            margin: 0;
            line-height: 1.4;
        }
        .modal-close-btn {
            background: #0a6f86;
            color: white;
            border: none;
            padding: 6px 10px;
            border-radius: 6px;
            cursor: pointer;
            font-weight: 600;
            font-size: 11px;
            transition: all 200ms ease;
            white-space: nowrap;
            flex-shrink: 0;
        }
        .modal-close-btn:hover {
            background: rgba(255,255,255,0.35);
            transform: translateY(-1px);
        }
        .modal-body {
            padding: 24px;
        }
        h2 {
            color: var(--brand);
            margin-bottom: 8px;
            font-size: 18px;
            font-weight: 700;
            font-family: var(--font-display);
        }
        .description {
            color: var(--muted);
            font-size: 13px;
            margin-bottom: 20px;
            line-height: 1.5;
        }
        .form-group {
            margin-bottom: 20px;
        }
        label {
            display: block;
            color: var(--ink);
            font-weight: 700;
            margin-bottom: 10px;
            font-size: 13px;
            letter-spacing: 0.3px;
        }
        select, input {
            width: 100%;
            padding: 12px 14px;
            border: 2px solid var(--border);
            border-radius: 8px;
            font-size: 13px;
            font-family: inherit;
            transition: all 200ms ease;
            background: white;
        }
        select:focus, input:focus {
            outline: none;
            border-color: var(--brand);
            box-shadow: 0 0 0 4px rgba(10,111,134,0.1);
            background: #f8fbfd;
        }
        .checkbox-group {
            border: 1px solid var(--border);
            border-radius: 8px;
            max-height: 280px;
            overflow-y: auto;
            padding: 10px;
            background: linear-gradient(135deg, #f7fafc 0%, #f0f5f9 100%);
        }
        .checkbox-item {
            display: flex;
            align-items: center;
            padding: 10px;
            border-radius: 6px;
            margin-bottom: 6px;
            background: white;
            border: 1px solid rgba(10,111,134,0.15);
            cursor: pointer;
            transition: all 200ms ease;
        }
        .checkbox-item:last-child {
            margin-bottom: 0;
        }
        .checkbox-item:hover {
            background: #f0f9fc;
            border-color: rgba(10,111,134,0.3);
        }
        .checkbox-item input[type="checkbox"] {
            width: auto;
            margin-right: 10px;
            cursor: pointer;
            accent-color: var(--brand);
        }
        .checkbox-item label {
            margin: 0;
            cursor: pointer;
            font-weight: 400;
            flex: 1;
        }
        .select-all-item {
            background: #f0f9fc;
            font-weight: 600;
            border-color: rgba(10,111,134,0.2);
            margin-bottom: 8px;
        }
        .search-scripts-container {
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 12px;
        }
        .search-scripts-input {
            flex: 1;
            padding: 12px 14px;
            border: 2px solid var(--border);
            border-radius: 8px;
            font-size: 13px;
            font-family: inherit;
            background: white;
            transition: all 200ms ease;
        }
        .search-scripts-input:focus {
            outline: none;
            border-color: var(--brand);
            box-shadow: 0 0 0 4px rgba(10,111,134,0.1);
            background: #f8fbfd;
        }
        .search-scripts-input::placeholder {
            color: #a0aec0;
        }
        .search-result-count {
            font-size: 12px;
            font-weight: 600;
            color: #0a6f86;
            white-space: nowrap;
            padding: 6px 10px;
            background: #d8f6ff;
            border-radius: 6px;
            border: 1px solid #a8e3f0;
        }
        .checkbox-item.hidden {
            display: none;
        }
        input[type="text"] {
            padding: 10px;
            color: var(--ink);
        }
        input[type="text"]::placeholder {
            color: var(--muted);
        }
        button[type="submit"] {
            background: linear-gradient(135deg, #0a9fb5 0%, #0a6f86 100%);
            color: white;
            padding: 14px 20px;
            border: none;
            border-radius: 8px;
            font-size: 14px;
            font-weight: 700;
            cursor: pointer;
            width: 100%;
            transition: all 200ms ease;
            box-shadow: 0 4px 12px rgba(10,111,134,0.2);
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        button[type="submit"]:hover {
            background: linear-gradient(135deg, #08899a 0%, #085a6d 100%);
            box-shadow: 0 6px 16px rgba(10,111,134,0.3);
            transform: translateY(-2px);
        }
        button[type="submit"]:active {
            transform: translateY(0);
        }
        #openConfirm {
            width: 100%;
            margin-top: 6px;
            background: linear-gradient(135deg, #0a9fb5 0%, #0a6f86 100%);
            color: #fff;
            padding: 14px 20px;
            border: none;
            border-radius: 10px;
            font-size: 13px;
            font-weight: 800;
            text-transform: uppercase;
            letter-spacing: 0.6px;
            cursor: pointer;
            box-shadow: 0 8px 20px rgba(10,111,134,0.25);
            transition: transform 160ms ease, box-shadow 160ms ease, filter 160ms ease;
        }
        #openConfirm:hover {
            transform: translateY(-2px);
            box-shadow: 0 12px 26px rgba(10,111,134,0.35);
            filter: brightness(1.03);
        }
        #openConfirm:active {
            transform: translateY(0);
            box-shadow: 0 6px 16px rgba(10,111,134,0.22);
        }
        .path-list {
            margin-top: 24px;
            padding: 18px;
            background: linear-gradient(135deg, #f0f8f9 0%, #e0f2f7 100%);
            border-radius: 10px;
            border: 2px solid rgba(10,111,134,0.15);
            box-shadow: inset 0 1px 3px rgba(10,111,134,0.05);
        }
        .path-list-title {
            font-weight: 800;
            color: var(--ink);
            margin-bottom: 14px;
            font-size: 13px;
            letter-spacing: 0.4px;
            text-transform: uppercase;
            color: #0a6f86;
        }
        .path-item {
            display: grid;
            grid-template-columns: 140px 1fr;
            gap: 12px;
            align-items: flex-start;
            padding: 10px 12px;
            background: white;
            border-radius: 6px;
            margin-bottom: 8px;
            font-size: 12px;
            border: 1px solid rgba(10,111,134,0.12);
            transition: all 200ms ease;
        }
        .path-item:hover {
            background: #fafbfc;
            border-color: rgba(10,111,134,0.2);
        }
        .path-item:last-child {
            margin-bottom: 0;
        }
        .path-item-label {
            font-weight: 700;
            color: #0a6f86;
            font-size: 12px;
        }
        .path-item-value {
            color: var(--muted);
            word-break: break-all;
            font-size: 11px;
            font-family: var(--font-mono);
            background: #f5f5f5;
            padding: 4px 6px;
            border-radius: 4px;
        }
        .note {
            background: linear-gradient(135deg, #e0f7fa 0%, #b3e5fc 100%);
            border: 2px solid #4fc3f7;
            color: #01579b;
            padding: 14px 16px;
            border-radius: 8px;
            font-size: 13px;
            margin-bottom: 20px;
            font-weight: 500;
            display: flex;
            align-items: center;
            gap: 10px;
            box-shadow: 0 2px 8px rgba(79,195,247,0.1);
        }
        .success-message {
            background: linear-gradient(135deg, #d4edda 0%, #c3e6cb 100%);
            border: 2px solid #28a745;
            color: #155724;
            padding: 14px 16px;
            border-radius: 8px;
            font-size: 13px;
            margin-bottom: 16px;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 10px;
            animation: slideIn 300ms ease;
        }
        .error-message {
            background: linear-gradient(135deg, #f8d7da 0%, #f5c6cb 100%);
            border: 2px solid #dc3545;
            color: #721c24;
            padding: 14px 16px;
            border-radius: 8px;
            font-size: 13px;
            margin-bottom: 16px;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 10px;
            animation: slideIn 300ms ease;
        }
        .confirm-modal {
            position: fixed;
            inset: 0;
            display: none;
            align-items: center;
            justify-content: center;
            padding: 20px;
            background: rgba(10,20,30,0.6);
            backdrop-filter: blur(4px);
            z-index: 1000;
        }
        .confirm-modal.open {
            display: flex;
            animation: fadeIn 200ms ease;
        }
        .confirm-card {
            width: 100%;
            max-width: 460px;
            background: #ffffff;
            border-radius: 16px;
            border: 1px solid rgba(10,111,134,0.18);
            box-shadow: 0 20px 50px rgba(10,20,30,0.3);
            overflow: hidden;
            animation: slideIn 250ms ease;
        }
        .confirm-header {
            padding: 16px 20px;
            background: linear-gradient(135deg, #0a9fb5 0%, #0a6f86 100%);
            color: #fff;
            font-weight: 800;
            font-size: 14px;
            letter-spacing: 0.4px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }
        .confirm-header button {
            background: rgba(255,255,255,0.2);
            color: #fff;
            border: none;
            width: 30px;
            height: 30px;
            border-radius: 8px;
            cursor: pointer;
            font-size: 16px;
        }
        .confirm-body {
            padding: 18px 20px;
            display: grid;
            gap: 12px;
            font-size: 13px;
        }
        .confirm-note {
            background: #f0f9fc;
            border-left: 3px solid #0a9fb5;
            padding: 10px 12px;
            border-radius: 8px;
            color: #0a3642;
            font-weight: 600;
        }
        .confirm-body label {
            font-size: 12px;
            color: var(--muted);
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.3px;
        }
        .confirm-body input {
            width: 100%;
            padding: 10px 12px;
            border-radius: 8px;
            border: 1.5px solid rgba(10,111,134,0.2);
            font-size: 13px;
        }
        .confirm-footer {
            padding: 14px 20px;
            display: flex;
            justify-content: flex-end;
            gap: 10px;
            border-top: 1px solid rgba(10,111,134,0.1);
            background: #f8fafc;
        }
        .confirm-cancel {
            background: #eef2f6;
            color: #0a3642;
            border: 1.5px solid rgba(10,111,134,0.2);
            padding: 9px 16px;
            border-radius: 8px;
            font-weight: 700;
            font-size: 12px;
            cursor: pointer;
        }
        .confirm-submit {
            background: linear-gradient(135deg, #0a9fb5 0%, #0a6f86 100%);
            color: #fff;
            border: none;
            padding: 9px 18px;
            border-radius: 8px;
            font-weight: 800;
            font-size: 12px;
            cursor: pointer;
            text-transform: uppercase;
            letter-spacing: 0.4px;
            box-shadow: 0 6px 16px rgba(10,111,134,0.25);
        }
        @keyframes slideIn {
            from {
                opacity: 0;
                transform: translateY(-10px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }
    </style>
</head>
<body>
    <div class="modal-card">
        <div class="modal-header">
            <div class="modal-header-content">
                <h2>Change Script Path</h2>
                <p class="modal-header-desc">Update script path for different PC configurations (e.g., different drive letters or usernames)</p>
            </div>
            
            <div class="header-stats">
                <div class="stat-box">
                    <div class="stat-number">{{ scripts|length }}</div>
                    <div class="stat-label">Total Scripts</div>
                </div>
                <div class="stat-box">
                    <div class="stat-number" id="selectedCount">0</div>
                    <div class="stat-label">Selected</div>
                </div>
            </div>
            
            <button type="button" onclick="window.close()" class="modal-close-btn">Back</button>
        </div>
        
        <div class="modal-body">
        <div id="successMessage" class="success-message" style="display:none;">
            ✓ <span id="successText"></span>
        </div>
        <div id="errorMessage" class="error-message" style="display:none;">
            ✗ <span id="errorText"></span>
        </div>
        
        <div class="note">
            💡 Select scripts and provide the directory path only (without filename)
        </div>

        <form id="updatePathForm" novalidate>
            <div class="form-group">
                <label>Select Scripts</label>
                <div class="search-scripts-container">
                    <input type="text" id="scriptSearch" placeholder="🔍 Search scripts..." class="search-scripts-input">
                    <span class="search-result-count" id="searchCount"></span>
                </div>
                <div class="checkbox-group" id="scriptCheckboxGroup">
                    <div class="checkbox-item select-all-item">
                        <input type="checkbox" id="selectAll">
                        <label for="selectAll">Select All</label>
                    </div>
                    {% for idx, script in enumerate(scripts) %}
                    <div class="checkbox-item" data-script-name="{{ script.name.lower() }}">
                        <input type="checkbox" name="script_ids[]" id="script{{ idx }}" value="{{ idx }}">
                        <label for="script{{ idx }}">{{ script.name }}</label>
                    </div>
                    {% endfor %}
                </div>
            </div>

            <div class="form-group">
                <label for="newPath">New Path (Directory Only)</label>
                <input type="text" id="newPath" name="new_path" placeholder="C:\Users\User\Downloads\Dashboard1\uploads" required>
            </div>

            <button type="button" id="openConfirm">Update Path</button>
        </form>

        <div class="confirm-modal" id="confirmModal" aria-hidden="true">
            <div class="confirm-card">
                <div class="confirm-header">
                    <span>Confirm Admin Access</span>
                    <button type="button" id="closeConfirmModal">✕</button>
                </div>
                <div class="confirm-body">
                    <div class="confirm-note">Enter admin credentials to update script paths.</div>
                    <label for="confirm_admin_user">Admin User</label>
                    <input id="confirm_admin_user" name="admin_user" type="text" form="updatePathForm" placeholder="Admin username" />
                    <label for="confirm_admin_password">Admin Password</label>
                    <input id="confirm_admin_password" name="admin_password" type="password" form="updatePathForm" placeholder="Admin password" />
                </div>
                <div class="confirm-footer">
                    <button class="confirm-cancel" type="button" id="cancelConfirmModal">Cancel</button>
                    <button class="confirm-submit" type="button" id="confirmUpdate">Confirm</button>
                </div>
            </div>
        </div>

        <div class="path-list">
            <div class="path-list-title">Current Paths:</div>
            {% for script in scripts %}
            <div class="path-item">
                <span class="path-item-label">{{ script.name }}</span>
                <span class="path-item-value">{{ script.path | dirname }}</span>
            </div>
            {% endfor %}
        </div>
        </div>
    </div>

    <script>
        const selectAll = document.getElementById('selectAll');
        const checkboxes = document.querySelectorAll('input[name="script_ids[]"]');
        const selectedCount = document.getElementById('selectedCount');

        function updateSelectedCount() {
            const count = document.querySelectorAll('input[name="script_ids[]"]:checked').length;
            if (selectedCount) {
                selectedCount.textContent = String(count);
            }
        }

        selectAll.addEventListener('change', function() {
            checkboxes.forEach(checkbox => {
                checkbox.checked = this.checked;
            });
            updateSelectedCount();
        });

        checkboxes.forEach(checkbox => {
            checkbox.addEventListener('change', function() {
                const allChecked = Array.from(checkboxes).every(cb => cb.checked);
                const anyChecked = Array.from(checkboxes).some(cb => cb.checked);
                selectAll.checked = allChecked;
                selectAll.indeterminate = anyChecked && !allChecked;
                updateSelectedCount();
            });
        });
        updateSelectedCount();

        // Script search functionality
        const searchInput = document.getElementById('scriptSearch');
        const searchCount = document.getElementById('searchCount');
        const checkboxGroup = document.getElementById('scriptCheckboxGroup');
        const checkboxItems = checkboxGroup.querySelectorAll('.checkbox-item:not(.select-all-item)');

        function updateSearchResults() {
            const searchTerm = searchInput.value.toLowerCase().trim();
            let visibleCount = 0;

            checkboxItems.forEach(item => {
                const scriptName = item.getAttribute('data-script-name');
                const isMatching = scriptName.includes(searchTerm);

                if (isMatching || searchTerm === '') {
                    item.classList.remove('hidden');
                    visibleCount++;
                } else {
                    item.classList.add('hidden');
                }
            });

            // Update result count
            if (searchTerm === '') {
                searchCount.textContent = '';
            } else {
                searchCount.textContent = visibleCount + ' result' + (visibleCount !== 1 ? 's' : '');
            }
        }

        searchInput.addEventListener('input', updateSearchResults);
        searchInput.addEventListener('keyup', updateSearchResults);

        const confirmModal = document.getElementById('confirmModal');
        const closeConfirmModal = document.getElementById('closeConfirmModal');
        const cancelConfirmModal = document.getElementById('cancelConfirmModal');
        const confirmUpdate = document.getElementById('confirmUpdate');
        const openConfirm = document.getElementById('openConfirm');
        const updatePathForm = document.getElementById('updatePathForm');

        function openConfirmModal() {
            confirmModal.classList.add('open');
            confirmModal.setAttribute('aria-hidden', 'false');
        }

        function closeConfirmModalFn() {
            confirmModal.classList.remove('open');
            confirmModal.setAttribute('aria-hidden', 'true');
        }

        function submitUpdatePath() {
            const selected = document.querySelectorAll('input[name="script_ids[]"]:checked').length;
            const path = document.getElementById('newPath').value.trim();
            const adminUser = document.getElementById('confirm_admin_user').value.trim();
            const adminPassword = document.getElementById('confirm_admin_password').value.trim();

            // Hide previous messages
            document.getElementById('successMessage').style.display = 'none';
            document.getElementById('errorMessage').style.display = 'none';

            if (selected === 0) {
                showError('Please select at least one script');
                return;
            }
            if (!path) {
                showError('Please enter a new path');
                return;
            }
            if (!adminUser || !adminPassword) {
                showError('Please enter admin credentials');
                return;
            }

            const formData = new FormData(updatePathForm);
            fetch('{{ url_for("update_script_path_bulk") }}', {
                method: 'POST',
                body: formData
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    showSuccess(data.message);
                    closeConfirmModalFn();
                    setTimeout(() => {
                        updatePathForm.reset();
                        document.getElementById('selectAll').checked = false;
                        updateSelectedCount();
                    }, 1500);
                } else {
                    showError(data.message);
                }
            })
            .catch(error => {
                showError('An error occurred: ' + error.message);
            });
        }

        if (openConfirm) {
            openConfirm.addEventListener('click', openConfirmModal);
        }
        updatePathForm.addEventListener('submit', function(e) {
            e.preventDefault();
            openConfirmModal();
        });

        if (confirmUpdate) {
            confirmUpdate.addEventListener('click', submitUpdatePath);
        }
        if (closeConfirmModal) {
            closeConfirmModal.addEventListener('click', closeConfirmModalFn);
        }
        if (cancelConfirmModal) {
            cancelConfirmModal.addEventListener('click', closeConfirmModalFn);
        }
        if (confirmModal) {
            confirmModal.addEventListener('click', function(e) {
                if (e.target === confirmModal) {
                    closeConfirmModalFn();
                }
            });
        }
        
        function showSuccess(message) {
            const el = document.getElementById('successMessage');
            document.getElementById('successText').textContent = message;
            el.style.display = 'flex';
            setTimeout(() => {
                el.style.display = 'none';
            }, 3500);
        }
        
        function showError(message) {
            const el = document.getElementById('errorMessage');
            document.getElementById('errorText').textContent = message;
            el.style.display = 'flex';
        }
    </script>
</body>
</html>
"""

EDIT_PAGE = """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Edit Script</title>
    <style>
      :root {
        --ink: #0b1220;
        --muted: #5f6b7a;
        --panel: #ffffff;
        --border: #d7dee6;
        --brand: #0a6f86;
        --font-body: "Bahnschrift", "Candara", "Trebuchet MS", sans-serif;
        --font-display: "Rockwell", "Constantia", "Georgia", serif;
        --font-mono: "Cascadia Mono", "Consolas", "Courier New", monospace;
      }
      * { box-sizing: border-box; }
      body {
        margin: 0;
        font-family: var(--font-body);
        background: {{ background_style|safe }};
        color: var(--ink);
        min-height: 100vh;
        padding: 24px;
      }
      .shell {
        max-width: 1100px;
        margin: 0 auto;
        background: var(--panel);
        border-radius: 12px;
        border: 1px solid var(--border);
        box-shadow: 0 12px 32px rgba(0,0,0,0.12);
        padding: 18px 22px 22px;
      }
      .header {
       display: flex;
       justify-content: space-between;
       align-items: center;
       margin: -28px -28px 24px -28px;
       padding: 24px 28px;
       background: linear-gradient(135deg, #0a6f86 0%, #0a9fb5 100%);
       border-bottom: none;
       border-radius: 12px 12px 0 0;
       box-shadow: 0 8px 24px rgba(10, 111, 134, 0.15);
      }
      .title {
       font-size: 26px;
       font-weight: 900;
       color: #ffffff;
       letter-spacing: 0.5px;
       display: flex;
       align-items: center;
       gap: 10px;
       font-family: var(--font-display);
      }
      .title::before {
       content: '✎';
       font-size: 28px;
       opacity: 0.9;
      }
      .btn {
       border: none;
       border-radius: 8px;
       padding: 11px 22px;
       font-weight: 700;
       font-size: 12px;
       cursor: pointer;
       text-decoration: none;
       text-transform: uppercase;
       letter-spacing: 0.5px;
       transition: all 200ms cubic-bezier(0.34, 1.56, 0.64, 1);
       display: inline-flex;
       align-items: center;
       gap: 8px;
       box-shadow: 0 4px 12px rgba(10, 111, 134, 0.2);
      }
      .header .btn {
       background: rgba(255, 255, 255, 0.2);
       color: #ffffff;
       border: 2px solid rgba(255, 255, 255, 0.3);
      }
      .header .btn:hover {
       background: rgba(255, 255, 255, 0.3);
       border-color: rgba(255, 255, 255, 0.5);
       transform: translateY(-2px);
       box-shadow: 0 8px 20px rgba(10, 111, 134, 0.4);
      }
      .header .btn::before {
       content: '←';
       font-size: 14px;
      }
      .btn {
       background: linear-gradient(135deg, #0a9fb5, #0a6f86);
       color: #fff;
      }
      .btn:hover {
       transform: translateY(-2px);
       box-shadow: 0 6px 20px rgba(10, 111, 134, 0.3);
      }
      .btn:active {
       transform: translateY(0);
      }
      .actions .btn {
       background: linear-gradient(135deg, #28a745, #34c759);
       font-size: 13px;
       padding: 12px 24px;
      }
      .actions .btn::before {
       content: '💾';
       font-size: 14px;
      }
      .actions .btn:hover {
       box-shadow: 0 8px 24px rgba(40, 167, 69, 0.3);
      }
      textarea {
       width: 100%;
       min-height: 360px;
       height: 50vh;
       border-radius: 10px;
       border: 2px solid #e0e7f1;
       padding: 18px;
       font-family: var(--font-mono);
       font-size: 13px;
       line-height: 1.7;
       resize: vertical;
       background: linear-gradient(135deg, #f9fbfc 0%, #f5f8fb 100%);
       color: #0b1220;
       transition: all 200ms ease;
       box-shadow: inset 0 2px 8px rgba(10, 111, 134, 0.05);
      }
      textarea:focus {
       outline: none;
       border-color: #0a9fb5;
       background: #ffffff;
       box-shadow: 0 0 0 4px rgba(10, 159, 181, 0.12), inset 0 1px 3px rgba(10, 111, 134, 0.05);
      }
      .meta {
       color: #5a7a8a;
       font-size: 12px;
       margin-bottom: 18px;
       font-weight: 600;
       word-break: break-all;
       padding: 12px 16px;
       background: #f0f7fa;
       border-left: 4px solid #0a9fb5;
       border-radius: 6px;
       font-family: var(--font-mono);
       letter-spacing: 0.3px;
      }
      .actions {
       display: flex;
       justify-content: flex-end;
       gap: 12px;
       margin-top: 24px;
       padding-top: 20px;
       border-top: 2px solid #e8ecf1;
      }
      .message {
       background: linear-gradient(135deg, #e7f5ff, #f0faff);
       border: 2px solid #0a9fb5;
       border-left: 4px solid #0a6f86;
       color: #094067;
       padding: 16px 18px;
       border-radius: 10px;
       font-size: 13px;
       margin-bottom: 18px;
       font-weight: 600;
       box-shadow: 0 4px 12px rgba(10, 159, 181, 0.1);
      }
      .message::before {
       content: '✓ ';
       color: #0a6f86;
       font-weight: 800;
      }
      .warning-message {
       background: linear-gradient(135deg, #fff8e6, #fffbf0);
       border: 2px solid #ff9800;
       border-left: 4px solid #f57c00;
       color: #6d4c00;
       padding: 16px 18px;
       border-radius: 10px;
       font-size: 13px;
       margin-bottom: 18px;
       font-weight: 600;
       box-shadow: 0 4px 12px rgba(255, 152, 0, 0.1);
      }
      .warning-message::before {
       content: '⚠ ';
       color: #f57c00;
       font-weight: 800;
       margin-right: 4px;
      }
    </style>
  </head>
  <body>
    <div class="shell">
      <div class="header">
        <div class="title">Edit Script</div>
        <a class="btn" href="{{ back_url }}">Back</a>
      </div>
      <div class="meta">{{ script_path }}</div>
      {% if message %}
      <div class="message">{{ message }}</div>
      {% endif %}
      {% if not script_body %}
      <div class="warning-message">⚠️ No script content found. File may not exist or is empty.</div>
      {% endif %}
      <form method="post">
        <textarea name="script_body" spellcheck="false" required>{{ script_body }}</textarea>
        <div class="actions">
          <button class="btn" type="submit">Save</button>
        </div>
      </form>
    </div>
  </body>
</html>
"""

LOG_PAGE = """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Script Log</title>
    <style>
      :root {
        --ink: #0b1220;
        --muted: #5f6b7a;
        --panel: #ffffff;
        --border: #d7dee6;
        --brand: #0a6f86;
        --bg: #e9eef4;
        --font-body: "Bahnschrift", "Candara", "Trebuchet MS", sans-serif;
        --font-display: "Rockwell", "Constantia", "Georgia", serif;
        --font-mono: "Cascadia Mono", "Consolas", "Courier New", monospace;
      }
      * { box-sizing: border-box; }
      body {
        margin: 0;
        font-family: var(--font-body);
        background: {{ background_style|safe }};
        color: var(--ink);
        min-height: 100vh;
        padding: 26px;
      }
      .shell {
        max-width: 1200px;
        margin: 0 auto;
        background: var(--panel);
        border-radius: 16px;
        border: none;
        box-shadow: 0 20px 50px rgba(0,0,0,0.15);
        padding: 0;
        overflow: hidden;
        display: flex;
        flex-direction: column;
        height: 90vh;
      }
      .header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 24px 28px;
        background: linear-gradient(135deg, #0a6f86 0%, #0a9fb5 100%);
        border-bottom: none;
        box-shadow: 0 8px 24px rgba(10, 111, 134, 0.15);
      }
      .title {
        font-size: 26px;
        font-weight: 900;
        color: #ffffff;
        letter-spacing: 0.5px;
        display: flex;
        align-items: center;
        gap: 10px;
        font-family: var(--font-display);
      }
      .title::before {
        content: '📋';
        font-size: 28px;
      }
      .btn {
        border: 2px solid rgba(255, 255, 255, 0.3);
        border-radius: 8px;
        padding: 11px 22px;
        font-weight: 700;
        font-size: 12px;
        cursor: pointer;
        text-decoration: none;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        background: rgba(255, 255, 255, 0.2);
        color: #ffffff;
        transition: all 200ms cubic-bezier(0.34, 1.56, 0.64, 1);
        display: inline-flex;
        align-items: center;
        gap: 8px;
      }
      .btn::before {
        content: '←';
        font-size: 14px;
      }
      .btn:hover {
        background: rgba(255, 255, 255, 0.3);
        border-color: rgba(255, 255, 255, 0.5);
        transform: translateY(-2px);
        box-shadow: 0 8px 20px rgba(10, 111, 134, 0.4);
      }
      .log {
        background: #0d1520;
        color: #c8d6e5;
        border-radius: 0;
        padding: 20px;
        font-family: var(--font-mono);
        font-size: 13px;
        line-height: 1.8;
        max-height: calc(90vh - 140px);
        overflow-y: auto;
        overflow-x: auto;
        border: none;
        white-space: pre-wrap;
        word-wrap: break-word;
        flex: 1;
        box-shadow: inset 0 2px 8px rgba(0, 0, 0, 0.2);
      }
      .log::-webkit-scrollbar {
        width: 8px;
        height: 8px;
      }
      .log::-webkit-scrollbar-track {
        background: rgba(0, 0, 0, 0.1);
      }
      .log::-webkit-scrollbar-thumb {
        background: #0a9fb5;
        border-radius: 4px;
      }
      .log::-webkit-scrollbar-thumb:hover {
        background: #0a6f86;
      }
      .meta {
        color: #5a7a8a;
        font-size: 12px;
        padding: 0 28px;
        padding-top: 16px;
        font-weight: 600;
        word-break: break-all;
        padding-bottom: 14px;
        background: #f0f7fa;
        border-left: 4px solid #0a9fb5;
        margin: 0;
        font-family: var(--font-mono);
        letter-spacing: 0.3px;
      }
    </style>
  </head>
  <body>
    <div class="shell">
      <div class="header">
        <div class="title">{{ script_name }} Log</div>
        <a class="btn" href="{{ back_url }}">Back</a>
      </div>
      <div class="meta">{{ log_path }}</div>
      <div id="logBox" class="log">{{ log_text }}</div>
    </div>
    <script>
      const logBox = document.getElementById("logBox");
      const logUrl = "{{ log_url }}";
      function refreshLog() {
        fetch(logUrl + "?ts=" + Date.now())
          .then((res) => res.text())
          .then((text) => {
            logBox.textContent = text || "No log output yet.";
            logBox.scrollTop = logBox.scrollHeight;
          })
          .catch(() => {});
      }
      setInterval(refreshLog, 2000);
      setTimeout(() => {
        logBox.scrollTop = logBox.scrollHeight;
      }, 100);
    </script>
  </body>
</html>
"""

SETTINGS_PAGE = """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Navigation Settings</title>
    <style>
      :root {
        --ink: #0b1220;
        --muted: #5f6b7a;
        --panel: #ffffff;
        --border: #d7dee6;
        --brand: #0a6f86;
        --brand-2: #0e879f;
        --green: #2ea043;
        --red: #d83a4a;
        --bg: #e9eef4;
        --font-body: "Bahnschrift", "Candara", "Trebuchet MS", sans-serif;
        --font-display: "Rockwell", "Constantia", "Georgia", serif;
        --font-mono: "Cascadia Mono", "Consolas", "Courier New", monospace;
      }
      * { box-sizing: border-box; }
      body {
        margin: 0;
        font-family: var(--font-body);
        background: {{ background_style|safe }};
        color: var(--ink);
        min-height: 100vh;
        padding: 28px;
      }
      .shell {
        max-width: 1100px;
        margin: 0 auto;
      }
      .hero {
        background: linear-gradient(135deg, #0a6f86 0%, #10a1b5 50%, #20c5d6 100%);
        color: #fff;
        border-radius: 16px;
        padding: 28px 32px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        box-shadow: 0 12px 32px rgba(10,111,134,0.25);
        position: relative;
        overflow: hidden;
      }
      .hero::before {
        content: '';
        position: absolute;
        top: -50%;
        right: -50%;
        width: 300px;
        height: 300px;
        background: radial-gradient(circle, rgba(255,255,255,0.1) 0%, transparent 70%);
        border-radius: 50%;
      }
      .hero > div {
        position: relative;
        z-index: 2;
      }
      .hero h1 {
        margin: 0;
        font-size: 24px;
        letter-spacing: 0.3px;
        font-weight: 800;
        font-family: var(--font-display);
      }
      .hero p {
        margin: 8px 0 0;
        font-size: 14px;
        opacity: 0.95;
        font-weight: 500;
      }
      .btn {
        border: none;
        border-radius: 10px;
        padding: 10px 16px;
        font-weight: 700;
        cursor: pointer;
        text-decoration: none;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        gap: 6px;
        font-size: 13px;
        transition: all 150ms ease;
        box-shadow: 0 2px 8px rgba(15,23,42,0.1);
      }
      .btn:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(15,23,42,0.15);
      }
      .btn-primary { 
        background: #ffffff; 
        color: #0a6f86;
        border: 1px solid rgba(10,111,134,0.2);
      }
      .btn-primary:hover {
        background: #f5fafb;
        border-color: #0a6f86;
      }
      .btn-green { 
        background: linear-gradient(135deg, #28a745, #20c997);
        color: #fff;
      }
      .btn-green:hover {
        background: linear-gradient(135deg, #218838, #1aa179);
      }
      .btn-red { 
        background: linear-gradient(135deg, #dc3545, #e74c63);
        color: #fff;
      }
      .btn-red:hover {
        background: linear-gradient(135deg, #c82333, #d63350);
      }
      .grid {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 20px;
        margin-top: 24px;
      }
      @media (max-width: 980px) {
        .grid { grid-template-columns: 1fr; }
      }
      .card {
        background: var(--panel);
        border: 1px solid var(--border);
        border-radius: 14px;
        padding: 20px 22px;
        box-shadow: 0 4px 12px rgba(15,23,42,0.08);
        transition: all 200ms ease;
        position: relative;
        overflow: hidden;
      }
      .card::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        height: 4px;
        background: linear-gradient(90deg, #0a6f86, #10a1b5);
        opacity: 0;
        transition: opacity 200ms ease;
      }
      .card:hover {
        box-shadow: 0 8px 20px rgba(15,23,42,0.12);
        border-color: rgba(10,111,134,0.15);
      }
      .card:hover::before {
        opacity: 1;
      }
      .card h3 {
        margin: 0 0 16px 0;
        font-size: 14px;
        text-transform: uppercase;
        letter-spacing: 0.8px;
        color: #0a6f86;
        font-weight: 700;
      }
      label {
        display: block;
        font-size: 12px;
        margin-bottom: 8px;
        color: var(--muted);
        font-weight: 600;
      }
      input[type="text"],
      select {
        width: 100%;
        padding: 10px 12px;
        border-radius: 8px;
        border: 1px solid var(--border);
        margin-bottom: 14px;
        font-size: 13px;
        background: #fff;
        transition: all 150ms ease;
        font-family: inherit;
      }
      input[type="text"]:focus,
      select:focus {
        outline: none;
        border-color: #0a6f86;
        box-shadow: 0 0 0 3px rgba(10,111,134,0.08);
        background: #f5fafb;
      }
      input[type="file"] {
        border: 2px dashed var(--border);
        border-radius: 10px;
        padding: 16px 12px;
        width: 100%;
        margin-bottom: 14px;
        background: linear-gradient(135deg, #f9fbfd 0%, #f5f8fb 100%);
        cursor: pointer;
        transition: all 150ms ease;
      }
      input[type="file"]:hover {
        border-color: #0a6f86;
        background: #eef5f8;
      }
      .btn-row {
        display: flex;
        gap: 8px;
      }
      .checklist {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 10px 14px;
        margin-bottom: 16px;
        background: linear-gradient(135deg, #f8fafb 0%, #f5f8fb 100%);
        padding: 14px;
        border-radius: 10px;
        border: 1px solid rgba(215,222,230,0.5);
      }
      @media (max-width: 720px) {
        .checklist { grid-template-columns: 1fr; }
      }
      .checklist label {
        display: flex;
        align-items: center;
        gap: 10px;
        font-size: 13px;
        color: var(--ink);
        padding: 10px 12px;
        border-radius: 8px;
        background: #ffffff;
        border: 1px solid rgba(10,111,134,0.1);
        cursor: pointer;
        transition: all 150ms ease;
        font-weight: 500;
      }
      .checklist label:hover {
        background: #f0f9fc;
        border-color: rgba(10,111,134,0.2);
        box-shadow: 0 2px 8px rgba(10,111,134,0.06);
      }
      .checklist label input[type="checkbox"] {
        width: 16px;
        height: 16px;
        cursor: pointer;
        accent-color: #0a6f86;
        flex-shrink: 0;
      }
      .note {
        margin-top: 28px;
        padding: 12px 16px;
        background: linear-gradient(135deg, #f0f7fa 0%, #eaf3f7 100%);
        border-left: 3px solid #0a6f86;
        border-radius: 6px;
        color: var(--muted);
        font-size: 12px;
        font-weight: 500;
      }
    </style>
  </head>
  <body>
    <div class="shell">
      <div class="hero">
        <div>
          <h1>Manage Navigation</h1>
          <p>Create menus and assign scripts to each navigation group.</p>
        </div>
        <a class="btn btn-primary" href="{{ url_for('index') }}">Back to Dashboard</a>
      </div>

      <div class="grid">
        <div class="card">
          <h3>Add New Main Navigation</h3>
          <form method="post" action="{{ url_for('add_main_nav') }}">
            <label for="main_name">New Navigation Name</label>
            <input id="main_name" type="text" name="main_name" />
            <div class="btn-row">
              <button class="btn btn-green" type="submit">Add Navigation</button>
            </div>
          </form>
        </div>

        <div class="card">
          <h3>Add New Sub-Menu</h3>
          <form method="post" action="{{ url_for('add_sub_nav') }}">
            <label for="main_parent">Select Main Navigation</label>
            <select id="main_parent" name="main_name">
              {% for item in nav_main %}
              <option value="{{ item }}">{{ item }}</option>
              {% endfor %}
            </select>
            <label for="sub_name">New Sub-Menu Name</label>
            <input id="sub_name" type="text" name="sub_name" />
            <div class="btn-row">
              <button class="btn btn-green" type="submit">Add Sub-Menu</button>
            </div>
          </form>
        </div>

        <div class="card">
          <h3>Remove Navigation</h3>
          <form method="post" action="{{ url_for('remove_main_nav') }}">
            <label for="remove_main">Select Navigation</label>
            <select id="remove_main" name="main_name">
              {% for item in nav_main %}
              <option value="{{ item }}">{{ item }}</option>
              {% endfor %}
            </select>
            <div class="btn-row">
              <button class="btn btn-red" type="submit">Remove</button>
            </div>
          </form>
        </div>

        <div class="card">
          <h3>Remove Sub-Menu</h3>
          <form method="post" action="{{ url_for('remove_sub_nav') }}">
            <label for="remove_sub">Select Sub-Menu</label>
            <select id="remove_sub" name="sub_key">
              {% for item in sub_select %}
              <option value="{{ item.value }}">{{ item.label }}</option>
              {% endfor %}
            </select>
            <div class="btn-row">
              <button class="btn btn-red" type="submit">Remove</button>
            </div>
          </form>
        </div>

        <div class="card" style="grid-column: 1 / -1;">
          <h3>Manage Scripts</h3>
          <form method="post" action="{{ url_for('add_script_settings') }}" enctype="multipart/form-data">
            <label for="script_file">Add New Script</label>
            <input id="script_file" type="file" name="script_file" accept=".py,.json" multiple />
            <label for="script_name">Display Name (optional - applies to all)</label>
            <input id="script_name" type="text" name="script_name" />
            <div class="checklist">
              {% for item in nav_pairs %}
              <label>
                <input type="checkbox" name="nav_pair" value="{{ item.value }}" />
                {{ item.label }}
              </label>
              {% endfor %}
            </div>
            <div class="btn-row">
              <button class="btn btn-green" type="submit">Add Script</button>
            </div>
          </form>
        </div>

        <div class="card">
          <h3>Remove Script</h3>
          <form method="post" action="{{ url_for('remove_script') }}">
            <label for="remove_script">Select Script</label>
            <select id="remove_script" name="script_id">
              {% for item in script_select %}
              <option value="{{ item.value }}">{{ item.label }}</option>
              {% endfor %}
            </select>
            <div class="btn-row">
              <button class="btn btn-red" type="submit">Remove Script</button>
            </div>
          </form>
        </div>

        <div class="card" style="grid-column: 1 / -1; padding: 24px 28px;">
          <h3 style="margin: 0 0 24px 0; font-size: 16px; letter-spacing: 1px;">Add Scripts to Navigation</h3>
          <form method="post" action="{{ url_for('add_scripts_to_nav') }}" id="addScriptsToNavForm">
            
            <div style="margin-bottom: 22px;">
              <label for="target_nav" style="display: block; font-size: 12px; color: #0a6f86; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 10px;">Select Target Navigation</label>
              <select id="target_nav" name="target_nav" required style="width: 100%; padding: 12px 14px; border-radius: 8px; border: 2px solid var(--border); font-size: 14px; background: white; transition: all 150ms ease;">
                <option value="">Choose Navigation...</option>
                {% for item in nav_main %}
                <option value="{{ item }}">{{ item }}</option>
                {% endfor %}
              </select>
            </div>
            
            <div style="margin-bottom: 22px;">
              <label for="target_sub" style="display: block; font-size: 12px; color: #0a6f86; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 10px;">Select Sub-Navigation (Optional)</label>
              <select id="target_sub" name="target_sub" style="width: 100%; padding: 12px 14px; border-radius: 8px; border: 2px solid var(--border); font-size: 14px; background: white; transition: all 150ms ease;">
                <option value="">All Sub-Menus</option>
                {% for item in sub_select %}
                <option value="{{ item.value }}">{{ item.label }}</option>
                {% endfor %}
              </select>
            </div>
            
            <div style="margin-bottom: 18px;">
              <label style="display: block; font-size: 12px; color: #0a6f86; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 14px;">Select Scripts to Add</label>
              <input type="text" id="addScriptSearch" placeholder="Search scripts..." style="width: 100%; padding: 10px 12px; border-radius: 8px; border: 1px solid var(--border); margin-bottom: 10px; font-size: 13px;" />
              <div style="border: 1px solid var(--border); border-radius: 10px; padding: 12px; background: linear-gradient(135deg, #f9fbfd 0%, #f5f8fb 100%); max-height: 360px; overflow-y: auto;">
                <label style="display: flex; align-items: center; gap: 10px; padding: 12px; margin-bottom: 6px; background: white; border-radius: 8px; border: 1px solid rgba(10, 111, 134, 0.15); cursor: pointer; transition: all 150ms ease; font-weight: 600; color: var(--ink);">
                  <input type="checkbox" id="selectAllScripts" style="width: 18px; height: 18px; cursor: pointer; accent-color: #0a6f86;" />
                  Select All Scripts
                </label>
                {% for item in script_select %}
                <label class="script-item" data-script-name="{{ item.label|lower }}" style="display: flex; align-items: center; gap: 10px; padding: 10px 12px; margin-bottom: 4px; background: white; border-radius: 6px; border: 1px solid rgba(10, 111, 134, 0.1); cursor: pointer; transition: all 150ms ease; font-size: 13px; font-weight: 500;">
                  <input type="checkbox" name="selected_scripts[]" value="{{ item.value }}" class="script-checkbox" style="width: 18px; height: 18px; cursor: pointer; accent-color: #0a6f86;" />
                  {{ item.label }}
                </label>
                {% endfor %}
              </div>
            </div>
            
            <div style="display: flex; gap: 8px;">
              <button class="btn btn-green" type="submit" style="width: 100%; padding: 13px 20px; font-size: 13px; font-weight: 700;">Add to Navigation</button>
            </div>
          </form>
        </div>

        <div class="card">
          <h3>Change Script Path</h3>
          <p style="font-size: 12px; color: #5f6b7a; margin-bottom: 14px;">Update script path for multiple scripts with a single directory path</p>
          <div class="btn-row">
            <a class="btn btn-primary" style="background: linear-gradient(135deg, #0a9fb5, #0a6f86); color: #fff; border: none; text-decoration: none; display: inline-block;" href="{{ url_for('change_path_modal') }}" target="_blank">Open Path Manager</a>
          </div>
        </div>
        </div>
        <div class="note">✓ Changes are saved automatically.</div>
        </div>
        <script>
        // Select All Scripts functionality
        const selectAllCheckbox = document.getElementById('selectAllScripts');
        const scriptCheckboxes = document.querySelectorAll('.script-checkbox');
        
        if (selectAllCheckbox) {
        selectAllCheckbox.addEventListener('change', function() {
          scriptCheckboxes.forEach(checkbox => {
            checkbox.checked = this.checked;
          });
        });
        
        // Update "Select All" checkbox state when individual checkboxes change
        scriptCheckboxes.forEach(checkbox => {
          checkbox.addEventListener('change', function() {
            const allChecked = Array.from(scriptCheckboxes).every(cb => cb.checked);
            const anyChecked = Array.from(scriptCheckboxes).some(cb => cb.checked);
            selectAllCheckbox.checked = allChecked;
            selectAllCheckbox.indeterminate = anyChecked && !allChecked;
          });
        });
        }

        const addScriptSearch = document.getElementById('addScriptSearch');
        const scriptItems = document.querySelectorAll('.script-item');
        if (addScriptSearch) {
          addScriptSearch.addEventListener('input', function() {
            const query = addScriptSearch.value.toLowerCase().trim();
            scriptItems.forEach(item => {
              const name = item.getAttribute('data-script-name') || '';
              item.style.display = name.includes(query) ? '' : 'none';
            });
          });
        }
        </script>
        </body>
        </html>
        """


def _process_running(path: str) -> bool:
    entry = _processes.get(path)
    if not entry:
        return False
    proc = entry.get("proc")
    return proc is not None and proc.poll() is None


def _start_process(path: str) -> str:
    if not os.path.isfile(path):
        return "Script not found. Check the file path."
    if _process_running(path):
        return "Process already running."
    os.makedirs(_log_dir, exist_ok=True)
    log_path = _get_log_path({"path": path})
    log_file = open(log_path, "w", encoding="utf-8")
    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    workdir = os.path.dirname(path) or None
    proc = subprocess.Popen(
        [sys.executable, path],
        stdout=log_file,
        stderr=subprocess.STDOUT,
        env=env,
        cwd=workdir,
    )
    _processes[path] = {"proc": proc, "log_path": log_path, "log_file": log_file}
    return "Process started."


def _stop_process(path: str) -> str:
    entry = _processes.get(path)
    if entry is None:
        return "Process is not running."
    proc = entry.get("proc")
    if proc is None or proc.poll() is not None:
        _kill_process_tree(proc)
        entry["proc"] = None
        return "Process is not running."
    proc.terminate()
    try:
        proc.wait(timeout=5)
        msg = "Process terminated."
    except subprocess.TimeoutExpired:
        _kill_process_tree(proc)
        msg = "Process killed after timeout."
    finally:
        _kill_process_tree(proc)
    log_file = entry.get("log_file")
    if log_file:
        log_file.close()
    entry["proc"] = None
    return msg


def _kill_process_tree(proc):
    if proc is None:
        return
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            return
        except OSError:
            pass
    try:
        proc.kill()
    except OSError:
        pass


def _add_script(path: str, display_name: str = "", categories=None) -> str:
    candidate = (path or "").strip()
    if not candidate:
        return "Path is required."
    if not candidate.lower().endswith(".py"):
        return "Only .py files are supported."
    if not os.path.isfile(candidate):
        return "File not found."
    for entry in _scripts:
        if entry.get("path") == candidate:
            return "Script already added."
    name = (display_name or "").strip()
    if not name:
        name = os.path.splitext(os.path.basename(candidate))[0]
    entry = {
        "path": candidate,
        "name": name,
        "categories": list(categories or []),
        "desired_state": "stopped",
    }
    _scripts.append(entry)
    _save_scripts()
    return "Script added."


def _resolve_script_path(script_path):
    """Resolve script path - handles both absolute and relative paths."""
    if not script_path:
        return script_path
    # If absolute path, return as is
    if os.path.isabs(script_path):
        return script_path
    # If relative path, resolve from Dashboard directory
    dashboard_dir = os.path.dirname(__file__)
    resolved_path = os.path.join(dashboard_dir, script_path)
    return resolved_path

def _load_scripts():
    global _scripts
    if os.path.isfile(_data_path):
        try:
            with open(_data_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, list):
                converted = []
                for item in data:
                    if isinstance(item, str):
                        resolved = _resolve_script_path(item)
                        converted.append(
                            {
                                "path": resolved,
                                "name": os.path.splitext(os.path.basename(item))[0],
                                "categories": [],
                                "desired_state": "stopped",
                            }
                        )
                    elif isinstance(item, dict) and "path" in item:
                        resolved = _resolve_script_path(item.get("path", ""))
                        converted.append(
                            {
                                "path": resolved,
                                "name": item.get("name", ""),
                                "categories": list(item.get("categories", [])),
                                "desired_state": item.get("desired_state", "stopped"),
                            }
                        )
                _scripts = [entry for entry in converted if entry.get("path")]
        except (OSError, ValueError):
            _scripts = []


def _save_scripts():
    print(f"[_SAVE_SCRIPTS] Saving {len(_scripts)} scripts to {_data_path}")
    os.makedirs(os.path.dirname(_data_path), exist_ok=True)
    with open(_data_path, "w", encoding="utf-8") as handle:
        json.dump(_scripts, handle, indent=2)
    print(f"[_SAVE_SCRIPTS] Saved successfully")


def _load_nav():
    global _nav
    if os.path.isfile(_nav_path):
        try:
            with open(_nav_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, dict):
                _nav = {
                    "main": list(data.get("main", [])),
                    "subs": dict(data.get("subs", {})),
                }
        except (OSError, ValueError):
            _nav = {"main": [], "subs": {}}


def _save_nav():
    print(f"[_SAVE_NAV] Saving nav to {_nav_path}")
    print(f"[_SAVE_NAV] Content: {_nav}")
    os.makedirs(os.path.dirname(_nav_path), exist_ok=True)
    with open(_nav_path, "w", encoding="utf-8") as handle:
        json.dump(_nav, handle, indent=2)
    print(f"[_SAVE_NAV] Saved successfully")


def _hash_password(password: str, salt: str) -> str:
    payload = f"{salt}{password}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _load_users():
    global _users
    if os.path.isfile(_users_path):
        try:
            with open(_users_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, list):
                _users = data
        except (OSError, ValueError):
            _users = []


def _save_users():
    os.makedirs(os.path.dirname(_users_path), exist_ok=True)
    with open(_users_path, "w", encoding="utf-8") as handle:
        json.dump(_users, handle, indent=2)


def _load_background():
    global _background
    if os.path.isfile(_background_path):
        try:
            with open(_background_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, dict):
                _background = {
                    "mode": data.get("mode", "default"),
                    "image": data.get("image", ""),
                }
        except (OSError, ValueError):
            _background = {"mode": "default", "image": ""}


def _save_background():
    os.makedirs(os.path.dirname(_background_path), exist_ok=True)
    with open(_background_path, "w", encoding="utf-8") as handle:
        json.dump(_background, handle, indent=2)


def _save_background_image(file_storage) -> str:
    if file_storage is None or file_storage.filename == "":
        return ""
    filename = secure_filename(file_storage.filename)
    ext = os.path.splitext(filename)[1].lower()
    if ext not in [".jpg", ".jpeg", ".png", ".webp", ".gif"]:
        return ""
    bg_dir = os.path.join(_upload_dir, "backgrounds")
    os.makedirs(bg_dir, exist_ok=True)
    dest = os.path.join(bg_dir, filename)
    file_storage.save(dest)
    return filename


def _get_background_style():
    base = "#e9eef4"
    if _background.get("mode") == "custom" and _background.get("image"):
        file_url = url_for("background_file", filename=_background["image"])
        return f"{base} url('{file_url}') center/cover fixed no-repeat"
    return base


def _get_background_label():
    if _background.get("mode") == "custom":
        return "Custom"
    return "Default"


def _load_history():
    global _history
    if os.path.isfile(_history_path):
        try:
            with open(_history_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, list):
                _history = data
        except (OSError, ValueError):
            _history = []


def _save_history():
    os.makedirs(os.path.dirname(_history_path), exist_ok=True)
    with open(_history_path, "w", encoding="utf-8") as handle:
        json.dump(_history, handle, indent=2)


def _append_history(username: str, action: str, script_name: str, ip_address: str = ""):
     entry = {
         "ts": _get_current_time_gmt7(),
         "user": username,
         "action": action,
         "script": script_name,
         "ip": ip_address or "",
     }
     _history.append(entry)
     _save_history()


def _load_access_log():
    global _access_log
    if os.path.isfile(_access_log_path):
        try:
            with open(_access_log_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, list):
                _access_log = data
        except (OSError, ValueError):
            _access_log = []


def _save_access_log():
    os.makedirs(os.path.dirname(_access_log_path), exist_ok=True)
    with open(_access_log_path, "w", encoding="utf-8") as handle:
        json.dump(_access_log, handle, indent=2)


def _append_access_log(username: str, status: str, ip_address: str = ""):
     entry = {
         "ts": _get_current_time_gmt7(),
         "user": (username or "").strip().upper() or "UNKNOWN",
         "status": status,
         "ip": ip_address or "",
     }
     _access_log.append(entry)
     _save_access_log()


def _load_ip_labels():
    global _ip_labels
    if os.path.isfile(_ip_labels_path):
        try:
            with open(_ip_labels_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, dict):
                _ip_labels = data
        except (OSError, ValueError):
            _ip_labels = {}


def _save_ip_labels():
    os.makedirs(os.path.dirname(_ip_labels_path), exist_ok=True)
    with open(_ip_labels_path, "w", encoding="utf-8") as handle:
        json.dump(_ip_labels, handle, indent=2)


def _set_ip_label(ip_address: str, label: str) -> str:
    ip = (ip_address or "").strip()
    name = (label or "").strip()
    if not ip or not name:
        return "IP address and label are required."
    _ip_labels[ip] = name
    _save_ip_labels()
    return "IP label saved."


def _load_ip_protection():
    global _ip_protection
    if os.path.isfile(_ip_protection_path):
        try:
            with open(_ip_protection_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, dict):
                _ip_protection = data
        except (OSError, ValueError):
            _ip_protection = {"enabled": False}
    else:
        _ip_protection = {"enabled": False}


def _save_ip_protection():
    os.makedirs(os.path.dirname(_ip_protection_path), exist_ok=True)
    with open(_ip_protection_path, "w", encoding="utf-8") as handle:
        json.dump(_ip_protection, handle, indent=2)


def _load_ip_protection_access():
    global _ip_protection_access
    if os.path.isfile(_ip_protection_access_path):
        try:
            with open(_ip_protection_access_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, list):
                _ip_protection_access = [u.upper() for u in data]
            else:
                _ip_protection_access = []
        except (OSError, ValueError):
            _ip_protection_access = []
    else:
        _ip_protection_access = []


def _save_ip_protection_access():
    os.makedirs(os.path.dirname(_ip_protection_access_path), exist_ok=True)
    with open(_ip_protection_access_path, "w", encoding="utf-8") as handle:
        json.dump(_ip_protection_access, handle, indent=2)


def _get_cpu_usage() -> float:
     """Get CPU usage percentage"""
     try:
         import psutil
         return psutil.cpu_percent(interval=0.1)
     except (ImportError, Exception):
         return 0.0


def _get_client_ip() -> str:
     forwarded = request.headers.get("X-Forwarded-For", "")
     if forwarded:
         ip = forwarded.split(",")[0].strip()
         if ip:
             return ip
     real_ip = request.headers.get("X-Real-IP", "").strip()
     if real_ip:
         return real_ip
     return request.remote_addr or ""


def _get_current_time_gmt7() -> str:
     """Get current time in GMT+7 format"""
     from datetime import timezone, timedelta
     gmt7 = timezone(timedelta(hours=7))
     return datetime.now(gmt7).isoformat(timespec="seconds").replace("+07:00", "Z")


def _format_timestamp(value: str) -> str:
     try:
         return value.replace("T", " ").replace("Z", "")
     except AttributeError:
         return str(value)


def _ensure_default_admin():
    if _get_user("ADMIN"):
        return
    if _has_admin():
        return
    _create_user("ADMIN", "Admin@8888", "ADMIN", list(_nav["main"]))


def _get_user(username: str):
    label = (username or "").strip().upper()
    for entry in _users:
        if entry.get("username") == label:
            return entry
    return None


def _has_admin():
    return any(entry.get("role") == "ADMIN" for entry in _users)


def _create_user(username: str, password: str, role: str, nav_access=None):
    label = (username or "").strip().upper()
    if not label:
        return "User name is required."
    if _get_user(label):
        return "User already exists."
    salt = os.urandom(8).hex()
    entry = {
        "username": label,
        "salt": salt,
        "password_hash": _hash_password(password or "", salt),
        "role": role,
        "nav_access": list(nav_access or []),
    }
    _users.append(entry)
    _save_users()
    return "Account created."


def _verify_user(username: str, password: str) -> bool:
    entry = _get_user(username)
    if not entry:
        return False
    salt = entry.get("salt", "")
    expected = entry.get("password_hash", "")
    return _hash_password(password or "", salt) == expected


def _get_current_user():
    username = session.get("user")
    return _get_user(username) if username else None


def _get_current_username():
    user = _get_current_user()
    return user.get("username", "UNKNOWN") if user else "UNKNOWN"


def _require_login(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not _get_current_user():
            return redirect(url_for("login"))
        return func(*args, **kwargs)
    return wrapper


def _require_admin(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        user = _get_current_user()
        if not user or user.get("role") != "ADMIN":
            return redirect(url_for("login"))
        return func(*args, **kwargs)
    return wrapper


def _allowed_nav(user):
    if not user or user.get("role") == "ADMIN":
        return list(_nav["main"])
    allowed = set(user.get("nav_access", []))
    return [item for item in _nav["main"] if item in allowed]


def _ensure_nav_defaults():
    if not _nav["main"]:
        _nav["main"] = [
            "EXPAY",
            "JUSTPAY",
            "TELEGRAM",
            "UPDATE BALANCE",
            "TRANSFERS",
            "SMART PAY",
            "BRAND DASHBOARD",
            "PG TRANSFER",
        ]
        _nav["subs"] = {
            "EXPAY": ["ACM BOT", "PG CHECK"],
        }
        _save_nav()


def _save_uploaded_file(file_storage) -> str:
    if file_storage is None or file_storage.filename == "":
        return ""
    filename = secure_filename(file_storage.filename)
    lower_name = filename.lower()
    if not (lower_name.endswith(".py") or lower_name.endswith(".json")):
        return ""
    os.makedirs(_upload_dir, exist_ok=True)
    dest = os.path.join(_upload_dir, filename)
    file_storage.save(dest)
    return dest


def _build_cards(scripts):
    cards = []
    for idx, path in scripts:
        script_path = path.get("path", "")
        running = _process_running(script_path)
        entry = _processes.get(script_path, {})
        proc = entry.get("proc")
        pid = proc.pid if proc and running else ""
        display_name = path.get("name") or os.path.splitext(os.path.basename(script_path))[0] or "Python"
        cards.append(
            {
                "id": idx,
                "name": display_name.upper(),
                "path": script_path,
                "status_text": "Running" if running else "Stopped",
                "status_color": "#36d399" if running else "#ff6b6b",
                "running": running,
                "pid": pid,
            }
        )
    return cards


def _filter_scripts(active_main: str, active_sub: str):
    filtered = []
    for idx, entry in enumerate(_scripts):
        categories = entry.get("categories", [])
        if not categories:
            filtered.append((idx, entry))
            continue
        if active_sub:
            if f"{active_main}||{active_sub}" in categories:
                filtered.append((idx, entry))
            continue
        for item in categories:
            if item.startswith(f"{active_main}||"):
                filtered.append((idx, entry))
                break
    return filtered


def _ensure_defaults():
    if not _scripts:
        _scripts.append(
            {
                "path": r"C:\Users\User\Downloads\TOPBOT\jwaypayment.py",
                "name": "JWAYPAYMENT",
                "categories": [],
                "desired_state": "stopped",
            }
        )
        _save_scripts()


def _get_log_path(entry) -> str:
    script_path = entry.get("path", "")
    if script_path:
        name = os.path.splitext(os.path.basename(script_path))[0] or "script"
        return os.path.join(_log_dir, f"{name}.log")
    name = (entry.get("name") or "script").strip() or "script"
    return os.path.join(_log_dir, f"{name}.log")


def _read_log(path: str, max_lines: int = 400) -> str:
    if not os.path.isfile(path):
        return "No log yet."
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        lines = handle.readlines()
    if len(lines) > max_lines:
        lines = lines[-max_lines:]
    return "".join(lines).strip() or "No log output yet."


def _normalize_nav_name(value: str) -> str:
    return (value or "").strip()


def _add_main_nav(name: str) -> str:
    label = _normalize_nav_name(name).upper()
    if not label:
        return "Main navigation name is required."
    if label in _nav["main"]:
        return "Main navigation already exists."
    _nav["main"].append(label)
    _save_nav()
    return "Main navigation added."


def _add_sub_nav(main_name: str, sub_name: str) -> str:
    main_label = _normalize_nav_name(main_name).upper()
    sub_label = _normalize_nav_name(sub_name).upper()
    if not main_label or not sub_label:
        return "Main and sub-menu names are required."
    if main_label not in _nav["main"]:
        return "Main navigation not found."
    subs = _nav["subs"].setdefault(main_label, [])
    if sub_label in subs:
        return "Sub-menu already exists."
    subs.append(sub_label)
    _save_nav()
    return "Sub-menu added."


def _remove_main_nav(main_name: str) -> str:
    main_label = _normalize_nav_name(main_name).upper()
    if main_label not in _nav["main"]:
        return "Main navigation not found."
    _nav["main"] = [item for item in _nav["main"] if item != main_label]
    _nav["subs"].pop(main_label, None)
    _save_nav()
    return "Main navigation removed."


def _remove_sub_nav(sub_key: str) -> str:
    if "||" not in (sub_key or ""):
        return "Invalid sub-menu selection."
    main_label, sub_label = sub_key.split("||", 1)
    subs = _nav["subs"].get(main_label, [])
    if sub_label not in subs:
        return "Sub-menu not found."
    _nav["subs"][main_label] = [item for item in subs if item != sub_label]
    _save_nav()
    return "Sub-menu removed."


def _rename_main_nav(old_name: str, new_name: str) -> str:
    """Rename a main navigation item and update all scripts' categories."""
    global _nav, _scripts
    old_label = _normalize_nav_name(old_name).upper()
    new_label = _normalize_nav_name(new_name).upper()
    
    if not old_label or not new_label:
        return "Navigation names are required."
    
    if old_label == new_label:
        return "New name must be different from current name."
    
    if old_label not in _nav["main"]:
        return "Main navigation not found."
    
    if new_label in _nav["main"]:
        return "Navigation with this name already exists."
    
    # Update navigation structure
    idx = _nav["main"].index(old_label)
    _nav["main"][idx] = new_label
    
    # Move sub-navigation items
    if old_label in _nav["subs"]:
        _nav["subs"][new_label] = _nav["subs"].pop(old_label)
    
    # Update all scripts' categories
    for script in _scripts:
        script_categories = script.get("categories", [])
        updated_categories = []
        for category in script_categories:
            if "||" in category:
                main_part, sub_part = category.split("||", 1)
                if main_part == old_label:
                    updated_categories.append(f"{new_label}||{sub_part}")
                else:
                    updated_categories.append(category)
            else:
                updated_categories.append(category)
        script["categories"] = updated_categories
    
    # Save changes
    _save_nav()
    _save_scripts()
    
    return f"Navigation renamed from {old_label} to {new_label}. All scripts updated."


def _rename_sub_nav(main_name: str, old_sub_name: str, new_sub_name: str) -> str:
    """Rename a sub-navigation item and update all scripts' categories."""
    global _nav, _scripts
    main_label = _normalize_nav_name(main_name).upper()
    old_sub_label = _normalize_nav_name(old_sub_name).upper()
    new_sub_label = _normalize_nav_name(new_sub_name).upper()
    
    if not main_label or not old_sub_label or not new_sub_label:
        return "Navigation names are required."
    
    if old_sub_label == new_sub_label:
        return "New name must be different from current name."
    
    if main_label not in _nav["main"]:
        return "Main navigation not found."
    
    subs = _nav["subs"].get(main_label, [])
    if old_sub_label not in subs:
        return "Sub-navigation not found."
    
    if new_sub_label in subs:
        return "Sub-navigation with this name already exists."
    
    # Update sub-navigation list
    idx = subs.index(old_sub_label)
    subs[idx] = new_sub_label
    
    # Update all scripts' categories
    for script in _scripts:
        script_categories = script.get("categories", [])
        updated_categories = []
        for category in script_categories:
            if "||" in category:
                main_part, sub_part = category.split("||", 1)
                if main_part == main_label and sub_part == old_sub_label:
                    updated_categories.append(f"{main_label}||{new_sub_label}")
                else:
                    updated_categories.append(category)
            else:
                updated_categories.append(category)
        script["categories"] = updated_categories
    
    # Save changes
    _save_nav()
    _save_scripts()
    
    return f"Sub-navigation renamed from {old_sub_label} to {new_sub_label}. All scripts updated."


def _get_active_main(selected: str, nav_main) -> str:
    if selected in nav_main:
        return selected
    return nav_main[0] if nav_main else "EXPAY"


def _build_sub_select():
    options = []
    for main_label in _nav["main"]:
        for sub_label in _nav["subs"].get(main_label, []):
            options.append(
                {
                    "label": f"{main_label} :: {sub_label}",
                    "value": f"{main_label}||{sub_label}",
                }
            )
    return options


def _build_nav_pairs():
    pairs = []
    for main_label in _nav["main"]:
        subs = _nav["subs"].get(main_label, [])
        if subs:
            for sub_label in subs:
                pairs.append(
                    {
                        "label": f"{main_label} > {sub_label}",
                        "value": f"{main_label}||{sub_label}",
                    }
                )
        else:
            pairs.append(
                {
                    "label": f"{main_label} > {main_label}",
                    "value": f"{main_label}||{main_label}",
                }
            )
    return pairs


def _build_script_select():
    options = []
    for idx, entry in enumerate(_scripts):
        label = entry.get("name") or os.path.splitext(os.path.basename(entry.get("path", "")))[0]
        options.append({"label": label, "value": str(idx)})
    return options


@app.route("/")
@_require_login
def index():
     # Check IP protection
     if _ip_protection.get("enabled", False):
         client_ip = _get_client_ip()
         if client_ip not in _ip_labels:
             _append_access_log(_get_current_username(), "BLOCKED_IP", client_ip)
             return render_template_string(
                 RESTRICTED_PAGE,
                 message="Your IP is not whitelisted. Access to dashboard is restricted.",
                 background_style=_get_background_style(),
             )
     
     with _lock:
         _ensure_defaults()
         _ensure_nav_defaults()
         user = _get_current_user()
         nav_main = _allowed_nav(user)
         if not nav_main:
             active_main = "NO ACCESS"
             nav_subs = []
             active_sub = ""
             filtered = []
             cards = []
         else:
             active_main = _get_active_main(request.args.get("main", ""), nav_main)
             nav_subs = list(_nav["subs"].get(active_main, []))
             active_sub = request.args.get("sub", "")
             if active_sub not in nav_subs:
                 active_sub = ""
             for entry in _scripts:
                 if entry.get("desired_state") == "stopped" and _process_running(entry.get("path", "")):
                     _stop_process(entry.get("path", ""))
             filtered = _filter_scripts(active_main, active_sub)
             cards = _build_cards(filtered)
     running_count = sum(1 for card in cards if card["running"])
     stopped_count = len(cards) - running_count
     cpu_usage = _get_cpu_usage()
     return render_template_string(
         PAGE,
         cards=cards,
         running_count=running_count,
         stopped_count=stopped_count,
         cpu_usage=cpu_usage,
         nav_main=nav_main,
         nav_subs=nav_subs,
         active_main=active_main,
         active_sub=active_sub,
         current_user=user,
         current_username=_get_current_username(),
         last_message=_last_message,
         background_style=_get_background_style(),
         background_label=_get_background_label(),
         background_mode=_background.get("mode", "default"),
     )


@app.route("/start/<int:script_id>", methods=["POST"])
@_require_login
def start(script_id: int):
    with _lock:
        global _last_message
        if 0 <= script_id < len(_scripts):
            _scripts[script_id]["desired_state"] = "running"
            _save_scripts()
            _last_message = _start_process(_scripts[script_id].get("path", ""))
            script_name = _scripts[script_id].get("name") or os.path.splitext(os.path.basename(_scripts[script_id].get("path", "")))[0]
            _append_history(_get_current_username(), "START", script_name, _get_client_ip())
        else:
            _last_message = "Invalid script id."
    return redirect(
        url_for(
            "index",
            main=request.args.get("main", ""),
            sub=request.args.get("sub", ""),
        )
    )


@app.route("/stop/<int:script_id>", methods=["POST"])
@_require_login
def stop(script_id: int):
    with _lock:
        global _last_message
        if 0 <= script_id < len(_scripts):
            _scripts[script_id]["desired_state"] = "stopped"
            _save_scripts()
            _last_message = _stop_process(_scripts[script_id].get("path", ""))
            script_name = _scripts[script_id].get("name") or os.path.splitext(os.path.basename(_scripts[script_id].get("path", "")))[0]
            _append_history(_get_current_username(), "STOP", script_name, _get_client_ip())
        else:
            _last_message = "Invalid script id."
    return redirect(
        url_for(
            "index",
            main=request.args.get("main", ""),
            sub=request.args.get("sub", ""),
        )
    )


@app.route("/add-script", methods=["POST"])
@_require_login
def add_script():
    with _lock:
        global _last_message
        uploaded_path = _save_uploaded_file(request.files.get("script_file"))
        display_name = request.form.get("script_name", "")
        categories = request.form.getlist("nav_pair")
        if uploaded_path:
            _last_message = _add_script(uploaded_path, display_name, categories)
        else:
            _last_message = _add_script(request.form.get("script_path", ""), display_name, categories)
    return redirect(
        url_for(
            "index",
            main=request.args.get("main", ""),
            sub=request.args.get("sub", ""),
        )
    )


@app.route("/scripts/add", methods=["POST"])
@_require_admin
def add_script_settings():
    with _lock:
        global _last_message
        script_files = request.files.getlist("script_file")
        display_name = request.form.get("script_name", "")
        categories = request.form.getlist("nav_pair")
        
        if not script_files or all(f.filename == "" for f in script_files):
            _last_message = "Please choose at least one .py or .json file."
            return redirect(url_for("settings"))
        
        messages = []
        for script_file in script_files:
            if script_file.filename == "":
                continue
            uploaded_path = _save_uploaded_file(script_file)
            if uploaded_path:
                result = _add_script(uploaded_path, display_name, categories)
                messages.append(result)
            else:
                messages.append(f"Failed to upload {script_file.filename}")
        
        if messages:
            _last_message = " | ".join(messages)
        else:
            _last_message = "No valid files were uploaded."
    return redirect(url_for("settings"))


@app.route("/scripts/remove", methods=["POST"])
@_require_admin
def remove_script():
     with _lock:
         global _last_message
         try:
             idx = int(request.form.get("script_id", "-1"))
         except ValueError:
             idx = -1
         if 0 <= idx < len(_scripts):
             removed = _scripts.pop(idx)
             _save_scripts()
             _last_message = f"Removed {removed.get('name', 'script')}."
         else:
             _last_message = "Invalid script selection."
     return redirect(url_for("settings"))


@app.route("/scripts/add-to-nav", methods=["POST"])
@_require_admin
def add_scripts_to_nav():
     with _lock:
         global _last_message
         target_nav = request.form.get("target_nav", "").strip().upper()
         target_sub = request.form.get("target_sub", "").strip()
         selected_script_ids = request.form.getlist("selected_scripts[]")
         
         if not target_nav:
             _last_message = "Please select a target navigation."
             return redirect(url_for("settings"))
         
         if not selected_script_ids:
             _last_message = "Please select at least one script."
             return redirect(url_for("settings"))
         
         # Validate target navigation exists
         if target_nav not in _nav["main"]:
             _last_message = "Target navigation not found."
             return redirect(url_for("settings"))
         
         # Handle target sub-navigation
         if target_sub and "||" in target_sub:
             main_label, sub_label = target_sub.split("||", 1)
             if main_label != target_nav:
                 _last_message = "Sub-navigation does not match target navigation."
                 return redirect(url_for("settings"))
             category_key = target_sub
         else:
             # Add to main navigation (with all sub-menus)
             category_key = None
         
         updated_scripts = []
         for script_id_str in selected_script_ids:
             try:
                 idx = int(script_id_str)
                 if 0 <= idx < len(_scripts):
                     script_entry = _scripts[idx]
                     current_categories = script_entry.get("categories", [])
                     
                     if category_key:
                         # Add to specific sub-navigation
                         if category_key not in current_categories:
                             current_categories.append(category_key)
                             updated_scripts.append(script_entry.get('name') or os.path.splitext(os.path.basename(script_entry.get("path", "")))[0])
                     else:
                         # Add to main navigation (all relevant sub-menus)
                         subs = _nav["subs"].get(target_nav, [])
                         for sub_label in subs:
                             sub_key = f"{target_nav}||{sub_label}"
                             if sub_key not in current_categories:
                                 current_categories.append(sub_key)
                         # Also add the main navigation key pattern
                         if not any(cat.startswith(f"{target_nav}||") for cat in current_categories):
                             current_categories.append(f"{target_nav}||{target_nav}")
                         updated_scripts.append(script_entry.get('name') or os.path.splitext(os.path.basename(script_entry.get("path", "")))[0])
                     
                     _scripts[idx]["categories"] = current_categories
             except ValueError:
                 pass
         
         if updated_scripts:
             _save_scripts()
             nav_display = target_nav
             if target_sub:
                 nav_display = target_sub.replace("||", " > ")
             _last_message = f"Added {len(updated_scripts)} script(s) to {nav_display}: {', '.join(updated_scripts)}"
         else:
             _last_message = "No scripts were updated."
     
     return redirect(url_for("settings"))


@app.route("/logs/<int:script_id>")
@_require_login
def view_log(script_id: int):
    with _lock:
        if not (0 <= script_id < len(_scripts)):
            return redirect(url_for("index"))
        entry = _scripts[script_id]
        log_path = _get_log_path(entry)
        script_name = entry.get("name") or os.path.splitext(os.path.basename(entry.get("path", "")))[0]
    log_text = _read_log(log_path)
    log_url = url_for("log_text", script_id=script_id)
    back_url = url_for(
        "index",
        main=request.args.get("main", ""),
        sub=request.args.get("sub", ""),
    )
    return render_template_string(
        LOG_PAGE,
        script_name=script_name,
        log_path=log_path,
        log_text=log_text,
        log_url=log_url,
        back_url=back_url,
        background_style=_get_background_style(),
    )


@app.route("/logs/<int:script_id>/text")
@_require_login
def log_text(script_id: int):
    if not (0 <= script_id < len(_scripts)):
        return ""
    entry = _scripts[script_id]
    log_path = _get_log_path(entry)
    response = make_response(_read_log(log_path))
    response.headers["Cache-Control"] = "no-store"
    return response


@app.route("/start-all", methods=["POST"])
@_require_login
def start_all():
    with _lock:
        global _last_message
        active_main = request.args.get("main", "")
        active_sub = request.args.get("sub", "")
        filtered = _filter_scripts(active_main, active_sub)
        for idx, entry in filtered:
            _scripts[idx]["desired_state"] = "running"
            _save_scripts()
            _start_process(entry.get("path", ""))
            script_name = entry.get("name") or os.path.splitext(os.path.basename(entry.get("path", "")))[0]
            _append_history(_get_current_username(), "START", script_name, _get_client_ip())
        _last_message = "Started all scripts."
    return redirect(
        url_for(
            "index",
            main=request.args.get("main", ""),
            sub=request.args.get("sub", ""),
        )
    )


@app.route("/stop-all", methods=["POST"])
@_require_login
def stop_all():
    with _lock:
        global _last_message
        active_main = request.args.get("main", "")
        active_sub = request.args.get("sub", "")
        filtered = _filter_scripts(active_main, active_sub)
        for idx, entry in filtered:
            _scripts[idx]["desired_state"] = "stopped"
            _save_scripts()
            _stop_process(entry.get("path", ""))
            script_name = entry.get("name") or os.path.splitext(os.path.basename(entry.get("path", "")))[0]
            _append_history(_get_current_username(), "STOP", script_name, _get_client_ip())
        _last_message = "Stopped all scripts."
    return redirect(
        url_for(
            "index",
            main=request.args.get("main", ""),
            sub=request.args.get("sub", ""),
        )
    )


@app.route("/api/cpu-usage")
@_require_login
def get_cpu_usage_api():
    """Get current CPU usage percentage"""
    try:
        cpu_usage = _get_cpu_usage()
        return jsonify({"success": True, "cpu_usage": round(cpu_usage, 1)})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/emergency-control", methods=["POST"])
@_require_login
def emergency_control():
    """Emergency bulk start/stop for all scripts across all navigations - OPTIMIZED for speed"""
    # Verify credentials FIRST (outside lock for speed)
    admin_user = request.form.get("admin_user", "")
    admin_password = request.form.get("admin_password", "")
    
    if not _verify_user(admin_user, admin_password):
        return jsonify({"success": False, "message": "Invalid admin credentials"}), 401
    
    user = _get_user(admin_user)
    if not user or user.get("role") != "ADMIN":
        return jsonify({"success": False, "message": "User is not an admin"}), 403
    
    action = request.form.get("action", "").lower()
    if action not in ["start", "stop"]:
        return jsonify({"success": False, "message": "Invalid action"}), 400
    
    # Now acquire lock for actual work
    with _lock:
        global _last_message
        try:
            # Batch update desired states first
            action_name = "EMERGENCY_START" if action == "start" else "EMERGENCY_STOP"
            desired_state = "running" if action == "start" else "stopped"
            
            for idx in range(len(_scripts)):
                _scripts[idx]["desired_state"] = desired_state
            
            # Save all state changes at once (single disk write)
            _save_scripts()
            
            # Start/stop all processes (non-blocking, async)
            for idx, entry in enumerate(_scripts):
                script_path = entry.get("path", "")
                if script_path:
                    if action == "start":
                        _start_process(script_path)
                    else:
                        _stop_process(script_path)
            
            # Log history entries (bulk)
            for entry in _scripts:
                script_name = entry.get("name") or os.path.splitext(os.path.basename(entry.get("path", "")))[0]
                _append_history(admin_user, action_name, script_name, _get_client_ip())
            
            _last_message = f"Emergency {action.upper()} ALL executed by {admin_user}"
            return jsonify({
                "success": True, 
                "message": f"Emergency {action.upper()} completed for all scripts"
            }), 200
        
        except Exception as e:
            return jsonify({"success": False, "message": str(e)}), 500


@app.route("/settings")
@_require_admin
def settings():
    with _lock:
        _ensure_nav_defaults()
        nav_main = list(_nav["main"])
        sub_select = _build_sub_select()
        nav_pairs = _build_nav_pairs()
        script_select = _build_script_select()
    return render_template_string(
        SETTINGS_PAGE,
        nav_main=nav_main,
        sub_select=sub_select,
        nav_pairs=nav_pairs,
        script_select=script_select,
        background_style=_get_background_style(),
    )


@app.route("/nav/add-main", methods=["POST"])
@_require_admin
def add_main_nav():
    with _lock:
        global _last_message
        _last_message = _add_main_nav(request.form.get("main_name", ""))
    return redirect(url_for("settings"))


@app.route("/nav/add-sub", methods=["POST"])
@_require_admin
def add_sub_nav():
    with _lock:
        global _last_message
        _last_message = _add_sub_nav(
            request.form.get("main_name", ""),
            request.form.get("sub_name", ""),
        )
    return redirect(url_for("settings"))


@app.route("/nav/remove-main", methods=["POST"])
@_require_admin
def remove_main_nav():
    with _lock:
        global _last_message
        _last_message = _remove_main_nav(request.form.get("main_name", ""))
    return redirect(url_for("settings"))


@app.route("/nav/remove-sub", methods=["POST"])
@_require_admin
def remove_sub_nav():
     with _lock:
         global _last_message
         _last_message = _remove_sub_nav(request.form.get("sub_key", ""))
     return redirect(url_for("settings"))


@app.route("/nav/rename-main", methods=["POST"])
@_require_login
def rename_main_nav():
    # Only WIN2 can rename navigation
    if _get_current_username() != "WIN2":
        return jsonify({"success": False, "message": "Only WIN2 can rename navigation"}), 403
    
    try:
        old_name = request.form.get("old_name", "")
        new_name = request.form.get("new_name", "")
        print(f"[RENAME-MAIN] old_name={old_name}, new_name={new_name}")
        
        with _lock:
            global _last_message, _nav, _scripts
            _last_message = _rename_main_nav(old_name, new_name)
            print(f"[RENAME-MAIN] Result: {_last_message}")
            print(f"[RENAME-MAIN] Updated _nav['main']: {_nav['main']}")
            import time
            time.sleep(0.5)  # Ensure file write completes
        
        return jsonify({"success": True, "message": _last_message})
    except Exception as e:
        print(f"[RENAME-MAIN] Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "message": str(e)}), 400


@app.route("/nav/rename-sub", methods=["POST"])
@_require_login
def rename_sub_nav():
    # Only WIN2 can rename navigation
    if _get_current_username() != "WIN2":
        return jsonify({"success": False, "message": "Only WIN2 can rename navigation"}), 403
    
    try:
        main_name = request.form.get("main_name", "")
        old_name = request.form.get("old_name", "")
        new_name = request.form.get("new_name", "")
        print(f"[RENAME-SUB] main_name={main_name}, old_name={old_name}, new_name={new_name}")
        
        with _lock:
            global _last_message, _nav, _scripts
            _last_message = _rename_sub_nav(main_name, old_name, new_name)
            print(f"[RENAME-SUB] Result: {_last_message}")
            print(f"[RENAME-SUB] Updated _nav['subs'][{main_name}]: {_nav['subs'].get(main_name, [])}")
            import time
            time.sleep(0.5)  # Ensure file write completes
        
        return jsonify({"success": True, "message": _last_message})
    except Exception as e:
        print(f"[RENAME-SUB] Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "message": str(e)}), 400


@app.route("/nav/reorder", methods=["POST"])
@_require_login
def reorder_nav():
    if _get_current_username() != "WIN2":
        return jsonify({"success": False, "message": "Only WIN2 can reorder navigation"}), 403
    try:
        dragged = request.form.get("dragged", "")
        target = request.form.get("target", "")
        before = request.form.get("before", "true").lower() == "true"
        if not dragged or not target or dragged == target:
            return jsonify({"success": False, "message": "Invalid reorder parameters"}), 400
        with _lock:
            global _nav
            main_list = list(_nav.get("main", []))
            if dragged not in main_list or target not in main_list:
                return jsonify({"success": False, "message": "Navigation item not found"}), 400
            main_list.remove(dragged)
            target_idx = main_list.index(target)
            if not before:
                target_idx += 1
            main_list.insert(target_idx, dragged)
            _nav["main"] = main_list
            nav_path = os.path.join(os.path.dirname(__file__), "nav.json")
            with open(nav_path, "w") as f:
                json.dump(_nav, f, indent=2)
            return jsonify({"success": True, "message": "Navigation reordered successfully"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 400


@app.route("/script/change-path-modal")
@_require_admin
def change_path_modal():
    """Serve the change script path modal dialog"""
    return render_template_string(CHANGE_PATH_MODAL, scripts=_scripts, background_style=_get_background_style())


@app.route("/script/update-path-bulk", methods=["POST"])
@_require_admin
def update_script_path_bulk():
    """Update paths for multiple scripts"""
    with _lock:
        script_ids = request.form.getlist("script_ids[]")
        new_path = request.form.get("new_path", "").strip()
        admin_user = request.form.get("admin_user", "").strip()
        admin_password = request.form.get("admin_password", "")
        admin = _get_user(admin_user)
        
        if not script_ids or not new_path:
            return make_response(jsonify({"success": False, "message": "Please select at least one script and enter a new path."}), 400)
        if not admin or admin.get("role") != "ADMIN" or not _verify_user(admin_user, admin_password):
            return make_response(jsonify({"success": False, "message": "Admin verification failed."}), 403)
        else:
            try:
                updated_count = 0
                for script_id_str in script_ids:
                    script_id = int(script_id_str)
                    if 0 <= script_id < len(_scripts):
                        # Extract filename from current path and combine with new path
                        old_path = _scripts[script_id]["path"]
                        filename = os.path.basename(old_path)
                        _scripts[script_id]["path"] = os.path.join(new_path, filename)
                        updated_count += 1
                
                if updated_count > 0:
                    _save_scripts()
                    return jsonify({"success": True, "message": f"Path updated for {updated_count} script(s)"})
                else:
                    return make_response(jsonify({"success": False, "message": "Invalid script selection."}), 400)
            except (ValueError, IndexError):
                return make_response(jsonify({"success": False, "message": "Error updating path."}), 400)


@app.route("/script/update-path", methods=["POST"])
@_require_admin
def update_script_path():
    with _lock:
        global _last_message
        script_id_str = request.form.get("script_id", "")
        new_path = request.form.get("new_path", "").strip()
        
        if not script_id_str or not new_path:
            _last_message = "Please select a script and enter a new path."
        else:
            try:
                script_id = int(script_id_str)
                if 0 <= script_id < len(_scripts):
                    _scripts[script_id]["path"] = new_path
                    _save_scripts()
                    _last_message = f"Path updated successfully: {new_path}"
                else:
                    _last_message = "Invalid script selection."
            except (ValueError, IndexError):
                _last_message = "Error updating path."
    return redirect(url_for("settings"))


@app.route("/backgrounds/<path:filename>")
def background_file(filename):
    bg_dir = os.path.join(_upload_dir, "backgrounds")
    return send_from_directory(bg_dir, filename)


@app.route("/background", methods=["POST"])
@_require_login
def update_background():
    with _lock:
        admin_user = request.form.get("admin_user", "")
        admin_password = request.form.get("admin_password", "")
        admin = _get_user(admin_user)
        if not admin or admin.get("role") != "ADMIN" or not _verify_user(admin_user, admin_password):
            return redirect(
                url_for(
                    "index",
                    main=request.args.get("main", ""),
                    sub=request.args.get("sub", ""),
                )
            )
        mode = request.form.get("bg_mode", "default")
        if mode == "custom":
            image_name = _save_background_image(request.files.get("bg_file"))
            if image_name:
                _background["mode"] = "custom"
                _background["image"] = image_name
                _save_background()
        else:
            _background["mode"] = "default"
            _background["image"] = ""
            _save_background()
    return redirect(
        url_for(
            "index",
            main=request.args.get("main", ""),
            sub=request.args.get("sub", ""),
        )
    )


@app.route("/history")
@_require_login
def history():
    with _lock:
        user = _get_current_user()
        entries = list(_history)
        if user and user.get("role") != "ADMIN":
            entries = [item for item in entries if item.get("user") == user.get("username")]
        formatted = [
            {
                "time": _format_timestamp(item.get("ts", "")),
                "user": item.get("user", ""),
                "action": item.get("action", ""),
                "script": item.get("script", ""),
                "ip": item.get("ip", ""),
            }
            for item in reversed(entries)
        ]
    return render_template_string(
        HISTORY_PAGE,
        entries=formatted,
        background_style=_get_background_style(),
    )


@app.route("/access-log")
@_require_admin
def access_log():
     with _lock:
         message = request.args.get("message", "")
         show_ip_list = request.args.get("view") == "ip-list"
         ip_list = [
             {"ip": ip, "label": label}
             for ip, label in sorted(_ip_labels.items())
         ]
         entries = [
             {
                 "time": _format_timestamp(item.get("ts", "")),
                 "user": item.get("user", ""),
                 "status": item.get("status", ""),
                 "ip": item.get("ip", ""),
                 "label": _ip_labels.get(item.get("ip", ""), "Unknown IP") if item.get("ip") else "Unknown IP",
             }
             for item in reversed(_access_log)
         ]
         current_username = _get_current_username()
         # Only show IP protection controls to authorized users
         show_ip_protection = current_username in _ip_protection_access
     return render_template_string(
         ACCESS_LOG_PAGE,
         entries=entries,
         message=message,
         show_ip_list=show_ip_list,
         ip_list=ip_list,
         background_style=_get_background_style(),
         ip_protection_enabled=_ip_protection.get("enabled", False),
         show_ip_protection=show_ip_protection,
     )


@app.route("/access-log/ip", methods=["POST"])
@_require_admin
def add_ip_label():
    with _lock:
        admin_user = request.form.get("admin_user", "")
        admin_password = request.form.get("admin_password", "")
        admin = _get_user(admin_user)
        if not admin or admin.get("role") != "ADMIN" or not _verify_user(admin_user, admin_password):
            return redirect(url_for("access_log", message="Admin verification failed."))
        message = _set_ip_label(
            request.form.get("ip_address", ""),
            request.form.get("ip_label", ""),
        )
    return redirect(url_for("access_log", message=message))


@app.route("/access-log/ip-list", methods=["POST"])
@_require_admin
def view_ip_list():
     with _lock:
         admin_user = request.form.get("admin_user", "")
         admin_password = request.form.get("admin_password", "")
         admin = _get_user(admin_user)
         if not admin or admin.get("role") != "ADMIN" or not _verify_user(admin_user, admin_password):
             return redirect(url_for("access_log", message="Admin verification failed."))
     return redirect(url_for("access_log", view="ip-list"))


@app.route("/access-log/remove-ip", methods=["POST"])
@_require_login
def remove_ip_label():
     # Only authorized users can remove IPs
     if _get_current_username() not in _ip_protection_access:
         return redirect(url_for("access_log", message="You do not have permission to remove IPs."))
     with _lock:
         ip_address = request.form.get("ip_address", "").strip()
         if ip_address in _ip_labels:
             del _ip_labels[ip_address]
             _save_ip_labels()
             return redirect(url_for("access_log", message=f"IP {ip_address} removed successfully.", view="ip-list"))
         else:
             return redirect(url_for("access_log", message="IP address not found."))


@app.route("/script/update-name", methods=["POST"])
@_require_admin
def update_script_name():
    try:
        script_id = int(request.form.get("script_id", "-1"))
        new_name = request.form.get("new_name", "").strip()
        
        if not (0 <= script_id < len(_scripts)):
            return {"success": False, "message": "Invalid script ID"}
        
        if not new_name:
            return {"success": False, "message": "Name cannot be empty"}
        
        with _lock:
            _scripts[script_id]["name"] = new_name
            _save_scripts()
        
        return {"success": True, "message": "Name updated"}
    except Exception as e:
        return {"success": False, "message": str(e)}


@app.route("/ip-protection/toggle", methods=["POST"])
@_require_admin
def toggle_ip_protection():
    with _lock:
        global _ip_protection
        action = request.form.get("action", "").lower()
        
        if action == "start":
            if not _ip_labels:
                return redirect(url_for("index", message="Cannot enable IP protection. No IPs are whitelisted. Add IPs first."))
            _ip_protection["enabled"] = True
        elif action == "stop":
            _ip_protection["enabled"] = False
        
        _save_ip_protection()
    
    return redirect(url_for("index"))


@app.route("/edit-verify", methods=["POST"])
@_require_admin
def edit_script_verify():
    admin_user = request.form.get("admin_user", "")
    admin_password = request.form.get("admin_password", "")
    script_id = request.form.get("script_id", "")
    main = request.form.get("main", "")
    sub = request.form.get("sub", "")
    
    admin = _get_user(admin_user)
    if not admin or admin.get("role") != "ADMIN" or not _verify_user(admin_user, admin_password):
        return redirect(url_for("index", main=main, sub=sub, message="Admin verification failed."))
    
    return redirect(url_for("edit_script", script_id=int(script_id), main=main, sub=sub))


@app.route("/edit/<int:script_id>", methods=["GET", "POST"])
@_require_admin
def edit_script(script_id: int):
    message = ""
    script_path = ""
    script_body = ""
    if not (0 <= script_id < len(_scripts)):
        return redirect(url_for("index"))
    entry = _scripts[script_id]
    script_path = entry.get("path", "")
    if request.method == "POST":
        script_body = request.form.get("script_body", "")
        if script_path and os.path.isfile(script_path):
            normalized = script_body.replace("\r\n", "\n").replace("\r", "\n")
            with open(script_path, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(normalized)
            message = "Script saved."
            script_name = entry.get("name") or os.path.splitext(os.path.basename(script_path))[0]
            _append_history(_get_current_username(), "EDIT", script_name, _get_client_ip())
        else:
            message = "Script file not found."
    if script_path and os.path.isfile(script_path):
        with open(script_path, "r", encoding="utf-8", errors="replace") as handle:
            script_body = handle.read()
    back_url = url_for(
        "index",
        main=request.args.get("main", ""),
        sub=request.args.get("sub", ""),
    )
    return render_template_string(
        EDIT_PAGE,
        script_path=script_path,
        script_body=script_body,
        message=message,
        back_url=back_url,
        background_style=_get_background_style(),
    )


@app.route("/login", methods=["GET", "POST"])
def login():
     message = ""
     if request.method == "POST":
         username = request.form.get("username", "")
         password = request.form.get("password", "")
         client_ip = _get_client_ip()
         
         if _verify_user(username, password):
             _append_access_log(username, "SUCCESS", client_ip)
             session["user"] = (username or "").strip().upper()
             return redirect(url_for("welcome"))
         _append_access_log(username, "FAIL", client_ip)
         message = "Invalid user name or password."
     return render_template_string(
         LOGIN_PAGE,
         message=message,
         background_style=_get_background_style(),
     )

@app.route("/welcome")
@_require_login
def welcome():
     return render_template_string(
         WELCOME_PAGE,
         background_style=_get_background_style(),
     )


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    with _lock:
        _ensure_nav_defaults()
        nav_main = list(_nav["main"])
        message = ""
        if request.method == "POST":
            username = request.form.get("new_username", "")
            password = request.form.get("new_password", "")
            confirm = request.form.get("confirm_password", "")
            role = request.form.get("role", "PAYMENT EDITOR").upper()
            nav_access = request.form.getlist("nav_access")
            if not username or not password:
                message = "User name and password are required."
            elif password != confirm:
                message = "Passwords do not match."
            else:
                if not _has_admin():
                    role = "ADMIN"
                if _has_admin():
                    admin_user = request.form.get("admin_user", "")
                    admin_password = request.form.get("admin_password", "")
                    admin = _get_user(admin_user)
                    if not admin or admin.get("role") != "ADMIN" or not _verify_user(admin_user, admin_password):
                        message = "Admin verification failed."
                if not message:
                    message = _create_user(username, password, role, nav_access)
        return render_template_string(
            REGISTER_PAGE,
            message=message,
            nav_main=nav_main,
            background_style=_get_background_style(),
        )


@app.route("/admin/ip-access", methods=["GET", "POST"])
@_require_admin
def admin_ip_access():
     # Only WIN2 can access IP protection settings
     if _get_current_username() != "WIN2":
         return redirect(url_for("admin", message="You do not have permission to manage IP protection access."))
     
     with _lock:
         message = ""
         if request.method == "POST":
             # Check if this is a credential verification POST (from modal)
             admin_user = request.form.get("admin_user", "").strip()
             admin_password = request.form.get("admin_password", "")
             action = request.form.get("action", "").lower()
             username = request.form.get("username", "").strip().upper()
             
             # Verify credentials
             if admin_user or admin_password:
                 admin = _get_user(admin_user)
                 if not admin or admin.get("role") != "ADMIN" or not _verify_user(admin_user, admin_password):
                     message = "Admin verification failed."
                     return redirect(url_for("admin", message=message))
             
             if action == "add" and username and username not in _ip_protection_access:
                 if _get_user(username):
                     _ip_protection_access.append(username)
                     _save_ip_protection_access()
                     message = f"User {username} added to IP protection access."
                 else:
                     message = f"User {username} does not exist."
             elif action == "remove" and username in _ip_protection_access:
                 _ip_protection_access.remove(username)
                 _save_ip_protection_access()
                 message = f"User {username} removed from IP protection access."
         
         all_users = [u.get("username", "") for u in _users]
     return render_template_string(
         IP_ACCESS_PAGE,
         authorized_users=_ip_protection_access,
         all_users=all_users,
         message=message,
         background_style=_get_background_style(),
     )


@app.route("/admin", methods=["GET", "POST"])
@_require_admin
def admin():
     with _lock:
         _ensure_nav_defaults()
         nav_main = list(_nav["main"])
         message = ""
         selected_user = request.form.get("username") or (request.args.get("user") or "")
         if request.method == "POST" and selected_user:
             entry = _get_user(selected_user)
             if entry:
                 entry["role"] = request.form.get("role", entry.get("role", "PAYMENT EDITOR"))
                 entry["nav_access"] = request.form.getlist("nav_access")
                 _save_users()
                 message = "Permissions updated."
         users = [{"username": item.get("username", ""), "role": item.get("role", "")} for item in _users]
         if not selected_user and users:
             selected_user = users[0]["username"]
         current = _get_user(selected_user) if selected_user else None
         selected_role = current.get("role") if current else ""
         selected_nav = current.get("nav_access", []) if current else []
     current_user_obj = _get_current_user()
     return render_template_string(
         ADMIN_PAGE,
         users=users,
         selected_user=selected_user,
         selected_role=selected_role,
         selected_nav=selected_nav,
         nav_main=nav_main,
         message=message,
         background_style=_get_background_style(),
         current_username=_get_current_username(),
     )


if __name__ == "__main__":
     _load_scripts()
     _ensure_defaults()
     _load_nav()
     _ensure_nav_defaults()
     _load_users()
     _ensure_default_admin()
     _load_background()
     _load_history()
     _load_access_log()
     _load_ip_labels()
     _load_ip_protection()
     _load_ip_protection_access()
     app.run(host="127.0.0.1", port=5000, debug=False)
