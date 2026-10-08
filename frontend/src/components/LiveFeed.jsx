import React, { useEffect, useRef } from 'react';

export default function LiveFeed({ messages }) {
    const feedRef = useRef(null);

    useEffect(() => {
        if (feedRef.current) {
            feedRef.current.scrollTop = feedRef.current.scrollHeight;
        }
    }, [messages]);

    return (
        <div className="live-feed" ref={feedRef}>
            {messages.length === 0 ? (
                <div style={{ color: 'var(--text-muted)', textAlign: 'center', marginTop: '2rem' }}>
                    Waiting for events...
                </div>
            ) : (
                messages.map((msg, idx) => (
                    <div key={idx} className={`feed-item ${msg.msgType}`}>
                        <div className="feed-meta">
                            {msg.msgType === 'tool_call' ? `Tool Call: ${msg.tool}` : `Message from ${msg.sender}`}
                            {msg.timestamp && <span style={{ marginLeft: '1rem' }}>{msg.timestamp}</span>}
                        </div>
                        <div className="feed-content">
                            {msg.msgType === 'tool_call' ? (
                                <pre style={{ margin: 0, fontSize: '0.75rem', overflowX: 'auto', color: 'var(--text-muted)' }}>
                                    {JSON.stringify(msg.args, null, 2)}
                                </pre>
                            ) : (
                                msg.content
                            )}
                        </div>
                    </div>
                ))
            )}
        </div>
    );
}
