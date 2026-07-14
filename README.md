# POS Cafè - Ultimate Multi-Branch Restaurant Management System

POS Cafè is a high-performance, full-featured restaurant Point of Sale (POS) system designed for modern cafes and restaurants. Built with a focus on speed, scalability, and premium user experience, it handles everything from floor management to real-time kitchen coordination.

## 🌟 Premium Features

- **Multi-Branch Architecture**: Manage multiple branches with scoped inventory, reports, and staff management from a single platform.
- **Interactive Floor Plan**: Visual table management with real-time status updates (Occupied, Reserved, Available).
- **Self-Order QR System**: Customers can scan table-specific QR codes to browse the menu and place orders directly from their mobile devices without logging in.
- **Real-Time Kitchen Display (KDS)**: Instant order synchronization between the POS terminal and kitchen via Socket.io.
- **WhatsApp Bill Sharing**: Send digital receipts directly to customers' WhatsApp numbers with one click.
- **Automated Menu Management**: Intelligent category-based image mapping for products, reducing manual overhead.
- **Comprehensive Analytics**: Dynamic dashboards with Chart.js showing sales trends, popular items, and branch performance.
- **Multiple Payment Gateways**: Integrated support for Cash, Card, and dynamic UPI QR code generation.
- **Guest Session Management**: Secure guest checkout for self-orders with privacy-focused bill viewing.

## 🛠️ Technology Stack

- **Backend**: Python 3.x, Flask, SQLAlchemy, Flask-SocketIO
- **Database**: SQLite (Development), PostgreSQL (Production ready)
- **Frontend**: HTML5, Tailwind CSS, Vanilla JavaScript, Socket.io-client
- **Real-time**: WebSockets for instant updates across POS, Kitchen, and Customer displays.
- **Branding**: Custom SVG icons, Syne & DM Sans typography for a sleek, modern look.

## 🚀 Quick Start

### Prerequisites
- Python 3.8+
- Node.js (for Tailwind/PostCSS processing if needed)

### Installation

1. **Clone & Navigate**:
   ```bash
   git clone https://github.com/shreybhut21/pos-cafe.git
   cd pos-cafe
   ```

2. **Environment Setup**:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Database Initialization**:
   The application automatically handles schema migrations and initial seeding on first run.

4. **Launch**:
   ```bash
   python app.py
   ```

### PostgreSQL

Set `DATABASE_URL` to use PostgreSQL instead of SQLite:

```env
DATABASE_URL=postgresql://username:password@localhost:5432/pos_cafe
```

### SQLite to PostgreSQL migration

1. Create an empty PostgreSQL database.
2. Set `DATABASE_URL` to that PostgreSQL database.
3. Run:
   ```bash
   python migrate_sqlite_to_postgres.py --sqlite-path instance/pos.db
   ```

This recreates the PostgreSQL schema first, so the new PostgreSQL-native types and indexes are applied cleanly.

Use `--keep-existing` only when you intentionally want to import into an existing PostgreSQL schema without recreating tables first.

## 🗺️ System Modules

| Route | Module | Description |
| :--- | :--- | :--- |
| `/auth` | **Authentication** | Secure Login/Signup with branch selection. |
| `/pos` | **POS Terminal** | The main interface for taking orders and processing payments. |
| `/backend` | **Admin Panel** | Configure products, floors, branches, and payment methods. |
| `/kitchen` | **Kitchen Display** | Real-time order queue for chefs. |
| `/customer` | **Customer Display** | Public-facing screen for order status and branding. |
| `/dashboard`| **Analytics** | Deep dive into sales data and performance metrics. |
| `/qr/<table_id>` | **Self-Order** | Guest interface for table-side ordering. |

## 🎨 Design Philosophy
POS Cafè follows a **Glassmorphism** design language with a focus on:
- **Micro-animations**: Smooth transitions for cart additions and status changes.
- **Responsive Layouts**: Optimized for both high-resolution desktops and tablet-based mobile POS.
- **Harmonious Palettes**: Tailored color schemes for Light and Dark modes.

---
Built with excellence by **Shrey**
