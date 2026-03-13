import numpy as np
import pandas as pd
import joblib
import tensorflow as tf
from sqlalchemy import text
from datetime import datetime, timedelta
import logging
import os
import json

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class NILMPredictor:
    def __init__(self, app=None):
        self.model = None
        self.mains_scaler = None
        self.fridge_scaler = None
        self.WINDOW_SIZE = 60
        self.FRIDGE_THRESHOLD = 20
        self.MODEL_PATH = "fridge_nilm_lstm.keras"
        self.MAINS_SCALER_PATH = "mains_scaler.pkl"
        self.FRIDGE_SCALER_PATH = "fridge_scaler.pkl"
        
        if app:
            self.init_app(app)
    
    def load_model_compat(self, model_path):
        """Load model with compatibility fixes for batch_shape issue"""
        try:
            # First attempt: Try normal loading
            return tf.keras.models.load_model(model_path, compile=False)
        except Exception as e:
            if 'batch_shape' in str(e):
                logger.info("Attempting to fix batch_shape compatibility issue...")
                try:
                    # Read the model file and fix the config
                    import h5py
                    with h5py.File(model_path, 'r') as f:
                        # Get model config
                        model_config = f.attrs.get('model_config')
                        if model_config:
                            if isinstance(model_config, bytes):
                                model_config = model_config.decode('utf-8')
                            config = json.loads(model_config)
                            
                            # Fix batch_shape in all InputLayer instances
                            if 'config' in config and 'layers' in config['config']:
                                for layer in config['config']['layers']:
                                    if layer.get('class_name') == 'InputLayer':
                                        layer_config = layer.get('config', {})
                                        if 'batch_shape' in layer_config:
                                            # Convert batch_shape to batch_input_shape
                                            layer_config['batch_input_shape'] = layer_config.pop('batch_shape')
                                            logger.info(f"Fixed InputLayer config: {layer_config}")
                            
                            # Recreate model with fixed config
                            model = tf.keras.models.model_from_json(json.dumps(config))
                            
                            # Load weights
                            weight_names = []
                            for name in f.attrs['weight_names']:
                                if isinstance(name, bytes):
                                    weight_names.append(name.decode('utf-8'))
                                else:
                                    weight_names.append(name)
                            
                            weights = [f[weight_name] for weight_name in weight_names]
                            model.set_weights(weights)
                            
                            logger.info("✅ Model loaded successfully with fixed config")
                            return model
                except Exception as e2:
                    logger.error(f"Failed to fix model config: {str(e2)}")
                    
                # Fallback: Try loading with safe_mode
                try:
                    return tf.keras.models.load_model(
                        model_path, 
                        compile=False,
                        safe_mode=False
                    )
                except Exception as e3:
                    logger.error(f"All loading attempts failed: {str(e3)}")
                    raise
            else:
                raise
    
    def init_app(self, app):
        """Initialize the NILM predictor with app context"""
        try:
            # Set CUDA to use CPU only
            os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
            
            # Get full paths
            model_path = os.path.join(app.root_path, self.MODEL_PATH)
            mains_scaler_path = os.path.join(app.root_path, self.MAINS_SCALER_PATH)
            fridge_scaler_path = os.path.join(app.root_path, self.FRIDGE_SCALER_PATH)
            
            # Check if files exist
            if not os.path.exists(model_path):
                logger.error(f"Model file not found at {model_path}")
                return
            if not os.path.exists(mains_scaler_path):
                logger.error(f"Scaler file not found at {mains_scaler_path}")
                return
            if not os.path.exists(fridge_scaler_path):
                logger.error(f"Scaler file not found at {fridge_scaler_path}")
                return
            
            logger.info(f"Loading scalers...")
            self.mains_scaler = joblib.load(mains_scaler_path)
            self.fridge_scaler = joblib.load(fridge_scaler_path)
            logger.info("✅ Scalers loaded successfully")
            
            logger.info(f"Loading model from: {model_path}")
            
            # Load model with compatibility fixes
            self.model = self.load_model_compat(model_path)
            
            logger.info("✅ NILM Predictor initialized successfully")
            
        except Exception as e:
            logger.error(f"Error initializing NILM Predictor: {str(e)}")
            import traceback
            traceback.print_exc()
            self.model = None
            self.mains_scaler = None
            self.fridge_scaler = None
    
    def get_mains_data(self, db_session, hours=24):
        """Fetch mains power data from database"""
        try:
            # Use a fixed date from 2013 since that's where your data is
            # Using August 4-5, 2013 which has about 24 hours of minute-level data
            query = text("""
                SELECT timestamp, active_power
                FROM mcb_readings_new
                ORDER BY timestamp ASC
            """)
            
            result = db_session.execute(query)
            data = result.fetchall()
            
            if not data or len(data) < self.WINDOW_SIZE + 1:
                logger.warning(f"Insufficient data. Need at least {self.WINDOW_SIZE + 1} samples, got {len(data) if data else 0}")
                return None
            
            df = pd.DataFrame(data, columns=['timestamp', 'active_power'])
            logger.info(f"Fetched {len(df)} records from 2013 data")
            
            return df
            
        except Exception as e:
            logger.error(f"Error fetching mains data: {str(e)}")
            return None
    
    def create_windows(self, data):
        """Create sliding windows for prediction"""
        X = []
        for i in range(len(data) - self.WINDOW_SIZE):
            X.append(data[i:i + self.WINDOW_SIZE])
        return np.array(X)
    
    def predict_fridge_power(self, db_session, hours=24):
        """Run NILM prediction"""
        try:
            # Check if model is loaded
            if self.model is None:
                logger.error("NILM Predictor not properly initialized - model is None")
                return None
            
            if self.mains_scaler is None or self.fridge_scaler is None:
                logger.error("NILM Predictor not properly initialized - scalers are None")
                return None
            
            # Get data from database
            df = self.get_mains_data(db_session, hours)
            if df is None:
                logger.warning("No data found")
                return None
            
            if len(df) < self.WINDOW_SIZE + 1:
                logger.warning(f"Insufficient data. Need at least {self.WINDOW_SIZE + 1} samples")
                return None
            
            # Extract power values
            mains_power = df["active_power"].values.reshape(-1, 1)
            
            # Scale the data
            mains_scaled = self.mains_scaler.transform(mains_power)
            
            # Create windows
            X_input = self.create_windows(mains_scaled)
            
            if len(X_input) == 0:
                logger.warning("No windows created - insufficient data")
                return None
            
            # Make predictions
            logger.info(f"Making predictions for {len(X_input)} windows...")
            y_pred_norm = self.model.predict(X_input, verbose=0)
            
            # Convert back to watts
            y_pred_watts = self.fridge_scaler.inverse_transform(y_pred_norm)
            
            # Apply threshold
            y_pred_final = np.where(y_pred_watts < self.FRIDGE_THRESHOLD, 0, y_pred_watts)
            
            # Align prediction length with original data
            fridge_prediction = np.zeros(len(mains_power))
            fridge_prediction[self.WINDOW_SIZE:] = y_pred_final.flatten()
            
            # Add predictions to dataframe
            df["predicted_fridge_power"] = fridge_prediction
            
            # Calculate statistics
            running_power = df[df["predicted_fridge_power"] > 0]["predicted_fridge_power"]
            
            stats = {
                'total_fridge_energy_kwh': float((df["predicted_fridge_power"].sum() / 1000) * (1/60)),
                'avg_fridge_power_w': float(running_power.mean()) if len(running_power) > 0 else 0,
                'max_fridge_power_w': float(df["predicted_fridge_power"].max()),
                'fridge_runtime_minutes': int((df["predicted_fridge_power"] > 0).sum()),
                'fridge_on_off_cycles': self.count_cycles(df["predicted_fridge_power"].values),
                'current_fridge_power': float(df["predicted_fridge_power"].iloc[-1]) if len(df) > 0 else 0
            }
            
            logger.info("Prediction complete")
            
            return {
                'predictions': df.to_dict('records'),
                'statistics': stats
            }
            
        except Exception as e:
            logger.error(f"Error in predict_fridge_power: {str(e)}")
            import traceback
            traceback.print_exc()
            return None
    
    def count_cycles(self, power_values, threshold=20):
        """Count on/off cycles of the fridge"""
        cycles = 0
        is_on = False
        
        for power in power_values:
            if power > threshold and not is_on:
                cycles += 1
                is_on = True
            elif power <= threshold and is_on:
                is_on = False
        
        return cycles

# Create global instance
nilm_predictor = NILMPredictor()