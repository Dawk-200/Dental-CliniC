# Willow Creek Dental Clinic — Website & Appointment Management System

A complete, production-ready dental clinic website with a patient-facing site and a
secure admin dashboard, built with **Flask + SQLAlchemy + SQLite** on the backend and
**vanilla HTML/CSS/JavaScript** on the frontend (no React/Vue/Node).

---

## 1. Project Overview

This project has two halves:

1. **Patient website** — home page, doctor profile, treatments (with individual SEO
   pages), clinic timings, contact, FAQ, blog, legal pages, and a full multi-step
   **appointment booking wizard** with live slot availability, cancellation, and
   rescheduling (all validated server-side).
2. **Admin dashboard** (`/admin`) — appointment & patient management, availability /
   slot configuration, treatment & blog CMS, reviews, notifications, statistics,
   clinic & SEO settings, an audit log, and database backups.

All clinic branding (name, doctor, contact info, hours) lives in the database and is
editable from **Clinic Settings** — nothing is hard-coded in templates.

---

## 2. Technology Stack

| Layer      | Technology                                   |
|------------|-----------------------------------------------|
| Frontend   | HTML5, CSS3, vanilla JavaScript (`fetch`)      |
| Backend    | Python 3, Flask, Flask-Login, Flask-WTF, Flask-Limiter |
| Database   | SQLite via SQLAlchemy ORM                      |
| Charts     | Chart.js (CDN, admin dashboard only)           |

No React, Vue, Angular, Node.js, MongoDB, Firebase, or Supabase is used anywhere.

---

## 3. Installation

### 3.1 Prerequisites
- Python 3.10+
- pip

### 3.2 Clone / copy the project, then create a virtual environment

```bash
cd dental_clinic
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
```

### 3.3 Install requirements

```bash
pip install -r requirements.txt
```

### 3.4 Configure environment variables

```bash
cp .env.example .env
```

Edit `.env` and set at minimum:
- `SECRET_KEY` — a long, random string (never reuse the placeholder in production)
- `ADMIN_EMAIL` / `ADMIN_PASSWORD` — used **only the first time** `seed.py` runs, to
  create the initial admin account
- `SITE_URL` — your public domain (used in the sitemap and canonical URLs)
- `WHATSAPP_NUMBER` — digits only, international format, no `+` or spaces

Leave `DATABASE_URL` blank to use the default SQLite file at `instance/clinic.db`.

### 3.5 Initialize the database and seed demo data

```bash
python seed.py
```

This creates all tables, one admin account, default working hours, ~12 demo
treatments, two blog posts, three reviews, and one demo appointment. Running it again
is safe — it only creates data that doesn't already exist.

### 3.6 Run the app

```bash
python run.py
```

Visit `http://127.0.0.1:5000` for the public site and
`http://127.0.0.1:5000/admin/login` for the admin dashboard.

**Demo admin credentials** (from your `.env`, defaults shown):
```
Email:    admin@example.com
Password: ChangeThisPassword123!
```
**Change this password immediately** after first login (Admin Profile page), and
never deploy with the default value.

---

## 4. How Appointment Booking Works

1. Patient selects a treatment (or "Other" with a free-text description).
2. Patient picks a date from a calendar that only allows open clinic days and
   disables past dates.
3. The frontend calls `GET /api/available-slots?date=...&treatment_id=...`, which is
   computed **entirely server-side** from:
   - `WorkingHours` (open/close time, break window) for that weekday
   - `BlockedSlot` entries (admin-blocked days/times)
   - existing, non-cancelled `Appointment` rows for that date
4. Patient selects a slot, enters contact details, and confirms.
5. `POST /book-appointment/confirm` **re-validates everything** (treatment, date,
   slot availability) before writing to the database — the frontend wizard is UX
   only and is never trusted for security or correctness.
6. A unique `(date, time)` database constraint provides a final safety net against
   race conditions/double-booking even under concurrent requests.
7. An `AppointmentHistory` row and an admin `Notification` are created automatically.

Patients can later cancel or reschedule via **My Appointment** using their
appointment reference code + phone number — no account required. Every change is
recorded in `AppointmentHistory` (appointments are never hard-deleted).

---

## 5. How to Change Clinic Information

Nothing is hard-coded. Log in to `/admin` and go to:
- **Clinic Settings** — name, tagline, doctor bio/qualifications, phone, WhatsApp,
  email, address, Google Maps embed URL, social links, default appointment duration
- **Availability** — weekly working hours, breaks, and one-off blocked dates/slots
- **Treatments** — add/edit/deactivate treatments, including full SEO-friendly detail
  pages with FAQs
- **SEO Settings** — default site title/meta description
- **Blog** — publish articles with categories, tags, and SEO fields
- **Reviews** — add genuine patient testimonials (do not fabricate reviews)

---

## 6. Deployment

This app ships with Flask's built-in development server for local use only. For
production:

```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:8000 "run:app"
```

Put a reverse proxy (nginx, Caddy, etc.) in front of gunicorn to terminate HTTPS.

Checklist before going live:
- [ ] Set a strong, unique `SECRET_KEY`
- [ ] Set `FLASK_ENV=production`
- [ ] Set `SESSION_COOKIE_SECURE=True` (requires HTTPS)
- [ ] Change the default admin password
- [ ] Set a real `SITE_URL`
- [ ] Confirm `instance/` (containing the SQLite DB and backups) is **not** served
      publicly by your web server / reverse proxy
- [ ] Take a backup via **Admin → Backup** before major changes

---

## 7. Security Considerations

- Passwords are hashed with Werkzeug's `generate_password_hash` (PBKDF2) — never
  stored in plaintext.
- All forms are protected by **CSRF tokens** (Flask-WTF `CSRFProtect`), including
  every admin action and the public booking/contact/cancel/reschedule forms.
- Session cookies are `HttpOnly`, `SameSite=Lax`, and `Secure` when
  `SESSION_COOKIE_SECURE=True` (enable this once serving over HTTPS).
- All database access goes through the SQLAlchemy ORM — no raw/string-built SQL.
- Every admin route is protected by `@login_required` + a custom `@admin_required`
  check (`app/decorators.py`), applied blueprint-wide via `before_request`.
- Sensitive/mutating admin actions (login, logout, settings changes, status changes,
  treatment/blog edits, backups, password changes, etc.) are written to the
  `AuditLog` table with the acting admin, action, target, and IP address.
- Rate limiting (Flask-Limiter) is applied to login, contact form, booking, and
  appointment-lookup endpoints to slow down brute-force/abuse attempts.
- Admin pages send `X-Robots-Tag: noindex, nofollow` and are excluded in
  `robots.txt`.
- Security headers (`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`)
  are set on every response.
- No secrets are ever placed in frontend JavaScript; all credentials/API keys live in
  environment variables (see `.env.example`).
- The database file lives under `instance/`, which should never be exposed by your
  web server configuration.

---

## 8. SEO Setup

Already implemented out of the box:
- Semantic HTML5, proper heading hierarchy, descriptive `alt` text
- Unique `<title>` and meta description per page/treatment/blog post (editable in
  admin)
- Canonical URLs on every page
- Open Graph + Twitter Card metadata
- JSON-LD structured data: `Dentist`/`LocalBusiness` sitewide, `MedicalProcedure` +
  `FAQPage` on treatment pages, `FAQPage` on the FAQ page
- Auto-generated `/sitemap.xml` (static pages + active treatments + published blog
  posts) and `/robots.txt` (disallows `/admin` and `/api/`)
- Breadcrumbs on inner pages
- Custom 404/403/500 error pages

### Google Search Console
1. Verify ownership using the `GOOGLE_SITE_VERIFICATION` meta tag — set the value in
   `.env` and it's automatically rendered site-wide.
2. Submit `https://yourdomain.com/sitemap.xml` in Search Console.

### Google Analytics
Set `GOOGLE_ANALYTICS_ID` in `.env` to automatically load gtag.js sitewide.

### Google Business Profile (recommendation)
Keep your clinic's name, address, and phone number in Admin → Clinic Settings
**identical** to what you list on your Google Business Profile — consistent NAP
(Name/Address/Phone) data across the web is one of the strongest local SEO signals.

---

## 9. Project Structure

```
dental_clinic/
├── app/
│   ├── __init__.py          # App factory, security headers, error handlers
│   ├── models.py            # SQLAlchemy models
│   ├── extensions.py        # db, csrf, login_manager, limiter
│   ├── decorators.py        # @admin_required
│   ├── utils.py             # Slot engine, audit logging, WhatsApp links, etc.
│   ├── routes/
│   │   ├── main.py          # Public pages
│   │   ├── booking.py       # Appointment booking / cancel / reschedule
│   │   ├── api.py           # JSON endpoints (slots, notifications)
│   │   ├── admin_auth.py    # Admin login/logout
│   │   ├── admin.py         # Admin dashboard (all management screens)
│   │   └── seo.py           # sitemap.xml, robots.txt
│   ├── templates/           # Jinja2 templates (public + admin/)
│   └── static/
│       ├── css/             # style.css (public), admin.css
│       └── js/               # main.js, booking.js, admin.js
├── instance/                 # SQLite DB + backups (never served publicly)
├── seed.py                   # Demo data seed script
├── run.py                    # Dev entry point
├── config.py                 # Environment-based configuration
├── requirements.txt
├── .env.example
└── README.md
```

---

## 10. Tested Flows

The following flows were manually verified against a running instance during
development:

- **Patient flow:** Home → Treatment detail → Book Appointment (treatment → date →
  slot → details → confirm) → confirmation page with reference code
- **Double-booking prevention:** booking the same slot twice is rejected server-side
- **Cancellation flow:** My Appointment lookup → Cancel → slot freed → admin
  notification created
- **Reschedule flow:** patient- and admin-side reschedule, validated against live
  availability, recorded in appointment history
- **Admin flow:** Login → Dashboard stats → Appointment detail → status change →
  Patient detail → Statistics (date-range filters)
- **Blog CMS:** create/publish a post from admin → appears on the public blog and in
  `sitemap.xml`
- **SEO flow:** page titles/meta/canonical/structured data render correctly;
  `sitemap.xml` and `robots.txt` respond with valid content
- **Security:** unauthenticated requests to `/admin/*` redirect to login; admin pages
  send `noindex`; POST requests without a valid CSRF token are rejected (HTTP 400)

---

## 11. Notes & Limitations

- Reminder channels (email/WhatsApp Business API) are wired up as configuration
  (`SMTP_*`, `WHATSAPP_API_*` in `.env`) but no external API calls are made — this
  keeps the demo free of fake integrations. Add your provider's SDK/API calls in
  `app/utils.py` when you're ready to connect a real service.
- Patient accounts/login were intentionally **not** implemented — patients manage
  appointments via a reference code + phone number instead, which is simpler and
  still fully self-service. Full patient accounts can be added later using the same
  `AdminUser`-style pattern (Flask-Login, hashed passwords) against a new patient
  auth table.
- Treatment/doctor photos use placeholder gradient panels — replace with real
  `<img>` tags pointing to uploaded files once available.
