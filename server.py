from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import requests
import os
import time
import base64
import re

app = Flask(__name__)
CORS(app)

ASSEMBLYAI_KEY = os.environ.get('ASSEMBLYAI_KEY', '')
ANTHROPIC_KEY = os.environ.get('ANTHROPIC_KEY', '')

def get_drive_direct_url(url):
    m = re.search(r'/file/d/([a-zA-Z0-9_-]+)', url)
    if not m:
        m = re.search(r'[?&]id=([a-zA-Z0-9_-]+)', url)
    if not m:
        return url, None
    file_id = m.group(1)
    return f'https://drive.usercontent.google.com/download?id={file_id}&export=download&authuser=0&confirm=t', file_id

@app.route('/')
def home():
    response = send_file('app.html')
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.route('/status')
def status():
    return jsonify({'status': 'CaptionAI szerver aktív ✅'})

@app.route('/image-proxy', methods=['POST'])
def image_proxy():
    data = request.json
    image_url = data.get('url')
    if not image_url:
        return jsonify({'error': 'Hiányzó URL'}), 400
    if 'drive.google.com' in image_url:
        image_url, _ = get_drive_direct_url(image_url)
    try:
        res = requests.get(image_url, timeout=20, allow_redirects=True)
        if res.status_code != 200:
            return jsonify({'error': f'HTTP {res.status_code}'}), 400
        content_type = res.headers.get('content-type', 'image/jpeg').split(';')[0]
        b64 = base64.b64encode(res.content).decode('utf-8')
        return jsonify({'data': f'data:{content_type};base64,{b64}'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/transcribe', methods=['POST'])
def transcribe():
    data = request.json
    audio_url = data.get('audio_url')
    api_key = data.get('api_key') or ASSEMBLYAI_KEY

    if not audio_url:
        return jsonify({'error': 'Hiányzó audio_url'}), 400
    if not api_key:
        return jsonify({'error': 'Hiányzó AssemblyAI API kulcs'}), 400

    headers = {'authorization': api_key, 'content-type': 'application/json'}

    if 'drive.google.com' in audio_url:
        audio_url, _ = get_drive_direct_url(audio_url)

    res = requests.post('https://api.assemblyai.com/v2/transcript',
                        json={'audio_url': audio_url, 'language_code': 'hu', 'speech_models': ['universal-2']},
                        headers=headers)
    job = res.json()
    if 'id' not in job:
        return jsonify({'error': job.get('error', 'Ismeretlen hiba')}), 500

    for _ in range(60):
        time.sleep(3)
        poll = requests.get(f"https://api.assemblyai.com/v2/transcript/{job['id']}",
                            headers=headers).json()
        if poll['status'] == 'completed':
            return jsonify({'transcript': poll['text']})
        if poll['status'] == 'error':
            return jsonify({'error': poll.get('error', 'Átírás sikertelen')}), 500

    return jsonify({'error': 'Időtúllépés'}), 504

@app.route('/analyze-image', methods=['POST'])
def analyze_image():
    data = request.json
    image_url = data.get('image_url')
    system_prompt = data.get('system', '')
    user_prompt = data.get('user', '')
    api_key = ANTHROPIC_KEY

    if not image_url:
        return jsonify({'error': 'Hiányzó image_url'}), 400
    if not api_key:
        return jsonify({'error': 'Hiányzó Anthropic API kulcs'}), 400

    # Convert Drive URL and download image
    if 'drive.google.com' in image_url:
        direct_url, _ = get_drive_direct_url(image_url)
    else:
        direct_url = image_url

    try:
        img_res = requests.get(direct_url, timeout=30, allow_redirects=True)
        if img_res.status_code != 200:
            return jsonify({'error': f'Kép letöltése sikertelen: HTTP {img_res.status_code}'}), 400
        
        content_type = img_res.headers.get('content-type', 'image/jpeg')
        if 'jpeg' in content_type or 'jpg' in content_type:
            media_type = 'image/jpeg'
        elif 'png' in content_type:
            media_type = 'image/png'
        elif 'gif' in content_type:
            media_type = 'image/gif'
        elif 'webp' in content_type:
            media_type = 'image/webp'
        else:
            media_type = 'image/jpeg'

        img_b64 = base64.b64encode(img_res.content).decode('utf-8')
    except Exception as e:
        return jsonify({'error': f'Kép letöltési hiba: {str(e)}'}), 500

    # Send to Claude Vision
    res = requests.post('https://api.anthropic.com/v1/messages',
        headers={
            'x-api-key': api_key,
            'anthropic-version': '2023-06-01',
            'content-type': 'application/json'
        },
        json={
            'model': 'claude-haiku-4-5-20251001',
            'max_tokens': 1500,
            'system': system_prompt,
            'messages': [{
                'role': 'user',
                'content': [
                    {
                        'type': 'image',
                        'source': {
                            'type': 'base64',
                            'media_type': media_type,
                            'data': img_b64
                        }
                    },
                    {
                        'type': 'text',
                        'text': user_prompt
                    }
                ]
            }]
        })

    result = res.json()
    if 'error' in result:
        return jsonify({'error': result['error'].get('message', 'Claude API hiba')}), 500

    text = ''.join(b.get('text', '') for b in result.get('content', []))
    return jsonify({'text': text})

@app.route('/generate', methods=['POST'])
def generate():
    data = request.json
    system = data.get('system', '')
    user = data.get('user', '')
    api_key = ANTHROPIC_KEY

    if not api_key:
        return jsonify({'error': 'Hiányzó Anthropic API kulcs'}), 400

    res = requests.post('https://api.anthropic.com/v1/messages',
        headers={
            'x-api-key': api_key,
            'anthropic-version': '2023-06-01',
            'content-type': 'application/json'
        },
        json={
            'model': 'claude-haiku-4-5-20251001',
            'max_tokens': 1000,
            'system': system,
            'messages': [{'role': 'user', 'content': user}]
        })

    result = res.json()
    if 'error' in result:
        return jsonify({'error': result['error'].get('message', 'Claude API hiba')}), 500

    text = ''.join(b.get('text', '') for b in result.get('content', []))
    return jsonify({'text': text})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
