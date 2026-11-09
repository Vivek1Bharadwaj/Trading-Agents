import { useState } from 'react';
import { Activity } from 'lucide-react';
import SetupWizard from './components/SetupWizard';
import AnalysisDashboard from './components/AnalysisDashboard';
import FinalReport from './components/FinalReport';
import { useAnalysisConfig } from './hooks/useAnalysisConfig';
import { useWebSocket } from './hooks/useWebSocket';
import './App.css';

function App() {
  const [view, setView] = useState('setup');
  const configHook = useAnalysisConfig();
  const wsHook = useWebSocket();

  const handleStart = () => {
    setView('analysis');
    wsHook.connect(configHook.config);
  };

  const handleComplete = () => {
    setView('report');
  };

  const handleRestart = () => {
    configHook.reset();
    wsHook.disconnect();
    setView('setup');
  };

  return (
    <div className="app-container">
      <header className="header">
        <Activity color="#bb0b0b" size={32} />
        <h1>Trading-Agents</h1>
      </header>
      
      <main className="main-content">
        {view === 'setup' && (
          <SetupWizard configHook={configHook} onStart={handleStart} />
        )}
        
        {view === 'analysis' && (
          <AnalysisDashboard 
            config={configHook.config} 
            wsHook={wsHook} 
            onComplete={handleComplete} 
          />
        )}

        {view === 'report' && (
          <FinalReport 
            config={configHook.config}
            wsHook={wsHook}
            onRestart={handleRestart} 
          />
        )}
      </main>

      <footer style={{
        textAlign: 'center',
        padding: '1rem',
        color: '#777777',
        fontSize: '0.8rem',
        borderTop: '1px solid #262626'
      }}>
        <a href="https://github.com/Vivek1Bharadwaj/Trading-Agents" style={{ color: '#bb0b0b', textDecoration: 'none' }}>Trading-Agents</a>
        {' '}by{' '}
        <a href="https://github.com/Vivek1Bharadwaj" style={{ color: '#bb0b0b', textDecoration: 'none' }}>Vivek Bharadwaj</a>
      </footer>
    </div>
  );
}

export default App;
