import React, { useEffect, useState } from 'react';
import AgentStatusGrid from './AgentStatusGrid';
import LiveFeed from './LiveFeed';
import StatsBar from './StatsBar';
import ReactMarkdown from 'react-markdown';
import { Activity, Clock, AlertTriangle, RotateCcw } from 'lucide-react';

export default function AnalysisDashboard({ config, wsHook, onComplete, onRestart }) {
    const { messages, agentStatuses, reportSections, stats, isConnected, connectionState, error, isComplete } = wsHook;
    const [elapsed, setElapsed] = useState(0);

    useEffect(() => {
        if (isComplete) {
            onComplete();
        }
    }, [isComplete, onComplete]);

    useEffect(() => {
        const timer = setInterval(() => {
            if (isConnected && !isComplete && !error) {
                setElapsed(e => e + 1);
            }
        }, 1000);
        return () => clearInterval(timer);
    }, [isConnected, isComplete, error]);

    const formatTime = (seconds) => {
        const m = Math.floor(seconds / 60);
        const s = seconds % 60;
        return `${m}:${s.toString().padStart(2, '0')}`;
    };

    const statusBadge = (() => {
        if (isConnected) {
            return {
                label: 'Running',
                bg: 'rgba(16, 185, 129, 0.1)',
                color: 'var(--bullish)',
                border: '#10b981',
            };
        }
        if (error || connectionState === 'error' || connectionState === 'disconnected') {
            return {
                label: connectionState === 'disconnected' && !error ? 'Disconnected' : 'Error',
                bg: 'rgba(239, 68, 68, 0.1)',
                color: 'var(--bearish)',
                border: '#ef4444',
            };
        }
        return {
            label: connectionState === 'reconnecting' ? 'Reconnecting...' : 'Connecting...',
            bg: 'rgba(245, 158, 11, 0.1)',
            color: '#f59e0b',
            border: '#f59e0b',
        };
    })();

    return (
        <div className="dashboard-container">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
                <h2 style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <Activity size={24} color="var(--accent)" />
                    Analyzing {config.ticker || 'Asset'}
                </h2>
                <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--text-muted)' }}>
                        <Clock size={16} /> {formatTime(elapsed)}
                    </div>
                    <span style={{ 
                        padding: '0.25rem 0.75rem', 
                        borderRadius: '1rem', 
                        fontSize: '0.875rem', 
                        backgroundColor: statusBadge.bg,
                        color: statusBadge.color,
                        border: `1px solid ${statusBadge.border}`
                    }}>
                        {statusBadge.label}
                    </span>
                </div>
            </div>

            {error && (
                <div style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    gap: '1rem',
                    padding: '0.875rem 1.25rem',
                    marginBottom: '1rem',
                    borderRadius: '0.75rem',
                    backgroundColor: 'rgba(239, 68, 68, 0.12)',
                    border: '1px solid #ef4444',
                    color: '#fecaca',
                }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', minWidth: 0 }}>
                        <AlertTriangle size={20} color="#ef4444" style={{ flexShrink: 0 }} />
                        <span style={{ fontSize: '0.925rem', wordBreak: 'break-word' }}>{error}</span>
                    </div>
                    {onRestart && (
                        <button className="btn-secondary" onClick={onRestart} style={{ flexShrink: 0, display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                            <RotateCcw size={15} /> Back to Setup
                        </button>
                    )}
                </div>
            )}

            <div className="dashboard-layout">
                <div className="glass-panel" style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
                    <div className="panel-header">Pipeline</div>
                    <div style={{ flex: 1, overflowY: 'auto' }}>
                        <AgentStatusGrid statuses={agentStatuses} />
                    </div>
                </div>

                <div className="glass-panel" style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
                    <div className="panel-header">Live Feed</div>
                    <LiveFeed messages={messages} />
                </div>

                <div className="glass-panel" style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
                    <div className="panel-header">Report Preview</div>
                    <div className="report-preview markdown-content">
                        {Object.keys(reportSections).length === 0 ? (
                            <div style={{ color: 'var(--text-muted)', textAlign: 'center', marginTop: '2rem' }}>
                                Awaiting report sections...
                            </div>
                        ) : (
                            Object.entries(reportSections).map(([section, content]) => (
                                <div key={section} className="report-section">
                                    <ReactMarkdown>{content}</ReactMarkdown>
                                </div>
                            ))
                        )}
                    </div>
                </div>
            </div>
            
            <StatsBar stats={stats} />
        </div>
    );
}
