from flask import Flask, request, render_template_string, jsonify
import requests, uuid, time, base64, io, struct, random, string, os, hashlib
from threading import Thread, Event
from Crypto.Cipher import AES, PKCS1_v1_5
from Crypto.PublicKey import RSA
from Crypto.Random import get_random_bytes

app = Flask(__name__)

# ==========================================
# 1. UPDATED CREDENTIALS (FROM YOUR APK)
# ==========================================
LITE_APP_ID = "275254692598279" 
LITE_API_KEY = "62f8ce9f74b12f84c123cc23437a4a32"
LITE_SECRET = "c1e620fa708a36b5b54fb9e220556f84" # Official Lite Secret

def generate_sig(data):
    """Facebook Signature Generator to bypass 2026 security"""
    sorted_data = "".join([f"{k}={v}" for k, v in sorted(data.items())])
    return hashlib.md5((sorted_data + LITE_SECRET).encode()).hexdigest()

class FacebookPasswordEncryptor:
    @staticmethod
    def get_public_key():
        try:
            url = 'https://b-graph.facebook.com/pwd_key_fetch'
            params = {'version': '2', 'access_token': f"{LITE_APP_ID}|{LITE_API_KEY}"}
            res = requests.get(url, params=params).json()
            return res.get('public_key'), str(res.get('key_id', '25'))
        except: return None, "25"

    @staticmethod
    def encrypt(password):
        pk, kid = FacebookPasswordEncryptor.get_public_key()
        if not pk: return password
        try:
            rk, iv = get_random_bytes(32), get_random_bytes(12)
            pub = RSA.import_key(pk)
            enc_rk = PKCS1_v1_5.new(pub).encrypt(rk)
            cipher = AES.new(rk, AES.MODE_GCM, nonce=iv)
            ts = int(time.time())
            cipher.update(str(ts).encode())
            enc_pw, tag = cipher.encrypt_and_digest(password.encode())
            buf = io.BytesIO()
            buf.write(bytes([1, int(kid)]))
            buf.write(iv)
            buf.write(struct.pack("<h", len(enc_rk)))
            buf.write(enc_rk)
            buf.write(tag)
            buf.write(enc_pw)
            return f"#PWD_FB4A:2:{ts}:{base64.b64encode(buf.getvalue()).decode()}"
        except: return password

# ==========================================
# 2. V7 TOKEN CONVERSION (EAADV)
# ==========================================
def get_v7_token(master_token):
    try:
        # Match User-Agent to your Build ID 917292898
        headers = {
            "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 14; SM-S918B) [FBAN/FB4A;FBAV/505.0.0.0.66;FBBV/917292898;]",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        data = {
            'access_token': master_token,
            'format': 'json',
            'new_app_id': LITE_APP_ID,
            'generate_session_cookies': '1'
        }
        res = requests.post('https://api.facebook.com/method/auth.getSessionforApp', data=data, headers=headers).json()
        return res.get('access_token', 'Conversion Failed')
    except:
        return 'Conversion Error'

# ==========================================
# 3. ROUTES & LOGIN LOGIC
# ==========================================
sessions_data = {}

@app.route('/')
def index():
    return """
    <body style="background:#0a0a0a;color:#00ff00;font-family:monospace;padding:20px;text-align:center;">
        <h2>ANURAG MISHRA V7 PRO</h2>
        <div style="border:1px solid #00ff00;padding:20px;display:inline-block;border-radius:10px;background:#111;">
            <input id="u" placeholder="Email/UID" style="width:250px;padding:10px;margin:5px;background:#000;color:#fff;border:1px solid #0f0;"><br>
            <input id="p" type="password" placeholder="Password" style="width:250px;padding:10px;margin:5px;background:#000;color:#fff;border:1px solid #0f0;"><br>
            <button onclick="login()" style="width:275px;padding:10px;margin-top:10px;background:#0f0;color:#000;font-weight:bold;cursor:pointer;border:none;">GET V7 TOKEN</button>
        </div>
        <div id="otpBox" style="display:none;margin-top:20px;">
            <input id="otp" placeholder="Enter 6-digit OTP" style="padding:10px;border:1px solid yellow;">
            <button onclick="verify()" style="padding:10px;background:yellow;border:none;">VERIFY</button>
        </div>
        <pre id="res" style="margin-top:30px;color:white;white-space:pre-wrap;word-break:break-all;text-align:left;max-width:500px;margin-left:auto;margin-right:auto;"></pre>
        
        <script>
            let sid = "";
            async function login(){
                document.getElementById('res').innerText = "Processing Handshake...";
                const fd = new FormData();
                fd.append('uid', document.getElementById('u').value);
                fd.append('password', document.getElementById('p').value);
                
                const res = await fetch('/login', { method:'POST', body:fd });
                const d = await res.json();
                
                if(d.two_factor){
                    sid = d.session_id;
                    document.getElementById('otpBox').style.display='block';
                    document.getElementById('res').innerText = "2FA Detected!";
                } else if(d.token1) {
                    document.getElementById('res').innerText = "Master: " + d.token1 + "\\n\\nV7 Token: " + d.token2;
                } else { alert(d.error); }
            }
            async function verify(){
                const fd = new FormData();
                fd.append('session_id', sid); fd.append('otp', document.getElementById('otp').value);
                const res = await fetch('/two_factor', { method:'POST', body:fd });
                const d = await res.json();
                if(d.token1) { 
                    document.getElementById('res').innerText = "Master: " + d.token1 + "\\n\\nV7 Token: " + d.token2;
                } else { alert(d.error); }
            }
        </script>
    </body>
    """

@app.route('/login', methods=['POST'])
def login():
    uid = request.form.get('uid')
    password = request.form.get('password')
    enc_pw = FacebookPasswordEncryptor.encrypt(password)
    
    headers = {
        "Authorization": f"OAuth {LITE_APP_ID}|{LITE_API_KEY}",
        "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 14; SM-S918B) [FBAN/FB4A;FBAV/505.0.0.0.66;FBBV/917292898;]",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    
    data = {
        "adid": str(uuid.uuid4()), "format": "json", "device_id": str(uuid.uuid4()),
        "email": uid, "password": enc_pw, "generate_session_cookies": "1",
        "error_detail_type": "button_with_disabled", "method": "auth.login"
    }
    data["sig"] = generate_sig(data)

    try:
        r = requests.post("https://b-graph.facebook.com/auth/login", headers=headers, data=data).json()
        if 'access_token' in r:
            master = r['access_token']
            return jsonify({'token1': master, 'token2': get_v7_token(master)})
        
        if 'error' in r and ('login_first_factor' in str(r) or r['error'].get('code') == 406):
            sid = str(uuid.uuid4())
            sessions_data[sid] = {'data': data, 'headers': headers, 'uid': uid, 'err': r['error']}
            return jsonify({'two_factor': True, 'session_id': sid})
        
        return jsonify({'error': r.get('error', {}).get('message', 'Login Failed')})
    except Exception as e: return jsonify({'error': str(e)})

@app.route('/two_factor', methods=['POST'])
def two_factor():
    sid, otp = request.form.get('session_id'), request.form.get('otp')
    if sid not in sessions_data: return jsonify({'error': 'Expired'})
    
    s = sessions_data[sid]
    v_data = s['data'].copy()
    v_data.pop('sig', None)
    v_data.update({
        "twofactor_code": otp, "userid": s['uid'], 
        "first_factor": s['err']['error_data'].get('login_first_factor'),
        "credentials_type": "two_factor"
    })
    v_data["sig"] = generate_sig(v_data)
    
    r = requests.post("https://b-graph.facebook.com/auth/login", headers=s['headers'], data=v_data).json()
    if 'access_token' in r:
        master = r['access_token']
        return jsonify({'token1': master, 'token2': get_v7_token(master)})
    return jsonify({'error': 'OTP Failed'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
