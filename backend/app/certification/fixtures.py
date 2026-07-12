"""
Phase F — Local Certification Fixtures (deterministic, offline).

Self-contained local HTML applications simulating common UI patterns. They are the
regression baseline: stable ids / data-testid / labels so locators resolve reliably, and
deterministic post-action state so success can be verified. Served by FixtureServer over
a local loopback HTTP server (no internet).

Each fixture is also a valid Website Intelligence input (analyze_html).
"""
from __future__ import annotations

import http.server
import socket
import socketserver
import threading
from typing import Optional

_DOC = "<!doctype html><html><head><meta charset='utf-8'><title>{title}</title></head><body>{body}</body></html>"


def _p(title: str, body: str) -> str:
    return _DOC.format(title=title, body=body)


# ── 1. Login ──────────────────────────────────────────────────────────────────
LOGIN = _p("Login", """
<header><h1>Acme Login</h1></header>
<main>
  <form id="login-form" aria-label="Login">
    <label for="username">Username</label>
    <input id="username" name="username" type="text" data-testid="username" required/>
    <label for="password">Password</label>
    <input id="password" name="password" type="password" data-testid="password" required/>
    <button id="login-btn" data-testid="login-btn" type="submit">Sign In</button>
  </form>
  <div id="result" role="status"></div>
</main>
<script>
document.getElementById('login-form').addEventListener('submit',function(e){
  e.preventDefault();
  var u=document.getElementById('username').value, p=document.getElementById('password').value;
  document.getElementById('result').textContent = (u && p) ? 'Welcome '+u : 'Missing credentials';
});
</script>""")

# ── 2. Registration ─────────────────────────────────────────────────────────--
REGISTER = _p("Register", """
<header><h1>Create Account</h1></header>
<main>
  <form id="reg-form" aria-label="Registration">
    <label for="email">Email</label>
    <input id="email" name="email" type="email" data-testid="email" required/>
    <label for="pw">Password</label>
    <input id="pw" name="pw" type="password" data-testid="pw" required minlength="8"/>
    <label for="country">Country</label>
    <select id="country" name="country" data-testid="country">
      <option value="us">United States</option><option value="in">India</option>
    </select>
    <label><input type="checkbox" id="tos" data-testid="tos"/> Accept terms</label>
    <button id="reg-btn" data-testid="reg-btn" type="submit">Register</button>
  </form>
  <div id="reg-result" role="status"></div>
</main>
<script>
document.getElementById('reg-form').addEventListener('submit',function(e){
  e.preventDefault();
  document.getElementById('reg-result').textContent =
    document.getElementById('tos').checked ? 'Account created' : 'Terms required';
});
</script>""")

# ── 3. Dashboard ────────────────────────────────────────────────────────────--
DASHBOARD = _p("Dashboard", """
<header><h1>Dashboard</h1></header>
<nav aria-label="Primary"><ul>
  <li><a href="/dashboard" class="active">Home</a></li>
  <li><a href="/crud">Records</a></li>
  <li><a href="/search">Search</a></li>
</ul></nav>
<main>
  <section class="dashboard">
    <div class="card"><h3>Users</h3><p id="kpi-users">1,204</p></div>
    <div class="card"><h3>Revenue</h3><p id="kpi-rev">$42k</p></div>
    <div class="card"><h3>Errors</h3><p id="kpi-err">3</p></div>
  </section>
  <button id="refresh" data-testid="refresh">Refresh</button>
  <div id="refreshed" role="status"></div>
</main>
<script>
document.getElementById('refresh').addEventListener('click',function(){
  document.getElementById('refreshed').textContent='Dashboard refreshed';});
</script>""")

# ── 4. CRUD table ───────────────────────────────────────────────────────────--
CRUD = _p("Records", """
<header><h1>Records</h1></header>
<main>
  <div class="data-table">
    <button id="add" data-testid="add">Add Row</button>
    <button id="export" data-testid="export">Export CSV</button>
    <table id="grid"><caption>Customers</caption>
      <thead><tr><th class="sortable">Name</th><th>Email</th><th>Actions</th></tr></thead>
      <tbody id="rows">
        <tr data-row="1"><td class="name">Alice</td><td>alice@x.com</td>
          <td><button class="edit" data-testid="edit-1">Edit</button>
              <button class="del" data-testid="del-1">Delete</button></td></tr>
        <tr data-row="2"><td class="name">Bob</td><td>bob@x.com</td>
          <td><button class="edit" data-testid="edit-2">Edit</button>
              <button class="del" data-testid="del-2">Delete</button></td></tr>
      </tbody>
    </table>
  </div>
  <div id="status" role="status"></div>
</main>
<script>
document.querySelectorAll('.edit').forEach(function(b){
  b.addEventListener('click',function(){
    var row=b.closest('tr'); var cell=row.querySelector('.name');
    cell.textContent='Alice (edited)';
    document.getElementById('status').textContent='Row updated';});});
document.getElementById('add').addEventListener('click',function(){
  document.getElementById('status').textContent='Row added';});
</script>""")

# ── 5. Search & filters ─────────────────────────────────────────────────────--
SEARCH = _p("Search", """
<header><h1>Catalog Search</h1></header>
<main>
  <form id="search-form" role="search">
    <input id="q" name="q" type="search" data-testid="q" placeholder="Search products"/>
    <select id="cat" name="cat" data-testid="cat" class="filter">
      <option value="">All</option><option value="books">Books</option><option value="toys">Toys</option>
    </select>
    <button id="go" data-testid="go" type="submit">Search</button>
  </form>
  <ul id="results">
    <li data-item="books">The Book</li><li data-item="toys">The Toy</li><li data-item="books">Another Book</li>
  </ul>
  <div id="count" role="status"></div>
</main>
<script>
function apply(){
  var q=document.getElementById('q').value.toLowerCase();
  var cat=document.getElementById('cat').value; var n=0;
  document.querySelectorAll('#results li').forEach(function(li){
    var ok=(!q||li.textContent.toLowerCase().indexOf(q)>=0)&&(!cat||li.dataset.item===cat);
    li.style.display=ok?'':'none'; if(ok)n++;});
  document.getElementById('count').textContent=n+' results';}
document.getElementById('search-form').addEventListener('submit',function(e){e.preventDefault();apply();});
document.getElementById('cat').addEventListener('change',apply);
</script>""")

# ── 6. File upload ──────────────────────────────────────────────────────────--
UPLOAD = _p("Upload", """
<header><h1>Upload</h1></header>
<main>
  <input id="file" type="file" data-testid="file"/>
  <div id="fname" role="status"></div>
</main>
<script>
document.getElementById('file').addEventListener('change',function(e){
  document.getElementById('fname').textContent='Uploaded: '+(e.target.files[0]?e.target.files[0].name:'');});
</script>""")

# ── 7. File download ────────────────────────────────────────────────────────--
DOWNLOAD = _p("Download", """
<header><h1>Reports</h1></header>
<main><a id="dl" data-testid="dl" href="/download-file" download="report.txt">Download Report</a></main>""")
DOWNLOAD_BODY = b"phase-f-certification-report-payload"

# ── 8. Pagination ───────────────────────────────────────────────────────────--
PAGINATION = _p("Pagination", """
<header><h1>Paged List</h1></header>
<main>
  <ul id="page-items"><li>Item A</li><li>Item B</li></ul>
  <nav class="pagination" aria-label="Pagination">
    <a id="prev" data-testid="prev" href="#">Prev</a>
    <a id="p1" href="#">1</a><a id="p2" data-testid="p2" href="#">2</a>
    <a id="next" data-testid="next" href="#">Next</a>
  </nav>
  <div id="page" role="status">page 1</div>
</main>
<script>
document.getElementById('next').addEventListener('click',function(e){
  e.preventDefault();
  document.getElementById('page-items').innerHTML='<li>Item C</li><li>Item D</li>';
  document.getElementById('page').textContent='page 2';});
</script>""")

# ── 9. Modal dialog ─────────────────────────────────────────────────────────--
MODAL = _p("Modal", """
<header><h1>Settings</h1></header>
<main>
  <button id="open" data-testid="open">Open Modal</button>
  <div id="modal" class="modal" role="dialog" aria-modal="true" aria-label="Edit Setting" style="display:none">
    <h2>Edit Setting</h2>
    <input id="setting" data-testid="setting" value="on"/>
    <button id="save" data-testid="save">Save</button>
    <button id="close" data-testid="close">Close</button>
  </div>
  <div id="modal-status" role="status"></div>
</main>
<script>
document.getElementById('open').addEventListener('click',function(){
  document.getElementById('modal').style.display='block';});
document.getElementById('save').addEventListener('click',function(){
  document.getElementById('modal-status').textContent='Setting saved';
  document.getElementById('modal').style.display='none';});
document.getElementById('close').addEventListener('click',function(){
  document.getElementById('modal').style.display='none';});
</script>""")

# ── 10. Multi-step form ─────────────────────────────────────────────────────--
MULTISTEP = _p("Wizard", """
<header><h1>Onboarding Wizard</h1></header>
<main>
  <form id="wizard">
    <fieldset id="s1"><legend>Step 1</legend>
      <label for="fullname">Full name</label>
      <input id="fullname" data-testid="fullname" name="fullname"/>
      <button id="next1" data-testid="next1" type="button">Next</button>
    </fieldset>
    <fieldset id="s2" style="display:none"><legend>Step 2</legend>
      <label for="role">Role</label>
      <input id="role" data-testid="role" name="role"/>
      <button id="finish" data-testid="finish" type="button">Finish</button>
    </fieldset>
  </form>
  <div id="wizard-status" role="status"></div>
</main>
<script>
document.getElementById('next1').addEventListener('click',function(){
  document.getElementById('s1').style.display='none';
  document.getElementById('s2').style.display='block';});
document.getElementById('finish').addEventListener('click',function(){
  document.getElementById('wizard-status').textContent='Onboarding complete';});
</script>""")

# ── 11. Infinite scroll ─────────────────────────────────────────────────────--
SCROLL = _p("Feed", """
<header><h1>Feed</h1></header>
<main>
  <ul id="feed"><li>post 1</li><li>post 2</li><li>post 3</li></ul>
  <div id="sentinel" style="height:20px"></div>
  <button id="more" data-testid="more">Load more</button>
  <div id="feed-status" role="status">3 posts</div>
</main>
<script>
var n=3;
document.getElementById('more').addEventListener('click',function(){
  for(var i=0;i<3;i++){var li=document.createElement('li');n++;li.textContent='post '+n;
    document.getElementById('feed').appendChild(li);}
  document.getElementById('feed-status').textContent=n+' posts';});
</script>""")

# ── 12. Nested navigation ───────────────────────────────────────────────────--
NAV = _p("Docs", """
<header><h1>Docs</h1></header>
<nav aria-label="Primary"><ul>
  <li><a href="/dashboard" data-testid="nav-home">Home</a></li>
  <li><a href="#guides" data-testid="nav-guides">Guides</a>
    <ul><li><a href="#install" data-testid="nav-install">Install</a></li>
        <li><a href="#config">Config</a></li></ul></li>
  <li><a href="#api">API</a></li>
</ul></nav>
<main><div id="content" role="status">Home content</div></main>
<script>
document.querySelectorAll('nav a').forEach(function(a){
  a.addEventListener('click',function(e){
    document.getElementById('content').textContent=a.textContent+' content';});});
</script>""")

# ── 13. Tabs ────────────────────────────────────────────────────────────────--
TABS = _p("Tabs", """
<header><h1>Account</h1></header>
<main>
  <div role="tablist">
    <button role="tab" id="tab-profile" data-testid="tab-profile" aria-selected="true">Profile</button>
    <button role="tab" id="tab-billing" data-testid="tab-billing" aria-selected="false">Billing</button>
  </div>
  <div id="panel" role="status">Profile panel</div>
</main>
<script>
document.getElementById('tab-billing').addEventListener('click',function(){
  document.getElementById('panel').textContent='Billing panel';});
</script>""")

# ── 14. Accordion ───────────────────────────────────────────────────────────--
ACCORDION = _p("FAQ", """
<header><h1>FAQ</h1></header>
<main class="accordion">
  <details id="q1"><summary data-testid="q1">What is it?</summary><p>An assistant.</p></details>
  <details id="q2"><summary data-testid="q2">How much?</summary><p id="a2">Free.</p></details>
</main>
<div id="acc-status" role="status"></div>
<script>
document.getElementById('q2').addEventListener('toggle',function(){
  if(this.open)document.getElementById('acc-status').textContent='q2 expanded';});
</script>""")

# ── 15. Dynamic loading (late element) ───────────────────────────────────────-
DYNAMIC = _p("Dynamic", """
<header><h1>Dynamic</h1></header>
<main>
  <div id="slot"></div>
  <div id="loading">Loading...</div>
</main>
<script>
setTimeout(function(){
  var b=document.createElement('button');
  b.id='ready';b.setAttribute('data-testid','ready');b.textContent='Ready';
  b.addEventListener('click',function(){document.getElementById('loading').textContent='Loaded';});
  document.getElementById('slot').appendChild(b);
  document.getElementById('loading').textContent='';},500);
</script>""")

# ── 16. Toast notifications ──────────────────────────────────────────────────-
TOAST = _p("Toast", """
<header><h1>Toasts</h1></header>
<main>
  <button id="trigger" data-testid="trigger">Save</button>
  <div id="toast-zone"></div>
</main>
<script>
document.getElementById('trigger').addEventListener('click',function(){
  var t=document.createElement('div');t.className='toast';t.setAttribute('role','status');
  t.textContent='Saved successfully';document.getElementById('toast-zone').appendChild(t);});
</script>""")

# ── 17. Confirmation dialog ─────────────────────────────────────────────────--
CONFIRM = _p("Confirm", """
<header><h1>Delete Item</h1></header>
<main>
  <button id="delete" data-testid="delete">Delete</button>
  <div id="confirm" class="modal" role="alertdialog" aria-label="Confirm delete" style="display:none">
    <p>Are you sure?</p>
    <button id="yes" data-testid="yes">Yes</button>
    <button id="no" data-testid="no">No</button>
  </div>
  <div id="confirm-status" role="status"></div>
</main>
<script>
document.getElementById('delete').addEventListener('click',function(){
  document.getElementById('confirm').style.display='block';});
document.getElementById('yes').addEventListener('click',function(){
  document.getElementById('confirm-status').textContent='Item deleted';
  document.getElementById('confirm').style.display='none';});
document.getElementById('no').addEventListener('click',function(){
  document.getElementById('confirm').style.display='none';});
</script>""")

# ── 18. Drag-and-drop placeholder (analysis only) ────────────────────────────-
DRAGDROP = _p("Board", """
<header><h1>Board</h1></header>
<main>
  <div id="drag" data-testid="drag" draggable="true" class="card">Card 1</div>
  <div id="drop" data-testid="drop" class="dropzone">Drop here</div>
  <div id="dd-status" role="status">analysis-only</div>
</main>""")


INVOICE = _p("Invoice Details", """
<header><h1>Invoice INV-2026-0711</h1></header>
<main>
  <section aria-labelledby="summary-heading">
    <h2 id="summary-heading">Billing Summary</h2>
    <dl>
      <dt>Invoice Number</dt><dd>INV-2026-0711</dd>
      <dt>Customer</dt><dd>Acme Supplies</dd>
      <dt>Invoice Date</dt><dd>July 11, 2026</dd>
      <dt>Status</dt><dd>Due</dd>
      <dt>Subtotal</dt><dd>INR 12,400.00</dd>
      <dt>Tax</dt><dd>INR 2,232.00</dd>
      <dt>Total Due</dt><dd id="invoice-total" data-testid="invoice-total">INR 14,632.00</dd>
      <dt>Payment Terms</dt><dd>Net 15</dd>
    </dl>
  </section>
  <button id="download-pdf" data-testid="download-pdf">Download PDF</button>
  <button id="print" data-testid="print">Print</button>
  <button id="pay-invoice" data-testid="pay-invoice">Pay Invoice</button>
</main>""")


FIXTURES: dict[str, str] = {
    "/login":      LOGIN,
    "/register":   REGISTER,
    "/dashboard":  DASHBOARD,
    "/crud":       CRUD,
    "/search":     SEARCH,
    "/upload":     UPLOAD,
    "/download":   DOWNLOAD,
    "/pagination": PAGINATION,
    "/modal":      MODAL,
    "/multistep":  MULTISTEP,
    "/scroll":     SCROLL,
    "/nav":        NAV,
    "/tabs":       TABS,
    "/accordion":  ACCORDION,
    "/dynamic":    DYNAMIC,
    "/toast":      TOAST,
    "/confirm":    CONFIRM,
    "/dragdrop":   DRAGDROP,
    "/invoice":    INVOICE,
}


def fixture_names() -> list[str]:
    return sorted(FIXTURES.keys())


def fixture_html(path: str) -> Optional[str]:
    return FIXTURES.get(path if path.startswith("/") else "/" + path)


# ── Local fixture HTTP server (loopback, offline) ─────────────────────────────

def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _make_handler():
    class _Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            path = self.path.split("?")[0]
            if path.startswith("/download-file"):
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Content-Disposition", 'attachment; filename="report.txt"')
                self.send_header("Content-Length", str(len(DOWNLOAD_BODY)))
                self.end_headers()
                self.wfile.write(DOWNLOAD_BODY)
                return
            html = FIXTURES.get(path)
            if html is None:
                html = FIXTURES["/dashboard"]
            body = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):  # silence
            pass

    return _Handler


class FixtureServer:
    """Loopback HTTP server serving the certification fixtures. Context-manager."""

    def __init__(self) -> None:
        self.port: int = 0
        self.base_url: str = ""
        self._httpd: Optional[socketserver.TCPServer] = None
        self._thread: Optional[threading.Thread] = None

    def start(self) -> "FixtureServer":
        self.port = _free_port()
        self._httpd = socketserver.TCPServer(("127.0.0.1", self.port), _make_handler())
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        self.base_url = f"http://127.0.0.1:{self.port}"
        return self

    def stop(self) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None

    def __enter__(self) -> "FixtureServer":
        return self.start()

    def __exit__(self, *exc) -> None:
        self.stop()
