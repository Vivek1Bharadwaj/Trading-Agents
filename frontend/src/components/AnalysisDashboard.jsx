import React, { useEffect, useState } from 'react';
import AgentStatusGrid from './AgentStatusGrid';
import LiveFeed from './LiveFeed';
import StatsBar from './StatsBar';
import ReactMarkdown from 'react-markdown';
import { Activity, Clock } from 'lucide-react';

export default function AnalysisDashboard({ config, wsHook, onComplete }) {
    const { messages, agentStatuses, reportSections, stats, isConnected, isComplete } = wsHook;
    const [elapsed, setElapsed] = useState(0);

    useEffect(() => {
        if (isComplete) {
            onComplete();
        }
    }, [isComplete, onComplete]);

    useEffect(() => {
        const timer = setInterval(() => {
            if (isConnected && !isComplete) {
                setElapsed(e => e + 1);
            }
        }, 1000);
        return () => clearInterval(timer);
    }, [isConnected, isComplete]);

    const formatTime = (seconds) => {
        const m = Math.floor(seconds / 60);
        const s = seconds % 60;
        return `${m}:${s.toString().padStart(2, '0')}`;
    };

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
                        backgroundColor: isConnected ? 'rgba(16, 185, 129, 0.1)' : 'rgba(239, 68, 68, 0.1)',
                        color: isConnected ? 'var(--bullish)' : 'var(--bearish)'
                    }}>
                        {isConnected ? 'Running' : 'Connecting...'}
                    </span>
                </div>
            </div>

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
