# 📚 **BitMinds**

```markdown
# ⚡ BitMinds - AI-Powered Energy Intelligence Platform

**This is an AI-powered energy management platform that transforms how households and businesses monitor electricity usage. It connects to ESP32 sensors via MQTT protocol to capture real-time voltage, current, and power data every second. Using advanced LSTM neural networks, it performs Non-Intrusive Load Monitoring (NILM) to detect individual appliances like refrigerators and AC units from a single mains meter without extra sensors. The platform provides an interactive dashboard with live gauges, 60-day bill predictions using tiered Indian pricing, and personalized energy-saving recommendations powered by DeepSeek AI. Built with Flask backend, PostgreSQL database, Redis cache, and WebSocket for real-time updates, this solution helps users reduce electricity costs by up to 30% through actionable insights and historical analytics.

---

## 🎯 Complete Features List

### Real-time Monitoring
- Live voltage, current, power display
- WebSocket instant updates (1 second delay)
- Interactive gauges and charts

### AI Appliance Detection (NILM)
- Detects Refrigerator from main meter data
- Detects Air Conditioner from main meter data
- No extra sensors needed - pure AI!

### Bill Prediction
- 60-day electricity bill forecast
- Indian tiered pricing (₹3.5 to ₹6.5 per unit)
- GST and fixed charges included

### AI Recommendations
- Personalized energy saving tips
- Powered by DeepSeek LLM
- Infrastructure upgrade suggestions

### Historical Analytics
- Monthly consumption charts
- Peak usage analysis
- Voltage fluctuation tracking

### User System
- Secure JWT authentication
- Password hashing with Bcrypt
- User-specific data isolation

---

## 🛠 Complete Technology Stack

### Programming Languages

| Language | Version | Used For |
|----------|---------|----------|
| **Python** | 3.10 | Backend API, AI models, Database logic |
| **JavaScript** | ES6 | Frontend dashboard, WebSocket, API calls |
| **HTML5** | - | Web page structure |
| **CSS3** | - | Styling, animations, responsive design |
| **Arduino C++** | - | ESP32 firmware, sensor reading |

### Backend Frameworks & Libraries

| Library | Purpose |
|---------|---------|
| **Flask 2.3** | Web framework, routing, API endpoints |
| **Flask-SocketIO** | WebSocket real-time communication |
| **Flask-JWT-Extended** | JWT token authentication |
| **Flask-Bcrypt** | Password hashing |
| **Flask-SQLAlchemy** | Database ORM |
| **Flask-CORS** | Cross-origin resource sharing |
| **Gunicorn** | Production WSGI server |

### Frontend Libraries

| Library | Purpose |
|---------|---------|
| **Socket.IO Client** | WebSocket connection from browser |
| **HighCharts** | Interactive energy consumption charts |
| **Font Awesome 6** | Icons and visual elements |
| **Fetch API** | HTTP requests to backend |

### AI & Machine Learning

| Library | Purpose |
|---------|---------|
| **TensorFlow 2.13** | LSTM neural network models |
| **NumPy** | Numerical data processing |
| **Pandas** | Data manipulation and analysis |
| **Scikit-learn** | Data scaling (StandardScaler) |
| **Joblib** | Model serialization (.pkl files) |

### Database & Cache

| Technology | Version | Purpose |
|------------|---------|---------|
| **PostgreSQL** | 15 | Primary database for users and readings |
| **Redis** | 7 | Real-time cache, session storage |

### IoT & Messaging

| Technology | Purpose |
|------------|---------|
| **Mosquitto MQTT** | Message broker for ESP32 |
| **Paho-MQTT** | Python MQTT client |
| **ESP32** | Hardware for sensor data collection |

### AI Integration

| Service | Purpose |
|---------|---------|
| **DeepSeek API** | LLM-powered energy recommendations |
| **OpenRouter** | API gateway for DeepSeek |

### DevOps & Containerization

| Technology | Purpose |
|------------|---------|
| **Docker** | Containerization |
| **Docker Compose** | Multi-container orchestration |
| **Nginx** | Reverse proxy, SSL termination |
| **Git** | Version control |

### Cloud Services (AWS)

| Service | Purpose |
|---------|---------|
| **EC2** | Backend hosting (t3.medium) |
| **RDS** | Managed PostgreSQL |
| **S3** | Static frontend hosting |
| **CloudFront** | CDN for faster delivery |

---

## 📁 Complete File Structure

```
```bash
bitminds/
├── 🐍 Python Backend Files
│   ├── app.py                    # Main Flask application (routes, MQTT, WebSocket)
│   ├── auth.py                   # JWT authentication endpoints
│   ├── models.py                 # Database models (User, MCBReading)
│   └── nilm_service.py           # NILM LSTM predictor class
│
├── 🧠 AI Model Files
│   ├── fridge_nilm_lstm.keras    # Fridge LSTM model (60 timesteps)
│   ├── ac1_full_model.keras      # AC LSTM model (120 timesteps)
│   ├── mains_scaler.pkl          # Mains power scaler
│   ├── fridge_scaler.pkl         # Fridge power scaler
│   ├── mains_scaler_ac.pkl       # AC mains scaler
│   └── ac_scaler.pkl             # AC power scaler
│
├── 🎨 Frontend Files
│   ├── templates/
│   │   ├── home.html             # Landing page
│   │   ├── index.html            # Main dashboard
│   │   ├── nilm.html             # NILM device monitor
│   │   └── ai_recommendation.html # AI insights page
│   └── static/                   # CSS, JS, images
│
├── 🐳 Docker Files
│   ├── Dockerfile                # Docker build instructions
│   ├── docker-compose.yml        # Multi-container orchestration
│   ├── .dockerignore             # Files excluded from Docker
│   ├── entrypoint.sh             # Startup initialization script
│   └── wait-for-it.sh            # Database readiness wait script
│
├── 🌐 Nginx Configuration
│   └── nginx/
│       └── nginx.conf            # Reverse proxy + SSL config
│
├── 🔒 Security
│   └── certs/                    # SSL certificates for MQTT
│
├── 📊 Database
│   └── migrations/               # Alembic database migrations
│
├── 📄 Configuration Files
│   ├── requirements.txt          # Python dependencies
│   ├── .env                      # Environment variables (secrets)
│   ├── .env.example              # Template for .env
│   
│
└── 📝 Documentation
    └── README.md                 # This file
```

---

## 🔄 Complete Data Flow

### Step 1: ESP32 Reads Sensors (Every Second)

```
ESP32 (Arduino C++)
    │
    ├── Read Voltage (230V typical)
    ├── Read Current (10-15A typical)
    ├── Calculate Power = Voltage × Current
    ├── Calculate Energy (kWh incremental)
    │
    └── Create JSON Payload
        {
          "voltage_v": 230.5,
          "current_a": 12.3,
          "power_w": 2835,
          "energy_kwh": 2.835,
          "mcb_id": 1,
          "user_id": 1,
          "timestamp": "2025-04-25 14:30:00"
        }
```

### Step 2: MQTT Publishing

```
ESP32 ──MQTT Publish──► Mosquitto Broker (Port 1883)
                         Topic: "energy/data"
```

### Step 3: Flask Backend Receives MQTT

```
Mosquitto Broker ──MQTT Subscribe──► Flask (on_message callback)
                                          │
                                          ├── Parse JSON
                                          ├── Validate data
                                          └── Process
```

### Step 4: Data Storage & Cache

```
Flask Backend
    │
    ├── Save to PostgreSQL (RDS)
    │   └── mcb_readings table (historical data)
    │
    ├── Update Redis Cache
    │   └── Last 120 readings for NILM
    │
    └── Emit WebSocket
        └── To user's specific room
```

### Step 5: WebSocket to Frontend

```
Flask Backend ──Socket.IO Emit──► User Browser
                                      │
                                      ├── Update voltage gauge
                                      ├── Update current gauge
                                      ├── Update power display
                                      └── Update consumption chart
```

### Step 6: NILM AI Prediction (When User Visits NILM Page)

```
Frontend ──GET /api/nilm/predict──► Flask
                                       │
                                       ├── Query last 24 hours from PostgreSQL
                                       ├── Scale data using .pkl scalers
                                       ├── Create 60-timestep windows
                                       ├── Run LSTM model (.keras)
                                       ├── Inverse transform prediction
                                       ├── Apply threshold (20W for fridge)
                                       │
                                       └── Return JSON to frontend
                                            {
                                              "predictions": [...],
                                              "statistics": {
                                                "total_energy": 2.5,
                                                "runtime": 180,
                                                "current_power": 45
                                              }
                                            }
```

### Step 7: DeepSeek AI Recommendation

```
Frontend ──POST /api/generate_recommendation──► Flask
                                                   │
                                                   ├── Get daily summary from DB
                                                   ├── Build prompt with actual data
                                                   ├── Call DeepSeek API via OpenRouter
                                                   ├── Receive AI response
                                                   │
                                                   └── Return to frontend
```

---

## 🔌 ESP32 + Mosquitto MQTT Setup

### ESP32 (Arduino C++)

**Required Libraries:**
- WiFi.h - Connect to WiFi
- PubSubClient.h - MQTT client
- ArduinoJson.h - JSON creation

**Publish Rate:** Every 1 second

**MQTT Topic:** `energy/data`

### Mosquitto Broker (Ubuntu Server)

**Installation:**
```bash
sudo apt update
sudo apt install mosquitto mosquitto-clients -y
```

**Configuration:** `/etc/mosquitto/mosquitto.conf`
```
listener 1883 0.0.0.0
allow_anonymous true
```

**Start Service:**
```bash
sudo systemctl enable mosquitto
sudo systemctl start mosquitto
```

---

## 🗄 Database Schema

### MCB Readings Table
| Column | Type | Description |
|--------|------|-------------|
| timestamp | TIMESTAMPTZ | Primary key |
| voltage_v | FLOAT | Voltage in volts |
| current_a | FLOAT | Current in amperes |
| power_factor | FLOAT | Power factor |
| power_w | FLOAT | Active power in watts |
| energy_kwh | FLOAT | Energy in kWh |
| mcb_id | INTEGER | Circuit breaker ID |
| user_id | INTEGER | Foreign key to users |

---

## 📡 API Endpoints

| Method | Endpoint | Auth Required | Description |
|--------|----------|---------------|-------------|
| POST | `/api/auth/signup` | No | Create new user account |
| POST | `/api/auth/login` | No | Login, returns JWT token |
| GET | `/api/monthly` | Yes | Monthly consumption data for charts |
| GET | `/api/predicted_bill` | Yes | 60-day bill prediction |
| GET | `/api/daily_summary` | Yes | Yesterday's energy summary |
| POST | `/api/generate_recommendation` | Yes | DeepSeek AI insights |
| GET | `/api/nilm/predict` | Yes | Fridge power prediction |
| GET | `/api/nilm/ac/predict` | Yes | AC power prediction |
| GET | `/api/nilm/detailed-status` | Yes | All device status |
| WS | `/socket.io` | Yes | WebSocket real-time updates |
| GET | `/health` | No | Service health check |

---

## 🧠 NILM AI Models

### Refrigerator LSTM Model

| Parameter | Value |
|-----------|-------|
| Input Shape | (60, 1) - 60 timesteps |
| Threshold | 20W (ignore below) |
| Architecture | LSTM(50) → Dense(25) → Dense(1) |
| Training Data | Mains power vs Fridge power |

### Air Conditioner LSTM Model

| Parameter | Value |
|-----------|-------|
| Input Shape | (120, 1) - 120 timesteps |
| Threshold | 100W (ignore below) |
| Architecture | LSTM(100) → Dense(50) → Dense(1) |

### Model Files Location
All `.keras` and `.pkl` files must be in the project root (same folder as `app.py`)

---

## 🌐 Frontend Pages

| File | Purpose | Key Features |
|------|---------|--------------|
| **home.html** | Landing page | Hero section, features, CTA buttons |
| **index.html** | Main dashboard | Real-time gauges, charts, bill prediction |
| **nilm.html** | Device monitor | Fridge/AC power charts, status indicators |
| **ai_recommendation.html** | AI insights | Daily summary, DeepSeek recommendations |

### Frontend Features by Page

**home.html:**
- Animated cosmic background
- Energy orb visualization
- Feature cards
- Login/Signup modals

**index.html:**
- Voltage/current gauges
- Real-time power display
- 60-day bill prediction
- Monthly consumption chart
- WebSocket connection

**nilm.html:**
- Fridge power chart (green theme)
- AC power chart (blue theme)
- Runtime statistics
- On/off cycle detection
- Matrix rain animation

**ai_recommendation.html:**
- Yesterday's energy summary
- Detailed metrics table
- Quantum AI insights
- Refresh button

---

## 🚀 Deployment 

### Docker Deployment

```bash
# Clone and deploy
git clone https://github.com/yourusername/bitminds.git
cd bitminds
cp .env.example .env
# Edit .env with your values

# Build and start containers
docker-compose up -d --build

# Check status
docker-compose ps

# View logs
docker-compose logs -f

# Stop containers
docker-compose down
```

### AWS Production

| Service | Configuration |
|---------|---------------|
| **EC2** | t3.medium, Ubuntu 22.04, 30GB gp3 |
| **RDS** | PostgreSQL 15, db.t3.micro, 20GB |
| **S3** | Static website hosting, public read |
| **Security Groups** | 22(SSH), 80(HTTP), 443(HTTPS), 1883(MQTT), 5000(Flask) |

**Deploy Commands:**
```bash
# On EC2
ssh -i key.pem ubuntu@EC2_IP
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker ubuntu && newgrp docker
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
git clone https://github.com/yourusername/bitminds.git
cd bitminds
docker-compose up -d --build

# On Local
aws s3 sync ./templates/ s3://bitminds-frontend/ --exclude "*.py"
aws s3 sync ./static/ s3://bitminds-frontend/static/
```

---

## 🔐 Environment Variables (.env)

```bash
# Database Configuration
DATABASE_URL=postgresql://postgres:password@localhost:5432/bitminds
DB_PASSWORD=your_password

# JWT Authentication
JWT_SECRET_KEY=your_super_secret_jwt_key_change_this

# DeepSeek AI API
DEEPSEEK_API_KEY=sk-your-deepseek-api-key

# MQTT Configuration (Mosquitto)
MQTT_BROKER=your-ec2-public-ip
MQTT_PORT=1883
MQTT_USERNAME=
MQTT_PASSWORD=
MQTT_TOPIC=energy/data

# Flask Configuration
SECRET_KEY=your_flask_secret_key
FLASK_ENV=production
```

---

## 🔄 Connection Flow Summary

```
[ESP32] ──MQTT──► [Mosquitto] ──Subscribe──► [Flask Backend]
                                                    │
                                                    ├──Save──► [PostgreSQL RDS]
                                                    ├──Cache──► [Redis]
                                                    └──Emit──► [WebSocket]
                                                         │
                                                         ▼
                                              [User Browser]
                                                    │
                                                    ├──Load──► [S3 Frontend]
                                                    └──Show──► [Dashboard]
                                                         │
                                                         ▼
                                              [NILM Models] ◄── [TensorFlow]
                                                         │
                                                         ▼
                                              [DeepSeek AI] ◄── [Recommendations]
```

---

## 🚨 Troubleshooting Guide

| Problem | Solution |
|---------|----------|
| MQTT not connecting | Check Mosquitto: `sudo systemctl status mosquitto` |
| WebSocket fails | Add `?token=JWT_TOKEN` to connection URL |
| Models not loading | Verify `.keras` files in project root |
| Database error | Check RDS security group inbound rule |
| CORS error | CORS already configured in `app.py` |
| Container won't start | Run `docker-compose logs` to see errors |
| ESP32 not publishing | Check WiFi connection and broker IP |

---

---

## 🙏 Acknowledgments

- **TensorFlow** - LSTM neural network implementation
- **DeepSeek** - AI-powered recommendations
- **Mosquitto** - MQTT broker
- **Flask** - Web framework
- **PostgreSQL** - Database
- **HighCharts** - Interactive charts

---




