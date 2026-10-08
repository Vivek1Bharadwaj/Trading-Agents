import React from 'react';

export default function StatsBar({ stats }) {
    return (
        <div className="stats-bar">
            <div className="stat-item">
                <span className="stat-value">{stats.llm_calls || 0}</span>
                <span className="stat-label">LLM Calls</span>
            </div>
            <div className="stat-item">
                <span className="stat-value">{stats.tool_calls || 0}</span>
                <span className="stat-label">Tool Calls</span>
            </div>
            <div className="stat-item">
                <span className="stat-value">{stats.tokens?.input || 0}</span>
                <span className="stat-label">Input Tokens</span>
            </div>
            <div className="stat-item">
                <span className="stat-value">{stats.tokens?.output || 0}</span>
                <span className="stat-label">Output Tokens</span>
            </div>
            <div className="stat-item">
                <span className="stat-value">{stats.elapsed ? stats.elapsed.toFixed(1) : 0}s</span>
                <span className="stat-label">Elapsed Time</span>
            </div>
        </div>
    );
}
