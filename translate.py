import os
import base64
import requests
import json
import uuid
import time
from flask import Flask, render_template_string, request, jsonify
from googletrans import LANGUAGES
from pydub import AudioSegment
import yt_dlp
from pypdf import PdfReader
from docx import Document
from gtts import gTTS

app = Flask(__name__)

if not os.path.exists("static"):
    os.makedirs("static")

API_KEY = os.environ.get("GEMINI_API_KEY")

if not API_KEY:
    raise RuntimeError("GEMINI_API_KEY environment variable is not set")

GEMINI_API_URL = (
    "https://generativelanguage.googleapis.com/"
    "v1beta/models/gemini-flash-latest:generateContent"
)

GEMINI_HEADERS = {
    "Content-Type": "application/json",
    "X-goog-api-key": API_KEY
}

def cleanup_stale_files(directory="static", age_seconds=3600):
    """Deletes temporary files in the static folder older than the specified age."""
    now = time.time()
    for filename in os.listdir(directory):
        filepath = os.path.join(directory, filename)
        if os.path.isfile(filepath):
            if now - os.path.getmtime(filepath) > age_seconds:
                try:
                    os.remove(filepath)
                except OSError:
                    pass

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI-Powered Universal Translator</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700&display=swap');
        body {
            font-family: 'Inter', sans-serif;
            background-color: #f0f4f8;
        }
        .main-container {
            background: linear-gradient(135deg, #ffffff 0%, #eef2f7 100%);
            border-radius: 20px;
            box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.15);
            border: 1px solid rgba(255, 255, 255, 0.5);
        }
        .btn { @apply font-semibold py-2 px-4 rounded-lg transition-all duration-300 shadow-sm; }
        .btn-primary { @apply bg-indigo-600 text-white hover:bg-indigo-700 shadow-indigo-200/50; }
        .btn-secondary { @apply bg-slate-200 text-slate-700 hover:bg-slate-300; }
        
        .loader {
            border: 4px solid #f3f3f3;
            border-top: 4px solid #4f46e5;
            border-radius: 50%;
            width: 40px;
            height: 40px;
            animation: spin 1s linear infinite;
        }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }

        .language-select-container { position: relative; }
        .language-select-button { @apply w-full bg-white border border-slate-300 rounded-lg p-3 text-left flex justify-between items-center; }
        .language-dropdown {
            @apply absolute z-10 w-full bg-white border border-slate-200 rounded-lg mt-1 shadow-lg;
            max-height: 200px;
            overflow-y: auto;
        }
        .language-dropdown input { @apply w-full p-2 border-b border-slate-200 sticky top-0; }
        .language-dropdown div { @apply p-2 hover:bg-indigo-50 cursor-pointer; }
    </style>
</head>
<body class="flex items-center justify-center min-h-screen p-4">
    <div class="main-container w-full max-w-5xl p-6 md:p-8">
        <header class="text-center mb-8">
            <h1 class="text-4xl md:text-5xl font-bold text-slate-800">Universal Translator</h1>
            <p class="text-slate-500 mt-2 text-lg">Translate Text, Speech, Files, and YouTube Videos with AI</p>
        </header>

        <div class="grid grid-cols-1 lg:grid-cols-2 gap-8">
            <div class="bg-white/60 p-6 rounded-xl shadow-inner-soft">
                <h2 class="text-2xl font-semibold text-slate-700 mb-4 flex items-center"><i class="fas fa-sign-in-alt mr-3 text-indigo-500"></i>Input</h2>
                <div class="space-y-4">
                    <div>
                         <label for="text-input" class="block text-sm font-medium text-slate-600 mb-1">Text</label>
                         <textarea id="text-input" rows="4" class="w-full p-3 bg-white border border-slate-300 rounded-lg" placeholder="Enter text to translate..."></textarea>
                    </div>
                    <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
                        <div>
                            <label for="file-upload" class="bg-slate-50 hover:bg-slate-100 border-2 border-dashed border-slate-300 rounded-lg p-4 text-center cursor-pointer h-full flex flex-col justify-center items-center">
                                <i class="fas fa-file-audio text-3xl text-slate-400"></i>
                                <span class="mt-2 block text-sm font-medium text-slate-600">Upload File (audio/video/.txt/.pdf/.docx)</span>
                                <span id="file-name" class="text-xs text-slate-500"></span>
                            </label>
                            <input id="file-upload" type="file" class="hidden" accept="audio/*,video/*,.txt,.pdf,.docx">
                        </div>
                        <div>
                             <label for="youtube-link" class="block text-sm font-medium text-slate-600 mb-1">YouTube</label>
                             <input type="text" id="youtube-link" class="w-full p-3 bg-white border border-slate-300 rounded-lg" placeholder="Paste YouTube link...">
                        </div>
                    </div>
                    <div class="flex items-center gap-4">
                        <button id="translate-btn" class="btn btn-primary flex-grow"><i class="fas fa-language mr-2"></i>Translate</button>
                        <button id="record-btn" class="btn btn-secondary !p-3 !rounded-full" title="Record Audio"><i class="fas fa-microphone"></i></button>
                    </div>
                    <p id="recording-status" class="text-sm text-center text-slate-500 h-4"></p>
                </div>
            </div>

            <div class="bg-white/60 p-6 rounded-xl shadow-inner-soft">
                <h2 class="text-2xl font-semibold text-slate-700 mb-4 flex items-center"><i class="fas fa-sign-out-alt mr-3 text-indigo-500"></i>Output</h2>
                <div class="space-y-4">
                    <div class="grid grid-cols-2 gap-4">
                        <div class="language-select-container">
                            <label class="block text-sm font-medium text-slate-600 mb-1">From</label>
                            <button id="source-lang-btn" class="language-select-button">
                                <span id="source-lang-text">Auto-Detect</span><i class="fas fa-chevron-down text-xs"></i>
                            </button>
                            <div id="source-lang-dropdown" class="language-dropdown hidden">
                                <input type="text" id="source-search" placeholder="Search...">
                                <div data-value="auto">Auto-Detect</div>
                            </div>
                        </div>
                        <div class="language-select-container">
                            <label class="block text-sm font-medium text-slate-600 mb-1">To</label>
                            <button id="target-lang-btn" class="language-select-button">
                                <span id="target-lang-text">English</span><i class="fas fa-chevron-down text-xs"></i>
                            </button>
                            <div id="target-lang-dropdown" class="language-dropdown hidden">
                                <input type="text" id="target-search" placeholder="Search...">
                            </div>
                        </div>
                    </div>
                    <div>
                        <label for="transcription" class="block text-sm font-medium text-slate-600 mb-1">Transcription</label>
                        <textarea id="transcription" rows="3" class="w-full p-3 bg-slate-100 border border-slate-200 rounded-lg" readonly></textarea>
                    </div>
                    <div class="relative">
                        <label for="translation" class="block text-sm font-medium text-slate-600 mb-1">Translation</label>
                        <textarea id="translation" rows="3" class="w-full p-3 bg-slate-100 border border-slate-200 rounded-lg" readonly></textarea>
                        <button id="copy-btn" class="absolute top-8 right-2 text-slate-400 hover:text-indigo-500" title="Copy to clipboard"><i class="fas fa-copy"></i></button>
                    </div>
                    <button id="play-audio-btn" class="btn btn-primary w-full" disabled><i class="fas fa-play mr-2"></i>Play Translation</button>
                    <audio id="tts-audio" style="display:none;"></audio>
                </div>
            </div>
        </div>
        <div id="loader-container" class="fixed inset-0 bg-white/70 backdrop-blur-sm flex justify-center items-center hidden z-50">
            <div class="loader"></div>
        </div>
        <div id="error-message" class="hidden fixed bottom-5 right-5 bg-red-500 text-white p-4 rounded-lg shadow-lg" role="alert"></div>
    </div>

    <script>
        const textInput = document.getElementById('text-input');
        const fileUpload = document.getElementById('file-upload');
        const fileNameDisplay = document.getElementById('file-name');
        const youtubeLinkInput = document.getElementById('youtube-link');
        const translateBtn = document.getElementById('translate-btn');
        const recordBtn = document.getElementById('record-btn');
        const recordingStatus = document.getElementById('recording-status');
        
        const sourceLangBtn = document.getElementById('source-lang-btn');
        const targetLangBtn = document.getElementById('target-lang-btn');
        const sourceLangText = document.getElementById('source-lang-text');
        const targetLangText = document.getElementById('target-lang-text');
        const sourceLangDropdown = document.getElementById('source-lang-dropdown');
        const targetLangDropdown = document.getElementById('target-lang-dropdown');
        const sourceSearch = document.getElementById('source-search');
        const targetSearch = document.getElementById('target-search');

        const transcription = document.getElementById('transcription');
        const translation = document.getElementById('translation');
        const copyBtn = document.getElementById('copy-btn');
        const playAudioBtn = document.getElementById('play-audio-btn');
        const ttsAudio = document.getElementById('tts-audio');
        const loaderContainer = document.getElementById('loader-container');
        const errorMessage = document.getElementById('error-message');

        let mediaRecorder;
        let audioChunks = [];
        let isRecording = false;
        let sourceLang = 'auto';
        let targetLang = 'en';

        const languages = {{ languages | tojson }};
        
        Object.entries(languages).forEach(([code, name]) => {
            const capitalizedName = name.charAt(0).toUpperCase() + name.slice(1);
            const sourceDiv = document.createElement('div');
            sourceDiv.textContent = capitalizedName;
            sourceDiv.dataset.value = code;
            sourceLangDropdown.appendChild(sourceDiv);

            const targetDiv = document.createElement('div');
            targetDiv.textContent = capitalizedName;
            targetDiv.dataset.value = code;
            targetLangDropdown.appendChild(targetDiv);
        });

        function setupDropdown(btn, dropdown, searchInput, langVarSetter, textElement) {
            btn.addEventListener('click', () => dropdown.classList.toggle('hidden'));
            searchInput.addEventListener('keyup', () => {
                const filter = searchInput.value.toLowerCase();
                dropdown.querySelectorAll('div').forEach(div => {
                    const txtValue = div.textContent || div.innerText;
                    div.style.display = txtValue.toLowerCase().includes(filter) ? '' : 'none';
                });
            });
            dropdown.addEventListener('click', (e) => {
                if (e.target.tagName === 'DIV') {
                    langVarSetter(e.target.dataset.value);
                    textElement.textContent = e.target.textContent;
                    dropdown.classList.add('hidden');
                }
            });
        }

        setupDropdown(sourceLangBtn, sourceLangDropdown, sourceSearch, (val) => sourceLang = val, sourceLangText);
        setupDropdown(targetLangBtn, targetLangDropdown, targetSearch, (val) => targetLang = val, targetLangText);
        
        document.addEventListener('click', (e) => {
            if (!sourceLangBtn.contains(e.target) && !sourceLangDropdown.contains(e.target)) sourceLangDropdown.classList.add('hidden');
            if (!targetLangBtn.contains(e.target) && !targetLangDropdown.contains(e.target)) targetLangDropdown.classList.add('hidden');
        });

        // Clear file upload selection when pasting a YouTube link
        youtubeLinkInput.addEventListener('input', () => {
            if (youtubeLinkInput.value.trim()) {
                fileUpload.value = ''; 
                fileNameDisplay.textContent = '';
                textInput.value = '';
            }
        });

        // Clear file upload selection when typing text
        textInput.addEventListener('input', () => {
            if (textInput.value.trim()) {
                fileUpload.value = '';
                fileNameDisplay.textContent = '';
                youtubeLinkInput.value = '';
            }
        });

        fileUpload.addEventListener('change', () => {
            const file = fileUpload.files[0];
            if (file) {
                fileNameDisplay.textContent = file.name.length > 20 ? file.name.substring(0, 17) + '...' : file.name;
                textInput.value = '';
                youtubeLinkInput.value = '';
            }
        });

        translateBtn.addEventListener('click', () => {
            const text = textInput.value.trim();
            const url = youtubeLinkInput.value.trim();
            const file = fileUpload.files[0];

            if (text) {
                processText(text);
            } else if (url) {
                processYouTubeLink(url);
            } else if (file) {
                if (file.size > 50 * 1024 * 1024) return showError('File size exceeds 50MB limit.');
                if (file.name.toLowerCase().endsWith('.txt') || file.type === 'text/plain') {
                    processTextFile(file);
                } else {
                    processFile(file);
                }
            } else {
                showError('Please provide an input: text, a file, or a YouTube link.');
            }
        });

        function processTextFile(file) {
            const reader = new FileReader();
            reader.onload = (e) => {
                const content = e.target.result.trim();
                if (!content) return showError('The uploaded text file is empty.');
                processText(content);
            };
            reader.onerror = () => showError('Could not read the text file.');
            reader.readAsText(file);
        }

        recordBtn.addEventListener('click', async () => {
            if (!isRecording) {
                try {
                    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                    mediaRecorder = new MediaRecorder(stream);
                    mediaRecorder.ondataavailable = event => audioChunks.push(event.data);
                    mediaRecorder.onstop = () => {
                        const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
                        processFile(audioBlob, 'recorded_audio.webm');
                        audioChunks = [];
                    };
                    mediaRecorder.start();
                    isRecording = true;
                    recordBtn.innerHTML = '<i class="fas fa-stop"></i>';
                    recordBtn.classList.replace('bg-slate-200', 'bg-red-500');
                    recordBtn.classList.replace('text-slate-700', 'text-white');
                    recordingStatus.textContent = 'Recording... Click to stop.';
                } catch (err) {
                    showError('Could not access microphone. Please grant permission.');
                }
            } else {
                mediaRecorder.stop();
                isRecording = false;
                recordBtn.innerHTML = '<i class="fas fa-microphone"></i>';
                recordBtn.classList.replace('bg-red-500', 'bg-slate-200');
                recordBtn.classList.replace('text-white', 'text-slate-700');
                recordingStatus.textContent = '';
            }
        });
        
        async function processText(text) {
            showLoader(true); hideError(); resetOutput();
            try {
                const response = await fetch('/translate-text', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ text: text, source_language: sourceLang, target_language: targetLang, target_language_name: targetLangText.textContent }),
                });
                if (!response.ok) throw new Error((await response.json()).error || `HTTP error! status: ${response.status}`);
                updateUIWithResults(await response.json(), true);
            } catch (error) { showError(error.message); } finally { showLoader(false); }
        }

        async function processYouTubeLink(url) {
            showLoader(true); hideError(); resetOutput();
            try {
                const response = await fetch('/translate-youtube', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ url: url, source_language: sourceLang, target_language: targetLang, target_language_name: targetLangText.textContent }),
                });
                if (!response.ok) throw new Error((await response.json()).error || `HTTP error! status: ${response.status}`);
                updateUIWithResults(await response.json());
            } catch (error) { showError(error.message); } finally { showLoader(false); }
        }

        async function processFile(file, filename = 'uploaded_file') {
            showLoader(true); hideError(); resetOutput();
            const formData = new FormData();
            formData.append('file', file, filename);
            formData.append('source_language', sourceLang);
            formData.append('target_language', targetLang);
            formData.append('target_language_name', targetLangText.textContent);
            try {
                const response = await fetch('/translate', { method: 'POST', body: formData });
                if (!response.ok) throw new Error((await response.json()).error || `HTTP error! status: ${response.status}`);
                updateUIWithResults(await response.json());
            } catch (error) { showError(error.message); } finally { showLoader(false); }
        }
        
        function updateUIWithResults(data, isText=false) {
            transcription.value = data.transcription;
            if (sourceLang === 'auto') sourceLangText.textContent = data.detected_language_name;
            translation.value = data.translation;
            if (data.translation) {
                playAudioBtn.disabled = false;
                copyBtn.style.display = 'block';
            }
        }
        
        const LOCALE_MAP = {
            en: 'en-US', es: 'es-ES', fr: 'fr-FR', de: 'de-DE', it: 'it-IT',
            pt: 'pt-PT', ru: 'ru-RU', ja: 'ja-JP', ko: 'ko-KR', zh: 'zh-CN',
            'zh-cn': 'zh-CN', 'zh-tw': 'zh-TW', ar: 'ar-SA', hi: 'hi-IN',
            bn: 'bn-BD', nl: 'nl-NL', sv: 'sv-SE', pl: 'pl-PL', tr: 'tr-TR',
            vi: 'vi-VN', th: 'th-TH', id: 'id-ID', uk: 'uk-UA', el: 'el-GR',
            he: 'he-IL', ta: 'ta-IN', te: 'te-IN', ur: 'ur-PK', fa: 'fa-IR'
        };

        function getVoicesAsync() {
            return new Promise((resolve) => {
                let voices = window.speechSynthesis.getVoices();
                if (voices.length) return resolve(voices);
                window.speechSynthesis.onvoiceschanged = () => resolve(window.speechSynthesis.getVoices());
                setTimeout(() => resolve(window.speechSynthesis.getVoices()), 1000);
            });
        }

        playAudioBtn.addEventListener('click', async () => {
            const textToSpeak = translation.value;
            if (!textToSpeak) return;

            playAudioBtn.disabled = true;
            const originalLabel = playAudioBtn.innerHTML;

            try {
                let matchedVoice = null;
                if ('speechSynthesis' in window) {
                    const locale = LOCALE_MAP[targetLang] || targetLang;
                    const voices = await getVoicesAsync();
                    matchedVoice = voices.find(v => v.lang === locale) || voices.find(v => v.lang.startsWith(targetLang));
                }

                if (matchedVoice) {
                    window.speechSynthesis.cancel();
                    const utterance = new SpeechSynthesisUtterance(textToSpeak);
                    utterance.voice = matchedVoice;
                    utterance.lang = matchedVoice.lang;
                    utterance.onerror = () => showError('Playback failed. Try again.');
                    window.speechSynthesis.speak(utterance);
                } else {
                    playAudioBtn.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i>Loading audio...';
                    const response = await fetch('/speak', {
                        method: 'POST', headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ text: textToSpeak, lang: targetLang })
                    });
                    const data = await response.json();
                    if (!response.ok || data.error) throw new Error(data.error || 'Could not generate audio for this language.');
                    ttsAudio.src = data.audio_url;
                    ttsAudio.play();
                }
            } catch (err) { showError(err.message); } finally {
                playAudioBtn.innerHTML = originalLabel;
                playAudioBtn.disabled = false;
            }
        });
        
        copyBtn.addEventListener('click', () => {
            translation.select();
            document.execCommand('copy');
        });

        function showLoader(show) { loaderContainer.style.display = show ? 'flex' : 'none'; }
        function showError(message) {
            errorMessage.textContent = message;
            errorMessage.style.display = 'block';
            setTimeout(() => { errorMessage.style.display = 'none'; }, 5000);
        }
        function hideError() { errorMessage.style.display = 'none'; }
        function resetOutput() {
            sourceLangText.textContent = 'Auto-Detect';
            sourceLang = 'auto';
            transcription.value = '';
            translation.value = '';
            playAudioBtn.disabled = true;
            copyBtn.style.display = 'none';
        }
    </script>
</body>
</html>
"""

def handle_api_error(response):
    try:
        error_data = response.json()
        message = error_data.get("error", {}).get("message", "Unknown API error.")
        if "API_KEY_INVALID" in message:
            return "The provided API Key is invalid. Please check your key and ensure the Gemini API is enabled in your Google Cloud project."
        return message
    except json.JSONDecodeError:
        return response.text

def process_audio_with_gemini(audio_path, target_language_name, source_language_code='auto'):
    with open(audio_path, "rb") as audio_file:
        audio_bytes = audio_file.read()
    encoded_audio = base64.b64encode(audio_bytes).decode("utf-8")

    if source_language_code == 'auto':
        prompt = "Transcribe this audio and identify its language. ONLY return a valid JSON object with two keys: 'language_code' (e.g., 'en', 'fr') and 'transcription'. Do not include any other text or formatting."
    else:
        source_language_name = LANGUAGES.get(source_language_code, "")
        prompt = f"This is an audio file in {source_language_name}. Transcribe it. ONLY return a valid JSON object with two keys: 'language_code' (which should be '{source_language_code}') and 'transcription'."

    payload = {
        "contents": [{"parts": [
            {"text": prompt},
            {"inlineData": {"mimeType": "audio/wav", "data": encoded_audio}}
        ]}]
    }
    response = requests.post(GEMINI_API_URL, json=payload, headers=GEMINI_HEADERS)
    
    if response.status_code != 200:
        raise ValueError(f"API Error: {handle_api_error(response)}")

    result = response.json()
    if not result.get('candidates'):
        raise ValueError("The API response did not contain any candidates. The audio might be silent or unrecognizable.")

    response_text = result['candidates'][0]['content']['parts'][0]['text']
    
    try:
        clean_json_str = response_text.strip().replace('```json', '').replace('```', '').strip()
        transcription_data = json.loads(clean_json_str)
    except json.JSONDecodeError:
        raise ValueError(f"Failed to parse AI response. The model returned: {response_text}")

    detected_lang_code = transcription_data.get('language_code', 'en')
    transcribed_text = transcription_data.get('transcription', '')
    detected_language_name = LANGUAGES.get(detected_lang_code, "Unknown").capitalize()

    if not transcribed_text:
        return {
            'detected_language_name': detected_language_name,
            'detected_language_code': detected_lang_code,
            'transcription': "(No speech detected)",
            'translation': "",
        }

    payload = {
        "contents": [{"parts": [
            {"text": f"Translate the following text from {detected_language_name} to {target_language_name}: {transcribed_text}"}
        ]}]
    }
    response = requests.post(GEMINI_API_URL, json=payload, headers=GEMINI_HEADERS)
    
    if response.status_code != 200:
        raise ValueError(f"API Error during translation: {handle_api_error(response)}")
    
    result = response.json()
    translated_text = result['candidates'][0]['content']['parts'][0]['text'].strip()

    return {
        'detected_language_name': detected_language_name,
        'detected_language_code': detected_lang_code,
        'transcription': transcribed_text,
        'translation': translated_text,
    }

def translate_plain_text(text_to_translate, source_language, target_language_name):
    if source_language == 'auto':
        prompt = f"First, identify the language of the following text. Then, translate the text to {target_language_name}. ONLY return a valid JSON object with three keys: 'detected_language_name', 'transcription' (which should be the original, untranslated text), and 'translation'."
    else:
        source_language_name = LANGUAGES.get(source_language, "the provided language")
        prompt = f"The following text is in {source_language_name}. Translate it to {target_language_name}. ONLY return a valid JSON object with three keys: 'detected_language_name' (which should be '{source_language_name}'), 'transcription' (the original text), and 'translation'."

    payload = {
        "contents": [{"parts": [
            {"text": prompt},
            {"text": text_to_translate}
        ]}]
    }

    response = requests.post(GEMINI_API_URL, json=payload, headers=GEMINI_HEADERS)

    if response.status_code != 200:
        raise ValueError(f"API Error: {handle_api_error(response)}")

    result = response.json()

    if not result.get('candidates'):
        raise ValueError("The API response did not contain any candidates.")

    response_text = result['candidates'][0]['content']['parts'][0]['text']
    clean_json_str = response_text.strip().replace('```json', '').replace('
