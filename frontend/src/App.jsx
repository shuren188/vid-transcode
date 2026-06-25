import React, { useState, useRef, useEffect, useCallback } from "react";
import "./App.css";

/* ─── Constants ─────────────────────────────────────────────── */
const API_BASE = "/api";

/* ─── Helpers ───────────────────────────────────────────────── */
function formatDuration(seconds) {
  if (!seconds || seconds <= 0) return "--:--";
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
}

function formatSize(mb) {
  if (!mb) return "--";
  return mb >= 1024 ? `${(mb / 1024).toFixed(2)} GB` : `${mb.toFixed(2)} MB`;
}

/* ─── App ────────────────────────────────────────────────────── */
export default function App() {
  const [phase, setPhase] = useState("upload");
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [fileId, setFileId] = useState(null);
  const [fileName, setFileName] = useState("");
  const [fileInfo, setFileInfo] = useState(null);
  const [jobId, setJobId] = useState(null);
  const [progress, setProgress] = useState(0);
  const [outputName, setOutputName] = useState(null);
  const [outputSize, setOutputSize] = useState(null);
  const [errorMsg, setErrorMsg] = useState("");
  const pollRef = useRef(null);
  const inputRef = useRef(null);
  useEffect(() => () => clearInterval(pollRef.current), []);

  const doUpload = useCallback(async (file) => {
    if (!file) return; setUploading(true); setErrorMsg("");
    const fd = new FormData(); fd.append("file", file);
    try {
      const res = await fetch(`${API_BASE}/upload`, { method: "POST", body: fd });
      if (!res.ok) { const err = await res.json(); throw new Error(err.detail || "Upload failed"); }
      const data = await res.json();
      setFileId(data.file_id); setFileName(data.filename); setFileInfo(data); setPhase("ready");
    } catch (e) { setErrorMsg(e.message); setPhase("error"); }
    finally { setUploading(false); }
  }, []);

  const handleFileSelect = useCallback((e) => { const f = e.target.files?.[0]; if (f) doUpload(f); }, [doUpload]);
  const handleDrop = useCallback((e) => { e.preventDefault(); setDragOver(false); const f = e.dataTransfer?.files?.[0]; if (f) doUpload(f); }, [doUpload]);
  const handleDragOver = useCallback((e) => { e.preventDefault(); setDragOver(true); }, []);
  const handleDragLeave = useCallback(() => setDragOver(false), []);

  const startTranscode = useCallback(async () => {
    setPhase("processing"); setProgress(0); setErrorMsg("");
    try {
      const res = await fetch(`${API_BASE}/transcode`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ file_id: fileId }),
      });
      if (!res.ok) { const err = await res.json(); throw new Error(err.detail || "Transcode failed"); }
      const data = await res.json();
      setJobId(data.job_id); startPolling(data.job_id);
    } catch (e) { setErrorMsg(e.message); setPhase("error"); }
  }, [fileId]);

  const startPolling = useCallback((id) => {
    clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const res = await fetch(`${API_BASE}/jobs/${id}`);
        if (!res.ok) { clearInterval(pollRef.current); return; }
        const data = await res.json();
        setProgress(data.progress);
        if (data.status === "completed") {
          clearInterval(pollRef.current); setOutputName(data.output_filename);
          setOutputSize(data.output_size_mb); setPhase("done");
        } else if (data.status === "failed") {
          clearInterval(pollRef.current); setErrorMsg(data.error || "Transcoding failed"); setPhase("error");
        }
      } catch { clearInterval(pollRef.current); }
    }, 800);
  }, []);

  const handleDownload = useCallback(() => {
    if (!jobId) return;
    const a = document.createElement("a");
    a.href = `${API_BASE}/download/${jobId}`;
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
  }, [jobId]);

  const handleReset = useCallback(() => {
    clearInterval(pollRef.current); setPhase("upload"); setUploading(false);
    setFileId(null); setFileName(""); setFileInfo(null);
    setJobId(null); setProgress(0); setOutputName(null); setOutputSize(null); setErrorMsg("");
  }, []);

  return (
    <div className="app">
      <div className="bg-grid" /><div className="bg-scanlines" /><div className="bg-glow" />
      <header className="header">
        <h1 className="logo">
          <span className="logo-icon">&#9674;</span>
          <span className="logo-text">vid-transcode</span>
          <span className="logo-sub">v0.1</span>
        </h1>
        <p className="tagline">&#35270;&#39057;&#36716;&#30721; &#183; &#19968;&#31186;&#21464; H.264</p>
      </header>
      <main className="main-card">
        <div className="card-border" />
        {phase === "upload" && (
          <section className="upload-section">
            <div className={`dropzone ${dragOver ? "dropzone--over" : ""} ${uploading ? "dropzone--loading" : ""}`}
              onDrop={handleDrop} onDragOver={handleDragOver} onDragLeave={handleDragLeave}
              onClick={() => inputRef.current?.click()}>
              <input ref={inputRef} type="file" accept=".mp4,.avi,.mov,.mkv,.webm,.flv,.wmv" hidden onChange={handleFileSelect} />
              {uploading ? (
                <div className="uploading-state"><div className="spinner" /><p>&#19978;&#20256;&#20013;...</p></div>
              ) : (
                <div className="upload-prompt">
                  <svg className="upload-icon" viewBox="0 0 48 48" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M24 34V14M14 24l10-10 10 10M8 38h32" /></svg>
                  <p className="upload-title">&#25302;&#25289;&#35270;&#39057;&#21040;&#27492;&#22788;</p>
                  <p className="upload-hint">&#25110;&#28857;&#20987;&#36873;&#25321;&#25991;&#20214; &#183; MP4 / AVI / MOV / MKV &#31561;</p>
                </div>
              )}
            </div>
          </section>
        )}
        {phase === "ready" && fileInfo && (
          <section className="ready-section">
            <div className="file-info">
              <div className="file-info-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" /></svg></div>
              <div className="file-info-text">
                <span className="file-name">{fileName}</span>
                <span className="file-meta">{fileInfo.width}&#215;{fileInfo.height} &#183; {formatDuration(fileInfo.duration)} &#183; {formatSize(fileInfo.size_mb)} &#183; {fileInfo.codec || "?"}</span>
              </div>
            </div>
            <p className="ready-hint">拼多多视频转码专用</p>
            <button className="btn-primary" onClick={startTranscode}>
              <span>&#24320;&#22987;&#36716;&#30721;</span>
              <svg className="btn-arrow" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polygon points="5 3 19 12 5 21 5 3" /></svg>
            </button>
          </section>
        )}
        {phase === "processing" && (
          <section className="progress-section">
            <div className="progress-header"><div className="progress-spinner" /><h2 className="section-title">&#36716;&#30721;&#20013;</h2></div>
            <div className="progress-info"><span className="progress-file">{fileName}</span></div>
            <div className="progress-bar-track">
              <div className="progress-bar-fill" style={{ width: `${progress}%` }} />
              <div className="progress-bar-glow" style={{ left: `${progress}%` }} />
            </div>
            <div className="progress-stats">
              <span className="progress-pct">{progress.toFixed(1)}%</span>
              <span className="progress-hint">H.264 &#183; &#21315;&#29275;&#20860;&#23481;&#26684;&#24335;</span>
            </div>
          </section>
        )}
        {phase === "done" && (
          <section className="done-section">
            <div className="done-icon"><svg viewBox="0 0 48 48" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="24" cy="24" r="20" /><polyline points="16 24 22 30 33 19" /></svg></div>
            <h2 className="section-title done-title">&#36716;&#30721;&#23436;&#25104;</h2>
            <div className="done-info"><span>{outputName}</span>{outputSize && <span className="done-size">{formatSize(outputSize)}</span>}</div>
            <div className="done-actions">
              <button className="btn-primary btn-download" onClick={handleDownload}>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3" /></svg>
                <span>&#19979;&#36733;&#25991;&#20214;</span>
              </button>
              <button className="btn-secondary" onClick={handleReset}>&#36716;&#25442;&#21478;&#19968;&#20010;</button>
            </div>
          </section>
        )}
        {phase === "error" && (
          <section className="error-section">
            <div className="error-icon"><svg viewBox="0 0 48 48" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="24" cy="24" r="20" /><line x1="16" y1="16" x2="32" y2="32" /><line x1="32" y1="16" x2="16" y2="32" /></svg></div>
            <h2 className="section-title error-title">&#20986;&#38169;&#20102;</h2>
            <p className="error-msg">{errorMsg}</p>
            <button className="btn-secondary" onClick={handleReset}>&#37325;&#35797;</button>
          </section>
        )}
      </main>
      <footer className="footer"><p>vid-transcode v0.2.3 &#183; &#22522;&#20110; FFmpeg &#183; H.264 / AVC</p></footer>
    </div>
  );
}
