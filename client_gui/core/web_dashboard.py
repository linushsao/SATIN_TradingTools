# ==============================================================================
# web_dashboard.py
#
# Version: V0.6-002 (Secure Production)
# 更新日期: 2025-11-30
# 描述:     輕量級網頁儀表板 (Production Mode)。
#           整合 Waitress WSGI 與 Basic Auth 驗證。
# ==============================================================================

import json
import zmq
import datetime
import os
from functools import wraps
from flask import Flask, render_template_string, request, redirect, url_for, flash, Response
from waitress import serve
from config_manager import load_config

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Load Config
config = load_config()
web_conf = config.get('web_dashboard', {})
WEB_USER = web_conf.get('username', 'admin')
WEB_PASS = web_conf.get('password', 'admin')
BIND_HOST = web_conf.get('host', '127.0.0.1') # 預設只聽本機，由 Caddy 轉發
BIND_PORT = int(web_conf.get('port', 8000))

# ZMQ Config
ZMQ_HOST = "127.0.0.1"
ZMQ_PORT = 5557
ZMQ_TIMEOUT = 2000 

# --- Auth Helper ---
def check_auth(username, password):
    """Check if a username/password combination is valid."""
    return username == WEB_USER and password == WEB_PASS

def authenticate():
    """Sends a 401 response that enables basic auth"""
    return Response(
    'Could not verify your access level for that URL.\n'
    'You have to login with proper credentials', 401,
    {'WWW-Authenticate': 'Basic realm="Login Required"'})

def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated

# --- ZMQ Helper ---
def send_zmq_command(cmd, args=None):
    context = zmq.Context()
    socket = context.socket(zmq.REQ)
    socket.setsockopt(zmq.RCVTIMEO, ZMQ_TIMEOUT)
    socket.setsockopt(zmq.LINGER, 0)
    try:
        socket.connect(f"tcp://{ZMQ_HOST}:{ZMQ_PORT}")
        socket.send_json({"cmd": cmd, "args": args or {}})
        return socket.recv_json()
    except zmq.error.Again: return {"status": "error", "msg": "Timeout"}
    except Exception as e: return {"status": "error", "msg": str(e)}
    finally: socket.close(); context.term()

# --- HTML Template ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-Hant">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Shioaji Dashboard</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <meta http-equiv="refresh" content="10">
    <style>
        body { background-color: #f8f9fa; padding-top: 20px; }
        .status-dot { height: 12px; width: 12px; border-radius: 50%; display: inline-block; }
        .status-on { background-color: #28a745; }
        .status-off { background-color: #dc3545; }
        .card { margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .log-box { max-height: 300px; overflow-y: auto; font-family: monospace; font-size: 0.9rem; background: #fff; }
    </style>
</head>
<body>
    <div class="container">
        <nav class="navbar navbar-light bg-white rounded p-3 mb-4 border">
            <div class="container-fluid">
                <span class="navbar-brand mb-0 h1">🤖 Shioaji Dashboard</span>
                <span class="navbar-text">
                    Engine: <span class="status-dot {% if engine_online %}status-on{% else %}status-off{% endif %}"></span>
                    {{ "Connected" if engine_online else "Disconnected" }}
                    <span class="ms-2 text-muted small">Last: {{ update_time }}</span>
                </span>
                <form action="{{ url_for('restart_engine') }}" method="post" class="d-inline" onsubmit="return confirm('Restart Engine?');">
                    <button class="btn btn-outline-danger btn-sm">Restart</button>
                </form>
            </div>
        </nav>

        {% with messages = get_flashed_messages(with_categories=true) %}
          {% if messages %}
            {% for category, message in messages %}
              <div class="alert alert-{{ category }} alert-dismissible fade show">{{ message }}<button type="button" class="btn-close" data-bs-dismiss="alert"></button></div>
            {% endfor %}
          {% endif %}
        {% endwith %}

        <div class="card">
            <div class="card-header bg-dark text-white">📈 Strategy Status</div>
            <div class="card-body p-0">
                <div class="table-responsive">
                    <table class="table table-hover align-middle mb-0">
                        <thead><tr><th>ID</th><th>Status</th><th>Name</th><th>Pos</th><th>Last</th><th>PnL</th><th>Config</th><th>Action</th></tr></thead>
                        <tbody>
                            {% if strategies %}
                                {% for s in strategies %}
                                <tr>
                                    <td>{{ s.id }}</td>
                                    <td><span class="badge {% if s.running %}bg-success{% else %}bg-secondary{% endif %}">{{ "RUNNING" if s.running else "STOPPED" }}</span></td>
                                    <td><strong>{{ s.name.split('(')[0] }}</strong>{% if 'Trailing' in s.name %}<br><span class="badge bg-info text-dark">Trail</span>{% endif %}</td>
                                    <td><span class="fw-bold {{ 'text-danger' if s.pos > 0 else 'text-success' if s.pos < 0 else 'text-muted' }}">{{ s.pos }}</span></td>
                                    <td>{{ s.last }}</td>
                                    <td><span class="{{ 'text-danger' if s.pos > 0 and (s.last - s.avg_cost) > 0 else 'text-success' if s.pos < 0 and (s.avg_cost - s.last) > 0 else 'text-muted' }}">{{ (s.last - s.avg_cost)*(s.pos|abs)|int if s.pos!=0 else '-' }}</span></td>
                                    <td class="small text-muted">Entry: {{ s.entry }}<br>SL/TP: {{ s.sl }}/{{ s.tp }}</td>
                                    <td>
                                        <form action="{{ url_for('toggle_strategy', id=s.id) }}" method="post">
                                            <button class="btn btn-sm w-100 {{ 'btn-danger' if s.running else 'btn-success' }}">{{ "Stop" if s.running else "Start" }}</button>
                                        </form>
                                    </td>
                                </tr>
                                {% endfor %}
                            {% else %}<tr><td colspan="8" class="text-center text-muted">No strategies.</td></tr>{% endif %}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
        
        <div class="card">
            <div class="card-header bg-light">📜 Live Event Log</div>
            <div class="card-body log-box">
                {% if logs %}
                    <ul class="list-unstyled mb-0">
                    {% for log in logs %}
                        <li class="border-bottom py-1">{{ log }}</li>
                    {% endfor %}
                    </ul>
                {% else %}
                    <div class="text-center text-muted">No events yet.</div>
                {% endif %}
            </div>
        </div>

        <div class="text-center text-muted small mt-3">Auto-refreshing every 10s.</div>
    </div>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""

@app.route('/')
@requires_auth # 確保此行存在
def index():
    ping = send_zmq_command("PING")
    online = (ping.get('status') == 'ok')
    strategies = []
    logs = []
    accounts = []

    if online:
        s_rep = send_zmq_command("STR_STATUS")
        if s_rep.get('status') == 'ok': strategies = s_rep.get('data', [])
        l_rep = send_zmq_command("STR_GET_LOGS")
        if l_rep.get('status') == 'ok': logs = l_rep.get('data', [])
        a_rep = send_zmq_command("GET_ACCOUNTS")
        if a_rep.get('status') == 'ok': accounts = a_rep.get('data', [])

    return render_template_string(HTML_TEMPLATE, engine_online=online, update_time=datetime.datetime.now().strftime('%H:%M:%S'), strategies=strategies, logs=logs, accounts=accounts)

@app.route('/toggle/<int:id>', methods=['POST'])
@requires_auth # 確保此行存在
def toggle_strategy(id):
    rep = send_zmq_command("STR_TOGGLE", {"id": id})
    flash(f"Strategy {id}: {rep.get('msg')}", "success" if rep.get('status')=='ok' else "danger")
    return redirect(url_for('index'))

@app.route('/restart', methods=['POST'])
@requires_auth # 確保此行存在
def restart_engine():
    send_zmq_command("RESTART")
    flash("Restart command sent.", "warning")
    return redirect(url_for('index'))

if __name__ == '__main__':
    print(f"Starting Secure Web Dashboard on {BIND_HOST}:{BIND_PORT}...")
    # 使用 Waitress
    serve(app, host=BIND_HOST, port=BIND_PORT, threads=4)