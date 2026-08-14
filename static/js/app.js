const textInput = document.getElementById("text-input");
const fileUpload = document.getElementById("file-upload");
const youtubeInput = document.getElementById("youtube-link");
const sourceLang = document.getElementById("source-lang");
const targetLang = document.getElementById("target-lang");
const translateBtn = document.getElementById("translate-btn");
const recordBtn = document.getElementById("record-btn");
const transcription = document.getElementById("transcription");
const translation = document.getElementById("translation");
const copyBtn = document.getElementById("copy-btn");
const playBtn = document.getElementById("play-btn");
const loader = document.getElementById("loader");
const errorMessage = document.getElementById("error-message");
const recordingStatus = document.getElementById("recording-status");

let recorder = null;
let chunks = [];

function showError(message) { errorMessage.textContent = message; }
function setLoading(value) { loader.classList.toggle("hidden", !value); }
function resetOutput() { transcription.value = ""; translation.value = ""; playBtn.disabled = true; showError(""); }

function clearOtherInputs(active) {
    if (active !== "text") textInput.value = "";
    if (active !== "file") fileUpload.value = "";
    if (active !== "youtube") youtubeInput.value = "";
}

textInput.addEventListener("input", () => {
    if (textInput.value.trim()) clearOtherInputs("text");
});

fileUpload.addEventListener("change", () => {
    if (fileUpload.files.length) clearOtherInputs("file");
});

youtubeInput.addEventListener("input", () => {
    if (youtubeInput.value.trim()) clearOtherInputs("youtube");
});

async function handleResponse(response) {
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Request failed.");
    return data;
}

function showResult(data) {
    transcription.value = data.transcription || "";
    translation.value = data.translation || "";
    playBtn.disabled = !data.translation;
}

async function translateText() {
    const text = textInput.value.trim();
    const response = await fetch("/translate-text", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
            text,
            source_language: sourceLang.value,
            target_language_name: targetLang.options[targetLang.selectedIndex].text
        })
    });
    showResult(await handleResponse(response));
}

async function translateFile(file) {
    const form = new FormData();
    form.append("file", file);
    form.append("source_language", sourceLang.value);
    form.append("target_language_name", targetLang.options[targetLang.selectedIndex].text);
    const response = await fetch("/translate", {method: "POST", body: form});
    showResult(await handleResponse(response));
}

async function translateYouTube(url) {
    const response = await fetch("/translate-youtube", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
            url,
            source_language: sourceLang.value,
            target_language_name: targetLang.options[targetLang.selectedIndex].text
        })
    });
    showResult(await handleResponse(response));
}

translateBtn.addEventListener("click", async () => {
    resetOutput();
    setLoading(true);
    try {
        const text = textInput.value.trim();
        const url = youtubeInput.value.trim();
        const file = fileUpload.files[0];
        const inputs = [Boolean(text), Boolean(url), Boolean(file)].filter(Boolean).length;

        if (inputs === 0) throw new Error("Provide one input: text, file, or YouTube URL.");
        if (inputs > 1) throw new Error("Please use only one input at a time.");

        if (text) await translateText();
        else if (url) await translateYouTube(url);
        else await translateFile(file);
    } catch (error) { showError(error.message); }
    finally { setLoading(false); }
});

recordBtn.addEventListener("click", async () => {
    try {
        if (!recorder) {
            clearOtherInputs("file");
            const stream = await navigator.mediaDevices.getUserMedia({audio: true});
            recorder = new MediaRecorder(stream);
            chunks = [];
            recorder.ondataavailable = e => chunks.push(e.data);
            recorder.onstop = async () => {
                const blob = new Blob(chunks, {type: "audio/webm"});
                setLoading(true);
                try { await translateFile(new File([blob], "recording.webm", {type: "audio/webm"})); }
                catch (error) { showError(error.message); }
                finally { setLoading(false); stream.getTracks().forEach(track => track.stop()); recorder = null; }
            };
            recorder.start();
            recordBtn.textContent = "⏹ Stop";
            recordingStatus.textContent = "Recording...";
        } else {
            recorder.stop();
            recordBtn.textContent = "🎙 Record";
            recordingStatus.textContent = "";
        }
    } catch { showError("Microphone access was denied or is unavailable."); }
});

copyBtn.addEventListener("click", async () => { await navigator.clipboard.writeText(translation.value); });

playBtn.addEventListener("click", () => {
    if (!translation.value) return;
    speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(translation.value);
    utterance.lang = targetLang.value;
    speechSynthesis.speak(utterance);
});
