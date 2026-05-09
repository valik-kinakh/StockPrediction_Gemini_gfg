import { useState } from 'react';
import './App.css';
import OptionsLab from './OptionsLab';
import PredictionForm from './PredictionForm';
import PredictionResult from './PredictionResult';
import Scanner from './Scanner';
import TabBar from './TabBar';

function App() {
  const [tab, setTab] = useState('forecast');

  // Shared state across tabs so picking AAPL+21 in Forecast carries over.
  const [ticker, setTicker] = useState('AAPL');
  const [horizon, setHorizon] = useState(21);

  // The Forecast tab also caches the last response so toggling tabs and
  // returning shows the previous chart instead of re-fetching.
  const [prediction, setPrediction] = useState(null);

  return (
    <div className="App">
      <header className="App-header">
        <h1>ML-Based Stock Market Forecast Generator</h1>
        <p className="App-subtitle">
          Naive · GBM · ARIMA · Chronos-Bolt · with options-context regime detection
        </p>
        <TabBar active={tab} onChange={setTab} />
      </header>

      {tab === 'forecast' && (
        prediction ? (
          <PredictionResult
            data={prediction}
            onReset={() => setPrediction(null)}
          />
        ) : (
          <PredictionForm
            ticker={ticker}
            setTicker={setTicker}
            horizon={horizon}
            setHorizon={setHorizon}
            onResult={setPrediction}
          />
        )
      )}

      {tab === 'options' && (
        <OptionsLab ticker={ticker} setTicker={setTicker} horizon={horizon} setHorizon={setHorizon} />
      )}

      {tab === 'scanner' && (
        <Scanner horizon={horizon} setHorizon={setHorizon} />
      )}
    </div>
  );
}

export default App;
