from flask import Flask, jsonify, render_template, request, g
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta, timezone
import os
from dotenv import load_dotenv
from flask_cors import CORS
from sqlalchemy.pool import QueuePool
import logging
from sqlalchemy import func, extract, create_engine, event
from sqlalchemy.orm import scoped_session, sessionmaker
from urllib.parse import quote_plus
import paho.mqtt.client as mqtt
import json
import threading
import time
from flask_socketio import SocketIO, emit
from dateutil.relativedelta import relativedelta
from sqlalchemy import text
import atexit
from contextlib import contextmanager
from flask_bcrypt import Bcrypt
from flask_jwt_extended import JWTManager
from collections import deque
from flask_migrate import Migrate
from dotenv import load_dotenv
from flask_jwt_extended import jwt_required, get_jwt_identity, verify_jwt_in_request
from flask import request 
from flask import Flask, jsonify, render_template, request, g, redirect, url_for
from flask_login import LoginManager
from flask import current_app
import psycopg2
from models import db, User, MCBReading
from functools import wraps
from sqlalchemy import text
from datetime import datetime, timedelta
from nilm_service import nilm_predictor
import numpy as np
import pandas as pd

# Load environment variables
load_dotenv()
def jwt_optional():
    """Custom decorator that tries to verify JWT but doesn't fail if no token"""
    def wrapper(fn):
        @wraps(fn)
        def decorator(*args, **kwargs):
            try:
                # Try to get token from header first
                if 'Authorization' in request.headers:
                    verify_jwt_in_request()
                # If no header, try to get from query parameter
                elif 'token' in request.args:
                    # Manually verify the token from query parameter
                    from flask_jwt_extended import decode_token
                    token = request.args.get('token')
                    decoded_token = decode_token(token)
                    # Set the jwt identity for the current request
                    from flask_jwt_extended import create_access_token
                    request.jwt_token = decoded_token
            except Exception:
                # Token is invalid or missing, but we don't block the request
                pass
            return fn(*args, **kwargs)
        return decorator
    return wrapper

app = Flask(__name__)
# Database configuration
app.config['DB_PASSWORD'] = os.getenv('DB_PASSWORD')
encoded_password = quote_plus(app.config['DB_PASSWORD'])
app.config['SQLALCHEMY_DATABASE_URI'] = f'postgresql://postgres:{encoded_password}@localhost:5432/bitminds'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_size': 10,
    'max_overflow': 20,
    'pool_timeout': 30,
    'pool_pre_ping': True,
    'pool_recycle': 300,
    'echo': True,
    'echo_pool': True,
    'isolation_level': 'READ COMMITTED'
    # Remove the connect_args section - it's redundant
}

# Remove this line - it can interfere with proper commits
# app.config['SQLALCHEMY_COMMIT_ON_TEARDOWN'] = False  # Already set, but make sure it's False
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(days=7)

app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY', 'your-secret-key-change-in-production')
app.config['DEEPSEEK_API_KEY'] = os.getenv('DEEPSEEK_API_KEY')


bcrypt = Bcrypt()
jwt = JWTManager()
migrate = Migrate()
login_manager = LoginManager()


# Initialize extensions with app
db.init_app(app)
bcrypt.init_app(app)
jwt.init_app(app)
migrate.init_app(app, db)
login_manager.init_app(app)
login_manager.login_view = 'auth_bp.login'
nilm_predictor.init_app(app)

# THEN register blueprint AFTER initialization
from auth import auth_bp



# Replace your existing CORS line with:
CORS(app, resources={
    r"/api/*": {
        "origins": "*",
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"]
    }
})
# Initialize SocketIO ONCE
socketio = SocketIO(
    app, 
    cors_allowed_origins="*", 
    async_mode='threading',
    logger=False,
    engineio_logger=False,
    ping_timeout=60,
    ping_interval=25,
    allow_upgrades=False,
    transports=['polling']
)
# Create engine and scoped session
engine = create_engine(
    app.config['SQLALCHEMY_DATABASE_URI'],
    pool_size=10,
    max_overflow=20,
    pool_timeout=30,
    pool_pre_ping=True
)

logging.basicConfig(level=logging.DEBUG)

    
   
    
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))
# Add this after your database setup
from sqlalchemy import event

@event.listens_for(db.session, "before_commit")
def before_commit(session):
    print("🔍 === BEFORE COMMIT ===")
    for obj in session.new:
        if hasattr(obj, '__tablename__'):
            print(f"➕ NEW: {obj.__tablename__} - {getattr(obj, 'email', 'No email')}")
    for obj in session.dirty:
        if hasattr(obj, '__tablename__'):
            print(f"✏️ DIRTY: {obj.__tablename__} - {getattr(obj, 'email', 'No email')}")

@event.listens_for(db.session, "after_commit")
def after_commit(session):
    print("✅ === AFTER COMMIT ===")

@event.listens_for(db.session, "after_rollback")
def after_rollback(session):
    print("💥 === DATABASE ROLLBACK OCCURRED ===")
    import traceback
    traceback.print_stack()

# Add this with other global variables
latest_readings = {
    'voltage': 0,
    'current': 0,
    'power': 0,
    'consumption': 0,
    'fluctuation': 0,
    'latest_timestamp': datetime.utcnow().isoformat() + 'Z',
    'mcb_count': 0
}


from collections import deque

# Add these with other global variables
VOLTAGE_HISTORY = deque(maxlen=60)  # Stores ~1 minute of data (assuming 1 reading/sec)
FLUCTUATION_WINDOW = 30  # Minimum readings needed to calculate fluctuation

# MQTT Configuration - Use environment variables
app.config['MQTT_BROKER'] = os.getenv('MQTT_BROKER')
app.config['MQTT_PORT'] = int(os.getenv('MQTT_PORT', 8883))
app.config['MQTT_USERNAME'] = os.getenv('MQTT_USERNAME')
app.config['MQTT_PASSWORD'] = os.getenv('MQTT_PASSWORD')
app.config['MQTT_TOPIC'] = os.getenv('MQTT_TOPIC')

app.register_blueprint(auth_bp)


# MQTT Client Setup
mqtt_client = mqtt.Client()
mqtt_client.username_pw_set(app.config['MQTT_USERNAME'], app.config['MQTT_PASSWORD'])
mqtt_client.tls_set()  # Enable TLS

# WITH this (for paho-mqtt 1.6.1):
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        logging.info("Connected to MQTT Broker!")
        client.subscribe(app.config['MQTT_TOPIC'])
    else:
        logging.error(f"Failed to connect, return code {rc}")
# Change the on_disconnect function signature to match MQTT v2
# REPLACE the on_disconnect function with this:
def on_disconnect(client, userdata, rc):
    logging.info("Disconnected from MQTT broker, attempting reconnect")
    reconnect_count = 0
    while reconnect_count < 5:
        try:
            time.sleep(5 * reconnect_count)
            client.reconnect()
            logging.info("Reconnected successfully")
            return
        except Exception as e:
            reconnect_count += 1
            logging.error(f"Reconnection attempt {reconnect_count} failed: {str(e)}")
    logging.error("Failed to reconnect after multiple attempts")
def on_subscribe(client, userdata, mid, granted_qos):
    logging.info(f"Subscribed to topic with QoS: {granted_qos}")
def on_message(client, userdata, msg):
    try:
        # Create application context
        with app.app_context():
            global latest_readings, VOLTAGE_HISTORY
            payload = json.loads(msg.payload.decode())
            
            logging.info(f"MQTT data received: {payload}")
            
            # Validate required fields
            required_fields = ['voltage_v', 'current_a', 'power_w', 'energy_kwh', 'mcb_id','user_id']
            if not all(field in payload for field in required_fields):
                logging.error(f"Missing fields in MQTT payload: {payload}")
                return
            
            # Parse timestamp
            timestamp = datetime.now(timezone.utc)
            if 'timestamp' in payload:
                try:
                    ts_str = payload['timestamp']
                    timestamp = datetime.strptime(ts_str, '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
                except ValueError:
                    logging.warning(f"Could not parse timestamp: {payload['timestamp']}")
            
            # Store in database
            try:
                new_reading = MCBReading(
                    timestamp=timestamp,
                    current_a=payload['current_a'],
                    voltage_v=payload['voltage_v'],
                    power_factor=payload.get('power_factor', 1.0),
                    power_w=payload['power_w'],
                    energy_kwh=payload['energy_kwh'],
                    mcb_id=payload['mcb_id'],
                    user_id=payload['user_id']
                )
                
                db.session.add(new_reading)
                db.session.commit()
                logging.info(f"Data stored in DB successfully for user {payload['user_id']}")
                    
            except Exception as db_error:
                logging.error(f"Database error: {str(db_error)}")
                db.session.rollback()
            
            # Calculate fluctuation
            voltage = payload['voltage_v']
            VOLTAGE_HISTORY.append(voltage)
            
            fluctuation = 0.0
            if len(VOLTAGE_HISTORY) >= FLUCTUATION_WINDOW:
                avg_voltage = sum(VOLTAGE_HISTORY) / len(VOLTAGE_HISTORY)
                if avg_voltage > 0:
                    fluctuation = ((max(VOLTAGE_HISTORY) - min(VOLTAGE_HISTORY)) / avg_voltage) * 100
            
            # Update latest readings - CORRECT STRUCTURE
            latest_readings = {
                'voltage': voltage,
                'current': payload['current_a'],
                'power': payload['power_w'],
                'consumption': payload['energy_kwh'],
                'fluctuation': round(fluctuation, 2),
                'timestamp': datetime.now().timestamp(),
                'user_id': payload['user_id'] 
            }
            
            # CRITICAL FIX: Add broadcast=True and namespace
            socketio.emit('energy_update', latest_readings, namespace='/', room=f"user_{payload['user_id']}")
            logging.info(f"WebSocket update sent for user {payload['user_id']}: V={voltage}V, I={payload['current_a']}A, P={payload['power_w']}W")
        
        
    except json.JSONDecodeError as e:
        logging.error(f"Invalid JSON in MQTT payload: {str(e)}")
    except Exception as e:
        logging.error(f"Error processing MQTT message: {str(e)}", exc_info=True)
mqtt_client.on_connect = on_connect
mqtt_client.on_disconnect = on_disconnect
mqtt_client.on_message = on_message

# Update your MQTT configuration
def connect_mqtt():
    try:
        mqtt_client.connect(
            app.config['MQTT_BROKER'], 
            app.config['MQTT_PORT'], 
            keepalive=60
        )
        mqtt_client.loop_start()
        logging.info(f"Connecting to MQTT broker at {app.config['MQTT_BROKER']}:{app.config['MQTT_PORT']}")
    except Exception as e:
        logging.error(f"MQTT connection error: {str(e)}")
        # Schedule reconnection
        threading.Timer(10.0, connect_mqtt).start()

# Start MQTT connection in a separate thread
mqtt_thread = threading.Thread(target=connect_mqtt)
mqtt_thread.daemon = True
mqtt_thread.start()

# WebSocket events
@socketio.on('connect')
def handle_connect():
    logging.info('Client connected')
    try:
        # Get token from query string
        token = request.args.get('token')
        if token:
            from flask_jwt_extended import decode_token
            decoded_token = decode_token(token)
            user_id = decoded_token['sub']
            
            # Join user-specific room
            socketio.server.enter_room(request.sid, f"user_{user_id}")
            
            # Send latest data
            user_readings = get_user_latest_readings(user_id)
            emit('energy_update', user_readings)
            
    except Exception as e:
        logging.error(f"WebSocket connection error: {str(e)}")
        # Allow connection even if token is invalid for public pages

@socketio.on('disconnect')
def handle_disconnect():
    try:
        user_id = get_jwt_identity()
        if user_id:
            socketio.server.leave_room(request.sid, f"user_{user_id}")
        logging.info('Client disconnected')
    except Exception as e:
        logging.error(f"WebSocket disconnect error: {str(e)}")
def get_user_latest_readings(user_id):
    """Get the latest readings for a specific user"""
    try:
        latest_reading = MCBReading.query.filter_by(user_id=user_id)\
            .order_by(MCBReading.timestamp.desc()).first()
        
        if latest_reading:
            return {
                'voltage': latest_reading.voltage_v,
                'current': latest_reading.current_a,
                'power': latest_reading.power_w,
                'consumption': latest_reading.energy_kwh,
                'fluctuation': 0.0,  # You'll need to calculate this per user
                'timestamp': latest_reading.timestamp.timestamp(),
                'user_id': user_id
            }
        return {}
    except Exception as e:
        logging.error(f"Error getting user readings: {str(e)}")
        return {}
@app.route('/test/mqtt')
def test_mqtt():
    return jsonify({
        'connected': mqtt_client.is_connected(),
        'broker': app.config['MQTT_BROKER'],  # Use app.config
        'port': app.config['MQTT_PORT']       # Use app.config
    })



@contextmanager
def database_session():
    try:
        yield db.session
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logging.error(f"Database error: {str(e)}")
        raise

# CORS headers
@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response
# FIXED ROUTES - Replace your current route definitions:

@app.route('/')
def home():
    return render_template('home.html')

@app.route('/dashboard')
def dashboard():
    token = request.args.get('token') or request.headers.get('Authorization', '').replace('Bearer ', '')
    
    if not token:
        return redirect(url_for('home'))
    
    try:
        from flask_jwt_extended import decode_token
        decoded = decode_token(token)
        user_id = decoded['sub']
        user = User.query.get(user_id)
        
        if not user:
            return redirect(url_for('home'))
            
        return render_template('index.html', user=user.to_dict())  # This renders your dashboard
    except Exception as e:
        app.logger.error(f"Dashboard auth error: {str(e)}")
        return redirect(url_for('home'))
@app.route('/nilm')
def nilm():
    # Same logic for NILM route
    token = request.args.get('token')
    if token:
        try:
            from flask_jwt_extended import decode_token
            decoded_token = decode_token(token)
            user_id = decoded_token['sub']
            user = User.query.get(user_id)
            return render_template('nilm.html', user=user)
        except Exception as e:
            return jsonify({"msg": "Invalid token"}), 401
    
    try:
        verify_jwt_in_request()
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        return render_template('nilm.html', user=user)
    except Exception as e:
        return jsonify({"msg": "Missing or invalid token"}), 401
@app.route('/api/monthly')
@jwt_required()
def get_monthly_data():
    user_id = get_jwt_identity()
    try:
        month = request.args.get('month')
        
        if not month:
            return jsonify({"error": "Month parameter is required"}), 400
        
        year, month_num = month.split('-')
        start_date = f"{year}-{month_num}-01"
        end_date = (datetime.strptime(start_date, "%Y-%m-%d") + relativedelta(months=1)).strftime("%Y-%m-%d")

        # Simple query to sum energy_kwh for each 12-hour interval
        query = text("""
            SELECT 
                DATE(timestamp) as day,
                CASE 
                    WHEN EXTRACT(HOUR FROM timestamp) < 12 THEN 1
                    ELSE 2
                END as interval_num,
                -- Sum energy_kwh directly and convert to Wh
                SUM(energy_kwh) * 1000 as consumption_wh
            FROM mcb_readings 
            WHERE user_id = :user_id
                     AND timestamp >= :start_date 
                     AND timestamp < :end_date
            
            GROUP BY DATE(timestamp), 
                     CASE WHEN EXTRACT(HOUR FROM timestamp) < 12 THEN 1 ELSE 2 END
            ORDER BY day, interval_num
        """)
        
        with database_session() as session:
            result = session.execute(query, {
                'user_id': user_id,
                'start_date': start_date,
                'end_date': end_date

            }).fetchall()

            month_start = datetime.strptime(start_date, "%Y-%m-%d")
            month_end = datetime.strptime(end_date, "%Y-%m-%d")
            days_in_month = (month_end - month_start).days
            
            consumption_data = {}
            total_consumption = 0
            
            for row in result:
                day = row[0].day if hasattr(row[0], 'day') else row[0]
                interval_num = row[1]
                consumption = float(row[2]) if row[2] is not None else 0
                consumption_data[(day, interval_num)] = consumption
                total_consumption += consumption
            
            app.logger.info(f"Total monthly consumption for user {user_id}: {total_consumption/1000:.2f} kWh")
            
            data = []
            point_index = 1
            
            for day in range(1, days_in_month + 1):
                for interval in [1, 2]:
                    consumption = consumption_data.get((day, interval), 0)
                    
                    data.append({
                        'x': point_index,
                        'y': consumption,  # In Wh
                        'day': day,
                        'interval': interval,
                        'interval_name': '00:00-11:59' if interval == 1 else '12:00-23:59'
                    })
                    
                    point_index += 1
            
            return jsonify(data)
            
    except Exception as e:
        app.logger.error(f"Error in monthly data for user {user_id}: {str(e)}")
        return jsonify({"error": str(e)}), 500
# Configure DeepSeek client (add after db initialization)
# WITH this:
import openai
openai.api_key = app.config['DEEPSEEK_API_KEY']
openai.base_url = "https://openrouter.ai/api/v1"

@app.route('/api/daily_summary')
@jwt_required()
def get_daily_summary():
    user_id = get_jwt_identity()
    try:
        with database_session() as session:
            # Get the most recent date with data
            latest_date = session.query(
                func.max(func.date(MCBReading.timestamp))
            ).filter(MCBReading.user_id == user_id).scalar()
            
            if not latest_date:
                return jsonify({"error": "No data available in user database"}), 404
            
            # Get total kWh (this part is working fine)
            total_kwh = session.query(
                func.sum(MCBReading.energy_kwh)
            ).filter(
                MCBReading.user_id == user_id,
                func.date(MCBReading.timestamp) == latest_date
            ).scalar() or 0
            
            # Get all readings using raw SQL (correctly fetches 1039 records)
            result = session.execute(text("""
                SELECT timestamp, voltage_v, current_a, power_w, energy_kwh, power_factor, mcb_id
                FROM mcb_readings 
                WHERE user_id = :user_id
                        AND DATE(timestamp) = :date 
                                          
                ORDER BY timestamp
            """), {"user_id": user_id, "date": latest_date})
            data = result.fetchall()

            if not data:
                return jsonify({
                    "error": f"No detailed data for {latest_date}",
                    "total_kwh": 0,
                    "avg_voltage": 0,
                    "avg_current": 0,
                    "max_power": 0,
                    "min_voltage": 0,
                    "max_voltage": 0,
                    "readings_count": 0,
                    "voltage_fluctuation": 0 
                })

            # FIX: Access Row objects using index or column name
            # Using column index (based on SELECT order)
            voltages = [row[1] for row in data]  # voltage_v is index 1
            currents = [row[2] for row in data]  # current_a is index 2
            powers = [row[3] for row in data]    # power_w is index 3

            avg_voltage = sum(row[1] for row in data) / len(data) if data else 0  # voltage_v is index 1
            avg_current = sum(row[2] for row in data) / len(data) if data else 0  # current_a is index 2
            max_power = max((row[3] for row in data), default=0)  # power_w is index 3
            min_voltage = min((row[1] for row in data), default=0)
            max_voltage = max((row[1] for row in data), default=0)

            if avg_voltage > 0:
                voltage_range = max_voltage - min_voltage
                voltage_fluctuation = (voltage_range / avg_voltage) * 100
            else:
                voltage_fluctuation = 0
            return jsonify({
                "date": latest_date.isoformat(),
                "total_kwh": round(float(total_kwh), 3),
                "avg_voltage": round(avg_voltage, 1),
                "avg_current": round(avg_current, 2),
                "max_power": round(max_power, 1),
                "min_voltage": round(min_voltage, 1),
                "max_voltage": round(max_voltage, 1),
                "readings_count": len(data),  # This will now correctly show 1039
                "voltage_fluctuation": round(voltage_fluctuation, 2),
                "user_id": user_id 
                
            })
            
    except Exception as e:
        app.logger.error(f"Daily summary error for user {user_id}: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@app.route('/api/generate_recommendation', methods=['POST'])
@jwt_required()
def generate_recommendation():
    try:
        # Get summary data
        summary_res = get_daily_summary()
        if summary_res.status_code != 200:
            return jsonify({"error": "Could not fetch energy data"}), 500
            
        summary = summary_res.get_json()
        
        # Safely convert to appropriate types, handling None and string values
        try:
            total_kwh = float(summary.get('total_kwh') or 0)
        except (ValueError, TypeError):
            total_kwh = 0.0
            
        try:
            avg_voltage = float(summary.get('avg_voltage') or 0)
        except (ValueError, TypeError):
            avg_voltage = 0.0
            
        try:
            avg_current = float(summary.get('avg_current') or 0)
        except (ValueError, TypeError):
            avg_current = 0.0
            
        try:
            voltage_fluctuation = float(summary.get('voltage_fluctuation', 0))
        except (ValueError, TypeError):
            voltage_fluctuation = 0.0
            
        try:
            readings_count = int(summary.get('readings_count', 0))
        except (ValueError, TypeError):
            readings_count = 0
        
        # Build prompt with safely converted values
        prompt = f"""As an Energy Guru analyzing a modern industrial facility, perform a comprehensive cosmic energy diagnostic:

**COSMIC ENERGY ANALYSIS** 
- Temporal Rhythm Analysis: {summary.get('date', 'N/A')}
- Energy Consumption Flow: {total_kwh:.2f} kWh (Prana Signature)
- Voltage Harmony: {avg_voltage:.1f}V with {voltage_fluctuation:.2f}% instability
- Current Stream: {avg_current:.2f}A (Electron Dance Intensity)
- Data Integrity: {readings_count} temporal samples

**ENERGY WISDOM MATRIX** 

**PHASE 1: INFRASTRUCTURE ENLIGHTENMENT**
Generate 3 specific hardware recommendations with technical specifications:
1. Smart Grid Evolution (specify precise equipment models)
2. Power Quality Harmony (with technical parameters for stable flow)
3. Energy Rebirth System (with efficiency metrics for sustainable operation)

**PHASE 2: WORKFORCE CONSCIOUSNESS**
Provide 2 behavioral energy protocols:
1. Team Energy Awareness Practices (specific mindful actions)
2. Automated System Refinement (technical implementation for seamless operation)

**PHASE 3: ECONOMIC ABUNDANCE PROJECTION**
Deliver detailed financial wisdom:
- Immediate cost-saving vision (30-day projection)
- Investment return timeline with cosmic alignment
- Environmental footprint reduction metrics
- Maintenance optimization savings for sustainable growth

**PHASE 4: DIGITAL TRANSFORMATION INTEGRATION**
Outline implementation journey:
- Phase 1: Essential upgrades (first 14 cycles - Foundation)
- Phase 2: System harmony (next 30 cycles - Growth)
- Phase 3: Intelligent optimization (ongoing - Enlightenment)

**WISDOM GUIDELINES:**
- Use enlightened technical terminology with cosmic references
- Include specific technical specifications for modern infrastructure
- Provide measurable metrics for sustainable development
- Structure with ancient wisdom concepts meeting modern technology
- Incorporate digital transformation references with traditional wisdom
- Maintain actionable, implementation-ready advice for progressive industries

**ENLIGHTENED FORMAT:**
Present as a multi-layered diagnostic report from the Energy Wisdom Core, using harmonious section headers, bullet points with symbolic icons (⚡🌊🏭🌱🔭), and measurable metrics aligned with sustainable development.

Begin the wisdom transmission:"""
        
        # Rest of your code remains the same...
        try:
            # WITH this:
            completion = openai.ChatCompletion.create(
            model="deepseek/deepseek-r1:free",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7
        )
            return jsonify({
                "recommendation": completion.choices[0].message.content,
                "summary": summary
            })
        except Exception as ai_error:
            app.logger.error(f"DeepSeek API error: {str(ai_error)}")
            return jsonify({
                "error": "AI service unavailable",
                "recommendation": "⚠️ AI service is currently unavailable. Here's a sample recommendation:\n\n1. Consider upgrading to energy-efficient LED lighting\n2. Install motion sensors in low-traffic areas\n3. Encourage staff to power down equipment when not in use\n4. Estimated savings: ₹15,000/year",
                "summary": summary
            })
            
    except Exception as e:
        app.logger.error(f"Recommendation generation error: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/ai_recommendation')
def ai_recommendation():
    # Check for token in query parameter first, then in header
    token = request.args.get('token')
    if token:
        try:
            from flask_jwt_extended import decode_token
            decoded_token = decode_token(token)
            user_id = decoded_token['sub']
            # Proceed with user_id
            user = User.query.get(user_id)
            return render_template('ai_recommendation.html', user=user)
        except Exception as e:
            return jsonify({"msg": "Invalid token"}), 401
    
    # If no token in query, check Authorization header
    try:
        verify_jwt_in_request()
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        return render_template('ai_recommendation.html', user=user)
    except Exception as e:
        return jsonify({"msg": "Missing or invalid token"}), 401

@app.route('/api/predicted_bill')
@jwt_required()
def get_predicted_bill():
    user_id = get_jwt_identity()

    try:
        app.logger.info(f"Predicted bill endpoint accessed by user {user_id}")
        
        with database_session() as session:
            # Check if we have any data
            has_data = session.query(MCBReading).filter_by(user_id=user_id).first()
            if not has_data:
                return jsonify({
                    "error": "No energy data available for your account",
                    "status": "no_data"
                }), 404
            
            # Get the most recent date with data
            latest_date = session.query(
                func.max(func.date(MCBReading.timestamp))
            ).filter(MCBReading.user_id == user_id).scalar()
            
            
            if not latest_date:
                return jsonify({
                    "error": "No data available",
                    "status": "no_data"
                }), 404
            
            # Calculate 7 days back from the latest date
            end_date = latest_date
            start_date = end_date - timedelta(days=6)  # 6 days back + today = 7 days
            
            # Sum energy_kwh for the 7-day period
            # Using SUM since energy_kwh appears to be incremental based on your requirements
            weekly_consumption = session.query(
                func.sum(MCBReading.energy_kwh)
            ).filter(
                MCBReading.user_id == user_id,
                func.date(MCBReading.timestamp) >= start_date,
                func.date(MCBReading.timestamp) <= end_date
            ).scalar() or 0
            
            # Count actual days with data
            days_with_data = session.query(
                func.count(func.distinct(func.date(MCBReading.timestamp)))
            ).filter(
                MCBReading.user_id == user_id,
                func.date(MCBReading.timestamp) >= start_date,
                func.date(MCBReading.timestamp) <= end_date
            ).scalar() or 0
            
            if weekly_consumption == 0 or days_with_data == 0:
                return jsonify({
                    "error": "No consumption data available for your account",
                    "status": "no_data"
                }), 404
            
            app.logger.info(f"Weekly consumption for user {user_id}: {weekly_consumption} kWh over {days_with_data} days")
            # Calculate 60-day (2 month) projection by multiplying by 8.5
            # (7 days * 8.5 = 59.5 days ≈ 2 months)
            projected_60day_consumption = weekly_consumption * 8.5
            
            # Calculate bill for projected consumption
            bill = calculate_electricity_bill(projected_60day_consumption)

            response = jsonify({
                "predicted_consumption": round(projected_60day_consumption, 2),
                "predicted_bill": bill,
                "period_consumption": round(weekly_consumption, 2),
                "days_analyzed": days_with_data,
                "avg_daily_consumption": round(weekly_consumption / days_with_data, 2),
                "data_range": {
                    "start": start_date.isoformat(),
                    "end": end_date.isoformat()
                },
                "projection_period": "60 days (2 months)",
                "status": "success",
                "note": f" ({weekly_consumption:.2f})",
                "user_id": user_id
            })
            
            response.headers.add('Access-Control-Allow-Origin', '*')
            return response

    except Exception as e:
        app.logger.error(f"Error in predicted_bill for user {user_id}: {str(e)}", exc_info=True)
        return jsonify({"error": str(e), "status": "error"}), 500

def calculate_electricity_bill(units):
    """Calculate electricity bill based on tiered pricing for 60 days (2 months)"""
    try:
        units = float(units)
        
        # Tiered pricing structure
        if units <= 100:
            cost = units * 3.5
        elif units <= 200:
            cost = 100 * 3.5 + (units - 100) * 4.5
        else:
            cost = 100 * 3.5 + 100 * 4.5 + (units - 200) * 6.5
        
        # Fixed charges for 2 months (₹50/month)
        fixed_charges = 50 * 2
        
        # Add 18% GST
        total = (cost + fixed_charges) * 1.18
        
        return round(total, 2)
    except Exception as e:
        app.logger.error(f"Bill calculation error: {str(e)}")
        return 0

def calculate_fluctuation():
    """Calculate and emit fluctuation every minute"""
    while True:
        time.sleep(60)  # Wait 1 minute
        if len(VOLTAGE_HISTORY) >= FLUCTUATION_WINDOW:
            avg = sum(VOLTAGE_HISTORY) / len(VOLTAGE_HISTORY)
            fluctuation = ((max(VOLTAGE_HISTORY) - min(VOLTAGE_HISTORY)) / avg) * 100
            latest_readings['fluctuation'] = round(fluctuation, 2)
            socketio.emit('energy_update', latest_readings)

# Start the fluctuation thread
fluctuation_thread = threading.Thread(target=calculate_fluctuation)
fluctuation_thread.daemon = True
fluctuation_thread.start()
@app.route('/api/debug/test-signup', methods=['POST'])
def debug_test_signup():
    """Test signup directly without frontend"""
    try:
        from app import db, bcrypt, User
        
        # Test data
        test_user = User(
            name="Test User",
            email="test@example.com", 
            is_verified=True,
            is_active=True
        )
        test_user.set_password("test123", bcrypt)
        
        db.session.add(test_user)
        db.session.commit()
        
        return jsonify({
            "success": True,
            "user_id": test_user.id,
            "message": "Test user created successfully"
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/debug/users-count')
def debug_users_count():
    """Check how many users are in database"""
    try:
        users_count = User.query.count()
        return jsonify({
            "users_count": users_count,
            "tables_exist": True
        })
    except Exception as e:
        return jsonify({
            "users_count": 0,
            "error": str(e),
            "tables_exist": False
        })

# Health check endpoint
@app.route('/health')
def health_check():
    try:
        with database_session() as session:
            session.execute('SELECT 1')
        return jsonify({"status": "healthy", "database": "connected"})
    except Exception as e:
        return jsonify({"status": "unhealthy", "error": str(e)}), 500
# Add this route to app.py for debugging
@app.route('/api/test-connection', methods=['GET'])
def test_connection():
    """Test database connection and configuration"""
    try:
        # Test database connection
        result = db.session.execute(text('SELECT 1'))
        db_connected = result is not None
        
        # Test if tables exist
        result = db.session.execute(text("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
        """))
        tables = [row[0] for row in result]
        
        # Test user count
        user_count = User.query.count()
        
        return jsonify({
            'database': {
                'connected': db_connected,
                'tables': tables,
                'user_count': user_count
            },
            'config': {
                'database_uri': app.config['SQLALCHEMY_DATABASE_URI'].split('@')[1],  # Hide password
                'autocommit': app.config.get('SQLALCHEMY_ENGINE_OPTIONS', {}).get('isolation_level') != 'AUTOCOMMIT'
            }
        }), 200
        
    except Exception as e:
        return jsonify({
            'error': str(e),
            'type': type(e).__name__
        }), 500
@app.route('/api/nilm/predict', methods=['GET'])
@jwt_required()
def get_nilm_predictions():
    """Get NILM predictions for the current user"""
    user_id = get_jwt_identity()
    
    print("=" * 50)
    print(f"🔵 API CALLED: /api/nilm/predict by user {user_id}")
    print("=" * 50)
    
    try:
        # Get query parameters
        hours = request.args.get('hours', default=24, type=int)
        print(f"📊 Hours requested: {hours}")
        
        with database_session() as session:
            print("🔄 Calling nilm_predictor.predict_fridge_power...")
            result = nilm_predictor.predict_fridge_power(session, hours)
            print(f"📦 Result received: {result is not None}")
            
            if result is None:
                print("❌ Result is None - insufficient data")
                return jsonify({
                    'status': 'insufficient_data',
                    'message': 'Insufficient data for prediction. Need at least 60 samples.',
                    'predictions': [],
                    'statistics': {
                        'total_fridge_energy_kwh': 0,
                        'avg_fridge_power_w': 0,
                        'max_fridge_power_w': 0,
                        'fridge_runtime_minutes': 0,
                        'fridge_on_off_cycles': 0,
                        'current_fridge_power': 0
                    }
                })
            
            # Get only the last 100 points for the chart
            recent_predictions = result['predictions'][-100:] if len(result['predictions']) > 100 else result['predictions']
            
            print(f"✅ Returning {len(recent_predictions)} predictions")
            print(f"📈 Statistics: {result['statistics']}")
            
            return jsonify({
                'status': 'success',
                'predictions': recent_predictions,
                'statistics': result['statistics'],
                'total_samples': len(result['predictions']),
                'hours_analyzed': hours
            })
            
    except Exception as e:
        print(f"❌ ERROR in prediction: {str(e)}")
        import traceback
        traceback.print_exc()
        app.logger.error(f"Error in NILM prediction for user: {str(e)}")
        return jsonify({'error': str(e)}), 500
@app.route('/api/nilm/fridge/current', methods=['GET'])
@jwt_required()
def get_current_fridge_power():
    """Get current fridge power prediction"""
    user_id = get_jwt_identity()
    
    try:
        with database_session() as session:
            # Get last 60 readings for prediction
            query = text("""
                SELECT timestamp, active_power as active_power
                FROM mcb_readings_new
                ORDER BY timestamp DESC
            """)
            
            result = session.execute(query)
            data = result.fetchall()
            
            if len(data) < 60:
                return jsonify({
                    'status': 'insufficient_data',
                    'current_power': 0,
                    'message': 'Need more data for prediction'
                })
            
            # Reverse to get chronological order
            data = data[::-1]
            
            # Extract power values
            mains_power = np.array([row[1] for row in data]).reshape(-1, 1)
            
            # Scale and predict
            mains_scaled = nilm_predictor.mains_scaler.transform(mains_power)
            X_input = np.array([mains_scaled.flatten()])
            
            y_pred_norm = nilm_predictor.model.predict(X_input, verbose=0)
            y_pred_watts = nilm_predictor.fridge_scaler.inverse_transform(y_pred_norm)
            
            current_power = float(y_pred_watts[0][0])
            
            # Apply threshold
            if current_power < nilm_predictor.FRIDGE_THRESHOLD:
                current_power = 0
            
            return jsonify({
                'status': 'success',
                'current_power': round(current_power, 2),
                'timestamp': data[-1][0].isoformat() if data else None
            })
            
    except Exception as e:
        app.logger.error(f"Error getting current fridge power: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/nilm/detailed-status')
@jwt_required()
def nilm_detailed_status():
    """Enhanced NILM status endpoint with fridge data"""
    user_id = get_jwt_identity()
    
    print("=" * 50)
    print(f"🟢 API CALLED: /api/nilm/detailed-status by user {user_id}")
    print("=" * 50)
    
    try:
        # Get user-specific data
        user = User.query.get(user_id)
        if not user:
            return jsonify({"error": "User not found"}), 404
            
        # Get latest readings
        latest_reading = MCBReading.query.order_by(MCBReading.timestamp.desc()).first()
        print(f"📊 Latest reading: {latest_reading.power_w if latest_reading else 'None'}W")
        
        # Get fridge prediction statistics
        with database_session() as session:
            print("🔄 Getting fridge statistics...")
            fridge_result = nilm_predictor.predict_fridge_power(session, hours=24)
            
            if fridge_result and fridge_result['statistics']:
                fridge_stats = fridge_result['statistics']
                current_fridge = fridge_stats['current_fridge_power']
                fridge_energy = fridge_stats['total_fridge_energy_kwh']
                avg_power = fridge_stats['avg_fridge_power_w']
                max_power = fridge_stats['max_fridge_power_w']
                print(f"✅ Fridge stats - Current: {current_fridge}W, Energy: {fridge_energy}kWh")
            else:
                current_fridge = 0
                fridge_energy = 0
                avg_power = 0
                max_power = 0
                print("⚠️ No fridge statistics available")
        
        # Calculate total power (main + fridge)
        main_power = latest_reading.power_w if latest_reading else 0
        total_power = main_power + current_fridge
        
        user_data = {
            'activeDevices': 2,
            'totalPower': round(total_power, 2),
            'efficiency': 85,
            'savings': round(fridge_energy * 5, 2),
            'fridge_power': round(current_fridge, 2),
            'fridge_energy': round(fridge_energy, 3),
            'avg_fridge_power': round(avg_power, 2),
            'max_fridge_power': round(max_power, 2),
            'user_id': user_id,
            'status': 'monitoring' if latest_reading else 'waiting_for_data'
        }
        
        print(f"📤 Returning user data: {user_data}")
        
        return jsonify(user_data)
        
    except Exception as e:
        print(f"❌ ERROR in status: {str(e)}")
        import traceback
        traceback.print_exc()
        app.logger.error(f"Error in status: {str(e)}")
        return jsonify({'error': str(e)}), 500
@app.route('/api/nilm/ac/predict', methods=['GET'])
@jwt_required()
def get_ac_predictions():
    """Get AC NILM predictions for the current user"""
    user_id = get_jwt_identity()
    
    print("=" * 50)
    print(f"🔵 API CALLED: /api/nilm/ac/predict by user {user_id}")
    print("=" * 50)
    
    try:
        hours = request.args.get('hours', default=24, type=int)
        print(f"📊 Hours requested: {hours}")
        
        with database_session() as session:
            print("🔄 Calling nilm_predictor.predict_ac_power...")
            result = nilm_predictor.predict_ac_power(session, hours)
            print(f"📦 AC Result received: {result is not None}")
            
            if result is None:
                print("❌ AC Result is None - insufficient data")
                return jsonify({
                    'status': 'insufficient_data',
                    'message': 'Insufficient data for AC prediction. Need at least 60 samples.',
                    'predictions': [],
                    'statistics': {
                        'total_ac_energy_kwh': 0,
                        'avg_ac_power_w': 0,
                        'max_ac_power_w': 0,
                        'ac_runtime_minutes': 0,
                        'ac_on_off_cycles': 0,
                        'current_ac_power': 0
                    }
                })
            
            # Get only the last 100 points for the chart
            recent_predictions = result['predictions'][-100:] if len(result['predictions']) > 100 else result['predictions']
            
            print(f"✅ Returning {len(recent_predictions)} AC predictions")
            print(f"📈 AC Statistics: {result['statistics']}")
            
            return jsonify({
                'status': 'success',
                'predictions': recent_predictions,
                'statistics': result['statistics'],
                'total_samples': len(result['predictions']),
                'hours_analyzed': hours
            })
            
    except Exception as e:
        print(f"❌ ERROR in AC prediction: {str(e)}")
        import traceback
        traceback.print_exc()
        app.logger.error(f"Error in AC NILM prediction: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/nilm/ac/current', methods=['GET'])
@jwt_required()
def get_current_ac_power():
    """Get current AC power prediction"""
    user_id = get_jwt_identity()
    
    try:
        with database_session() as session:
            # Get last 60 readings for prediction
            query = text("""
                SELECT timestamp, active_power as active_power
                FROM mcb_readings_new
                ORDER BY timestamp DESC
                LIMIT 60
            """)
            
            result = session.execute(query)
            data = result.fetchall()
            
            if len(data) < 60:
                return jsonify({
                    'status': 'insufficient_data',
                    'current_power': 0,
                    'message': 'Need more data for AC prediction'
                })
            
            # Reverse to get chronological order
            data = data[::-1]
            
            # Extract power values
            mains_power = np.array([row[1] for row in data]).reshape(-1, 1)
            
            # Scale using AC mains scaler and predict
            mains_scaled = nilm_predictor.ac_mains_scaler.transform(mains_power)
            X_input = np.array([mains_scaled.flatten()])
            
            y_pred_norm = nilm_predictor.ac_model.predict(X_input, verbose=0)
            y_pred_watts = nilm_predictor.ac_scaler.inverse_transform(y_pred_norm)
            
            current_power = float(y_pred_watts[0][0])
            
            # Apply AC threshold
            if current_power < nilm_predictor.AC_THRESHOLD:
                current_power = 0
            
            return jsonify({
                'status': 'success',
                'current_power': round(current_power, 2),
                'timestamp': data[-1][0].isoformat() if data else None
            })
            
    except Exception as e:
        app.logger.error(f"Error getting current AC power: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/nilm/ac/detailed-status')
@jwt_required()
def ac_detailed_status():
    """Enhanced NILM status endpoint with AC data"""
    user_id = get_jwt_identity()
    
    print("=" * 50)
    print(f"🟢 API CALLED: /api/nilm/ac/detailed-status by user {user_id}")
    print("=" * 50)
    
    try:
        user = User.query.get(user_id)
        if not user:
            return jsonify({"error": "User not found"}), 404
            
        # Get AC prediction statistics
        with database_session() as session:
            print("🔄 Getting AC statistics...")
            ac_result = nilm_predictor.predict_ac_power(session, hours=24)
            
            if ac_result and ac_result['statistics']:
                ac_stats = ac_result['statistics']
                current_ac = ac_stats['current_ac_power']
                ac_energy = ac_stats['total_ac_energy_kwh']
                avg_power = ac_stats['avg_ac_power_w']
                max_power = ac_stats['max_ac_power_w']
                runtime = ac_stats['ac_runtime_minutes']
                print(f"✅ AC stats - Current: {current_ac}W, Energy: {ac_energy}kWh, Runtime: {runtime}min")
            else:
                current_ac = 0
                ac_energy = 0
                avg_power = 0
                max_power = 0
                runtime = 0
                print("⚠️ No AC statistics available")
        
        ac_data = {
            'ac_power': round(current_ac, 2),
            'ac_energy': round(ac_energy, 3),
            'avg_ac_power': round(avg_power, 2),
            'max_ac_power': round(max_power, 2),
            'ac_runtime': runtime,
            'status': 'active' if current_ac > 0 else 'inactive',
            'user_id': user_id
        }
        
        print(f"📤 Returning AC data: {ac_data}")
        
        return jsonify(ac_data)
        
    except Exception as e:
        print(f"❌ ERROR in AC status: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
# Database connection pool monitoring
@event.listens_for(engine.pool, "checkout")
def on_checkout(dbapi_connection, connection_record, connection_proxy):
    logging.debug(f"Connection checked out: {connection_record.info}")

@event.listens_for(engine.pool, "checkin")
def on_checkin(dbapi_connection, connection_record):
    logging.debug(f"Connection checked in: {connection_record.info}")

# Shut down scheduler when exiting
atexit.register(lambda: VOLTAGE_HISTORY.clear())  # Clean up voltage history
atexit.register(lambda: mqtt_client.disconnect())  # Disconnect MQTT

if __name__ == '__main__':
    # Create database tables if they don't exist
    with app.app_context():
        db.create_all()
    
    # INDENTED PROPERLY:
    socketio.run(
        app, 
        debug=True, 
        host='0.0.0.0',
        port=5000,
        use_reloader=False,
        log_output=False
    )