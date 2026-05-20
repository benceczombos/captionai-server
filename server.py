from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import requests
import os
import time

app = Flask(__name__)
CORS(app)

ASSEMBLYAI_KEY = os.environ.get('ASSEMBLYAI_KEY', '')
ANTHROPIC_KEY = os.environ.get('ANTHROPIC_KEY', '')

@app.route('/')
def home():
    return send_file('app.html')

@app.route('/status')
def status():
    return jsonify({'status': 'CaptionAI szerver aktív ✅'})

def get_drive_direct_url(url):
    import re
    m = re.search(r'/file/d/([a-zA-Z0-9_-]+)', url)
    if not m:
        m = re.search(r'[?&]id=([a-zA-Z0-9_-]+)', url)
    if not m:
        return url
    file_id = m.group(1)
    # Use the direct download URL that bypasses the virus scan page
    return f'https://drive.usercontent.google.com/download?id={file_id}&export=download&authuser=0&confirm=t'

@app.route('/transcribe', methods=['POST'])
def transcribe():
    data = request.json
    audio_url = data.get('audio_url')
    api_key = data.get('api_key') or ASSEMBLYAI_KEY

    if not audio_url:
        return jsonify({'error': 'Hiányzó audio_url'}), 400
    if not api_key:
        return jsonify({'error': 'Hiányzó AssemblyAI API kulcs'}), 400

    # Convert Drive URL to direct download
    if 'drive.google.com' in audio_url:
        audio_url = get_drive_direct_url(audio_url)

    headers = {'authorization': api_key, 'content-type': 'application/json'}

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

@app.route('/generate', methods=['POST'])
def generate():
    data = request.json
    system = data.get('system', '')
    user = data.get('user', '')
    api_key = ANTHROPIC_KEY

    if not api_key:
        return jsonify({'error': 'Hiányzó Anthropic API kulcs a szerveren'}), 400

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
