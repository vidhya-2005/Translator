const textInput = document.getElementById("text-input");
const fileUpload = document.getElementById("file-upload");
const wordUpload = document.getElementById("word-upload");
const youtubeInput = document.getElementById("youtube-link");
const sourceLang = document.getElementById("source-lang");
const targetLang = document.getElementById("target-lang");
const sourceSearch = document.getElementById("source-search");
const targetSearch = document.getElementById("target-search");
const swapLanguages = document.getElementById("swap-languages");
const translateBtn = document.getElementById("translate-btn");
const recordBtn = document.getElementById("record-btn");
const transcription = document.getElementById("transcription");
const translation = document.getElementById("translation");
const detectedLanguage = document.getElementById("detected-language");
const resultsSection = document.getElementById("results-section");
const downloadResult = document.getElementById("download-result");
const downloadResultBtn = document.getElementById("download-result-btn");
const downloadTitle = document.getElementById("download-title");
const downloadDetail = document.getElementById("download-detail");
const copyBtn = document.getElementById("copy-btn");
const playBtn = document.getElementById("play-btn");
const errorMessage = document.getElementById("error-message");
const recordingStatus = document.getElementById("recording-status");
const fileName = document.getElementById("file-name");
const wordFileName = document.getElementById("word-file-name");
const methodButtons = document.querySelectorAll(".input-method");
const panels = document.querySelectorAll(".input-panel");

let activeMethod = "text";
let recorder = null;
let chunks = [];
let recordedFile = null;
let currentSpeechAudio = null;
let speechCache = new Map();
let processingStartedAt = 0;
let processingTimer = null;

function showError(message) { errorMessage.textContent = message; }

function ensureProcessingUI() {
    if (document.getElementById("translation-processing")) return;
    const el = document.createElement("div");
    el.id = "translation-processing";
    el.setAttribute("role", "status");
    el.setAttribute("aria-live", "polite");
    el.innerHTML = `
        <div class="processing-spinner" aria-hidden="true"></div>
        <div class="processing-copy">
            <strong id="processing-title">Translating…</strong>
            <span id="processing-detail">Working on your translation. Please keep this page open.</span>
        </div>
    `;
    translateBtn.parentNode.insertBefore(el, translateBtn.nextSibling);

    const style = document.createElement("style");
    style.textContent = `
        #translation-processing { display:none; align-items:center; gap:12px; margin:12px 0 0; padding:12px 14px; border:1px solid rgba(100,100,100,.16); border-radius:12px; background:rgba(100,100,100,.045); }
        #translation-processing.visible { display:flex; }
        .processing-spinner { width:18px; height:18px; flex:0 0 18px; border:2px solid rgba(100,100,100,.2); border-top-color:currentColor; border-radius:50%; animation:translation-spin .75s linear infinite; }
        .processing-copy { display:flex; flex-direction:column; gap:2px; min-width:0; }
        .processing-copy strong { font-size:.94rem; line-height:1.25; }
        .processing-copy span { font-size:.82rem; opacity:.68; line-height:1.35; }
        @keyframes translation-spin { to { transform:rotate(360deg); } }
    `;
    document.head.appendChild(style);
}

function setProcessing(value, method = activeMethod) {
    ensureProcessingUI();
    const processingUI = document.getElementById("translation-processing");
    const title = document.getElementById("processing-title");
    const detail = document.getElementById("processing-detail");

    translateBtn.disabled = value;
    methodButtons.forEach(b => b.disabled = value);
    recordBtn.disabled = value;

    if (!value) {
        processingUI.classList.remove("visible");
        if (processingTimer) clearInterval(processingTimer);
        processingTimer = null;
        processingStartedAt = 0;
        return;
    }

    const labels = {
        text: ["Translating…", "Almost there."],
        file: ["Translating file…", "Larger files can take a little longer."],
        word: ["Translating document…", "Keeping the document formatting intact."],
        youtube: ["Translating video…", "Fetching and translating the spoken content."],
        record: ["Translating recording…", "Converting speech and translating it."],
    };
    const [label, hint] = labels[method] || labels.text;
    title.textContent = label;
    detail.textContent = hint;
    processingUI.classList.add("visible");
    processingStartedAt = Date.now();

    if (processingTimer) clearInterval(processingTimer);
    processingTimer = setInterval(() => {
        const elapsed = Math.floor((Date.now() - processingStartedAt) / 1000);
        if (elapsed >= 8) detail.textContent = "Still working — the translation service is processing your request.";
        if (elapsed >= 25) detail.textContent = "Still working — please keep this page open. No action is needed.";
    }, 1000);
}

function resetOutput() {
    resultsSection.classList.add("hidden");
    downloadResult.classList.add("hidden");
    transcription.value = "";
    translation.value = "";
    detectedLanguage.textContent = "Detected language: —";
    playBtn.disabled = true;
    showError("");
    if (currentSpeechAudio) { currentSpeechAudio.pause(); currentSpeechAudio = null; }
}

function clearInactiveInputs(method) {
    if (method !== "text") textInput.value = "";
    if (method !== "file") { fileUpload.value = ""; fileName.textContent = "PNG, JPG, PDF, audio or video"; }
    if (method !== "word") { wordUpload.value = ""; wordFileName.textContent = "Formatting, images and document structure will be preserved"; }
    if (method !== "youtube") youtubeInput.value = "";
    if (method !== "record") { recordedFile = null; if (!recorder) recordingStatus.textContent = "Click the button to start recording."; }
}

function setMethod(method) {
    activeMethod = method;
    clearInactiveInputs(method);
    methodButtons.forEach(b => b.classList.toggle("active", b.dataset.method === method));
    panels.forEach(p => p.classList.toggle("active", p.id === `panel-${method}`));
    panels.forEach(p => p.classList.toggle("hidden", p.id !== `panel-${method}`));
    resetOutput();
}

methodButtons.forEach(button => button.addEventListener("click", () => setMethod(button.dataset.method)));
fileUpload.addEventListener("change", () => { fileName.textContent = fileUpload.files[0]?.name || "PNG, JPG, PDF, audio or video"; resetOutput(); });
wordUpload.addEventListener("change", () => { wordFileName.textContent = wordUpload.files[0]?.name || "Formatting, images and document structure will be preserved"; resetOutput(); });
youtubeInput.addEventListener("input", resetOutput);
textInput.addEventListener("input", resetOutput);

function syncLanguageSearch(input, select) {
    const value = input.value.trim().toLowerCase();
    const exact = Array.from(select.options).find(o => o.text.toLowerCase() === value);
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
if (swapLanguages) swapLanguages.addEventListener("click", () => {
    if (sourceLang.value === "auto") return;
    const s = sourceLang.value;
    sourceLang.value = targetLang.value;
    targetLang.value = s;
    syncLanguageInput(sourceLang, sourceSearch);
    syncLanguageInput(targetLang, targetSearch);
});

function showResult(data) {
    transcription.value = data.transcription || "";
    translation.value = data.translation || "";
    detectedLanguage.textContent = `Detected language: ${data.detected_language_name || data.detected_language_code || "—"}`;
    playBtn.disabled = !data.translation;
    resultsSection.classList.remove("hidden");
    setTimeout(() => resultsSection.scrollIntoView({behavior:"smooth", block:"start"}), 80);
}

function showDownload(data, title, detail) {
    if (!data.download_url) throw new Error("The translated file was created, but no download link was returned.");
    downloadTitle.textContent = title;
    downloadDetail.textContent = detail;
    downloadResultBtn.href = data.download_url;
    downloadResultBtn.download = data.download_name || "translated_file";
    downloadResult.classList.remove("hidden");
    setTimeout(() => downloadResult.scrollIntoView({behavior:"smooth", block:"start"}), 80);
}

async function handleResponse(response) {
    const contentType = response.headers.get("content-type") || "";
    const data = contentType.includes("application/json") ? await response.json() : null;
    if (!response.ok) throw new Error(data?.error || `Request failed (${response.status}).`);
    if (!data) throw new Error(`Server returned an unexpected response (${response.status}).`);
    return data;
}

function languageName() { return targetLang.options[targetLang.selectedIndex].text; }

async function translateText() {
    const response = await fetch("/translate-text", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({text:textInput.value.trim(), source_language:sourceLang.value, target_language_name:languageName()})});
    showResult(await handleResponse(response));
}

async function translateFile(file) {
    const form = new FormData();
    form.append("file", file);
    form.append("source_language", sourceLang.value);
    form.append("target_language_name", languageName());
    const type = (file.type || "").toLowerCase();
    if (type.startsWith("audio/") || type.startsWith("video/")) {
        const data = await handleResponse(await fetch("/translate-media", {method:"POST", body:form}));
        showResult(data);
        showDownload(data, type.startsWith("video/") ? "Translated video ready" : "Translated audio ready", type.startsWith("video/") ? "The original video is retained with the translated audio track." : "Your translated audio is ready to download.");
        return;
    }
    if (type === "application/pdf" || type === "image/png" || type === "image/jpeg") {
        const data = await handleResponse(await fetch("/translate-visual", {method:"POST", body:form}));
        showResult(data);
        showDownload(data, type === "application/pdf" ? "Translated PDF ready" : "Translated image ready", "The translated visual file is ready to download.");
        return;
    }
    showResult(await handleResponse(await fetch("/translate", {method:"POST", body:form})));
}

async function translateYouTube(url) {
    const response = await fetch("/translate-youtube", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({url, source_language:sourceLang.value, target_language_name:languageName()})});
    showResult(await handleResponse(response));
}

async function translateWord(file) {
    const form = new FormData();
    form.append("file", file);
    form.append("source_language", sourceLang.value);
    form.append("target_language_name", languageName());
    const data = await handleResponse(await fetch("/translate-word", {method:"POST", body:form}));
    showResult(data);
    showDownload(data, "Translated Word document ready", "The translated .docx is ready to download. Original document formatting and images are retained.");
}

translateBtn.addEventListener("click", async () => {
    resetOutput();
    try {
        setProcessing(true, activeMethod);
        if (activeMethod === "text") {
            if (!textInput.value.trim()) throw new Error("Enter some text to translate.");
            await translateText();
        } else if (activeMethod === "file") {
            if (!fileUpload.files[0]) throw new Error("Choose a file to translate.");
            await translateFile(fileUpload.files[0]);
        } else if (activeMethod === "youtube") {
            if (!youtubeInput.value.trim()) throw new Error("Paste a YouTube URL.");
            await translateYouTube(youtubeInput.value.trim());
        } else if (activeMethod === "word") {
            if (!wordUpload.files[0]) throw new Error("Choose a .docx Word document.");
            await translateWord(wordUpload.files[0]);
        } else {
            if (!recordedFile) throw new Error("Record your voice first.");
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
            const stream = await navigator.mediaDevices.getUserMedia({audio:true});
            recorder = new MediaRecorder(stream);
            chunks = [];
            recorder.ondataavailable = e => { if (e.data.size) chunks.push(e.data); };
            recorder.onstop = () => {
                const blob = new Blob(chunks, {type:"audio/webm"});
                recordedFile = new File([blob], "recording.webm", {type:"audio/webm"});
                recordingStatus.textContent = "Recording ready. Click Translate to continue.";
                recordBtn.textContent = "Record again";
                stream.getTracks().forEach(t => t.stop());
                recorder = null;
            };
            recorder.start();
            recordBtn.textContent = "Stop recording";
            recordingStatus.textContent = "Recording... click Stop when finished.";
        } else {
            recorder.stop();
        }
    } catch (_) {
        showError("Microphone access was denied or is unavailable.");
    }
});

copyBtn.addEventListener("click", async () => { if (translation.value) await navigator.clipboard.writeText(translation.value); });

playBtn.addEventListener("click", async () => {
    const text = translation.value.trim();
    if (!text) return;
    if (currentSpeechAudio) {
        currentSpeechAudio.pause();
        currentSpeechAudio = null;
        playBtn.disabled = false;
        return;
    }
    playBtn.disabled = true;
    showError("");
    try {
        let audioUrl = speechCache.get(`${languageName()}\n${text}`);
        if (!audioUrl) {
            const response = await fetch("/tts", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({text, language_name:languageName()})});
            if (!response.ok) {
                let message = `Speech generation failed (${response.status}).`;
                try { message = (await response.json()).error || message; } catch (_) {}
                throw new Error(message);
            }
            const blob = await response.blob();
            audioUrl = URL.createObjectURL(blob);
            speechCache.set(`${languageName()}\n${text}`, audioUrl);
        }
        currentSpeechAudio = new Audio(audioUrl);
        currentSpeechAudio.onended = () => { currentSpeechAudio = null; playBtn.disabled = false; };
        currentSpeechAudio.onerror = () => { currentSpeechAudio = null; playBtn.disabled = false; showError("Could not play the generated translation audio."); };
        await currentSpeechAudio.play();
    } catch (error) {
        currentSpeechAudio = null;
        playBtn.disabled = false;
        showError(error.message);
    }
});
