# sems_project
# ⚡ BitMinds Smart Energy Monitoring System

<div align="center">

![BitMinds Logo](https://img.shields.io/badge/BitMinds-Smart%20Energy-blueviolet)
![Python](https://img.shields.io/badge/Python-3.8+-blue)
![Flask](https://img.shields.io/badge/Flask-2.0+-green)
![ESP32](https://img.shields.io/badge/Hardware-ESP32-orange)
![MQTT](https://img.shields.io/badge/Protocol-MQTT-yellow)
![TensorFlow](https://img.shields.io/badge/TensorFlow-2.0+-orange)
![LSTM](https://img.shields.io/badge/NILM-LSTM-red)
![DeepSeek](https://img.shields.io/badge/AI-DeepSeek-blue)
![License](https://img.shields.io/badge/License-MIT-red)

**Real-time Energy Monitoring | AI-Powered Recommendations | NILM Appliance Detection | LSTM Neural Networks | DeepSeek LLM Integration**

[Features](#-key-features) • [Architecture](#-system-architecture) • [NILM Technology](#-nilm-non-intrusive-load-monitoring) • [Quick Start](#-quick-start) • [API](#-api-documentation) • [Screenshots](#-screenshots)

</div>

---

## 📋 Table of Contents

- [Overview](#-overview)
- [Key Features](#-key-features)
- [System Architecture](#-system-architecture)
- [NILM Technology (ML Core)](#-nilm-non-intrusive-load-monitoring)
- [Technology Stack](#-technology-stack)
- [Hardware Setup](#-hardware-setup-esp32--sensors)
- [Software Setup](#-software-setup)
- [Configuration](#-configuration)
- [API Documentation](#-api-documentation)
- [Project Structure](#-project-structure)
- [Deployment](#-deployment)
- [Screenshots](#-screenshots)
- [Contributing](#-contributing)
- [License](#-license)
- [Contact](#-contact)

---

## 🎯 Overview

**BitMinds** is an intelligent energy monitoring system that combines IoT hardware, machine learning (LSTM neural networks), and AI (DeepSeek LLM) to provide real-time insights into energy consumption. The system uses ESP32 microcontrollers with PZEM-004T sensors to measure electrical parameters, transmits data securely via MQTT protocol, and processes it through a Flask backend with PostgreSQL database. 

**The core innovation** is our **NILM (Non-Intrusive Load Monitoring)** technology using LSTM neural networks that can identify individual appliance consumption from the total aggregate power reading - without needing individual sensors on each appliance. This is complemented by an AI recommendation engine powered by DeepSeek that provides personalized energy optimization advice.

**Why BitMinds?**
- 📊 **Real-time visibility** into energy usage (1-second updates)
- 🧠 **AI-powered insights** for 15-30% cost reduction
- 🔌 **Appliance-level detection** without sub-metering (NILM technology)
- 💰 **Predictive billing** with 60-day forecasts (92% accuracy)
- 🌱 **Sustainability tracking** for carbon footprint
- 🔐 **Enterprise-grade security** (TLS, JWT, bcrypt)

---

## ✨ Key Features

### 🔌 Hardware Integration
- **ESP32** microcontroller with WiFi connectivity
- **PZEM-004T** energy monitoring sensors (voltage, current, power, energy, power factor)
- **3-phase** monitoring capability (up to 3 sensors simultaneously)
- **1-second** sampling rate for granular data
- **Non-invasive** current transformers (no electrical work required)

### 📡 Communication Protocol (MQTT)
- **Lightweight MQTT protocol** for IoT data transmission
- **Mosquitto broker** with TLS/SSL encryption
- **Certificate-based authentication** (CA, client, server certificates)
- **Automatic reconnection** with exponential backoff
- **Topic structure:** `sem/mcb/user_{user_id}/{device_id}`

### 🖥️ Backend Services (Flask)
- **RESTful API** with 20+ endpoints
- **JWT authentication** for secure access (7-day tokens)
- **WebSocket** real-time updates via Socket.IO
- **PostgreSQL** database with connection pooling (10-30 connections)
- **Database migrations** with Flask-Migrate
- **Blueprints** for modular code organization

### 🤖 Machine Learning - NILM Technology
- **LSTM (Long Short-Term Memory)** neural networks for time-series analysis
- **Non-Intrusive Load Monitoring** - disaggregate total consumption into individual appliances
- **Sequence-to-sequence** architecture with 3 LSTM layers (128→64→32 units)
- **Dropout layers** (0.2-0.3) to prevent overfitting
- **Pre-trained models** for common appliances:

| Appliance | Model File | Accuracy | Training Data | Architecture |
|-----------|------------|----------|---------------|--------------|
| Refrigerator | `fridge_nilm_lstm.keras` | 92% | 50,000 cycles | 3-layer LSTM |


- **Feature extraction:** Voltage, Current, Power, Power Factor, Timestamp (hour/minute)
- **Sequence length:** 60 seconds (60 timesteps) for context
- **Normalization:** Min-max scaling per user
- **Real-time inference:** <100ms per prediction

### 🧠 AI Integration (DeepSeek LLM)
- **DeepSeek-R1** language model via OpenRouter API
- **Personalized energy recommendations** based on user consumption patterns
- **Smart prompt engineering** with energy data injection
- **Rate limiting** (60 seconds between calls) for free tier
- **Queue management system** for multiple concurrent users
- **Intelligent fallback** when API is unavailable:


        return "Schedule regular equipment maintenance..."
