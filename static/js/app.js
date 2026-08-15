const textInput = document.getElementById("text-input");
const fileUpload = document.getElementById("file-upload");
const youtubeInput = document.getElementById("youtube-link");
const sourceLang = document.getElementById("source-lang");
const targetLang = document.getElementById("target-lang");
const sourceSearch = document.getElementById("source-search");
const targetSearch = document.getElementById("target-search");
const translateBtn = document.getElementById("translate-btn");
const recordBtn = document.getElementById("record-btn");
const transcription = document.getElementById("transcription");
const translation = document.getElementById("translation");
const detectedLanguage = document.getElementById("detected-language");
const copyBtn = document.getElementById("copy-btn");
const playBtn = document.getElementById("play-btn");
const errorMessage = document.getElementById("error-message");
const recordingStatus = document.getElementById("recording-status");
const processingPanel = document.getElementById("processing-panel");
const processingTitle = document.getElementById("processing-title");
const processingDetail = document.getElementById("processing-detail");
const steps = [document.getElementById("step-1"), document.getElementById("step-2"), document.getElementById("step-3")];

let recorder = null;
let chunks = [];

function showError(message) { errorMessage.textContent = message; }

function setProcessing(value, type = "text") {
    processingPanel.classList.toggle("hidden", !value);
    translateBtn.disabled = value;
    recordBtn.disabled = value;
    if (!value) return;

    const labels = {
        text: ["Translating text", "Reading your text and preparing the translation..."],
        file: ["Processing your file", "Extracting content and preparing the translation..."],
        youtube: ["Analyzing YouTube video", "Sending the public video to Gemini for analysis..."]
    };
    const [title, detail] = labels[type] || labels.text;
    processingTitle.textContent = title;
    processingDetail.textContent = detail;
    steps.forEach((step, index) => step.classList.toggle("active", index === 0));

    setTimeout(() => { if (processingPanel.classList.contains("hidden")) return; steps[1].classList.add("active"); processingDetail.textContent = type === "youtube" ? "Analyzing the video and spoken language..." : "Detecting language and understanding the content..."; }, 350);
    setTimeout(() => { if (processingPanel.classList.contains("hidden")) return; steps[2].classList.add("active"); processingDetail.textContent = "Generating your translation..."; }, 1100);
}

function resetOutput() {
    transcription.value = "";
    translation.value = "";
    detectedLanguage.textContent = "Detected language: —";
    playBtn.disabled = true;
    showError("");
}

function clearOtherInputs(active) {
    if (active !== "text") textInput.value = "";
    if (active !== "file") fileUpload.value = "";
    if (active !== "youtube") youtubeInput.value = "";
}

function syncLanguageSearch(input, select) {
    const value = input.value.trim().toLowerCase();
    const options = Array.from(select.options);
    const exact = options.find(option => option.text.toLowerCase() === value);
    if (exact) select.value = exact.value;
}

function syncLanguageInput(select, input) {
    const option = select.options[select.selectedIndex];
    input.value = option ? option.text : "";
}

sourceSearch.addEventListener("input", () => syncLanguageSearch(sourceSearch, sourceLang));
targetSearch.addEventListener("input", () => syncLanguageSearch(targetSearch, targetLang));
sourceSearch.addEventListener("change", () => syncLanguageSearch(sourceSearch, sourceLang));
targetSearch.addEventListener("change", () => syncLanguageSearch(targetSearch, targetLang));
sourceLang.addEventListener("change", () => syncLanguageInput(sourceLang, sourceSearch));
targetLang.addEventListener("change", () => syncLanguageInput(targetLang, targetSearch));

textInput.addEventListener("input", () => { if (textInput.value.trim()) clearOtherInputs("text"); });
fileUpload.addEventListener("change", () => { if (fileUpload.files.length) clearOtherInputs("file"); });
youtubeInput.addEventListener("input", () => { if (youtubeInput.value.trim()) clearOtherInputs("youtube"); });

async function handleResponse(response) {
    const contentType = response.headers.get("content-type") || "";
    if (!contentType.includes("application/json")) throw new Error(`Server returned an unexpected response (${response.status}).`);
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Request failed.");
    return data;
}

function showResult(data) {
    transcription.value = data.transcription || "";
    translation.value = data.translation || "";
    const language = data.detected_language_name || data.detected_language_code || "—";
    detectedLanguage.textContent = `Detected language: ${language}`;
    playBtn.disabled = !data.translation;
}

async function translateText() {
    const response = await fetch("/translate-text", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({ text: textInput.value.trim(), source_language: sourceLang.value, target_language_name: targetLang.options[targetLang.selectedIndex].text }) });
    showResult(await handleResponse(response));
}

async function translateFile(file) {
    const form = new FormData();
    form.append("file", file);
    form.append("source_language", sourceLang.value);
    form.append("target_language_name", targetLang.options[targetLang.selectedIndex].text);
    showResult(await handleResponse(await fetch("/translate", {method: "POST", body: form})));
}

async function translateYouTube(url) {
    const response = await fetch("/translate-youtube", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({ url, source_language: sourceLang.value, target_language_name: targetLang.options[targetLang.selectedIndex].text }) });
    showResult(await handleResponse(response));
}

translateBtn.addEventListener("click", async () => {
    resetOutput();
    const text = textInput.value.trim();
    const url = youtubeInput.value.trim();
    const file = fileUpload.files[0];
    const inputs = [Boolean(text), Boolean(url), Boolean(file)].filter(Boolean).length;
    if (inputs === 0) { showError("Provide one input: text, file, or YouTube URL."); return; }
    if (inputs > 1) { showError("Please use only one input at a time."); return; }

    const type = text ? "text" : url ? "youtube" : "file";
    setProcessing(true, type);
    try {
        if (text) await translateText();
        else if (url) await translateYouTube(url);
        else await translateFile(file);
    } catch (error) { showError(error.message); }
    finally { setProcessing(false); }
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
                setProcessing(true, "file");
                try { await translateFile(new File([blob], "recording.webm", {type: "audio/webm"})); }
                catch (error) { showError(error.message); }
                finally { setProcessing(false); stream.getTracks().forEach(track => track.stop()); recorder = null; }
            };
            recorder.start();
            recordBtn.textContent = "⏹ Stop";
            recordingStatus.textContent = "Recording... click Stop when finished.";
        } else {
            recorder.stop();
            recordBtn.textContent = "🎙 Record";
            recordingStatus.textContent = "Processing recording...";
        }
    } catch { showError("Microphone access was denied or is unavailable."); }
});

copyBtn.addEventListener("click", async () => { if (translation.value) await navigator.clipboard.writeText(translation.value); });

playBtn.addEventListener("click", () => {
    if (!translation.value) return;
    speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(translation.value);
    utterance.lang = targetLang.value;
    speechSynthesis.speak(utterance);
});
