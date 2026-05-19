from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import requests
import os
import time

app = Flask(__name__)
CORS(app)

ASSEMBLYAI_KEY = os.environ.get('ASSEMBLYAI_KEY', '')
GEMINI_KEY = os.environ.get('GEMINI_KEY', '')

@app.route('/')
def home():
    return send_file('app.html')

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
    api_key = GEMINI_KEY

    if not api_key:
        return jsonify({'error': 'Hiányzó Gemini API kulcs a szerveren'}), 400

    prompt = f"{system}\n\n{user}"

    res = requests.post(
        f'https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}',
        headers={'Content-Type': 'application/json'},
        json={
            'contents': [{'parts': [{'text': prompt}]}],
            'generationConfig': {'maxOutputTokens': 1000}
        }
    )

    result = res.json()
    if 'error' in result:
        return jsonify({'error': result['error'].get('message', 'Gemini API hiba')}), 500

    try:
        text = result['candidates'][0]['content']['parts'][0]['text']
    except (KeyError, IndexError):
        return jsonify({'error': 'Üres válasz a Gemini-től'}), 500

    return jsonify({'text': text})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
