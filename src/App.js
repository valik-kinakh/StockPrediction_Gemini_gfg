import { useState } from 'react';
import './App.css';
import PredictionForm from './PredictionForm';
import PredictionResult from './PredictionResult';

function App() {
  const [prediction, setPrediction] = useState(null);

  return (
    <div className="App">
      <header className="App-header">
        <h1>Stock Prediction</h1>
      </header>
      {prediction ? (
        <PredictionResult
          data={prediction}
          onReset={() => setPrediction(null)}
        />
      ) : (
        <PredictionForm onResult={setPrediction} />
      )}
    </div>
  );
}

export default App;
