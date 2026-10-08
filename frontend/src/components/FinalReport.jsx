import React from 'react';
import ReactMarkdown from 'react-markdown';
import { Download, RefreshCcw } from 'lucide-react';

export default function FinalReport({ config, wsHook, onRestart }) {
    const { reportSections, rating } = wsHook;

    const downloadMarkdown = () => {
        const fullReport = Object.values(reportSections).join('\n\n---\n\n');
        const blob = new Blob([fullReport], { type: 'text/markdown' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${config.ticker}-analysis.md`;
        a.click();
        URL.revokeObjectURL(url);
    };

    const ratingClass = rating ? rating.toLowerCase() : 'neutral';

    return (
        <div className="final-report glass-panel">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2rem' }}>
                <h2>Analysis Report: {config.ticker}</h2>
                <div style={{ display: 'flex', gap: '1rem' }}>
                    <button className="btn-secondary" onClick={downloadMarkdown} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                        <Download size={16} /> Download
                    </button>
                    <button className="btn-primary" onClick={onRestart} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                        <RefreshCcw size={16} /> New Analysis
                    </button>
                </div>
            </div>

            {rating && (
                <div className={`rating-badge ${ratingClass}`}>
                    {rating}
                </div>
            )}

            <div className="markdown-content">
                {Object.entries(reportSections).map(([section, content]) => (
                    <div key={section} className="report-section">
                        <ReactMarkdown>{content}</ReactMarkdown>
                    </div>
                ))}
            </div>
        </div>
    );
}
