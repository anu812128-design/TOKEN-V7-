from flask import Flask, request, render_template_string, jsonify
import requests
import uuid
import time
import base64
import io
import struct
import random
import string
from threading import Thread, Event
from Crypto.Cipher import AES, PKCS1_v1_5
from Crypto.PublicKey import RSA
from Crypto.Random import get_random_bytes
import os

app = Flask(__name__)

# ==========================================
# 1. FACEBOOK ENCRYPTION & TOKEN LOGIC
# ==========================================
class FacebookPasswordEncryptor:
    @staticmethod
    def get_public_key():
        try:
            url = 'https://b-graph.facebook.com/pwd_key_fetch'
            params = {
                'version': '2', 'flow': 'CONTROLLER_INITIALIZATION', 'method': 'GET',
                'fb_api_req_friendly_name': 'pwdKeyFetch', 'fb_api_caller_class': 'com.facebook.auth.login.AuthOperations',
                'access_token': '350685531728|62f8ce9f74b12f84c123cc23437a4a32'
            }
            response = requests.post(url, params=params).json()
            return response.get('public_key'), str(response.get('key_id', '25'))
        except Exception:
            return None, "25"

    @staticmethod
    def encrypt(password, public_key=None, key_id="25"):
        if public_key is None:
            public_key, key_id = FacebookPasswordEncryptor.get_public_key()
            if public_key is None: return password
        try:
            rand_key = get_random_bytes(32)
            iv = get_random_bytes(12)
            pubkey = RSA.import_key(public_key)
            cipher_rsa = PKCS1_v1_5.new(pubkey)
            encrypted_rand_key = cipher_rsa.encrypt(rand_key)
            cipher_aes = AES.new(rand_key, AES.MODE_GCM, nonce=iv)
            current_time = int(time.time())
            cipher_aes.update(str(current_time).encode("utf-8"))
            encrypted_passwd, auth_tag = cipher_aes.encrypt_and_digest(password.encode("utf-8"))
            buf = io.BytesIO()
            buf.write(bytes([1, int(key_id)]))
            buf.write(iv)
            buf.write(struct.pack("<h", len(encrypted_rand_key)))
            buf.write(encrypted_rand_key)
            buf.write(auth_tag)
            buf.write(encrypted_passwd)
            encoded = base64.b64encode(buf.getvalue()).decode("utf-8")
            return f"#PWD_FB4A:2:{current_time}:{encoded}"
        except:
            return password

sessions_data = {}

def get_all_tokens(master_token):
    tokens_dict = {}
    tokens_dict['Master Token (EAAG)'] = master_token
    app_ids = {
        'Pages Manager (EAAB)': '165907476854626',   
        'Instagram (EAAI)': '124024574287414',       
        'Lite / E7 Token (EAADV)': '275254692598279' 
    }
    for name, app_id in app_ids.items():
        try:
            res = requests.get(f"https://api.facebook.com/method/auth.getSessionforApp?access_token={master_token}&format=json&new_app_id={app_id}&generate_session_cookies=1").json()
            if 'access_token' in res:
                tokens_dict[name] = res['access_token']
            else:
                res_post = requests.post('https://api.facebook.com/method/auth.getSessionforApp', data={'access_token': master_token, 'format': 'json', 'new_app_id': app_id, 'generate_session_cookies': '1'}).json()
                if 'access_token' in res_post:
                    tokens_dict[name] = res_post['access_token']
                # Agar nahi nikla toh dictionary me add hi nahi hoga (HIDE ho jayega)
        except Exception:
            pass
    return tokens_dict

# ==========================================
# 2. ANTI-BAN MESSAGE SENDER LOGIC
# ==========================================
tasks = {}

def send_messages(task_id, access_tokens, thread_id, messages, speed, hater_name):
    task = tasks.get(task_id)
    if not task: return

    # Multiple Real User-Agents to prevent Ban
    user_agents = [
        'Mozilla/5.0 (Linux; Android 13; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Mobile Safari/537.36',
        'Mozilla/5.0 (Linux; Android 12; Pixel 6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Mobile Safari/537.36',
        'Mozilla/5.0 (Linux; Android 11; TECNO CE7j) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/101.0.4951.40 Mobile Safari/537.36',
        'Mozilla/5.0 (iPhone; CPU iPhone OS 16_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.3 Mobile/15E148 Safari/604.1'
    ]

    while not task['stop_event'].is_set():
        for message in messages:
            if task['stop_event'].is_set(): break
            
            for token in access_tokens:
                if task['stop_event'].is_set(): break
                
                full_message = f"{hater_name} {message}"
                url = f"https://graph.facebook.com/v15.0/t_{thread_id}"
                parameters = {'access_token': token, 'message': full_message}
                headers = {
                    'User-Agent': random.choice(user_agents),
                    'Accept': 'application/json'
                }
                
                try:
                    response = requests.post(url, data=parameters, headers=headers)
                    if response.status_code == 200:
                        print(f"[{task_id}] Success: {full_message}")
                    else:
                        print(f"[{task_id}] Failed (Status {response.status_code})")
                except Exception as e:
                    print(f"[{task_id}] Error: {e}")
                
                # Human Jitter Delay (Base Speed + Random 0.5 to 1.5 seconds)
                # Ye account block hone se bachayega
                jitter = random.uniform(0.5, 1.5)
                time.sleep(speed + jitter)

# ==========================================
# 3. ROUTES & INLINE HTML UI (2-IN-1)
# ==========================================

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ANURAG MISHRA 2-IN-1 PANNEL</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;600;800&display=swap" rel="stylesheet">
    <style>
        body {
            background: #0f172a; color: #f1f5f9; font-family: 'Poppins', sans-serif;
            min-height: 100vh; padding: 20px;
        }
        .main-container {
            max-width: 550px; margin: 0 auto;
        }
        h1.main-title {
            text-align: center; font-weight: 800; font-size: 32px;
            background: linear-gradient(90deg, #00d2ff 0%, #3a7bd5 100%);
            -webkit-background-clip: text; -webkit-text-fill-color: transparent;
            margin-bottom: 5px; text-transform: uppercase;
        }
        p.subtitle { text-align: center; color: #94a3b8; font-size: 14px; margin-bottom: 25px; }
        
        .nav-tabs { border-bottom: 1px solid rgba(255,255,255,0.1); margin-bottom: 20px; }
        .nav-tabs .nav-link { 
            color: #94a3b8; font-weight: 600; border: none; background: transparent; padding: 12px 20px; border-radius: 10px 10px 0 0;
        }
        .nav-tabs .nav-link.active {
            color: #fff; background: rgba(30, 41, 59, 0.9); border-bottom: 3px solid #00d2ff;
        }
        
        .main-card {
            background: rgba(30, 41, 59, 0.8); backdrop-filter: blur(15px);
            border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 0 0 20px 20px;
            padding: 30px; box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
        }
        .form-label { font-weight: 600; color: #cbd5e1; font-size: 13px; margin-bottom: 5px; }
        .form-control, .form-select {
            background: rgba(15, 23, 42, 0.6); border: 1px solid rgba(255, 255, 255, 0.1);
            color: #fff; border-radius: 10px; padding: 12px; font-size: 14px; margin-bottom: 15px;
        }
        .form-control:focus, .form-select:focus {
            background: rgba(15, 23, 42, 0.9); border-color: #3a7bd5; color: #fff; box-shadow: none;
        }
        
        /* Buttons */
        .btn-gradient {
            background: linear-gradient(90deg, #3a7bd5 0%, #00d2ff 100%);
            border: none; border-radius: 10px; padding: 12px; font-weight: 700; color: white; width: 100%; transition: 0.3s;
        }
        .btn-gradient:hover { transform: translateY(-2px); box-shadow: 0 8px 15px rgba(0, 210, 255, 0.3); color: white; }
        
        .btn-stop { background: #ef4444; color: white; border: none; font-weight: 700; border-radius: 0 10px 10px 0; }
        
        /* Token Box */
        .token-item { background: #0f172a; border-radius: 10px; padding: 15px; margin-bottom: 15px; border: 1px solid #334155; }
        .token-item label { color: #00d2ff; font-weight: 600; font-size: 13px; }
        .token-item textarea { width: 100%; background: transparent; color: #fff; border: none; font-family: monospace; font-size: 11px; resize: none; height: 60px; outline: none; }
        .btn-copy { background: #10b981; color: white; font-size: 12px; padding: 6px 12px; border-radius: 6px; border: none; font-weight: 600; }
        
        .whatsapp-btn {
            background: #25D366; color: white; border-radius: 50px; padding: 10px 25px;
            text-decoration: none; display: flex; align-items: center; justify-content: center; gap: 8px;
            font-weight: 600; margin-top: 25px; transition: 0.3s;
        }
        .whatsapp-btn:hover { background: #128C7E; color: white; transform: translateY(-2px); }
        .hidden { display: none !important; }
        .error-text { color: #ef4444; font-size: 13px; font-weight: 600; margin-top: 10px; text-align: center; }
    </style>
</head>
<body>

<div class="main-container">
    <h1 class="main-title">ANURAG MISHRA</h1>
    <p class="subtitle">Ultimate Token Extractor & Convo Server</p>

    <ul class="nav nav-tabs" id="myTab" role="tablist">
        <li class="nav-item" role="presentation">
            <button class="nav-link active" id="extractor-tab" data-bs-toggle="tab" data-bs-target="#extractor" type="button" role="tab">1. Token Extractor</button>
        </li>
        <li class="nav-item" role="presentation">
            <button class="nav-link" id="server-tab" data-bs-toggle="tab" data-bs-target="#server" type="button" role="tab">2. Message Server</button>
        </li>
    </ul>

    <div class="tab-content main-card">
        
        <div class="tab-pane fade show active" id="extractor" role="tabpanel">
            <form id="loginForm">
                <label class="form-label">Facebook ID / Email / Number</label>
                <input type="text" id="uid" name="uid" class="form-control" placeholder="Enter FB ID" required>
                
                <label class="form-label">Password</label>
                <input type="password" id="password" name="password" class="form-control" placeholder="Enter Password" required>
                
                <button type="submit" id="extBtn" class="btn-gradient"><i class="fas fa-key"></i> Extract Tokens</button>
            </form>

            <form id="twoFactorForm" class="hidden mt-3">
                <label class="form-label" style="color: #f59e0b;"><i class="fas fa-lock"></i> 2FA Code Required</label>
                <input type="text" id="otp" name="otp" class="form-control" placeholder="Enter 6-digit OTP" required>
                <button type="submit" id="otpBtn" class="btn-gradient">Verify & Extract</button>
            </form>

            <div id="extError" class="error-text"></div>

            <div id="tokenResultBox" class="hidden mt-4">
                <div id="tokensContainer" style="max-height: 300px; overflow-y: auto;"></div>
                <button class="btn btn-secondary w-100 mt-2" onclick="resetExtForm()">Extract Another</button>
            </div>
        </div>

        <div class="tab-pane fade" id="server" role="tabpanel">
            <form id="taskForm" enctype="multipart/form-data">
                <label class="form-label">Token Method</label>
                <select class="form-select" name="token_type" id="tokenType">
                    <option value="single">Paste Single Token</option>
                    <option value="multi">Upload Tokens File (.txt)</option>
                </select>
                
                <div id="singleTokenBox">
                    <label class="form-label">Access Token</label>
                    <input type="text" class="form-control" name="single_token" placeholder="EAAG... / EAAB...">
                </div>
                
                <div id="multiTokenBox" class="hidden">
                    <label class="form-label">Upload Tokens (.txt)</label>
                    <input type="file" class="form-control" name="token_file" accept=".txt">
                </div>
                
                <label class="form-label">Hater Name</label>
                <input type="text" class="form-control" name="hater_name" placeholder="Enter Hater Name" required>

                <label class="form-label">Target Thread ID (UID / Group ID)</label>
                <input type="text" class="form-control" name="thread_id" placeholder="Enter Target ID" required>
                
                <label class="form-label">Base Speed (Seconds)</label>
                <input type="number" class="form-control" name="speed" value="5" min="1" required>
                <small style="color:#64748b; display:block; margin-top:-10px; margin-bottom:15px; font-size:11px;">Anti-ban random jitter will be auto-added.</small>
                
                <label class="form-label">Upload Messages File (.txt)</label>
                <input type="file" class="form-control" name="msg_file" accept=".txt" required>
                
                <button type="submit" id="serverBtn" class="btn-gradient"><i class="fas fa-paper-plane"></i> START SERVER</button>
            </form>
            
            <hr style="border-color: rgba(255,255,255,0.1); margin: 25px 0;">
            
            <label class="form-label">Stop Running Task</label>
            <div class="input-group">
                <input type="text" id="stopTaskId" class="form-control" style="margin-bottom:0; border-radius: 10px 0 0 10px;" placeholder="Enter Task ID">
                <button onclick="stopTask()" class="btn btn-stop">STOP</button>
            </div>
            
            <div id="serverStatus" class="mt-3 text-center" style="color: #10b981; font-weight: 600;"></div>
        </div>
    </div>

    <a href="https://wa.me/916394812128" target="_blank" class="whatsapp-btn">
        <i class="fab fa-whatsapp" style="font-size: 20px;"></i> CONTACT OWNER
    </a>
</div>

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
<script>
    // --- TAB 1: EXTRACTOR LOGIC ---
    let currentSessionId = "";

    document.getElementById('loginForm').addEventListener('submit', async (e) => {
        e.preventDefault();
        submitExtData('/login', new FormData(document.getElementById('loginForm')), 'extBtn', 'Extract Tokens');
    });

    document.getElementById('twoFactorForm').addEventListener('submit', async (e) => {
        e.preventDefault();
        const fd = new FormData();
        fd.append('session_id', currentSessionId); fd.append('otp', document.getElementById('otp').value);
        submitExtData('/two_factor', fd, 'otpBtn', 'Verify & Extract');
    });

    async function submitExtData(endpoint, formData, btnId, originalText) {
        const btn = document.getElementById(btnId);
        const errBox = document.getElementById('extError');
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Processing...';
        btn.disabled = true; errBox.innerText = "";

        try {
            const res = await fetch(endpoint, { method: 'POST', body: formData });
            const data = await res.json();

            if (data.tokens) {
                renderTokens(data.tokens);
                document.getElementById('loginForm').classList.add('hidden');
                document.getElementById('twoFactorForm').classList.add('hidden');
                document.getElementById('tokenResultBox').classList.remove('hidden');
            } else if (data.two_factor) {
                currentSessionId = data.session_id;
                document.getElementById('loginForm').classList.add('hidden');
                document.getElementById('twoFactorForm').classList.remove('hidden');
            } else {
                errBox.innerText = data.error || "Failed!";
            }
        } catch (err) {
            errBox.innerText = "Server Error!";
        }
        btn.innerHTML = originalText; btn.disabled = false;
    }

    function renderTokens(tokensObj) {
        const container = document.getElementById('tokensContainer');
        container.innerHTML = ''; 
        let c = 1;
        for (const [name, val] of Object.entries(tokensObj)) {
            // Error hide logic implementation in UI side as well
            if (val.startsWith('Error')) continue; 
            
            const shortName = name.split(' ')[0];
            const div = document.createElement('div');
            div.className = 'token-item';
            div.innerHTML = `
                <div class="d-flex justify-content-between align-items-center mb-1">
                    <label>${name}</label>
                    <button class="btn-copy" onclick="copyTk('t_${c}', this, '${shortName}')"><i class="fas fa-copy"></i> Copy</button>
                </div>
                <textarea id="t_${c}" readonly spellcheck="false">${val}</textarea>
            `;
            container.appendChild(div);
            c++;
        }
        if(container.innerHTML === '') {
            container.innerHTML = '<p class="text-center text-warning" style="font-size:13px;">No tokens successfully generated. FB blocked token creation for this account.</p>';
        }
    }

    function copyTk(id, btn, name) {
        document.getElementById(id).select();
        document.execCommand("copy");
        btn.innerHTML = '<i class="fas fa-check"></i> Copied';
        btn.style.background = '#059669';
        setTimeout(() => { btn.innerHTML = '<i class="fas fa-copy"></i> Copy'; btn.style.background = '#10b981'; }, 2000);
    }

    function resetExtForm() {
        document.getElementById('loginForm').reset();
        document.getElementById('twoFactorForm').reset();
        document.getElementById('tokenResultBox').classList.add('hidden');
        document.getElementById('loginForm').classList.remove('hidden');
        currentSessionId = "";
    }

    // --- TAB 2: SERVER LOGIC ---
    document.getElementById('tokenType').addEventListener('change', function() {
        if(this.value === 'single') {
            document.getElementById('singleTokenBox').classList.remove('hidden');
            document.getElementById('multiTokenBox').classList.add('hidden');
        } else {
            document.getElementById('singleTokenBox').classList.add('hidden');
            document.getElementById('multiTokenBox').classList.remove('hidden');
        }
    });

    document.getElementById('taskForm').onsubmit = async (e) => {
        e.preventDefault();
        const btn = document.getElementById('serverBtn');
        const status = document.getElementById('serverStatus');
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Starting...'; btn.disabled = true;
        
        try {
            const res = await fetch('/start', { method: 'POST', body: new FormData(e.target) });
            const data = await res.json();
            if (data.success) {
                status.innerHTML = `✅ TASK STARTED!<br>Save this ID to stop later: <strong style="color:#00d2ff; font-size:18px;">${data.task_id}</strong>`;
                e.target.reset(); // clear form
            } else {
                status.innerHTML = `<span style="color:#ef4444;">Error: ${data.message}</span>`;
            }
        } catch (err) {
            status.innerHTML = `<span style="color:#ef4444;">Request failed!</span>`;
        }
        btn.innerHTML = '<i class="fas fa-paper-plane"></i> START SERVER'; btn.disabled = false;
    };

    async function stopTask() {
        const tId = document.getElementById('stopTaskId').value;
        const status = document.getElementById('serverStatus');
        if(!tId) return alert("Please enter Task ID");
        
        try {
            const res = await fetch('/stop', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({task_id: tId})
            });
            const data = await res.json();
            if(data.success) status.innerHTML = `<span style="color:#ef4444;">🛑 ${data.message}</span>`;
            else status.innerHTML = `<span style="color:#ef4444;">Error: ${data.message}</span>`;
        } catch (err) {
            status.innerHTML = `<span style="color:#ef4444;">Stop request failed.</span>`;
        }
    }
</script>
</body>
</html>
'''

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

# --- EXTRACTOR ROUTES ---
@app.route('/login', methods=['POST'])
def login():
    try:
        uid = request.form.get('uid')
        password = request.form.get('password')
        if not uid or not password: return jsonify({'error': 'Email and Password are required'})
        
        enc_pw = FacebookPasswordEncryptor.encrypt(password)
        adid, dev_id, fam_id = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
        client_ip = request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0].strip()

        headers = {
            "Authorization": "OAuth 350685531728|62f8ce9f74b12f84c123cc23437a4a32",
            "X-FB-Connection-Quality": "EXCELLENT", "X-FB-Connection-Type": "WIFI",
            "X-FB-SIM-HNI": "310260", "X-FB-Net-HNI": "310260", "X-Forwarded-For": client_ip,
            "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 13; SM-S918B Build/TP1A.220624.014) [FBAN/FB4A;FBAV/473.0.0.45.85;FBPN/com.facebook.katana;FBLC/en_US;FBBV/615875241;FBCR/T-Mobile;FBMF/samsung;FBBD/samsung;FBDV/SM-S918B;FBSV/13;FBCA/arm64-v8a:null;FBDM/{density=3.0,width=1080,height=2340};FB_FW/1;FBRV/0;]",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        data = {
            "adid": adid, "format": "json", "device_id": dev_id, "email": uid,
            "password": enc_pw, "generate_analytics_claim": "1", "cpl": "true", "try_num": "1", "family_device_id": fam_id,
            "credentials_type": "password", "source": "login", "error_detail_type": "button_with_disabled",
            "enroll_misauth": "false", "generate_session_cookies": "1", "generate_machine_id": "1",
            "currently_logged_in_userid": "0", "fb_api_req_friendly_name": "authenticate", "locale": "en_US", "client_country_code": "US",
        }
        res_data = requests.post("https://b-graph.facebook.com/auth/login", headers=headers, data=data).json()
        
        if 'access_token' in res_data:
            return jsonify({'success': True, 'tokens': get_all_tokens(res_data['access_token'])})
        if 'error' in res_data:
            err = res_data['error']
            if 'abusive' in err.get('message', '').lower(): return jsonify({'error': 'Server IP flagged. Try later.'})
            if 'approval' in err.get('message', '').lower() or err.get('code') == 459 or 'login_first_factor' in err.get('error_data', {}):
                sid = str(uuid.uuid4())
                sessions_data[sid] = {'uid': uid, 'err_data': err.get('error_data', {}), 'headers': headers, 'data': data}
                return jsonify({'two_factor': True, 'session_id': sid})
            return jsonify({'error': err.get('message', 'Login failed')})
    except Exception as e: return jsonify({'error': str(e)})

@app.route('/two_factor', methods=['POST'])
def two_factor():
    try:
        sid = request.form.get('session_id')
        otp = request.form.get('otp')
        if not sid or sid not in sessions_data: return jsonify({'error': 'Session expired. Refresh.'})
        
        s = sessions_data[sid]
        s['data']['twofactor_code'] = otp
        s['data']['userid'] = s.get('uid', '')
        s['data']['credentials_type'] = 'two_factor'
        if isinstance(s.get('err_data'), dict) and s['err_data'].get('login_first_factor'):
            s['data']['first_factor'] = s['data']['machine_id'] = s['err_data']['login_first_factor']
            
        res_data = requests.post("https://b-graph.facebook.com/auth/login", headers=s['headers'], data=s['data']).json()
        if 'access_token' in res_data:
            return jsonify({'success': True, 'tokens': get_all_tokens(res_data['access_token'])})
        return jsonify({'error': res_data.get('error', {}).get('message', '2FA failed! Invalid OTP.')})
    except Exception as e: return jsonify({'error': str(e)})


# --- SERVER ROUTES ---
@app.route('/start', methods=['POST'])
def start_task():
    try:
        token_type = request.form.get('token_type')
        thread_id = request.form.get('thread_id')
        speed = float(request.form.get('speed', 5))
        hater_name = request.form.get('hater_name', '')
        
        if token_type == 'single':
            single_token = request.form.get('single_token')
            if not single_token: return jsonify({'success': False, 'message': 'Token is required'})
            tokens = [single_token]
        else:
            token_file = request.files.get('token_file')
            if not token_file: return jsonify({'success': False, 'message': 'Token file is required'})
            tokens = token_file.read().decode().splitlines()
        
        msg_file = request.files.get('msg_file')
        if not msg_file: return jsonify({'success': False, 'message': 'Message file is required'})
        messages = msg_file.read().decode().splitlines()
        
        task_id = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        stop_event = Event()
        
        tasks[task_id] = {
            'stop_event': stop_event,
            'thread': Thread(target=send_messages, args=(task_id, tokens, thread_id, messages, speed, hater_name))
        }
        tasks[task_id]['thread'].start()
        
        return jsonify({'success': True, 'task_id': task_id})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/stop', methods=['POST'])
def stop_task():
    task_id = request.get_json().get('task_id')
    if task_id in tasks:
        tasks[task_id]['stop_event'].set()
        return jsonify({'success': True, 'message': f"Task {task_id} stopped successfully."})
    return jsonify({'success': False, 'message': "Invalid Task ID or Task already stopped."})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
