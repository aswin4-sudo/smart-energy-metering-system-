import numpy as np
import pandas as pd
import joblib
import tensorflow as tf
from sqlalchemy import text
import logging
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class NILMPredictor:
    def __init__(self, app=None):
        # Fridge models
        self.model = None
        self.mains_scaler = None
        self.fridge_scaler = None
        
        # AC models
        self.ac_model = None
        self.ac_mains_scaler = None
        self.ac_scaler = None
        
        # Parameters - Different window sizes for each model
        self.FRIDGE_WINDOW_SIZE = 60
        self.AC_WINDOW_SIZE = 120
        self.FRIDGE_THRESHOLD = 20
        self.AC_THRESHOLD = 100
        
        # File paths
        self.MODEL_PATH = "fridge_nilm_lstm.keras"
        self.MAINS_SCALER_PATH = "mains_scaler.pkl"
        self.FRIDGE_SCALER_PATH = "fridge_scaler.pkl"
        self.AC_MODEL_PATH = "ac1_full_model.keras"
        self.AC_MAINS_SCALER_PATH = "mains_scaler_ac.pkl"
        self.AC_SCALER_PATH = "ac_scaler.pkl"
        
        if app:
            self.init_app(app)
    
    def load_ac_model_safe(self, model_path):
        """Load AC model while ignoring quantization_config parameter"""
        try:
            logger.info("Attempting to load AC model with safe_mode=True...")
            return tf.keras.models.load_model(model_path, compile=False, safe_mode=True)
        except Exception as e:
            error_msg = str(e)
            logger.warning(f"Safe mode failed: {error_msg[:100]}")
            
            if 'quantization_config' in error_msg:
                logger.info("Detected quantization_config issue, applying patch...")
                
                from tensorflow.keras import layers
                original_dense_init = layers.Dense.__init__
                
                def patched_dense_init(self_obj, *args, **kwargs):
                    kwargs.pop('quantization_config', None)
                    original_dense_init(self_obj, *args, **kwargs)
                
                try:
                    layers.Dense.__init__ = patched_dense_init
                    model = tf.keras.models.load_model(model_path, compile=False)
                    logger.info("✅ AC model loaded successfully with patched Dense layer!")
                    return model
                finally:
                    layers.Dense.__init__ = original_dense_init
            
            try:
                logger.info("Trying to load with custom_objects...")
                return tf.keras.models.load_model(model_path, compile=False, custom_objects={})
            except Exception as e2:
                logger.error(f"Custom objects loading failed: {str(e2)[:100]}")
                raise
    
    def init_app(self, app):
        """Initialize the NILM predictor"""
        try:
            os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
            
            model_path = os.path.join(app.root_path, self.MODEL_PATH)
            mains_scaler_path = os.path.join(app.root_path, self.MAINS_SCALER_PATH)
            fridge_scaler_path = os.path.join(app.root_path, self.FRIDGE_SCALER_PATH)
            ac_model_path = os.path.join(app.root_path, self.AC_MODEL_PATH)
            ac_mains_scaler_path = os.path.join(app.root_path, self.AC_MAINS_SCALER_PATH)
            ac_scaler_path = os.path.join(app.root_path, self.AC_SCALER_PATH)
            
            # ========== LOAD FRIDGE ==========
            logger.info("=" * 50)
            logger.info("📦 Loading FRIDGE components...")
            
            self.mains_scaler = joblib.load(mains_scaler_path)
            self.fridge_scaler = joblib.load(fridge_scaler_path)
            logger.info("✅ FRIDGE scalers loaded")
            
            self.model = tf.keras.models.load_model(model_path, compile=False)
            logger.info("✅ FRIDGE model loaded")
            
            # ========== LOAD AC ==========
            logger.info("=" * 50)
            logger.info("📦 Loading AC components...")
            
            if os.path.exists(ac_mains_scaler_path) and os.path.exists(ac_scaler_path):
                self.ac_mains_scaler = joblib.load(ac_mains_scaler_path)
                self.ac_scaler = joblib.load(ac_scaler_path)
                logger.info("✅ AC scalers loaded")
            
            if os.path.exists(ac_model_path):
                try:
                    logger.info(f"Attempting to load AC model from: {ac_model_path}")
                    self.ac_model = self.load_ac_model_safe(ac_model_path)
                    logger.info("✅ AC model loaded successfully!")
                    
                    # Test the model
                    test_input = np.random.randn(1, self.AC_WINDOW_SIZE, 1)
                    test_output = self.ac_model.predict(test_input, verbose=0)
                    logger.info(f"✅ AC model test passed! Output: {test_output[0][0]:.2f}")
                except Exception as e:
                    logger.warning(f"⚠️ AC model failed: {str(e)[:150]}")
                    self.ac_model = None
            else:
                logger.warning(f"⚠️ AC model file not found: {ac_model_path}")
                self.ac_model = None
            
            # ========== FINAL STATUS ==========
            logger.info("=" * 50)
            logger.info("✅ NILM Predictor initialized!")
            logger.info(f"   FRIDGE: {'✅ WORKING' if self.model else '❌ FAILED'}")
            logger.info(f"   AC:     {'✅ WORKING' if self.ac_model else '⚠️ DISABLED'}")
            logger.info("=" * 50)
            
        except Exception as e:
            logger.error(f"❌ Init failed: {str(e)}")
            import traceback
            traceback.print_exc()
    
    def get_mains_data(self, db_session, hours=24):
        try:
            query = text("SELECT timestamp, active_power FROM mcb_readings_new ORDER BY timestamp ASC")
            result = db_session.execute(query)
            data = result.fetchall()
            if not data or len(data) < max(self.FRIDGE_WINDOW_SIZE, self.AC_WINDOW_SIZE) + 1:
                return None
            return pd.DataFrame(data, columns=['timestamp', 'active_power'])
        except Exception as e:
            logger.error(f"Error fetching mains data: {e}")
            return None
    
    def create_windows(self, data, window_size):
        """Create sliding windows for prediction"""
        X = []
        for i in range(len(data) - window_size):
            X.append(data[i:i + window_size])
        return np.array(X)
    
    def predict_fridge_power(self, db_session, hours=24):
        try:
            if self.model is None:
                return None
            
            df = self.get_mains_data(db_session, hours)
            if df is None or len(df) < self.FRIDGE_WINDOW_SIZE + 1:
                return None
            
            mains_power = df["active_power"].values.reshape(-1, 1)
            mains_scaled = self.mains_scaler.transform(mains_power)
            X_input = self.create_windows(mains_scaled, self.FRIDGE_WINDOW_SIZE)
            
            y_pred_norm = self.model.predict(X_input, verbose=0)
            y_pred_watts = self.fridge_scaler.inverse_transform(y_pred_norm)
            y_pred_final = np.where(y_pred_watts < self.FRIDGE_THRESHOLD, 0, y_pred_watts)
            
            fridge_prediction = np.zeros(len(mains_power))
            fridge_prediction[self.FRIDGE_WINDOW_SIZE:] = y_pred_final.flatten()
            df["predicted_fridge_power"] = fridge_prediction
            
            running_power = df[df["predicted_fridge_power"] > 0]["predicted_fridge_power"]
            stats = {
                'total_fridge_energy_kwh': float((df["predicted_fridge_power"].sum() / 1000) * (1/60)),
                'avg_fridge_power_w': float(running_power.mean()) if len(running_power) > 0 else 0,
                'max_fridge_power_w': float(df["predicted_fridge_power"].max()),
                'fridge_runtime_minutes': int((df["predicted_fridge_power"] > 0).sum()),
                'fridge_on_off_cycles': self.count_cycles(df["predicted_fridge_power"].values),
                'current_fridge_power': float(df["predicted_fridge_power"].iloc[-1]) if len(df) > 0 else 0
            }
            return {'predictions': df.to_dict('records'), 'statistics': stats}
        except Exception as e:
            logger.error(f"Fridge error: {e}")
            return None
    
    def predict_ac_power(self, db_session, hours=24):
        if self.ac_model is None:
            df = self.get_mains_data(db_session, hours)
            if df is None:
                return None
            stats = {
                'total_ac_energy_kwh': 0.0, 'avg_ac_power_w': 0, 'max_ac_power_w': 0.0,
                'ac_runtime_minutes': 0, 'ac_on_off_cycles': 0, 'current_ac_power': 0.0
            }
            df["predicted_ac_power"] = 0
            return {'predictions': df.to_dict('records'), 'statistics': stats}
        
        try:
            if self.ac_mains_scaler is None or self.ac_scaler is None:
                return None
            
            df = self.get_mains_data(db_session, hours)
            if df is None or len(df) < self.AC_WINDOW_SIZE + 1:
                return None
            
            mains_power = df["active_power"].values.reshape(-1, 1)
            mains_scaled = self.ac_mains_scaler.transform(mains_power)
            X_input = self.create_windows(mains_scaled, self.AC_WINDOW_SIZE)
            
            y_pred_norm = self.ac_model.predict(X_input, verbose=0)
            
            if len(y_pred_norm.shape) == 3:
                y_pred_norm = y_pred_norm.reshape(y_pred_norm.shape[0], -1)
            
            y_pred_watts = self.ac_scaler.inverse_transform(y_pred_norm)
            
            if len(y_pred_watts.shape) > 1:
                y_pred_watts = y_pred_watts.flatten()
            
            y_pred_final = np.where(y_pred_watts < self.AC_THRESHOLD, 0, y_pred_watts)
            
            ac_prediction = np.zeros(len(mains_power))
            ac_prediction[self.AC_WINDOW_SIZE:] = y_pred_final.flatten()
            df["predicted_ac_power"] = ac_prediction
            
            running_power = df[df["predicted_ac_power"] > 0]["predicted_ac_power"]
            stats = {
                'total_ac_energy_kwh': float((df["predicted_ac_power"].sum() / 1000) * (1/60)),
                'avg_ac_power_w': float(running_power.mean()) if len(running_power) > 0 else 0,
                'max_ac_power_w': float(df["predicted_ac_power"].max()),
                'ac_runtime_minutes': int((df["predicted_ac_power"] > 0).sum()),
                'ac_on_off_cycles': self.count_cycles(df["predicted_ac_power"].values, self.AC_THRESHOLD),
                'current_ac_power': float(df["predicted_ac_power"].iloc[-1]) if len(df) > 0 else 0
            }
            return {'predictions': df.to_dict('records'), 'statistics': stats}
        except Exception as e:
            logger.error(f"AC error: {e}")
            return None
    
    def count_cycles(self, power_values, threshold=20):
        cycles = 0
        is_on = False
        for power in power_values:
            if power > threshold and not is_on:
                cycles += 1
                is_on = True
            elif power <= threshold and is_on:
                is_on = False
        return cycles

nilm_predictor = NILMPredictor()