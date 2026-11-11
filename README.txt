MATSYODARI RENEWABLES - WEBSITE WITH WORKING BACKEND
=====================================================

WHAT YOU HAVE
  index.html, css/, js/, images/   the website
  admin/                           the admin panel (where you read customer enquiries)
  server.py                        the backend (saves enquiries, sends e-mail, runs the admin panel)
  .env.example                     settings template (copy to ".env")
  start.bat / start.sh             double-click to start the server (Windows / Mac-Linux)

HOW TO RUN IT (2 minutes)
  1. Install Python 3 from python.org if you do not have it (tick "Add Python to PATH").
     Nothing else is needed - the server uses only what comes with Python.
  2. Double-click start.bat   (or open a terminal in this folder and run:  python server.py)
  3. Open  http://127.0.0.1:8000        -> the website
     Open  http://127.0.0.1:8000/admin  -> the admin panel

  On the very first run the server prints your ADMIN PASSWORD and saves it in data/admin_password.txt.
  To choose your own, copy ".env.example" to ".env" and set ADMIN_PASSWORD there.

HOW THE ENQUIRY FORM WORKS
  A customer fills in the form -> "Send Enquiry" -> the server checks it, saves it in
  data/enquiries.db and (if e-mail is set up) e-mails it to you and sends the customer a receipt.
  The customer sees a reference number such as MR-00012.
  WhatsApp and Email buttons remain as backups, and are used automatically as advice if the
  server cannot be reached.

  In the admin panel you can search, see new/contacted/closed counts, change a status,
  add notes, delete spam and download all enquiries as a CSV (Excel) file.

GET E-MAIL ALERTS (recommended)
  Copy ".env.example" to ".env", remove the # in front of the SMTP lines and fill them in.
  Easiest is a Gmail account with an "App password". Restart the server afterwards.
  Without this, enquiries are still saved - you just have to look in the admin panel.

USING VS CODE "LIVE SERVER"
  The site also works when opened with Live Server (port 5500) as long as server.py is running
  on port 8000 at the same time - the form finds the backend automatically.

PUTTING IT ONLINE
  The website files can go on any host, but the backend needs a place that can run Python
  (a small VPS, Render, Railway, PythonAnywhere ...). On a real server set in ".env":
      HOST=0.0.0.0
      TRUST_PROXY=1      (when behind HTTPS / a proxy such as nginx or Caddy)
      COOKIE_SECURE=1    (when the site is served over HTTPS)
  Always use HTTPS and a strong ADMIN_PASSWORD. Back up the "data" folder - that is where all
  enquiries live. Never share the ".env" or "data" folders; the server does not serve them.

BUILT-IN PROTECTION
  Input checks on every field, a hidden spam trap field, limits on how often one visitor can
  submit, a locked admin area (password, signed cookie, brute-force lock after 8 wrong tries),
  protection against forged requests, CSV formula protection and no access to server files.

EDITING THE TEXT
  Team names, roles and all text are in index.html (search for "Our team").
  Colours are at the top of css/style.css. Phone and email for WhatsApp/Email are in js/script.js.
