# Odoo POS Cafe — Hackathon Project

A full-featured Restaurant POS system built with Flask + HTML/CSS/JS + Tailwind CSS.

## Features
- Login / Signup authentication
- Floor Plan & Table Management
- Product Management (CRUD + categories)
- Order creation with cart
- Real-time Kitchen Display (Socket.io)
- Customer Display screen
- Multiple Payment Methods: Cash, Card, UPI QR (auto-generated)
- Reports Dashboard with Charts
- Backend Configuration panel

## Setup

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run the app
python app.py

# 4. Open in browser
http://localhost:5000
```

## Demo Credentials
Sign up with any email/password OR use the pre-seeded data.

## Pages
| URL | Description |
|-----|-------------|
| `/auth` | Login / Signup |
| `/pos` | POS Terminal (floor + orders + payment) |
| `/backend` | Config: products, floors, payment methods |
| `/kitchen` | Kitchen Display (open on kitchen screen) |
| `/customer` | Customer Display (face toward customer) |
| `/dashboard` | Reports & Analytics |

## Tech Stack
- **Backend**: Flask, Flask-SQLAlchemy, Flask-SocketIO
- **Database**: SQLite (zero config)
- **Frontend**: HTML, Tailwind CSS (CDN), Vanilla JS
- **Real-time**: Socket.io
- **Charts**: Chart.js
- **Fonts**: Syne (display) + DM Sans (body)
