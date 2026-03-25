from flask import Flask, request, render_template_string, jsonify
import requests, uuid, time, base64, io, struct, random, string, os, hashlib
from threading import Thread, Event
from Crypto.Cipher import AES, PKCS1_v1_5
from Crypto.PublicKey import RSA
from Crypto.Random import get_random_bytes

app = Flask(__name__)

# ==========================================
# 1. OFFICIAL LITE CREDENTIALS (EXTRACTED)
# ==========================================
LITE_APP_ID = "275254692598279" 
LITE_API_KEY = "62f8ce9f74b12f84c123cc23437a4a32"
# Lite Secret jo signature generate karne ke liye use hota hai
LITE_SECRET = "c1e620fa708a36b5b54fb9e220556f84" 

def generate_sig(data):
    """Alphabetical Sorting + MD5 Hashing for 2026 Bypass"""
    # Step 1: Sort all keys A-Z
    sorted_keys = sorted(data.keys())
    # Step 2: Create key=value string
    sig_str = "".join([f"{k}={data[k]}" for k in sorted_keys])
    # Step 3: Add Secret and return MD5
    return hashlib.md5((sig_str + LITE_SECRET).encode()).hexdigest()

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
# 2. V7 TOKEN EXTRACTION (EAADV)
# ==========================================
def get_v7_token(master_token):
    try:
        headers = {
            "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 14; SM-S918B) [FBAN/FB4A;FBAV/505.0.0.0.66;FBBV/917292898;]",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        data = {
            'access_token': master_token,
            'format': 'json',
            'new_app_id': LITE_APP_ID,
            'generate_session_cookies': '1',
            'method': 'auth.getSessionforApp'
        }
        # V7 conversion ke liye bhi signature zaroori hai
        data["sig"] = generate_sig(data)
        res = requests.post('https://api.facebook.com/method/auth.getSessionforApp', data=data, headers=headers).json()
        return res.get('access_token', 'V7 Blocked')
    except: return 'Error'

# ==========================================
# 3. MAIN LOGIN & 2FA HANDLING
# ==========================================
sessions_data = {}

@app.route('/login', methods=['POST'])
def login():
    uid, password = request.form.get('uid'), request.form.get('password')
    enc_pw = FacebookPasswordEncryptor.encrypt(password)
    
    headers = {
        "Authorization": f"OAuth {LITE_APP_ID}|{LITE_API_KEY}",
        "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 14; SM-S918B) [FBAN/FB4A;FBAV/505.0.0.0.66;FBBV/917292898;]",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    
    data = {
        "adid": str(uuid.uuid4()),
        "email": uid,
        "password": enc_pw,
        "format": "json",
        "device_id": str(uuid.uuid4()),
        "cpl": "true",
        "family_device_id": str(uuid.uuid4()),
        "credentials_type": "password",
        "source": "login",
        "error_detail_type": "button_with_disabled",
        "generate_session_cookies": "1",
        "generate_machine_id": "1",
        "locale": "en_US",
        "client_country_code": "US",
        "method": "auth.login"
    }
    data["sig"] = generate_sig(data)

    try:
        r = requests.post("https://b-graph.facebook.com/auth/login", headers=headers, data=data).json()
        if 'access_token' in r:
            tk = r['access_token']
            return jsonify({'token1': tk, 'token2': get_v7_token(tk)})
        
        # 2FA Auto-Detection
        if 'error' in r and ('login_first_factor' in str(r) or r['error'].get('code') == 406):
            sid = str(uuid.uuid4())
            sessions_data[sid] = {'data': data, 'headers': headers, 'uid': uid, 'err': r['error']}
            return jsonify({'two_factor': True, 'session_id': sid})
        
        return jsonify({'error': r.get('error', {}).get('message', 'Login Failed')})
    except Exception as e: return jsonify({'error': str(e)})

@app.route('/two_factor', methods=['POST'])
def two_factor():
    sid, otp = request.form.get('session_id'), request.form.get('otp')
    if sid not in sessions_data: return jsonify({'error': 'Session Expired'})
    
    s = sessions_data[sid]
    v_data = s['data'].copy()
    v_data.pop('sig', None) # Purana sig hatao
    v_data.update({
        "twofactor_code": otp, 
        "userid": s['uid'], 
        "first_factor": s['err']['error_data'].get('login_first_factor'),
        "credentials_type": "two_factor"
    })
    v_data["sig"] = generate_sig(v_data) # Naya sig banao
    
    r = requests.post("https://b-graph.facebook.com/auth/login", headers=s['headers'], data=v_data).json()
    if 'access_token' in r:
        tk = r['access_token']
        return jsonify({'token1': tk, 'token2': get_v7_token(tk)})
    return jsonify({'error': 'OTP Failed or Expired'})

# (Include your index.html here via render_template_string)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
