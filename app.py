import re
import os
import json
import requests 
from flask_cors import CORS
from flask import Flask, request, redirect, jsonify, session
from flask_session import Session
from urllib.parse import urlencode
from bs4 import BeautifulSoup


app = Flask(__name__)
CORS(app, supports_credentials=True, resources={r"/*": {"origins": "http://localhost:3000"}})

app.config['SESSION_TYPE'] = 'filesystem'
Session(app)

CLIENT_ID = 'a74dd22caa104ec9a3bd4af388adc9d4'
CLIENT_SECRET = '7671a42e3d2949e99fd2ec31528bbbc4'
REDIRECT_URI = 'http://localhost:5001/callback'
SCOPE = 'user-read-currently-playing'

AUTH_URL = 'https://accounts.spotify.com/authorize'
TOKEN_URL = 'https://accounts.spotify.com/api/token'
API_BASE_URL = 'https://api.spotify.com/v1/'

GENIUS_API_BASE_URL = 'https://api.genius.com'
GENIUS_ACCESS_TOKEN = '0cOiiPFMBqkM3a-iILBmPEWNvHiIYE00iIm-j-J7fcNm7A1ebFyirNVQUXzQK7r7'

DEEPL_API_KEY = '6695f6e0-f572-b52d-d7b6-3f936263bde6:fx'  # Replace with your actual DeepL API key

@app.route('/')
def home():
    query_params = {
        'response_type': 'code',
        'client_id': CLIENT_ID,
        'scope': SCOPE,
        'redirect_uri': REDIRECT_URI
    }
    url = f"{AUTH_URL}?{urlencode(query_params)}"
    return redirect(url)

@app.route('/login')
def login():
    query_params = {
        'response_type': 'code',
        'client_id': CLIENT_ID,
        'scope': SCOPE,
        'redirect_uri': REDIRECT_URI
    }
    url = f"{AUTH_URL}?{urlencode(query_params)}"
    return redirect(url)

@app.route('/callback')
def callback():
    if 'error' in request.args:
        return jsonify({"error": request.args['error']})

    if 'code' in request.args:
        req_body = {
            'code': request.args['code'],
            'grant_type': 'authorization_code',
            'redirect_uri': REDIRECT_URI,
            'client_id': CLIENT_ID,
            'client_secret': CLIENT_SECRET
        }

        response = requests.post(TOKEN_URL, data=req_body)
        token_info = response.json()

        session['access_token'] = token_info['access_token']
        return redirect('http://localhost:3000/app')  # Redirect to the main app page

    return jsonify({"error": "Authorization failed"})

@app.route('/check_auth')
def check_auth():
    if 'access_token' in session:
        return jsonify({"isAuthenticated": True})
    return jsonify({"isAuthenticated": False})

def get_spotify_token():
    return session.get('access_token')

def fetch_current_song():
    access_token = get_spotify_token()
    headers = {
        'Authorization': f"Bearer {access_token}"
    }
    response = requests.get(f"{API_BASE_URL}me/player/currently-playing", headers=headers)

    # Log the response for debugging
    print("Response status code:", response.status_code)

    if response.status_code == 204:
        print("No song currently playing")
        return None

    if response.status_code == 401:
        print("Access token expired")
        session.pop('access_token', None)
        return "expired"

    try:
        return response.json()
    except requests.exceptions.JSONDecodeError:
        print("Error decoding JSON response")
        return {}

def translate_lyrics(lyrics, target_language):
    # Split lyrics into lines
    lyrics_lines = lyrics.split('\n')
    translated_lyrics_lines = []
    for line in lyrics_lines:
        if line.strip() == '':
            # Empty line (stanza break), keep it
            translated_lyrics_lines.append('')
            continue
        response = requests.post('https://api-free.deepl.com/v2/translate', data={
            'auth_key': DEEPL_API_KEY,
            'text': line,
            'target_lang': target_language
        })
        if response.status_code == 200:
            translated_line = response.json()['translations'][0]['text']
            translated_lyrics_lines.append(translated_line)
        else:
            print(f"Error translating line: {line}, status code: {response.status_code}")
            translated_lyrics_lines.append(line)  # Fallback to original line if translation fails
    # Join translated lines back into a string
    translated_lyrics = '\n'.join(translated_lyrics_lines)
    return translated_lyrics

def search_genius_song(song_title, artist_name):
    headers = {
        'Authorization': f'Bearer {GENIUS_ACCESS_TOKEN}'
    }
    search_url = f"{GENIUS_API_BASE_URL}/search"
    params = {'q': f"{song_title} {artist_name}"}
    response = requests.get(search_url, headers=headers, params=params)

    if response.status_code != 200:
        print(f"Error searching Genius: {response.status_code}")
        return None

    try:
        return response.json()
    except requests.exceptions.JSONDecodeError:
        print("Error decoding JSON response from Genius")
        return None

def fetch_genius_url(song_title, artist_name):
    print("Attempting to fetch Genius Lyrics")
    search_results = search_genius_song(song_title, artist_name)
    print(f"Searched for {song_title} by {artist_name}")
    if not search_results or 'response' not in search_results or 'hits' not in search_results['response']:
        return None

    # Get the first hit
    song_info = search_results['response']['hits'][0]['result']
    song_url = song_info['url']
    print(f"Song URL: {song_url}")

    return song_url

def fetch_genius_lyrics(song_url):
    lyrics_page = requests.get(song_url)

    soup = BeautifulSoup(lyrics_page.content, 'html.parser')
    lyrics_divs = soup.find_all('div', {'data-lyrics-container': 'true'})

    if not lyrics_divs:
        print("Lyrics div not found")
        return None
    print("Lyrics divs found:", len(lyrics_divs))

    lyrics = ''
    for div in lyrics_divs:
        for element in div.contents:
            if isinstance(element, str):
                lyrics += element
            elif element.name == 'br':
                lyrics += '\n'
            else:
                lyrics += element.get_text()
        lyrics += '\n\n'  # Add stanza break

    lyrics = lyrics.strip()
    return lyrics

@app.route('/current_song_info')
def get_current_song_info():
    current_song = fetch_current_song()
    if current_song == "expired":
        return redirect('http://localhost:3000/login')  # Redirect to the login page

    if not current_song or 'item' not in current_song:
        return jsonify({"error": "No song currently playing"}), 400

    song_title = current_song['item']['name']
    artist_name = ', '.join([artist['name'] for artist in current_song['item']['artists']])

    return jsonify({
        'song_title': song_title,
        'artist_name': artist_name
    })

@app.route('/lyrics')
def get_lyrics():
    song_title = request.args.get('song_title')
    artist_name = request.args.get('artist_name')
    if not song_title or not artist_name:
        return jsonify({"error": "Song title and artist name are required"}), 400

    # Fetch lyrics from Genius
    genius_lyrics_url = fetch_genius_url(song_title, artist_name)
    if not genius_lyrics_url:
        return jsonify({'lyrics': '', 'error': "Song not found on Genius"}), 404

    genius_lyrics = fetch_genius_lyrics(genius_lyrics_url)
    if not genius_lyrics:
        return jsonify({'lyrics': '', 'error': "Lyrics not found on Genius"}), 404

    # Return the lyrics as a string
    return jsonify({'lyrics': genius_lyrics})

@app.route('/translate_lyrics', methods=['POST'])
def translate_lyrics_endpoint():
    data = request.get_json()
    lyrics = data.get('lyrics', '')
    target_language = data.get('lang', 'EN')

    if not lyrics:
        return jsonify({"error": "Lyrics are required"}), 400

    translated_lyrics = translate_lyrics(lyrics, target_language)
    return jsonify({'translated_lyrics': translated_lyrics})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)
