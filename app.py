from flask import Flask, render_template, request, jsonify
import requests
import uuid
import time
import base64
import io
import struct
from Crypto.Cipher import AES, PKCS1_v1_5
from Crypto.PublicKey import RSA
from Crypto.Random import get_random_bytes
import os

app = Flask(__name__)

# --- ENCRYPTION LOGIC ---
class FacebookPasswordEncryptor:
    @staticmethod
    def get_public_key():
        try:
            url = 'https://b-graph.facebook.com/pwd_key_fetch'
            params = {
                'version': '2',
                'flow': 'CONTROLLER_INITIALIZATION',
                'method': 'GET',
                'fb_api_req_friendly_name': 'pwdKeyFetch',
                'fb_api_caller_class': 'com.facebook.auth.login.AuthOperations',
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

# --- UNIVERSAL TOKEN EXTRACTION ENGINE ---
def get_all_tokens(master_token):
    tokens_dict = {}
    tokens_dict['Master Token (EAAG)'] = master_token
    
    # All Official Facebook App IDs for different token types
    app_ids = {
        'Pages Manager (EAAB)': '165907476854626',   # Generates EAAB
        'Instagram (EAAI)': '124024574287414',       # Generates EAAI
        'Lite / E7 Token (EAADV)': '275254692598279',# Generates EAADV (E7)
        'iOS Token (EAAD)': '6628568379'             # Generates EAAD
    }
    
    for name, app_id in app_ids.items():
        try:
            res = requests.post(
                'https://api.facebook.com/method/auth.getSessionforApp',
                data={
                    'access_token': master_token,
                    'format': 'json',
                    'new_app_id': app_id,
                    'generate_session_cookies': '1'
                }
            )
            tkn = res.json().get('access_token')
            if tkn:
                tokens_dict[name] = tkn
        except Exception:
            continue
            
    return tokens_dict

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['POST'])
def login():
    try:
        uid = request.form.get('uid')
        password = request.form.get('password')
        if not uid or not password:
            return jsonify({'error': 'Email and Password are required'})
            
        encrypted_password = FacebookPasswordEncryptor.encrypt(password)
        adid = str(uuid.uuid4())
        device_id = str(uuid.uuid4())
        family_device_id = str(uuid.uuid4())
        
        client_ip = request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0].strip()

        headers = {
            "Authorization": "OAuth 350685531728|62f8ce9f74b12f84c123cc23437a4a32",
            "X-FB-Connection-Quality": "EXCELLENT",
            "X-FB-Connection-Type": "WIFI",
            "X-FB-SIM-HNI": "310260",
            "X-FB-Net-HNI": "310260",
            "X-Forwarded-For": client_ip,
            "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 13; SM-S918B Build/TP1A.220624.014) [FBAN/FB4A;FBAV/473.0.0.45.85;FBPN/com.facebook.katana;FBLC/en_US;FBBV/615875241;FBCR/T-Mobile;FBMF/samsung;FBBD/samsung;FBDV/SM-S918B;FBSV/13;FBCA/arm64-v8a:null;FBDM/{density=3.0,width=1080,height=2340};FB_FW/1;FBRV/0;]",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        
        data = {
            "adid": adid, "format": "json", "device_id": device_id, "email": uid,
            "password": encrypted_password, "generate_analytics_claim": "1",
            "cpl": "true", "try_num": "1", "family_device_id": family_device_id,
            "credentials_type": "password", "source": "login",
            "error_detail_type": "button_with_disabled", "enroll_misauth": "false",
            "generate_session_cookies": "1", "generate_machine_id": "1",
            "currently_logged_in_userid": "0", "fb_api_req_friendly_name": "authenticate",
            "locale": "en_US", "client_country_code": "US",
        }
        
        response = requests.post("https://b-graph.facebook.com/auth/login", headers=headers, data=data)
        res_data = response.json()
        
        if 'access_token' in res_data:
            master_token = res_data['access_token']
            all_tokens = get_all_tokens(master_token)
            return jsonify({'success': True, 'tokens': all_tokens})
            
        if 'error' in res_data:
            err = res_data['error']
            err_data = err.get('error_data', {})
            err_msg = err.get('message', '').lower()
            
            if 'abusive' in err_msg or 'disallowed' in err_msg:
                 return jsonify({'error': 'Facebook Security Block: Server IP flagged.'})
                 
            if 'approval' in err_msg or err.get('code') == 459 or 'login_first_factor' in err_data:
                session_id = str(uuid.uuid4())
                sessions_data[session_id] = {'uid': uid, 'err_data': err_data, 'headers': headers, 'data': data}
                return jsonify({'two_factor': True, 'session_id': session_id})
                
            return jsonify({'error': err.get('message', 'Login failed')})
    except Exception as e:
        return jsonify({'error': f"Login Error: {str(e)}"})

@app.route('/two_factor', methods=['POST'])
def two_factor():
    try:
        session_id = request.form.get('session_id')
        otp = request.form.get('otp')
        
        if not session_id or session_id not in sessions_data:
            return jsonify({'error': 'Session expired. Please refresh page and login again.'})
            
        s = sessions_data[session_id]
        login_data = s['data']
        err_data = s.get('err_data', {})
        
        login_data['twofactor_code'] = otp
        login_data['userid'] = s.get('uid', '')
        login_data['credentials_type'] = 'two_factor'
        
        if isinstance(err_data, dict):
            first_factor = err_data.get('login_first_factor')
            if first_factor:
                login_data['first_factor'] = first_factor
                login_data['machine_id'] = first_factor
                
        response = requests.post("https://b-graph.facebook.com/auth/login", headers=s['headers'], data=login_data)
        res_data = response.json()
        
        if 'access_token' in res_data:
            master_token = res_data['access_token']
            all_tokens = get_all_tokens(master_token)
            return jsonify({'success': True, 'tokens': all_tokens})
            
        return jsonify({'error': res_data.get('error', {}).get('message', '2FA failed! Invalid OTP.')})
        
    except Exception as e:
        return jsonify({'error': f"2FA Backend Error: {str(e)}"})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
