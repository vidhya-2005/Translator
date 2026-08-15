const textInput = document.getElementById("text-input");
const fileUpload = document.getElementById("file-upload");
const wordUpload = document.getElementById("word-upload");
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
const resultsSection = document.getElementById("results-section");
const wordResult = document.getElementById("word-result");
const downloadWordBtn = document.getElementById("download-word-btn");
const copyBtn = document.getElementById("copy-btn");
const playBtn = document.getElementById("play-btn");
const errorMessage = document.getElementById("error-message");
const recordingStatus = document.getElementById("recording-status");
const fileName = document.getElementById("file-name");
const wordFileName = document.getElementById("word-file-name");
const processingPanel = document.getElementById("processing-panel");
const processingTitle = document.getElementById("processing-title");
const processingDetail = document.getElementById("processing-detail");
const steps = [document.getElementById("step-1"), document.getElementById("step-2"), document.getElementById("step-3")];
const swapLanguages = document.getElementById("swap-languages");
const methodButtons = document.querySelectorAll(".input-method");
const panels = document.querySelectorAll(".input-panel");

let activeMethod = "text";
let recorder = null;
let chunks = [];
let recordedFile = null;

function showError(message) { errorMessage.textContent = message; }

function resetOutput() {
    resultsSection.classList.add("hidden");
    wordResult.classList.add("hidden");
    transcription.value = "";
    translation.value = "";
    detectedLanguage.textContent = "Detected language: —";
    playBtn.disabled = true;
    showError("");
}

function setMethod(method) {
    activeMethod = method;
    methodButtons.forEach(button => button.classList.toggle("active", button.dataset.method === method));
    panels.forEach(panel => panel.classList.toggle("active", panel.id === `panel-${method}`));
    panels.forEach(panel => panel.classList.toggle("hidden", panel.id !== `panel-${method}`));
    resetOutput();
}

methodButtons.forEach(button => button.addEventListener("click", () => setMethod(button.dataset.method)));

fileUpload.addEventListener("change", () => {
    fileName.textContent = fileUpload.files[0]?.name || "PNG, JPG, PDF, audio or video";
    resetOutput();
});
wordUpload.addEventListener("change", () => {
    wordFileName.textContent = wordUpload.files[0]?.name || "Formatting, images and document structure will be preserved";
    resetOutput();
});
youtubeInput.addEventListener("input", resetOutput);
textInput.addEventListener("input", resetOutput);

function syncLanguageSearch(input, select) {
    const value = input.value.trim().toLowerCase();
    const exact = Array.from(select.options).find(option => option.text.toLowerCase() === value);
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
swapLanguages.addEventListener("click", () => {
    if (sourceLang.value === "auto") return;
    const sourceValue = sourceLang.value;
    sourceLang.value = targetLang.value;
    targetLang.value = sourceValue;
    syncLanguageInput(sourceLang, sourceSearch);
    syncLanguageInput(targetLang, targetSearch);
});

function setProcessing(value, type = "text") {
    processingPanel.classList.toggle("hidden", !value);
    translateBtn.disabled = value;
    methodButtons.forEach(button => button.disabled = value);
    recordBtn.disabled = value;
    if (!value) return;
    const labels = {
        text: ["Translating text", "Reading your text and preparing the translation..."],
        file: ["Processing your file", "Extracting content and preparing the translation..."],
        youtube: ["Analyzing YouTube video", "Sending the public video to Gemini for analysis..."],
        record: ["Processing your recording", "Transcribing your recorded speech..."],
        word: ["Translating Word document", "Translating text while preserving document structure and formatting..."]
    };
    const [title, detail] = labels[type] || labels.text;
    processingTitle.textContent = title;
    processingDetail.textContent = detail;
    steps.forEach((step, index) => step.classList.toggle("active", index === 0));
    setTimeout(() => {
        if (processingPanel.classList.contains("hidden")) return;
        steps[1].classList.add("active");
        processingDetail.textContent = type === "word" ? "Translating document text and keeping formatting intact..." : "Detecting language and understanding the content...";
    }, 350);
    setTimeout(() => {
        if (processingPanel.classList.contains("hidden")) return;
        steps[2].classList.add("active");
        processingDetail.textContent = type === "word" ? "Creating your downloadable Word document..." : "Generating your translation...";
    }, 1100);
}

function showResult(data) {
    transcription.value = data.transcription || "";
    translation.value = data.translation || "";
    const language = data.detected_language_name || data.detected_language_code || "—";
    detectedLanguage.textContent = `Detected language: ${language}`;
    playBtn.disabled = !data.translation;
    resultsSection.classList.remove("hidden");
    setTimeout(() => resultsSection.scrollIntoView({behavior: "smooth", block: "start"}), 80);
}

async function handleResponse(response) {
    const contentType = response.headers.get("content-type") || "";
    if (!contentType.includes("application/json")) throw new Error(`Server returned an unexpected response (${response.status}).`);
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Request failed.");
    return data;
}
async function translateText() {
    const response = await fetch("/translate-text", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({text: textInput.value.trim(), source_language: sourceLang.value, target_language_name: targetLang.options[targetLang.selectedIndex].text})});
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
    const response = await fetch("/translate-youtube", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({url, source_language: sourceLang.value, target_language_name: targetLang.options[targetLang.selectedIndex].text})});
    showResult(await handleResponse(response));
}
async function translateWord(file) {
    const form = new FormData();
    form.append("file", file);
    form.append("source_language", sourceLang.value);
    form.append("target_language_name", targetLang.options[targetLang.selectedIndex].text);
    const response = await fetch("/translate-word", {method: "POST", body: form});
    if (!response.ok) {
        let message = `Word translation failed (${response.status}).`;
        try { const data = await response.json(); message = data.error || message; } catch (_) {}
        throw new Error(message);
    }
    const blob = await response.blob();
    const disposition = response.headers.get("Content-Disposition") || "";
    const match = disposition.match(/filename="?([^\"]+)"?/i);
    const filename = match ? match[1] : "translated_document.docx";
    const url = URL.createObjectURL(blob);
    downloadWordBtn.onclick = () => {
        const link = document.createElement("a");
        link.href = url;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        link.remove();
    };
    wordResult.classList.remove("hidden");
    setTimeout(() => wordResult.scrollIntoView({behavior: "smooth", block: "start"}), 80);
}

translateBtn.addEventListener("click", async () => {
    resetOutput();
    try {
        if (activeMethod === "text") {
            if (!textInput.value.trim()) throw new Error("Enter some text to translate.");
            setProcessing(true, "text");
            await translateText();
        } else if (activeMethod === "file") {
            if (!fileUpload.files[0]) throw new Error("Choose a file to translate.");
            setProcessing(true, "file");
            await translateFile(fileUpload.files[0]);
        } else if (activeMethod === "youtube") {
            if (!youtubeInput.value.trim()) throw new Error("Paste a YouTube URL.");
            setProcessing(true, "youtube");
            await translateYouTube(youtubeInput.value.trim());
        } else if (activeMethod === "word") {
            if (!wordUpload.files[0]) throw new Error("Choose a .docx Word document.");
            setProcessing(true, "word");
            await translateWord(wordUpload.files[0]);
        } else {
            if (!recordedFile) throw new Error("Record your voice first.");
            setProcessing(true, "record");
            await translateFile(recordedFile);
        }
    } catch (error) {
        showError(error.message);
    } finally {
        setProcessing(false);
    }
});

recordBtn.addEventListener("click", async () => {
    try {
        if (!recorder) {
            resetOutput();
            const stream = await navigator.mediaDevices.getUserMedia({audio: true});
            recorder = new MediaRecorder(stream);
            chunks = [];
            recorder.ondataavailable = event => { if (event.data.size) chunks.push(event.data); };
            recorder.onstop = () => {
                const blob = new Blob(chunks, {type: "audio/webm"});
                recordedFile = new File([blob], "recording.webm", {type: "audio/webm"});
                recordingStatus.textContent = "Recording ready. Click Translate to continue.";
                recordBtn.textContent = "Record again";
                stream.getTracks().forEach(track => track.stop());
                recorder = null;
            };
            recorder.start();
            recordBtn.textContent = "Stop recording";
            recordingStatus.textContent = "Recording... click Stop when finished.";
        } else {
            recorder.stop();
        }
    } catch (_) { showError("Microphone access was denied or is unavailable."); }
});

copyBtn.addEventListener("click", async () => { if (translation.value) await navigator.clipboard.writeText(translation.value); });
playBtn.addEventListener("click", () => {
    if (!translation.value) return;
    speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(translation.value);
    utterance.lang = targetLang.value;
    speechSynthesis.speak(utterance);
});
