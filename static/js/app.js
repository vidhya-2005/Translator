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
const wordResult = document.getElementById("word-result");
const downloadWordBtn = document.getElementById("download-word-btn");
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
const processingPanel = document.getElementById("processing-panel");
const methodButtons = document.querySelectorAll(".input-method");
const panels = document.querySelectorAll(".input-panel");

let activeMethod = "text";
let recorder = null;
let chunks = [];
let recordedFile = null;
let currentSpeechAudio = null;
let speechCache = new Map();

function showError(message) { errorMessage.textContent = message; }
function resetOutput() {
    resultsSection.classList.add("hidden"); wordResult.classList.add("hidden"); downloadResult.classList.add("hidden");
    transcription.value = ""; translation.value = ""; detectedLanguage.textContent = "Detected language: —"; playBtn.disabled = true; showError("");
    if (currentSpeechAudio) { currentSpeechAudio.pause(); currentSpeechAudio = null; }
}
function setMethod(method) {
    activeMethod = method; methodButtons.forEach(b => b.classList.toggle("active", b.dataset.method === method)); panels.forEach(p => p.classList.toggle("active", p.id === `panel-${method}`)); panels.forEach(p => p.classList.toggle("hidden", p.id !== `panel-${method}`)); resetOutput();
}
methodButtons.forEach(button => button.addEventListener("click", () => setMethod(button.dataset.method)));
fileUpload.addEventListener("change", () => { fileName.textContent = fileUpload.files[0]?.name || "PNG, JPG, PDF, audio or video"; resetOutput(); });
wordUpload.addEventListener("change", () => { wordFileName.textContent = wordUpload.files[0]?.name || "Formatting, images and document structure will be preserved"; resetOutput(); });
youtubeInput.addEventListener("input", resetOutput); textInput.addEventListener("input", resetOutput);
function syncLanguageSearch(input, select) { const value = input.value.trim().toLowerCase(); const exact = Array.from(select.options).find(o => o.text.toLowerCase() === value); if (exact) select.value = exact.value; }
function syncLanguageInput(select, input) { const option = select.options[select.selectedIndex]; input.value = option ? option.text : ""; }
sourceSearch.addEventListener("input", () => syncLanguageSearch(sourceSearch, sourceLang)); targetSearch.addEventListener("input", () => syncLanguageSearch(targetSearch, targetLang));
sourceSearch.addEventListener("change", () => syncLanguageSearch(sourceSearch, sourceLang)); targetSearch.addEventListener("change", () => syncLanguageSearch(targetSearch, targetLang));
sourceLang.addEventListener("change", () => syncLanguageInput(sourceLang, sourceSearch)); targetLang.addEventListener("change", () => syncLanguageInput(targetLang, targetSearch));
if (swapLanguages) swapLanguages.addEventListener("click", () => { if (sourceLang.value === "auto") return; const s = sourceLang.value; sourceLang.value = targetLang.value; targetLang.value = s; syncLanguageInput(sourceLang, sourceSearch); syncLanguageInput(targetLang, targetSearch); });
function setProcessing(value) { translateBtn.disabled = value; methodButtons.forEach(b => b.disabled = value); recordBtn.disabled = value; if (processingPanel) processingPanel.classList.add("hidden"); }
function showResult(data) { transcription.value = data.transcription || ""; translation.value = data.translation || ""; detectedLanguage.textContent = `Detected language: ${data.detected_language_name || data.detected_language_code || "—"}`; playBtn.disabled = !data.translation; resultsSection.classList.remove("hidden"); setTimeout(() => resultsSection.scrollIntoView({behavior:"smooth",block:"start"}),80); }
function showDownload(data, title, detail) { if (!data.download_url) throw new Error("The translated file was created, but no download link was returned."); downloadTitle.textContent = title; downloadDetail.textContent = detail; downloadResultBtn.href = data.download_url; downloadResultBtn.download = data.download_name || "translated_file"; downloadResult.classList.remove("hidden"); setTimeout(() => downloadResult.scrollIntoView({behavior:"smooth",block:"start"}),80); }
async function handleResponse(response) { const contentType = response.headers.get("content-type") || ""; const data = contentType.includes("application/json") ? await response.json() : null; if (!response.ok) throw new Error(data?.error || `Request failed (${response.status}).`); if (!data) throw new Error(`Server returned an unexpected response (${response.status}).`); return data; }
function languageName() { return targetLang.options[targetLang.selectedIndex].text; }
async function translateText() { const response = await fetch("/translate-text", {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({text:textInput.value.trim(),source_language:sourceLang.value,target_language_name:languageName()})}); showResult(await handleResponse(response)); }
async function translateFile(file) {
    const form = new FormData(); form.append("file", file); form.append("source_language", sourceLang.value); form.append("target_language_name", languageName()); const type = (file.type || "").toLowerCase();
    if (type.startsWith("audio/") || type.startsWith("video/")) { const data = await handleResponse(await fetch("/translate-media", {method:"POST",body:form})); showResult(data); showDownload(data, type.startsWith("video/") ? "Translated video ready" : "Translated audio ready", type.startsWith("video/") ? "The original video is retained with the translated audio track." : "Your translated audio is ready to download."); return; }
    if (type === "application/pdf" || type === "image/png" || type === "image/jpeg") { const data = await handleResponse(await fetch("/translate-visual", {method:"POST",body:form})); showResult(data); showDownload(data, type === "application/pdf" ? "Translated PDF ready" : "Translated image ready", "The translated visual file is ready to download."); return; }
    showResult(await handleResponse(await fetch("/translate", {method:"POST",body:form})));
}
async function translateYouTube(url) { const response = await fetch("/translate-youtube", {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({url,source_language:sourceLang.value,target_language_name:languageName()})}); showResult(await handleResponse(response)); }
async function translateWord(file) {
    const form = new FormData(); form.append("file", file); form.append("source_language", sourceLang.value); form.append("target_language_name", languageName()); const response = await fetch("/translate-word", {method:"POST",body:form});
    if (!response.ok) { let message = `Word translation failed (${response.status}).`; try { message = (await response.json()).error || message; } catch (_) {} throw new Error(message); }
    const blob = await response.blob(); const disposition = response.headers.get("Content-Disposition") || ""; const match = disposition.match(/filename="?([^\"]+)"?/i); const filename = match ? match[1] : "translated_document.docx"; const url = URL.createObjectURL(blob);
    downloadWordBtn.onclick = () => { const link = document.createElement("a"); link.href = url; link.download = filename; document.body.appendChild(link); link.click(); link.remove(); }; wordResult.classList.remove("hidden"); setTimeout(() => wordResult.scrollIntoView({behavior:"smooth",block:"start"}),80);
}
translateBtn.addEventListener("click", async () => {
    resetOutput();
    try {
        if (activeMethod === "text") { if (!textInput.value.trim()) throw new Error("Enter some text to translate."); setProcessing(true); await translateText(); }
        else if (activeMethod === "file") { if (!fileUpload.files[0]) throw new Error("Choose a file to translate."); setProcessing(true); await translateFile(fileUpload.files[0]); }
        else if (activeMethod === "youtube") { if (!youtubeInput.value.trim()) throw new Error("Paste a YouTube URL."); setProcessing(true); await translateYouTube(youtubeInput.value.trim()); }
        else if (activeMethod === "word") { if (!wordUpload.files[0]) throw new Error("Choose a .docx Word document."); setProcessing(true); await translateWord(wordUpload.files[0]); }
        else { if (!recordedFile) throw new Error("Record your voice first."); setProcessing(true); await translateFile(recordedFile); }
    } catch (error) { showError(error.message); } finally { setProcessing(false); }
});
recordBtn.addEventListener("click", async () => {
    try {
        if (!recorder) { resetOutput(); const stream = await navigator.mediaDevices.getUserMedia({audio:true}); recorder = new MediaRecorder(stream); chunks = []; recorder.ondataavailable = e => { if (e.data.size) chunks.push(e.data); }; recorder.onstop = () => { const blob = new Blob(chunks,{type:"audio/webm"}); recordedFile = new File([blob],"recording.webm",{type:"audio/webm"}); recordingStatus.textContent="Recording ready. Click Translate to continue."; recordBtn.textContent="Record again"; stream.getTracks().forEach(t=>t.stop()); recorder=null; }; recorder.start(); recordBtn.textContent="Stop recording"; recordingStatus.textContent="Recording... click Stop when finished."; }
        else recorder.stop();
    } catch (_) { showError("Microphone access was denied or is unavailable."); }
});
copyBtn.addEventListener("click", async () => { if (translation.value) await navigator.clipboard.writeText(translation.value); });
playBtn.addEventListener("click", async () => {
    const text = translation.value.trim(); if (!text) return;
    if (currentSpeechAudio) { currentSpeechAudio.pause(); currentSpeechAudio = null; playBtn.disabled = false; return; }
    playBtn.disabled = true; showError("");
    try {
        let audioUrl = speechCache.get(text);
        if (!audioUrl) {
            const response = await fetch("/tts", {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({text,language_name:languageName()})});
            if (!response.ok) { let message = `Speech generation failed (${response.status}).`; try { message = (await response.json()).error || message; } catch (_) {} throw new Error(message); }
            const blob = await response.blob(); audioUrl = URL.createObjectURL(blob); speechCache.set(text, audioUrl);
        }
        currentSpeechAudio = new Audio(audioUrl);
        currentSpeechAudio.onended = () => { currentSpeechAudio = null; playBtn.disabled = false; };
        currentSpeechAudio.onerror = () => { currentSpeechAudio = null; playBtn.disabled = false; showError("Could not play the generated translation audio."); };
        await currentSpeechAudio.play();
    } catch (error) { currentSpeechAudio = null; playBtn.disabled = false; showError(error.message); }
});
