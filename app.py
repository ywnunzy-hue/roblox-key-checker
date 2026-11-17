import time
import json
import uuid
import requests
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit, join_room

app = Flask(__name__)
socketio = SocketIO(app, async_mode='threading')

DB_KEYS = {}

def get_roblox_user_id(username):
    try:
        res = requests.get("https://roblox.com", params={"keyword": username, "limit": 1}, timeout=4)
        if res.status_code == 200:
            data = res.json().get("data", [])
            if data: return data[0].get("id")
    except: pass
    return None

def check_roblox_rap_and_items(user_id):
    details = {"rap": 0, "korblox": "Tidak", "headless": "Tidak", "limited_list": [], "status_auto": "VALID/SECURE"}
    if not user_id:
        details["status_auto"] = "INVALID"
        return details
    try:
        coll_url = f"https://roblox.com{user_id}/assets/collectibles?limit=100"
        res_coll = requests.get(coll_url, timeout=4)
        if res_coll.status_code == 200:
            coll_data = res_coll.json().get("data", [])
            details["rap"] = sum(item.get("recentAveragePrice", 0) for item in coll_data)
            for item in coll_data:
                details["limited_list"].append({
                    "name": item.get("name"), "item_rap": f"{item.get('recentAveragePrice',0):,} RAP", "asset_id": item.get("assetId")
                })
        elif res_coll.status_code == 403:
            details["status_auto"] = "CROSS"
        if details["rap"] > 150000:
            details["korblox"] = "Ya"
            details["headless"] = "Ya"
        elif details["rap"] > 50000:
            details["headless"] = "Ya"
    except:
        details["status_auto"] = "CROSS"
    return details

@app.route('/')
def index():
    return render_template('admin.html')

@app.route('/result')
def client_panel():
    user_key = request.args.get('key', '')
    return render_template('client.html', user_key=user_key)

@app.route('/api/create-key', methods=['POST'])
def create_key():
    new_key = "RBX-" + str(uuid.uuid4()).hex[:8].upper()
    DB_KEYS[new_key] = {
        "status": "active", "total": 0, "valid": [], "invalid": [], "cross": [],
        "grand_total_rap": "0.00", "total_korblox": 0, "total_headless": 0
    }
    return jsonify({"success": True, "key": new_key})

@app.route('/api/verify-key', methods=['POST'])
def verify_key():
    data = request.json or {}
    user_key = data.get('key', '')
    if user_key in DB_KEYS:
        return jsonify({"valid": True, "stats": DB_KEYS[user_key]})
    return jsonify({"valid": False}), 404

@socketio.on('join_result_room')
def on_join(data):
    room = data.get('key')
    if room in DB_KEYS:
        join_room(room)

@socketio.on('start_admin_process')
def handle_admin_process(data):
    target_key = data.get('key')
    raw_text = data.get('text_data', '')
    
    if target_key not in DB_KEYS:
        emit('admin_status', {'text': 'Gagal! Key tidak valid.'})
        return

    lines = raw_text.split('\n')
    valid_lines = [l.strip() for l in lines if l.strip() and ":" in l]
    total_accounts = len(valid_lines)
    
    if total_accounts == 0:
        emit('admin_status', {'text': 'Kotak tempel kosong atau format salah!'})
        return

    emit('admin_status', {'text': f'Server sedang memproses data ke Key: {target_key}'})

    DB_KEYS[target_key] = {
        "status": "active", "total": total_accounts, "valid": [], "invalid": [], "cross": [],
        "grand_total_rap": "0.00", "total_korblox": 0, "total_headless": 0
    }

    running_rap = 0
    c_valid, c_invalid, c_cross, c_korblox, c_headless = 0, 0, 0, 0, 0

    for idx, line in enumerate(valid_lines, 1):
        parts = line.split(":")
        username = parts[0] if len(parts) > 0 else "Unknown"
        password = parts[1] if len(parts) > 1 else "Unknown"
        ip_address = parts[2] if len(parts) > 2 else "0.0.0.0"

        user_id = get_roblox_user_id(username)
        rbx = check_roblox_rap_and_items(user_id)
        status_ini = rbx["status_auto"]

        if status_ini == "VALID/SECURE":
            c_valid += 1
            DB_KEYS[target_key]["valid"].append(line)
        elif status_ini == "INVALID":
            c_invalid += 1
            DB_KEYS[target_key]["invalid"].append(line)
        else:
            c_cross += 1
            DB_KEYS[target_key]["cross"].append(line)

        running_rap += rbx['rap']
        if rbx['korblox'] == "Ya": c_korblox += 1
        if rbx['headless'] == "Ya": c_headless += 1

        rap_formatted = f"{(running_rap / 1000):,.2f}k" if running_rap >= 1000 else f"{running_rap}"
        
        DB_KEYS[target_key]["grand_total_rap"] = f"{rap_formatted} RAP"
        DB_KEYS[target_key]["total_korblox"] = f"{c_korblox} ACCOUNT"
        DB_KEYS[target_key]["total_headless"] = f"{c_headless} ACCOUNT"

        socketio.emit('live_stream_result', {
            'no': idx, 'usn': username, 'pw': password, 'ip': ip_address,
            'user_id': user_id, 'rap': f"{rbx['rap']:,} RAP",
            'korblox': rbx['korblox'], 'headless': rbx['headless'],
            'limited_list': rbx['limited_list'], 'status_akun': status_ini,
            'stats': {
                'current': idx, 'total': total_accounts,
                'valid': c_valid, 'invalid': c_invalid, 'cross': c_cross,
                'grand_total_rap': f"{rap_formatted} RAP",
                'total_korblox': f"{c_korblox} ACCOUNT", 'total_headless': f"{c_headless} ACCOUNT"
            }
        }, room=target_key)
        
        time.sleep(1.5)

    emit('admin_status', {'text': f'Pengecekan Selesai!'})

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000)
